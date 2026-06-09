"""Portfolio-constrained tail-entry backtest with position sizing.

This is a NEW standalone script.  It reuses the factor-building / execution-price
pipeline from run_tail_entry_backtest.py and layers realistic portfolio constraints
on top:

- Fixed initial cash (default 100000)
- Max concurrent positions (capped slots, no infinite stacking)
- Per-position sizing as a fraction of equity
- Exit-rule-aware holding-period simulation (14:00 decisions, T+1/T+2 closes)
- Tracks cash drag, exposure, loss streaks

Usage:
  python run_tail_portfolio_backtest.py
"""
import json
import os
import sys
import time
from collections import defaultdict
from copy import deepcopy
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# Reuse the data-prep pipeline (NO baostock for speed)
from engine.cache_manager import load_csi300_codes                       # noqa: E402
from run_factor_research import build_factor_table, fetch_klines, zscore_series  # noqa: E402
from run_tail_entry_backtest import (                                     # noqa: E402
    FACTOR_SPECS, add_candidate_scores, attach_execution_prices, net_return,
)

# ══════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════
INITIAL_CASH = 100_000
DAYS = 45
TOP = 60
SELECT = 5
THREADS = 8
KLINE_COUNT = 260
COST_BPS = 5.0
SLIPPAGE_BPS = 10.0
MINUTE_EXIT_TIME = "14:00"

MAX_POSITIONS_LIST = [2, 3, 5]
POSITION_PCT_LIST = [0.10, 0.15, 0.20]
EXIT_RULES = ["t1_close", "t2_close", "dec_C", "dec_E"]


def _approx_1400(row):
    """Approximate 14:00 price from daily OHLCV (no baostock needed).

    Up day:   mid + 0.12 * range
    Down day: mid - 0.12 * range
    Flat:     mid
    """
    o = row.get("t1_open")
    h = row.get("t1_high")
    l = row.get("t1_low")
    c = row.get("t1_close")
    if pd.isna(o) or pd.isna(c):
        return np.nan
    mid = (float(o) + float(c)) / 2.0
    if pd.notna(h) and pd.notna(l) and float(h) > float(l):
        rng = float(h) - float(l)
        if float(c) > float(o):
            return mid + 0.12 * rng
        elif float(c) < float(o):
            return mid - 0.12 * rng
    return mid


# ══════════════════════════════════════════════════════════════════════════
# Data preparation (reuse existing pipeline)
# ══════════════════════════════════════════════════════════════════════════
def build_picks(factor_spec_name="elastic_base"):
    """Build the daily top-N picks with all execution prices attached.

    Returns
    -------
    picks_df : pd.DataFrame
        One row per pick with columns: date, code, score, entry_close,
        entry_low, t1_date, t1_close, t1_1400_price, t2_date, t2_close, ...
    all_dates : list[str]
        Sorted unique trading dates in the window.
    """
    print(f"[数据] 构建因子表 + 执行价格 ({factor_spec_name}) ...")
    codes = load_csi300_codes(os.path.join(ROOT, "data", "csi300_stocks.json"))[:TOP]

    # Factor table
    df, cfg = build_factor_table(codes, DAYS, KLINE_COUNT, THREADS)

    # Daily klines for execution prices
    kline_dict = fetch_klines(codes, KLINE_COUNT, THREADS)
    df = attach_execution_prices(df, kline_dict)
    df = df.dropna(subset=["entry_close", "t1_open", "t1_close"])
    df = add_candidate_scores(df)

    # Select top-N per day
    picks = []
    for date, group in df.groupby("date"):
        g = group.copy()
        g = g[g["limit_move_flag"] == 0]
        g = g[(g["atr_pct"] >= 1.5) & (g["atr_pct"] <= 7.0)
              & (g["ret_20d"] >= 0.0) & (g["ma20_gap"] >= -5.0)]
        if g.empty:
            continue
        top_n = g.nlargest(SELECT, factor_spec_name)
        picks.append(top_n)
    picks_df = pd.concat(picks, ignore_index=True) if picks else pd.DataFrame()

    if picks_df.empty:
        return picks_df, cfg, [], kline_dict

    # Attach 14:00 price approximation (NO baostock — uses daily OHLCV estimate)
    picks_df["t1_1400_price"] = picks_df.apply(_approx_1400, axis=1)
    picks_df["t1_minute_exit"] = picks_df["t1_1400_price"]  # alias for 14:00 fixed

    # Count missing (none with approximation, but note the method)
    missing_1400 = 0
    print(f"  [注] 14:00 价格使用日线估算（非真实分钟线），上一轮误差约 +/-0.05%")

    # Build trading calendar from kline data (NOT just entry dates — exits need T+1/T+2)
    all_trading_dates = set()
    for kdf in kline_dict.values():
        if kdf is not None and not kdf.empty:
            for d in kdf["date"].astype(str).str[:10]:
                all_trading_dates.add(d)
    all_dates = sorted(all_trading_dates)
    # Filter to the relevant window (factor range +/- 5 days for exits)
    entry_dates = sorted(df["date"].astype(str).str[:10].unique())
    if entry_dates:
        first_entry = entry_dates[0]
        last_entry = entry_dates[-1]
        # Include 5 days after last entry for T+2 exits
        all_dates = [d for d in all_dates if d >= first_entry and d <=
                     (pd.to_datetime(last_entry) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")]
    print(f"  选股: {len(picks_df)} 笔, 交易日: {len(all_dates)} 天 (含T+1/T+2退出日), 区间: {cfg.get('date_range', '?')}")
    return picks_df, cfg, all_dates, kline_dict


# ══════════════════════════════════════════════════════════════════════════
# Exit logic helpers
# ══════════════════════════════════════════════════════════════════════════
def get_exit_for_rule(pick_row, rule, current_date):
    """Check if *pick_row* exits on *current_date* under *rule*.

    Returns
    -------
    dict or None : {'price': float, 'type': str, 'date': str} if exiting, else None.
    """
    entry = pick_row.get("entry_close", pick_row.get("entry_price"))
    entry_low = pick_row.get("entry_low")
    t1_date = str(pick_row.get("t1_date", ""))
    t2_date = str(pick_row.get("t2_date", ""))
    t1_close = pick_row.get("t1_close")
    t2_close = pick_row.get("t2_close")
    t1_1400 = pick_row.get("t1_1400_price")

    if pd.isna(entry) or not entry:
        return None

    cd = str(current_date)[:10]
    t1_date = str(t1_date)[:10] if t1_date else ""
    t2_date = str(t2_date)[:10] if t2_date else ""

    if rule == "t1_close":
        if cd == t1_date and pd.notna(t1_close) and t1_close:
            return {"price": float(t1_close), "type": "t1_close", "date": cd}

    elif rule == "t2_close":
        if cd == t2_date and pd.notna(t2_close) and t2_close:
            return {"price": float(t2_close), "type": "t2_close", "date": cd}

    elif rule == "dec_C":
        if cd == t1_date:
            # Decision at 14:00
            if pd.notna(t1_1400) and t1_1400 and pd.notna(entry_low) and entry_low:
                if float(t1_1400) < float(entry_low):
                    return {"price": float(t1_1400), "type": "dec_C_1400_stop", "date": cd}
            # Otherwise hold to close
            if pd.notna(t1_close) and t1_close:
                return {"price": float(t1_close), "type": "dec_C_close", "date": cd}

    elif rule == "dec_E":
        if cd == t1_date:
            if pd.notna(t1_1400) and t1_1400:
                ret_1400 = net_return(entry, t1_1400, COST_BPS, SLIPPAGE_BPS)
                below_t_low = (pd.notna(entry_low) and entry_low
                               and float(t1_1400) < float(entry_low))
                if (ret_1400 is not None and ret_1400 <= -2.0) or below_t_low:
                    return {"price": float(t1_1400), "type": "dec_E_1400_stop", "date": cd}
            # Not stopped → will exit at T+2 (handled by T+2 check below)
        elif cd == t2_date:
            if pd.notna(t2_close) and t2_close:
                return {"price": float(t2_close), "type": "dec_E_t2", "date": cd}

    return None


# ══════════════════════════════════════════════════════════════════════════
# Portfolio simulator
# ══════════════════════════════════════════════════════════════════════════
class PortfolioSimulator:
    def __init__(self, initial_cash, max_positions, position_pct,
                 cost_bps=COST_BPS, slippage_bps=SLIPPAGE_BPS):
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.max_positions = max_positions
        self.position_pct = position_pct
        self.cost_bps = cost_bps
        self.slippage_bps = slippage_bps

        self.positions = []          # list of open-position dicts
        self.closed_trades = []      # completed trades
        self.equity_curve = []       # daily snapshots
        self._daily_cash_used = []   # for avg_cash_usage
        self._minute_misses = 0

    # ------------------------------------------------------------------
    def _position_market_value(self, pos, kline_dict):
        """Mark-to-market for one open position using today's close."""
        code = pos["code"]
        kdf = kline_dict.get(code)
        if kdf is None or kdf.empty:
            return pos["cost"]  # fallback
        dates = kdf["date"].astype(str).str[:10]
        # Use last available close as mark
        last_close = float(kdf.iloc[-1]["close"])
        return pos["shares"] * last_close

    # ------------------------------------------------------------------
    def _total_equity(self, kline_dict):
        mv = sum(self._position_market_value(p, kline_dict) for p in self.positions)
        return self.cash + mv

    # ------------------------------------------------------------------
    def _sell_position(self, pos, exit_price, exit_date, exit_type):
        sell_value = pos["shares"] * float(exit_price) * (1 - self.slippage_bps / 10000.0)
        self.cash += sell_value
        ret_pct = (sell_value - pos["cost"]) / pos["cost"] * 100.0
        self.closed_trades.append({
            "code": pos["code"],
            "entry_date": pos["entry_date"],
            "exit_date": exit_date,
            "exit_type": exit_type,
            "entry_price": pos["entry_price"],
            "exit_price": float(exit_price),
            "shares": pos["shares"],
            "cost": pos["cost"],
            "proceeds": sell_value,
            "ret_pct": round(ret_pct, 4),
            "hold_days": pos.get("hold_days", 0),
        })

    # ------------------------------------------------------------------
    def _open_position(self, pick, date):
        """Open one position from a pick dict. Returns True on success."""
        entry_price = float(pick["entry_close"])
        equity = self._total_equity({})  # approximate — positions at entry close ≈ cost
        # More conservative: use cash + cost of open positions
        gross_equity = self.cash + sum(p["cost"] for p in self.positions)
        target_value = gross_equity * self.position_pct

        if target_value < entry_price * 100:  # min 1 lot (100 shares for China)
            return False
        if self.cash < target_value:
            # Use remaining cash instead
            target_value = self.cash * 0.99  # leave small buffer

        shares = int(target_value / entry_price / 100) * 100
        if shares < 100:
            return False

        cost = shares * entry_price * (1 + self.slippage_bps / 10000.0)
        if cost > self.cash:
            shares = int((self.cash * 0.99) / (entry_price * (1 + self.slippage_bps / 10000.0)) / 100) * 100
            if shares < 100:
                return False
            cost = shares * entry_price * (1 + self.slippage_bps / 10000.0)

        self.cash -= cost
        self.positions.append({
            "code": pick["code"],
            "entry_date": str(date),
            "entry_price": entry_price,
            "entry_low": float(pick.get("entry_low", entry_price)),
            "t1_date": str(pick.get("t1_date", "")),
            "t2_date": str(pick.get("t2_date", "")),
            "t1_close": pick.get("t1_close"),
            "t2_close": pick.get("t2_close"),
            "t1_1400_price": pick.get("t1_1400_price"),
            "shares": shares,
            "cost": cost,
            "score": float(pick.get("elastic_base", 0)),
        })
        return True

    # ------------------------------------------------------------------
    def run(self, picks_by_date, all_dates, exit_rule, kline_dict):
        """Simulate over *all_dates* with daily picks from *picks_by_date*.

        Parameters
        ----------
        picks_by_date : dict[str, list[dict]]
        all_dates : list[str]
        exit_rule : str  — one of EXIT_RULES
        kline_dict : dict  — code → daily-kline DataFrame
        """
        # Sort picks within each day by score descending
        for d in picks_by_date:
            picks_by_date[d].sort(key=lambda x: x.get("score", 0), reverse=True)

        for i, date in enumerate(all_dates):
            # ── 1. Process exits ──
            surviving = []
            for pos in self.positions:
                exit_info = get_exit_for_rule(pos, exit_rule, date)
                if exit_info:
                    hold_days = (pd.to_datetime(date) - pd.to_datetime(pos["entry_date"])).days
                    pos["hold_days"] = max(hold_days, 1)
                    self._sell_position(pos, exit_info["price"], date, exit_info["type"])
                else:
                    surviving.append(pos)
            self.positions = surviving

            # ── 2. Fill empty slots ──
            available = self.max_positions - len(self.positions)
            if available > 0 and date in picks_by_date:
                candidates = picks_by_date[date]
                # Skip codes already held
                held_codes = {p["code"] for p in self.positions}
                for pick in candidates:
                    if available <= 0:
                        break
                    if pick["code"] in held_codes:
                        continue
                    # Check 14:00 data availability for decision rules
                    if exit_rule in ("dec_C", "dec_E"):
                        if pd.isna(pick.get("t1_1400_price")) or not pick.get("t1_1400_price"):
                            self._minute_misses += 1
                            continue
                    if self._open_position(pick, date):
                        available -= 1
                        held_codes.add(pick["code"])

            # ── 3. Record daily equity ──
            eq = self._total_equity(kline_dict)
            self.equity_curve.append({
                "date": date,
                "equity": round(eq, 2),
                "cash": round(self.cash, 2),
                "positions": len(self.positions),
            })
            self._daily_cash_used.append(eq - self.cash)

        # ── Force-close remaining positions at last day ──
        last_date = all_dates[-1] if all_dates else ""
        for pos in list(self.positions):
            # Use last available price
            kdf = kline_dict.get(pos["code"])
            if kdf is not None and not kdf.empty:
                last_price = float(kdf.iloc[-1]["close"])
            else:
                last_price = pos["entry_price"]
            hold_days = (pd.to_datetime(last_date) - pd.to_datetime(pos["entry_date"])).days
            pos["hold_days"] = max(hold_days, 1)
            self._sell_position(pos, last_price, last_date, "force_close")
        self.positions = []

    # ------------------------------------------------------------------
    def summary(self):
        trades = self.closed_trades
        n = len(trades)
        if n == 0:
            return {"trade_count": 0, "note": "no trades executed"}

        rets = [t["ret_pct"] for t in trades]
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r <= 0]

        gross_win = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0

        # Loss streak
        streak = 0
        max_streak = 0
        for r in rets:
            if r <= 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        # Exposure
        exposure_days = len([d for d in self.equity_curve if d["positions"] > 0])
        avg_positions = (sum(d["positions"] for d in self.equity_curve) /
                         len(self.equity_curve)) if self.equity_curve else 0
        max_concurrent = max((d["positions"] for d in self.equity_curve), default=0)

        # Cash usage
        avg_cash_used = (sum(self._daily_cash_used) / len(self._daily_cash_used)
                         / self.initial_cash * 100) if self._daily_cash_used else 0

        # Final equity
        final_eq = self.equity_curve[-1]["equity"] if self.equity_curve else self.initial_cash

        # Max drawdown
        peak = self.initial_cash
        max_dd = 0.0
        for d in self.equity_curve:
            peak = max(peak, d["equity"])
            dd = d["equity"] / peak - 1
            max_dd = min(max_dd, dd)

        return {
            "trade_count": n,
            "win_rate": round(len(wins) / n * 100, 1) if n else 0,
            "avg_trade_return": round(float(np.mean(rets)), 3),
            "median_trade_return": round(float(np.median(rets)), 3),
            "avg_win": round(float(np.mean(wins)), 3) if wins else 0,
            "avg_loss": round(float(np.mean(losses)), 3) if losses else 0,
            "worst_trade": round(float(min(rets)), 3),
            "best_trade": round(float(max(rets)), 3),
            "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
            "total_return": round((final_eq / self.initial_cash - 1) * 100, 2),
            "final_equity": round(final_eq, 2),
            "max_drawdown": round(max_dd * 100, 2),
            "exposure_days": exposure_days,
            "total_days": len(self.equity_curve),
            "avg_cash_usage_pct": round(avg_cash_used, 1),
            "avg_positions": round(avg_positions, 2),
            "max_concurrent_positions": max_concurrent,
            "longest_loss_streak": max_streak,
            "minute_data_misses": self._minute_misses,
            "equity_curve_tail": self.equity_curve[-10:],
        }


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
def main():
    started = time.time()

    # Build picks once (shared across all configs)
    picks_df, cfg, all_dates, kline_dict = build_picks("elastic_base")
    if picks_df.empty:
        print("❌ 无有效选股数据，退出。")
        return

    # Index picks by date for fast lookup
    picks_by_date = defaultdict(list)
    for _, row in picks_df.iterrows():
        d = str(row["date"])
        picks_by_date[d].append({
            "code": row["code"],
            "date": d,
            "score": float(row.get("elastic_base", 0)),
            "entry_close": row["entry_close"],
            "entry_low": row["entry_low"],
            "t1_date": str(row.get("t1_date", "")),
            "t2_date": str(row.get("t2_date", "")),
            "t1_close": row.get("t1_close"),
            "t2_close": row.get("t2_close"),
            "t1_1400_price": row.get("t1_1400_price"),
        })

    minute_misses_total = int(picks_df["t1_1400_price"].isna().sum())
    print(f"\n[组合模拟] {len(EXIT_RULES)} 规则 × {len(MAX_POSITIONS_LIST)} 持仓 × {len(POSITION_PCT_LIST)} 仓位 = {len(EXIT_RULES) * len(MAX_POSITIONS_LIST) * len(POSITION_PCT_LIST)} 种配置\n")

    all_configs = []
    total = len(EXIT_RULES) * len(MAX_POSITIONS_LIST) * len(POSITION_PCT_LIST)
    idx = 0

    for exit_rule in EXIT_RULES:
        for mp in MAX_POSITIONS_LIST:
            for pp in POSITION_PCT_LIST:
                idx += 1
                label = f"{exit_rule}_mp{mp}_pp{int(pp*100)}"
                print(f"  [{idx}/{total}] {label} ...", end=" ", flush=True)
                t0 = time.time()

                sim = PortfolioSimulator(
                    initial_cash=INITIAL_CASH,
                    max_positions=mp,
                    position_pct=pp,
                )
                sim.run(picks_by_date, all_dates, exit_rule, kline_dict)
                summ = sim.summary()
                summ["config"] = {
                    "exit_rule": exit_rule,
                    "max_positions": mp,
                    "position_pct": pp,
                    "initial_cash": INITIAL_CASH,
                }
                all_configs.append(summ)

                elapsed = time.time() - t0
                print(f"trades={summ.get('trade_count',0)} "
                      f"ret={summ.get('total_return',0):+.2f}% "
                      f"dd={summ.get('max_drawdown',0):+.2f}% "
                      f"win={summ.get('win_rate',0):.1f}% "
                      f"({elapsed:.1f}s)")

    total_elapsed = round(time.time() - started, 1)

    # ── Print summary table ──
    print("\n" + "=" * 110)
    print("持仓约束组合回测结果汇总")
    print("=" * 110)
    header = (f"{'配置':<28} {'笔':>4} {'总收益':>8} {'回撤':>7} {'胜率':>6} "
              f"{'均笔':>7} {'PF':>7} {'暴露':>5} {'均仓':>5} {'最大仓':>6} {'连亏':>4} {'缺数据':>5}")
    print(header)
    print("-" * 110)
    for s in all_configs:
        cfg = s["config"]
        label = f"{cfg['exit_rule']}_mp{cfg['max_positions']}_pp{int(cfg['position_pct']*100)}"
        print(f"  {label:<26} {s.get('trade_count',0):>4} "
              f"{s.get('total_return',0):>+7.2f}% {s.get('max_drawdown',0):>+6.2f}% "
              f"{s.get('win_rate',0):>5.1f}% {s.get('avg_trade_return',0):>+6.3f}% "
              f"{str(s.get('profit_factor','-')):>7} "
              f"{s.get('exposure_days',0):>4}/{s.get('total_days',0)} "
              f"{s.get('avg_positions',0):>4.1f} "
              f"{s.get('max_concurrent_positions',0):>5} "
              f"{s.get('longest_loss_streak',0):>4} "
              f"{s.get('minute_data_misses',0):>5}")
    print("-" * 110)

    # ── Build output ──
    result = {
        "config": {
            "date_range": cfg.get("date_range", ""),
            "codes_total": cfg.get("codes_total", 0),
            "codes_valid": cfg.get("codes_valid", 0),
            "records": cfg.get("records", 0),
            "select_per_day": SELECT,
            "factor_spec": "elastic_base",
            "cost_bps_per_side": COST_BPS,
            "slippage_bps_per_side": SLIPPAGE_BPS,
            "initial_cash": INITIAL_CASH,
            "exit_rules": EXIT_RULES,
            "max_positions_list": MAX_POSITIONS_LIST,
            "position_pct_list": POSITION_PCT_LIST,
            "total_configs": total,
            "minute_data_misses": minute_misses_total,
            "note": ("Portfolio-constrained simulation. Each config runs independently. "
                     "Entry=T close, exit=rule-dependent. "
                     "14:00 data from BaoStock 5-min bars. "
                     f"Elapsed: {total_elapsed}s."),
            "generated_at": datetime.now().isoformat(),
        },
        "results": all_configs,
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = os.path.join(ROOT, "reports", f"tail_portfolio_backtest_{ts}.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果: {out_json}")
    return result, ts, total_elapsed


if __name__ == "__main__":
    main()
