"""Market-filtered portfolio backtest for tail-entry strategy.

Extends run_tail_portfolio_backtest.py with market environment filters.
Goal: reduce max_drawdown from ~-11.64% to -6%~-8% while keeping acceptable returns.

Base strategy is FIXED: elastic_base + dec_E + max_positions=2.
Tests two position_pct (0.15, 0.20) × N market filters.

Usage:
  python run_tail_market_filter_backtest.py
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

# Reuse the portfolio backtest building blocks
from engine.data_fetcher import fetch_csi300_index                              # noqa: E402
from run_factor_research import build_factor_table, fetch_klines               # noqa: E402
from run_tail_portfolio_backtest import (                                       # noqa: E402
    build_picks, PortfolioSimulator, get_exit_for_rule,
    _approx_1400, COST_BPS, SLIPPAGE_BPS,
)

# ══════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════
INITIAL_CASH = 100_000
MAX_POSITIONS = 2                                         # Fixed per task spec
POSITION_PCT_LIST = [0.15, 0.20]
EXIT_RULE = "dec_E"                                       # Best from previous round
FACTOR_SPEC = "elastic_base"

# ── Filter definitions ──
FILTER_DEFS = {
    "none":               {"description": "无过滤（baseline）"},
    "csi_ma20":           {"description": "CSI300收盘 >= MA20 才开新仓"},
    "csi_ret20_pos":      {"description": "CSI300 20日收益 >= 0 才开新仓"},
    "csi_ma20_ret20":     {"description": "CSI300收盘>=MA20 且 20日收益>=0"},
    "breadth45":          {"description": "市场宽度(涨家占比) >= 45% 才开新仓"},
    "breadth50":          {"description": "市场宽度(涨家占比) >= 50% 才开新仓"},
    "csi_ma20_b45":       {"description": "CSI300>=MA20 + 宽度>=45%"},
    "csi_ma20_b50":       {"description": "CSI300>=MA20 + 宽度>=50%"},
    "csi_ma20_ret20_b45": {"description": "CSI300>=MA20 + ret20>=0 + 宽度>=45%"},
    "csi_ma20_ret20_b50": {"description": "CSI300>=MA20 + ret20>=0 + 宽度>=50%"},
}

# ══════════════════════════════════════════════════════════════════════════
# Market environment data
# ══════════════════════════════════════════════════════════════════════════
def build_market_env(kline_dict, all_dates):
    """Build per-date market environment signals.

    Returns
    -------
    dict[str, dict] : date -> {csi300_close, csi300_ma20, csi300_ret20,
                               breadth_up, breadth_down, breadth_ratio, ...}
    """
    print("[市场环境] 获取CSI300指数数据 ...")
    csi300_df = fetch_csi300_index(count=260)
    if csi300_df is None or csi300_df.empty:
        print("  [错误] 无法获取CSI300指数数据")
        return {}

    csi300_df["date_str"] = csi300_df["date"].astype(str).str[:10]
    csi300_df = csi300_df.sort_values("date").reset_index(drop=True)

    # Pre-calculate MA20 and 20-day return for every date
    csi300_df["ma20"] = csi300_df["close"].rolling(20).mean()
    csi300_df["ret_20d"] = csi300_df["close"].pct_change(20) * 100

    env = {}
    csi_missing = 0
    breadth_missing = 0

    for date in all_dates:
        entry = {"date": date}

        # ── CSI300 data ──
        csi_row = csi300_df[csi300_df["date_str"] == date]
        if not csi_row.empty:
            r = csi_row.iloc[-1]
            entry["csi300_close"] = float(r["close"])
            entry["csi300_ma20"] = float(r["ma20"]) if pd.notna(r["ma20"]) else None
            entry["csi300_ret20"] = float(r["ret_20d"]) if pd.notna(r["ret_20d"]) else None
        else:
            entry["csi300_close"] = None
            entry["csi300_ma20"] = None
            entry["csi300_ret20"] = None
            csi_missing += 1

        # ── Market breadth (from individual stock klines) ──
        up, down = 0, 0
        for code, kdf in kline_dict.items():
            if kdf is None or kdf.empty:
                continue
            kdf_dates = kdf["date"].astype(str).str[:10]
            rows = kdf[kdf_dates == date]
            if rows.empty:
                continue
            row = rows.iloc[0]
            if float(row["close"]) >= float(row["open"]):
                up += 1
            else:
                down += 1
        total = up + down
        if total > 0:
            entry["breadth_up"] = up
            entry["breadth_down"] = down
            entry["breadth_ratio"] = round(up / total, 4)
        else:
            entry["breadth_up"] = 0
            entry["breadth_down"] = 0
            entry["breadth_ratio"] = None
            breadth_missing += 1

        env[date] = entry

    print(f"  交易日: {len(env)}, CSI300缺失: {csi_missing}, 宽度缺失: {breadth_missing}")
    return env


# ══════════════════════════════════════════════════════════════════════════
# Filter check functions
# ══════════════════════════════════════════════════════════════════════════
def check_filter(filter_name, env_entry):
    """Check if a date passes the given market filter.

    Returns (passes: bool, reason: str)
    """
    if filter_name == "none":
        return True, "no_filter"

    e = env_entry

    # ── CSI300 MA20 ──
    if filter_name == "csi_ma20":
        close = e.get("csi300_close")
        ma20 = e.get("csi300_ma20")
        if close is None or ma20 is None or pd.isna(ma20):
            return False, "csi300_data_missing"
        return close >= ma20, f"close={close:.1f} vs ma20={ma20:.1f}"

    # ── CSI300 20-day return ──
    if filter_name == "csi_ret20_pos":
        ret20 = e.get("csi300_ret20")
        if ret20 is None or pd.isna(ret20):
            return False, "csi300_data_missing"
        return ret20 >= 0, f"ret20={ret20:.2f}%"

    # ── CSI300 MA20 + ret20 ──
    if filter_name == "csi_ma20_ret20":
        close = e.get("csi300_close")
        ma20 = e.get("csi300_ma20")
        ret20 = e.get("csi300_ret20")
        if close is None or ma20 is None or ret20 is None or pd.isna(ma20) or pd.isna(ret20):
            return False, "csi300_data_missing"
        ok = close >= ma20 and ret20 >= 0
        return ok, f"close>={ma20:.1f}?={close>=ma20}, ret20>={0}?={ret20>=0}"

    # ── Breadth filters ──
    if filter_name == "breadth45":
        br = e.get("breadth_ratio")
        if br is None:
            return False, "breadth_data_missing"
        return br >= 0.45, f"breadth={br:.1%}"

    if filter_name == "breadth50":
        br = e.get("breadth_ratio")
        if br is None:
            return False, "breadth_data_missing"
        return br >= 0.50, f"breadth={br:.1%}"

    # ── Combined filters ──
    if filter_name == "csi_ma20_b45":
        close = e.get("csi300_close")
        ma20 = e.get("csi300_ma20")
        br = e.get("breadth_ratio")
        if close is None or ma20 is None or pd.isna(ma20) or br is None:
            return False, "data_missing"
        ok = close >= ma20 and br >= 0.45
        return ok, f"ma20={'Y' if close>=ma20 else 'N'}, b45={'Y' if br>=0.45 else 'N'}"

    if filter_name == "csi_ma20_b50":
        close = e.get("csi300_close")
        ma20 = e.get("csi300_ma20")
        br = e.get("breadth_ratio")
        if close is None or ma20 is None or pd.isna(ma20) or br is None:
            return False, "data_missing"
        ok = close >= ma20 and br >= 0.50
        return ok, f"ma20={'Y' if close>=ma20 else 'N'}, b50={'Y' if br>=0.50 else 'N'}"

    if filter_name == "csi_ma20_ret20_b45":
        close = e.get("csi300_close")
        ma20 = e.get("csi300_ma20")
        ret20 = e.get("csi300_ret20")
        br = e.get("breadth_ratio")
        if close is None or ma20 is None or ret20 is None or pd.isna(ma20) or pd.isna(ret20) or br is None:
            return False, "data_missing"
        ok = close >= ma20 and ret20 >= 0 and br >= 0.45
        return ok, f"ma20={'Y' if close>=ma20 else 'N'}, ret20={'Y' if ret20>=0 else 'N'}, b45={'Y' if br>=0.45 else 'N'}"

    if filter_name == "csi_ma20_ret20_b50":
        close = e.get("csi300_close")
        ma20 = e.get("csi300_ma20")
        ret20 = e.get("csi300_ret20")
        br = e.get("breadth_ratio")
        if close is None or ma20 is None or ret20 is None or pd.isna(ma20) or pd.isna(ret20) or br is None:
            return False, "data_missing"
        ok = close >= ma20 and ret20 >= 0 and br >= 0.50
        return ok, f"ma20={'Y' if close>=ma20 else 'N'}, ret20={'Y' if ret20>=0 else 'N'}, b50={'Y' if br>=0.50 else 'N'}"

    return True, "unknown_filter"


# ══════════════════════════════════════════════════════════════════════════
# Filter-aware portfolio simulator
# ══════════════════════════════════════════════════════════════════════════
class FilteredPortfolioSimulator(PortfolioSimulator):
    """PortfolioSimulator that can skip opening on filtered-out days."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filter_stats = {
            "dates_total": 0,
            "dates_with_picks": 0,
            "dates_passed": 0,
            "dates_blocked": 0,
            "signals_total": 0,
            "signals_blocked": 0,
        }

    def run_with_filter(self, picks_by_date, all_dates, exit_rule,
                         kline_dict, market_env, filter_name):
        """Run simulation with market filter on new position entries.

        Filter only affects opening NEW positions — existing positions
        are always processed for exits regardless of filter state.
        """
        # Sort picks within each day
        for d in picks_by_date:
            picks_by_date[d].sort(key=lambda x: x.get("score", 0), reverse=True)

        for i, date in enumerate(all_dates):
            self.filter_stats["dates_total"] += 1

            # ── 1. Process exits (ALWAYS — filter doesn't block exits) ──
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

            # ── 2. Fill empty slots (ONLY if filter passes) ──
            available = self.max_positions - len(self.positions)
            if available > 0 and date in picks_by_date:
                self.filter_stats["dates_with_picks"] += 1

                # Check market filter
                env_entry = market_env.get(date, {})
                filter_ok, reason = check_filter(filter_name, env_entry)

                if filter_ok:
                    self.filter_stats["dates_passed"] += 1
                else:
                    self.filter_stats["dates_blocked"] += 1
                    # Count blocked signals
                    candidates = picks_by_date[date]
                    held_codes = {p["code"] for p in self.positions}
                    blocked = sum(1 for p in candidates if p["code"] not in held_codes)
                    self.filter_stats["signals_blocked"] += min(blocked, available)
                    # Record equity and continue
                    eq = self._total_equity(kline_dict)
                    self.equity_curve.append({
                        "date": date,
                        "equity": round(eq, 2),
                        "cash": round(self.cash, 2),
                        "positions": len(self.positions),
                    })
                    self._daily_cash_used.append(eq - self.cash)
                    continue

                candidates = picks_by_date[date]
                held_codes = {p["code"] for p in self.positions}
                signals_opened = 0
                signals_considered = 0
                for pick in candidates:
                    if available <= 0:
                        break
                    if pick["code"] in held_codes:
                        continue
                    signals_considered += 1
                    # Check 14:00 data for decision rules
                    if exit_rule in ("dec_C", "dec_E"):
                        if pd.isna(pick.get("t1_1400_price")) or not pick.get("t1_1400_price"):
                            self._minute_misses += 1
                            continue
                    if self._open_position(pick, date):
                        available -= 1
                        held_codes.add(pick["code"])
                        signals_opened += 1
                self.filter_stats["signals_total"] += signals_considered

            # ── 3. Record daily equity ──
            eq = self._total_equity(kline_dict)
            self.equity_curve.append({
                "date": date,
                "equity": round(eq, 2),
                "cash": round(self.cash, 2),
                "positions": len(self.positions),
            })
            self._daily_cash_used.append(eq - self.cash)

        # ── Force-close remaining positions ──
        last_date = all_dates[-1] if all_dates else ""
        for pos in list(self.positions):
            kdf = kline_dict.get(pos["code"])
            if kdf is not None and not kdf.empty:
                last_price = float(kdf.iloc[-1]["close"])
            else:
                last_price = pos["entry_price"]
            hold_days = (pd.to_datetime(last_date) - pd.to_datetime(pos["entry_date"])).days
            pos["hold_days"] = max(hold_days, 1)
            self._sell_position(pos, last_price, last_date, "force_close")
        self.positions = []

    def filtered_summary(self, filter_name, position_pct):
        """Extend summary with filter-specific fields."""
        base = self.summary()
        base["filter_name"] = filter_name
        base["position_pct"] = position_pct
        base["return_to_drawdown"] = round(
            abs(base["total_return"] / base["max_drawdown"]) if base["max_drawdown"] != 0 else 0, 2
        )
        base["filtered_dates"] = self.filter_stats["dates_blocked"]
        base["filtered_signal_count"] = self.filter_stats["signals_blocked"]
        base["filter_pass_rate"] = round(
            self.filter_stats["dates_passed"] / self.filter_stats["dates_with_picks"] * 100, 1
        ) if self.filter_stats["dates_with_picks"] > 0 else 0
        return base


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
def main():
    started = time.time()

    # ── Build picks once (shared across all configs) ──
    print("=" * 80)
    print("尾盘买入 市场环境过滤回测")
    print(f"基准策略: {FACTOR_SPEC} + {EXIT_RULE} + mp{MAX_POSITIONS}")
    print(f"初始资金: {INITIAL_CASH:,}  手续费: {COST_BPS}bps/边  滑点: {SLIPPAGE_BPS}bps/边")
    print("=" * 80)

    picks_df, cfg, all_dates, kline_dict = build_picks(FACTOR_SPEC)
    if picks_df.empty:
        print("[错误] 无有效选股数据，退出。")
        return

    # Index picks by date
    picks_by_date = defaultdict(list)
    for _, row in picks_df.iterrows():
        d = str(row["date"])
        picks_by_date[d].append({
            "code": row["code"],
            "date": d,
            "score": float(row.get(FACTOR_SPEC, 0)),
            "entry_close": row["entry_close"],
            "entry_low": row["entry_low"],
            "t1_date": str(row.get("t1_date", "")),
            "t2_date": str(row.get("t2_date", "")),
            "t1_close": row.get("t1_close"),
            "t2_close": row.get("t2_close"),
            "t1_1400_price": row.get("t1_1400_price"),
        })

    # ── Build market environment ──
    market_env = build_market_env(kline_dict, all_dates)
    if not market_env:
        print("[错误] 市场环境数据不可用，退出。")
        return

    # ── Print market environment summary ──
    csi300_dates_with_data = sum(1 for e in market_env.values() if e.get("csi300_close") is not None)
    breadth_dates_with_data = sum(1 for e in market_env.values() if e.get("breadth_ratio") is not None)
    print(f"  市场环境: {len(market_env)}天, CSI300覆盖{csi300_dates_with_data}天, 宽度覆盖{breadth_dates_with_data}天")

    # Print daily filter states for key filters
    print(f"\n  {'日期':<12} {'CSI300':>8} {'MA20':>8} {'ret20':>8} {'宽度':>8} {'ma20?':>6} {'ret20?':>7} {'宽45?':>6} {'宽50?':>6}")
    print(f"  {'-'*70}")
    for date in all_dates:
        e = market_env.get(date, {})
        close = e.get("csi300_close")
        ma20 = e.get("csi300_ma20")
        ret20 = e.get("csi300_ret20")
        br = e.get("breadth_ratio")
        c_str = f"{close:.0f}" if close is not None else "N/A"
        m_str = f"{ma20:.0f}" if ma20 is not None and not pd.isna(ma20) else "N/A"
        r_str = f"{ret20:+.1f}%" if ret20 is not None and not pd.isna(ret20) else "N/A"
        b_str = f"{br:.0%}" if br is not None else "N/A"
        ma_ok = "Y" if close is not None and ma20 is not None and not pd.isna(ma20) and close >= ma20 else "N"
        ret_ok = "Y" if ret20 is not None and not pd.isna(ret20) and ret20 >= 0 else "N"
        b45 = "Y" if br is not None and br >= 0.45 else "N"
        b50 = "Y" if br is not None and br >= 0.50 else "N"
        print(f"  {date:<12} {c_str:>8} {m_str:>8} {r_str:>8} {b_str:>8} {ma_ok:>6} {ret_ok:>7} {b45:>6} {b50:>6}")

    # ── Run all filter × position_pct combos ──
    filter_names = list(FILTER_DEFS.keys())
    total = len(filter_names) * len(POSITION_PCT_LIST)
    print(f"\n[回测] {len(filter_names)} 过滤 × {len(POSITION_PCT_LIST)} 仓位 = {total} 种配置\n")

    all_configs = []
    idx = 0

    for filter_name in filter_names:
        for pp in POSITION_PCT_LIST:
            idx += 1
            label = f"{filter_name}_pp{int(pp*100)}"
            print(f"  [{idx:2d}/{total}] {label:<32} ...", end=" ", flush=True)
            t0 = time.time()

            sim = FilteredPortfolioSimulator(
                initial_cash=INITIAL_CASH,
                max_positions=MAX_POSITIONS,
                position_pct=pp,
                cost_bps=COST_BPS,
                slippage_bps=SLIPPAGE_BPS,
            )
            sim.run_with_filter(picks_by_date, all_dates, EXIT_RULE,
                               kline_dict, market_env, filter_name)
            summ = sim.filtered_summary(filter_name, pp)
            all_configs.append(summ)

            elapsed = time.time() - t0
            print(f"trades={summ.get('trade_count',0):>3} "
                  f"ret={summ.get('total_return',0):>+6.2f}% "
                  f"dd={summ.get('max_drawdown',0):>+6.2f}% "
                  f"r/dd={summ.get('return_to_drawdown',0):.2f} "
                  f"win={summ.get('win_rate',0):.1f}% "
                  f"PF={summ.get('profit_factor','-'):>5} "
                  f"blocked={summ.get('filtered_signal_count',0):>3} "
                  f"({elapsed:.1f}s)")

    total_elapsed = round(time.time() - started, 1)

    # ── Print summary table ──
    print("\n" + "=" * 130)
    print("市场环境过滤回测结果汇总")
    print(f"基准: {FACTOR_SPEC} + {EXIT_RULE} + mp{MAX_POSITIONS} | 初始资金 {INITIAL_CASH:,}")
    print("=" * 130)
    header = (f"{'过滤规则':<28} {'仓位':>5} {'笔数':>4} {'总收益':>8} {'回撤':>7} "
              f"{'r/dd':>6} {'胜率':>6} {'均笔':>7} {'中位':>7} {'PF':>6} "
              f"{'连亏':>4} {'过滤日':>6} {'过滤信号':>7} {'通过率':>6}")
    print(header)
    print("-" * 130)

    # Sort: baseline first, then by return_to_drawdown desc
    def sort_key(s):
        is_baseline = 0 if s["filter_name"] == "none" else 1
        return (is_baseline, -s.get("return_to_drawdown", 0))

    all_configs.sort(key=sort_key)

    for s in all_configs:
        print(f"  {s['filter_name']:<28} {int(s['position_pct']*100):>3}% "
              f"{s.get('trade_count',0):>4} "
              f"{s.get('total_return',0):>+7.2f}% {s.get('max_drawdown',0):>+6.2f}% "
              f"{s.get('return_to_drawdown',0):>5.2f} "
              f"{s.get('win_rate',0):>5.1f}% {s.get('avg_trade_return',0):>+6.3f}% "
              f"{s.get('median_trade_return',0):>+6.3f}% "
              f"{str(s.get('profit_factor','-')):>6} "
              f"{s.get('longest_loss_streak',0):>4} "
              f"{s.get('filtered_dates',0):>5} "
              f"{s.get('filtered_signal_count',0):>6} "
              f"{s.get('filter_pass_rate',0):>5.0f}%")
    print("-" * 130)

    # ── Build output ──
    result = {
        "config": {
            "date_range": cfg.get("date_range", ""),
            "factor_spec": FACTOR_SPEC,
            "exit_rule": EXIT_RULE,
            "max_positions": MAX_POSITIONS,
            "position_pct_list": POSITION_PCT_LIST,
            "initial_cash": INITIAL_CASH,
            "cost_bps_per_side": COST_BPS,
            "slippage_bps_per_side": SLIPPAGE_BPS,
            "total_configs": total,
            "filter_defs": FILTER_DEFS,
            "market_env_dates": len(market_env),
            "note": (
                "Market-filtered portfolio simulation. "
                "Base strategy: elastic_base + dec_E + mp2. "
                "Filters only affect opening new positions; exits always process. "
                "CSI300 data from Tencent API; breadth from stock kline_dict. "
                "US tech overnight risk filter: unavailable (no historical data). "
                f"Elapsed: {total_elapsed}s."
            ),
            "generated_at": datetime.now().isoformat(),
        },
        "results": all_configs,
        "market_env_summary": {
            "total_dates": len(market_env),
            "csi300_missing": sum(1 for e in market_env.values() if e.get("csi300_close") is None),
            "breadth_missing": sum(1 for e in market_env.values() if e.get("breadth_ratio") is None),
            "avg_breadth": round(
                np.mean([e["breadth_ratio"] for e in market_env.values() if e.get("breadth_ratio") is not None]) * 100, 1
            ),
            "filter_pass_rates": {},
        },
    }

    # Calculate pass rates for each filter
    for fname in filter_names:
        passes = sum(1 for date in all_dates
                    if check_filter(fname, market_env.get(date, {}))[0])
        result["market_env_summary"]["filter_pass_rates"][fname] = round(
            passes / len(all_dates) * 100, 1) if all_dates else 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = os.path.join(ROOT, "reports", f"tail_market_filter_backtest_{ts}.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果: {out_json}")
    return result, ts, total_elapsed


if __name__ == "__main__":
    result, ts, elapsed = main()
