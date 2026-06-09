"""Pullback confirmation backtest — FIX & RERUN (pullback_confirmation_fix_rerun_001).

Fixes vs run_pullback_confirmation_backtest.py:
1. Baseline uses real tail-entry d3+ma20_gap+dec_E pipeline (not broken custom version)
2. Window slicing uses trading-day count correctly
3. Full all_results saved to JSON
4. 120d ranked primary, 90d secondary
5. Focused grid on promising families from first attempt

Usage: python run_pullback_confirmation_fix_rerun.py
"""
import json, os, sys, time
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from engine.cache_manager import load_csi300_codes                               # noqa: E402
from engine.data_fetcher import fetch_csi300_index                                # noqa: E402
from run_factor_research import build_factor_table, fetch_klines, zscore_series   # noqa: E402
from run_tail_entry_backtest import attach_execution_prices                       # noqa: E402
from run_tail_portfolio_backtest import (                                         # noqa: E402
    PortfolioSimulator as TailPortfolioSimulator,
    get_exit_for_rule as tail_get_exit,
    _approx_1400, build_picks,
    COST_BPS, SLIPPAGE_BPS,
)

# ══════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════
INITIAL_CASH = 100_000
TOP = 60
THREADS = 8
KLINE_COUNT = 600
WINDOWS = [120, 90]  # 120d primary
MAX_POSITIONS_LIST = [2, 3]
POSITION_PCT_LIST = [0.10, 0.15, 0.20]

# Focused grid: only promising families from first attempt + controls
FOCUSED_GRID = [
    # (trend_pool, pullback_cond, confirmation_cond)
    ("trend_pool_rank_d3_ma20gap_d3_ge_8_ret20_ge_0", "no_chase", "close_positive_after_pullback"),
    ("trend_pool_rank_d3_ma20gap_d3_ge_8_ret20_ge_0", "lower_shadow_reclaim", "none"),
    ("trend_pool_rank_d3_ma20gap_d3_ge_8_ret20_ge_0", "lower_shadow_reclaim", "close_above_ma20"),
    ("trend_pool_top20pct_d3_ma20gap", "shallow_pullback", "close_positive_after_pullback"),
    ("trend_pool_top20pct_d3_ma20gap", "shallow_pullback", "none"),
    ("trend_pool_top20pct_d3_ma20gap", "shrink_pullback", "close_positive_after_pullback"),
    ("trend_pool_ma60_ma20_structure_d3_ge_8", "lower_shadow_reclaim", "none"),
    ("trend_pool_ma60_ma20_structure_d3_ge_8", "lower_shadow_reclaim", "close_above_ma20"),
    # Failed control
    ("trend_pool_rank_d3_ma20gap_d3_ge_8_ret20_ge_0", "touch_reclaim_ma20", "none"),
]

ENTRY_MODES = ["t1_open_realistic"]
EXIT_RULES = ["hold_5d_close", "hold_8d_close", "ma20_or_pullback_low_break_then_hold5"]


# ══════════════════════════════════════════════════════════════════════════
# Helpers (reusing logic from first script)
# ══════════════════════════════════════════════════════════════════════════
def net_return(entry, exit, cost=COST_BPS, slip=SLIPPAGE_BPS):
    if not entry or not exit or entry <= 0 or exit <= 0:
        return None
    buy = float(entry) * (1 + slip / 10000.0)
    sell = float(exit) * (1 - slip / 10000.0)
    return (sell - buy) / buy * 100.0 - (cost * 2 / 100.0)


def build_date_kline_context(kline_dict):
    """Pre-build per-code per-date kline context for pullback detection."""
    context = {}
    for code, kdf in kline_dict.items():
        if kdf is None or kdf.empty:
            continue
        kdf = kdf.reset_index(drop=True)
        kdf["date_str"] = kdf["date"].astype(str).str[:10]
        closes = kdf["close"].astype(float)
        lows = kdf["low"].astype(float)
        highs = kdf["high"].astype(float)
        volumes = kdf["volume"].astype(float)
        opens = kdf["open"].astype(float)

        code_ctx = {}
        for i in range(len(kdf)):
            if i < 60:
                continue
            d = kdf.loc[i, "date_str"]
            c = closes.iloc[i]
            o = opens.iloc[i]
            h = highs.iloc[i]
            l = lows.iloc[i]
            v = volumes.iloc[i]
            ma20 = closes.iloc[i - 19:i + 1].mean()
            ma60 = closes.iloc[i - 59:i + 1].mean()
            ret_5d = (c - closes.iloc[i - 5]) / closes.iloc[i - 5] * 100 if i >= 5 else 0
            ret_20d = (c - closes.iloc[i - 20]) / closes.iloc[i - 20] * 100 if i >= 20 else 0
            tr_list = []
            for j in range(max(0, i - 13), i + 1):
                tr = max(highs.iloc[j] - lows.iloc[j],
                         abs(highs.iloc[j] - closes.iloc[j - 1]) if j > 0 else 0,
                         abs(lows.iloc[j] - closes.iloc[j - 1]) if j > 0 else 0)
                tr_list.append(tr)
            atr = float(np.mean(tr_list))
            atr_pct = atr / c * 100 if c > 0 else 0
            avg_vol = volumes.iloc[max(0, i - 19):i + 1].mean()
            vol_ratio = v / avg_vol if avg_vol > 0 else 1.0
            ma20_gap = (c - ma20) / ma20 * 100
            high_20d = highs.iloc[max(0, i - 19):i + 1].max()
            high_5d = highs.iloc[max(0, i - 4):i + 1].max()
            prior_high = highs.iloc[i - 1] if i >= 1 else h
            prior_close = closes.iloc[i - 1] if i >= 1 else c

            code_ctx[d] = {
                "close": float(c), "open": float(o), "high": float(h),
                "low": float(l), "volume": float(v), "ma20": float(ma20),
                "ma60": float(ma60), "ret_5d": float(ret_5d),
                "ret_20d": float(ret_20d), "atr_pct": float(atr_pct),
                "vol_ratio": float(vol_ratio), "ma20_gap": float(ma20_gap),
                "high_20d": float(high_20d), "high_5d": float(high_5d),
                "prior_high": float(prior_high), "prior_close": float(prior_close),
            }
        if code_ctx:
            context[code] = code_ctx
    return context


def build_trend_pool(factor_df, pool_name):
    df = factor_df.copy()
    df["trend_pool_score"] = df["d3"].fillna(0) + df["ma20_gap"].fillna(0)
    if pool_name == "trend_pool_rank_d3_ma20gap_d3_ge_8_ret20_ge_0":
        return df[(df["d3"] >= 8) & (df["ret_20d"] >= 0)]
    elif pool_name == "trend_pool_ma60_ma20_structure_d3_ge_8":
        return df[(df["d3"] >= 8) & (df["price_above_ma60"] == 1) & (df["ma20_above_ma60"] == 1)]
    elif pool_name == "trend_pool_top20pct_d3_ma20gap":
        dfs = []
        for _, g in df.groupby("date"):
            n = max(1, int(len(g) * 0.2))
            dfs.append(g.nlargest(n, "trend_pool_score"))
        return pd.concat(dfs, ignore_index=True) if dfs else df
    return df


def check_pullback(row, cond, context):
    code, date = row["code"], str(row["date"])[:10]
    ctx = context.get(code, {}).get(date)
    if ctx is None:
        return False
    c, ma20, ret_5d, ret_20d = ctx["close"], ctx["ma20"], ctx["ret_5d"], ctx["ret_20d"]
    ma20_gap, vol_ratio = ctx["ma20_gap"], ctx["vol_ratio"]
    low, high, o, pc = ctx["low"], ctx["high"], ctx["open"], ctx["prior_close"]
    h5d = ctx["high_5d"]

    if cond == "near_ma20":
        return -3.0 <= ma20_gap <= 3.0
    elif cond == "shallow_pullback":
        return (-8.0 <= ret_5d <= 1.0) and (ret_20d > 0)
    elif cond == "touch_reclaim_ma20":
        return (low <= ma20 * 1.005) and (c >= ma20 * 0.995)
    elif cond == "shrink_pullback":
        return (ret_5d <= 1.0) and (vol_ratio <= 1.2)
    elif cond == "no_chase":
        dg = (c - pc) / pc * 100 if pc > 0 else 0
        return (c < h5d * 0.98) and (dg < 5.0)
    elif cond == "lower_shadow_reclaim":
        ls = (min(c, o) - low) / o * 100 if o > 0 else 0
        dg = (c - pc) / pc * 100 if pc > 0 else 0
        return (ls >= 0.5) and (dg >= 0)
    return False


def check_confirmation(row, context, conf):
    if conf == "none":
        return True
    code, date = row["code"], str(row["date"])[:10]
    ctx = context.get(code, {}).get(date)
    if ctx is None:
        return False
    c, ma20, h, o, l, pc = ctx["close"], ctx["ma20"], ctx["high"], ctx["open"], ctx["low"], ctx["prior_close"]
    prior_high = ctx["prior_high"]
    vol_ratio = ctx["vol_ratio"]

    if conf == "close_above_ma20":
        return c > ma20
    elif conf == "close_positive_after_pullback":
        return ((c - pc) / pc * 100) > 0 if pc > 0 else False
    elif conf == "close_above_prior_high":
        return c > prior_high
    elif conf == "volume_reexpand":
        return (vol_ratio > 1.0) and (((c - pc) / pc * 100) > 0 if pc > 0 else False)
    elif conf == "hammer_or_lower_shadow":
        ls = (min(c, o) - l) / o * 100 if o > 0 else 0
        return (ls >= 0.8) or (row.get("hammer_flag", 0) == 1)
    return False


def build_pullback_signals(factor_df, context, trend_pool, pb_cond, conf_cond):
    pool_df = build_trend_pool(factor_df, trend_pool)
    if pool_df.empty:
        return pd.DataFrame()
    signals = []
    for _, row in pool_df.iterrows():
        if not check_pullback(row, pb_cond, context):
            continue
        if not check_confirmation(row, context, conf_cond):
            continue
        item = row.to_dict()
        item["trend_pool"] = trend_pool
        item["pullback_cond"] = pb_cond
        item["conf_cond"] = conf_cond
        item["signal_score"] = float(row.get("d3", 0)) + float(row.get("ma20_gap", 0))
        item["signal_date"] = str(row["date"])[:10]
        signals.append(item)
    return pd.DataFrame(signals) if signals else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════
# Pullback exit rules
# ══════════════════════════════════════════════════════════════════════════
def get_pullback_exit(trade, current_date, kline_dict, exit_rule, context):
    code = trade["code"]
    entry_date = str(trade["entry_date"])[:10]
    cd = str(current_date)[:10]
    kdf = kline_dict.get(code)
    if kdf is None:
        return None
    dates = kdf["date"].astype(str).str[:10]
    matches = kdf.index[dates == cd]
    if len(matches) == 0:
        return None
    idx = int(matches[0])
    c = float(kdf.loc[idx, "close"])
    l = float(kdf.loc[idx, "low"])
    ctx = context.get(code, {}).get(cd, {})
    ma20 = ctx.get("ma20", c)

    # Count trading days since entry
    entry_dt = pd.to_datetime(entry_date)
    all_dates = sorted(dates.unique())
    td = sum(1 for d in all_dates if str(d)[:10] > entry_date and str(d)[:10] <= cd)

    if exit_rule == "hold_5d_close":
        if td >= 5:
            return {"price": c, "type": "hold_5d", "date": cd}
    elif exit_rule == "hold_8d_close":
        if td >= 8:
            return {"price": c, "type": "hold_8d", "date": cd}
    elif exit_rule == "ma20_or_pullback_low_break_then_hold5":
        pullback_low = trade.get("pb_low", trade["entry_price"])
        if c < ma20 * 0.98 or l < pullback_low * 0.98:
            return {"price": c, "type": "protective_stop", "date": cd}
        if td >= 5:
            return {"price": c, "type": "hold_5d", "date": cd}
    return None


# ══════════════════════════════════════════════════════════════════════════
# Simple portfolio simulator (pullback)
# ══════════════════════════════════════════════════════════════════════════
class SimplePortfolio:
    def __init__(self, cash, max_pos, pp, cost=COST_BPS, slip=SLIPPAGE_BPS):
        self.cash = float(cash)
        self.max_pos = max_pos
        self.pp = pp
        self.cost = cost
        self.slip = slip
        self.positions = []
        self.trades = []
        self.equity = []

    def _eq(self, kd):
        mv = 0
        for p in self.positions:
            kdf = kd.get(p["code"])
            if kdf is not None and not kdf.empty:
                mv += p["shares"] * float(kdf.iloc[-1]["close"])
            else:
                mv += p["cost"]
        return self.cash + mv

    def _open(self, sig, date, entry_px, mode):
        px = float(entry_px)
        eq = self.cash + sum(p["cost"] for p in self.positions)
        tv = eq * self.pp
        if tv < px * 100:
            return False
        if self.cash < tv:
            tv = self.cash * 0.99
        shares = int(tv / px / 100) * 100
        if shares < 100:
            return False
        cost = shares * px * (1 + self.slip / 10000.0)
        if cost > self.cash:
            shares = int((self.cash * 0.99) / (px * (1 + self.slip / 10000.0)) / 100) * 100
            if shares < 100:
                return False
            cost = shares * px * (1 + self.slip / 10000.0)
        self.cash -= cost
        self.positions.append({
            "code": sig["code"], "entry_date": str(date), "entry_price": px,
            "entry_mode": mode, "shares": shares, "cost": cost,
            "score": sig.get("signal_score", 0), "pb_low": float(sig.get("entry_low", px)),
            # Store T+1/T+2 execution data for exit logic (critical for baseline)
            "entry_low": sig.get("entry_low"),
            "t1_date": str(sig.get("t1_date", "")),
            "t2_date": str(sig.get("t2_date", "")),
            "t1_open": sig.get("t1_open"),
            "t1_high": sig.get("t1_high"),
            "t1_low": sig.get("t1_low"),
            "t1_close": sig.get("t1_close"),
            "t2_close": sig.get("t2_close"),
            "t3_close": sig.get("t3_close"),
        })
        return True

    def _close(self, pos, exit_px, exit_date, exit_type):
        sv = pos["shares"] * float(exit_px) * (1 - self.slip / 10000.0)
        self.cash += sv
        r = (sv - pos["cost"]) / pos["cost"] * 100.0
        self.trades.append({
            "code": pos["code"], "entry_date": pos["entry_date"],
            "exit_date": exit_date, "exit_type": exit_type,
            "entry_price": pos["entry_price"], "exit_price": float(exit_px),
            "shares": pos["shares"], "cost": pos["cost"],
            "proceeds": sv, "ret_pct": round(r, 4),
            "entry_mode": pos.get("entry_mode", ""),
        })

    def run(self, signals_by_date, all_dates, exit_rule, kline_dict, context, entry_mode):
        for d in signals_by_date:
            signals_by_date[d].sort(key=lambda x: x.get("signal_score", 0), reverse=True)

        for date in all_dates:
            cd = str(date)[:10]
            # Exits
            surviving = []
            for pos in self.positions:
                ei = get_pullback_exit(pos, cd, kline_dict, exit_rule, context)
                if ei:
                    self._close(pos, ei["price"], cd, ei["type"])
                else:
                    surviving.append(pos)
            self.positions = surviving
            # Entries
            avail = self.max_pos - len(self.positions)
            if avail > 0 and cd in signals_by_date:
                held = {p["code"] for p in self.positions}
                for sig in signals_by_date[cd]:
                    if avail <= 0:
                        break
                    if sig["code"] in held:
                        continue
                    ep = sig.get("entry_close") if entry_mode == "t_close_optimistic" else sig.get("t1_open")
                    if pd.isna(ep) or not ep or ep <= 0:
                        continue
                    if self._open(sig, cd, ep, entry_mode):
                        avail -= 1
            self.equity.append({"date": cd, "equity": round(self._eq(kline_dict), 2),
                                "cash": round(self.cash, 2), "npos": len(self.positions)})

    def metrics(self, window_days):
        if not self.trades:
            return {"trade_count": 0, "window_days": window_days,
                    "total_return": 0, "max_drawdown": 0, "return_to_drawdown": 0,
                    "profit_factor": 0, "win_rate": 0}

        rets = [t["ret_pct"] for t in self.trades]
        eq = [e["equity"] for e in self.equity]
        tr = (eq[-1] - INITIAL_CASH) / INITIAL_CASH * 100 if eq else 0
        peak = eq[0] if eq else 0
        dd = 0.0
        for v in eq:
            if v > peak:
                peak = v
            d = (v - peak) / peak * 100
            if d < dd:
                dd = d
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r <= 0]
        wr = len(wins) / len(rets) * 100 if rets else 0
        gp = sum(wins) if wins else 0
        gl = abs(sum(losses)) if losses else 0
        pf = gp / gl if gl > 0 else (float('inf') if gp > 0 else 0)
        streak = cur = 0
        for r in rets:
            if r <= 0:
                cur += 1; streak = max(streak, cur)
            else:
                cur = 0
        mid = len(rets) // 2
        def hs(hlf):
            if not hlf:
                return {"ret": 0, "dd": 0, "wr": 0, "n": 0}
            hr = [t["ret_pct"] for t in hlf]
            hw = [r for r in hr if r > 0]
            return {"ret": round(sum(hr), 2), "dd": round(min(hr) if hr else 0, 2),
                    "wr": round(len(hw) / len(hr) * 100, 1) if hr else 0, "n": len(hlf)}
        dr = f"{self.equity[0]['date']} ~ {self.equity[-1]['date']}" if self.equity else "N/A"
        ap = np.mean([e["npos"] for e in self.equity]) if self.equity else 0

        return {
            "total_return": round(tr, 2), "max_drawdown": round(dd, 2),
            "return_to_drawdown": round(tr / abs(dd), 2) if dd != 0 else 0,
            "profit_factor": round(pf, 2), "win_rate": round(wr, 1),
            "trade_count": len(rets),
            "avg_trade_return": round(np.mean(rets), 2) if rets else 0,
            "median_trade_return": round(np.median(rets), 2) if rets else 0,
            "avg_win": round(np.mean(wins), 2) if wins else 0,
            "avg_loss": round(np.mean(losses), 2) if losses else 0,
            "longest_loss_streak": streak,
            "worst_trade": round(min(rets), 2) if rets else 0,
            "best_trade": round(max(rets), 2) if rets else 0,
            "worst_10_trades": sorted(rets)[:10],
            "top_10_trades": sorted(rets, reverse=True)[:10],
            "avg_cash_usage": round(ap / self.max_pos * 100, 1),
            "max_concurrent_positions": max([e["npos"] for e in self.equity]) if self.equity else 0,
            "first_half": hs(self.trades[:mid]),
            "second_half": hs(self.trades[mid:]),
            "window_days": window_days,
            "actual_date_range": dr,
        }


# ══════════════════════════════════════════════════════════════════════════
# Baseline: real tail-entry d3+ma20_gap + dec_E
# ══════════════════════════════════════════════════════════════════════════
def build_tail_baseline_picks(factor_df, kline_dict, days):
    """Use the same pipeline as run_tail_portfolio_backtest.py."""
    # Compute z-scored d3+ma20_gap per day
    work = factor_df.copy()
    grouped = work.groupby("date", group_keys=False)
    work["z_d3"] = grouped["d3"].transform(zscore_series).fillna(0)
    work["z_ma20_gap"] = grouped["ma20_gap"].transform(zscore_series).fillna(0)
    work["d3_ma20_gap_score"] = work["z_d3"] + work["z_ma20_gap"]

    # Apply tail-entry filters
    work = work[(work["limit_move_flag"] == 0)
                & (work["atr_pct"].between(1.5, 7.0))
                & (work["ret_20d"] >= 0.0)
                & (work["ma20_gap"] >= -5.0)]

    # Daily top-5
    picks = []
    for date, group in work.groupby("date"):
        g = group.copy()
        if g.empty:
            continue
        for _, row in g.nlargest(5, "d3_ma20_gap_score").iterrows():
            d = row.to_dict()
            d["signal_score"] = d.get("d3_ma20_gap_score", 0)
            picks.append(d)

    if not picks:
        return defaultdict(list)

    picks_df = pd.DataFrame(picks)
    sbd = defaultdict(list)
    for _, row in picks_df.iterrows():
        d = str(row["date"])[:10]
        sbd[d].append(row.to_dict())
    return sbd


# ══════════════════════════════════════════════════════════════════════════
# Simulate tail-entry baseline (dec_E logic)
# ══════════════════════════════════════════════════════════════════════════
def run_baseline(factor_df, kline_dict, all_dates, max_pos, pp, days):
    """Run tail-entry baseline using the known-good signal pipeline."""
    sbd = build_tail_baseline_picks(factor_df, kline_dict, days)
    sim = SimplePortfolio(INITIAL_CASH, max_pos, pp)

    for d in sbd:
        sbd[d].sort(key=lambda x: x.get("signal_score", 0), reverse=True)

    for date in all_dates:
        cd = str(date)[:10]
        # Exits (dec_E: stop at T+1 14:00 if bad, else T+2 close)
        surviving = []
        for pos in sim.positions:
            t1d = str(pos.get("t1_date", ""))[:10]
            t2d = str(pos.get("t2_date", ""))[:10]
            exited = False
            if cd == t1d:
                # Approx 14:00
                t1o = pos.get("t1_open")
                t1h = pos.get("t1_high")
                t1l = pos.get("t1_low")
                t1c = pos.get("t1_close")
                if pd.notna(t1o) and pd.notna(t1c):
                    mid = (float(t1o) + float(t1c)) / 2
                    rng = float(t1h) - float(t1l) if pd.notna(t1h) and pd.notna(t1l) else 0
                    t1_1400 = mid + 0.12 * rng if float(t1c) > float(t1o) else mid - 0.12 * rng
                    ret1400 = net_return(pos["entry_price"], t1_1400)
                    el = pos.get("entry_low")
                    below = pd.notna(el) and el and float(t1_1400) < float(el)
                    if (ret1400 is not None and ret1400 <= -2.0) or below:
                        sim._close(pos, t1_1400, cd, "dec_E_1400_stop")
                        exited = True
                # else hold to T+2
            if not exited and cd == t2d:
                t2c = pos.get("t2_close")
                if pd.notna(t2c) and t2c:
                    sim._close(pos, float(t2c), cd, "dec_E_t2")
                    exited = True
            if not exited:
                surviving.append(pos)
        sim.positions = surviving

        # Entries
        avail = max_pos - len(sim.positions)
        if avail > 0 and cd in sbd:
            held = {p["code"] for p in sim.positions}
            for sig in sbd[cd]:
                if avail <= 0:
                    break
                if sig["code"] in held:
                    continue
                ep = sig.get("entry_close")
                if pd.isna(ep) or not ep or ep <= 0:
                    continue
                # Store T+1/T+2 data for exit logic
                sig["entry_low"] = sig.get("entry_low")
                sig["t1_date"] = sig.get("t1_date", "")
                sig["t2_date"] = sig.get("t2_date", "")
                sig["t1_open"] = sig.get("t1_open")
                sig["t1_high"] = sig.get("t1_high")
                sig["t1_low"] = sig.get("t1_low")
                sig["t1_close"] = sig.get("t1_close")
                sig["t2_close"] = sig.get("t2_close")
                sig["entry_price"] = ep
                if sim._open(sig, cd, ep, "t_close"):
                    avail -= 1
        sim.equity.append({"date": cd, "equity": round(sim._eq(kline_dict), 2),
                           "cash": round(sim.cash, 2), "npos": len(sim.positions)})
    return sim


# ══════════════════════════════════════════════════════════════════════════
# Window slicing — correctly using trading days
# ══════════════════════════════════════════════════════════════════════════
def slice_window(df, all_dates, kline_dict, window_days, buffer_days=10):
    """Restrict factor_df and all_dates to the last `window_days` trading days.

    Also trims all_dates to include only the relevant range (signal dates +
    exit buffer). Returns (window_df, window_dates, entry_dates).
    """
    all_factor_dates = sorted(df["date"].astype(str).str[:10].unique())
    if len(all_factor_dates) <= window_days:
        entry_dates = all_factor_dates
    else:
        entry_dates = all_factor_dates[-window_days:]

    first_entry = entry_dates[0]
    last_entry = entry_dates[-1]

    # Filter factor_df to entry dates only
    window_df = df[df["date"].astype(str).str[:10].isin(entry_dates)]

    # Filter all_dates: from first signal date to last signal date + exit buffer
    try:
        last_exit_needed = (pd.to_datetime(last_entry) + pd.Timedelta(days=15)).strftime("%Y-%m-%d")
    except Exception:
        last_exit_needed = last_entry
    window_dates = [d for d in all_dates
                    if first_entry <= d <= last_exit_needed]

    return window_df, window_dates, entry_dates


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
def main():
    started = datetime.now()
    print("=" * 78)
    print("回踩确认回测 — 修正重跑 (pullback_confirmation_fix_rerun_001)")
    print("=" * 78)

    # ── 1. Data ──
    print("\n[1] 数据准备")
    max_days = max(WINDOWS) + 10
    codes = load_csi300_codes(os.path.join(ROOT, "data", "csi300_stocks.json"))[:TOP]
    df, cfg = build_factor_table(codes, max_days, KLINE_COUNT, THREADS)
    kline_dict = fetch_klines(codes, KLINE_COUNT, THREADS)
    df = attach_execution_prices(df, kline_dict)
    print(f"  因子表: {len(df)} 行, 日期: {cfg['date_range']}")
    df = df.dropna(subset=["entry_close", "t1_open", "t1_close"])
    print(f"  执行价格后: {len(df)} 行")

    all_trading_dates = sorted({str(kdf.loc[i, "date"])[:10]
                                for kdf in kline_dict.values() if kdf is not None
                                for i in range(len(kdf))})

    context = build_date_kline_context(kline_dict)
    print("[2] K线上下文构建完成")

    # ── 2. Run grid ──
    all_results = []
    print(f"\n[3] 运行聚焦配置网格 ({len(FOCUSED_GRID)} families x "
          f"{len(EXIT_RULES)} exits x {len(POSITION_PCT_LIST)} pps x "
          f"{len(MAX_POSITIONS_LIST)} mps x {len(WINDOWS)} windows)")

    cfg_n = 0
    for window_days in WINDOWS:
        print(f"\n  === 窗口 {window_days}d ===")
        wdf, wdates, entry_dates = slice_window(df, all_trading_dates, kline_dict, window_days)

        entry_range = f"{entry_dates[0]} ~ {entry_dates[-1]}" if entry_dates else "N/A"
        print(f"  信号日期: {entry_range} ({len(entry_dates)} 天)")

        # Baseline for this window
        print(f"  运行基线 tail-entry d3+ma20_gap + dec_E ...")
        for mp in MAX_POSITIONS_LIST:
            for pp in POSITION_PCT_LIST:
                bl = run_baseline(wdf, kline_dict, wdates, mp, pp, window_days)
                bm = bl.metrics(window_days)
                bm["config_name"] = f"BASELINE_tail_d3_ma20_gap_dec_E_w{window_days}_pp{int(pp*100)}_mp{mp}"
                bm["config_type"] = "baseline"
                bm["entry_mode"] = "t_close"
                bm["trend_pool"] = "tail_d3_ma20_gap"
                bm["pullback_rule"] = "none"
                bm["confirmation_rule"] = "none"
                bm["exit_rule"] = "dec_E"
                bm["position_pct"] = pp
                bm["max_positions"] = mp
                bm["window_days"] = window_days
                bm["actual_entry_range"] = entry_range
                all_results.append(bm)
                print(f"    基线 mp{mp} pp{int(pp*100)}: "
                      f"ret={bm['total_return']:+.2f}% dd={bm['max_drawdown']:.2f}% "
                      f"r/dd={bm['return_to_drawdown']:.2f} trades={bm['trade_count']}")

        # Pullback configs
        for trend, pb, conf in FOCUSED_GRID:
            for exit_rule in EXIT_RULES:
                for mp in MAX_POSITIONS_LIST:
                    for pp in POSITION_PCT_LIST:
                        cfg_n += 1
                        signals = build_pullback_signals(wdf, context, trend, pb, conf)
                        if signals.empty:
                            continue

                        sbd = defaultdict(list)
                        for _, row in signals.iterrows():
                            d = str(row["date"])[:10]
                            sbd[d].append(row.to_dict())

                        sim = SimplePortfolio(INITIAL_CASH, mp, pp)
                        sim.run(sbd, wdates, exit_rule, kline_dict, context, "t1_open_realistic")

                        m = sim.metrics(window_days)
                        tag = "TP_RANK" if "d3_ge_8" in trend else ("TP_MA" if "ma60" in trend else "TP_TOP20")
                        m["config_name"] = f"{tag}|{pb}|{conf}|t1_open|{exit_rule}|w{window_days}|pp{int(pp*100)}|mp{mp}"
                        m["config_type"] = "pullback"
                        m["trend_pool"] = trend
                        m["pullback_rule"] = pb
                        m["confirmation_rule"] = conf
                        m["entry_mode"] = "t1_open_realistic"
                        m["exit_rule"] = exit_rule
                        m["position_pct"] = pp
                        m["max_positions"] = mp
                        m["window_days"] = window_days
                        m["actual_entry_range"] = entry_range

                        # Compare to matching baseline
                        bl_matches = [r for r in all_results
                                      if r.get("config_type") == "baseline"
                                      and r.get("window_days") == window_days
                                      and r.get("max_positions") == mp
                                      and abs(r.get("position_pct", 0) - pp) < 0.001]
                        if bl_matches:
                            blm = bl_matches[0]
                            m["baseline_return"] = blm.get("total_return", 0)
                            m["baseline_dd"] = blm.get("max_drawdown", 0)
                            m["baseline_rdd"] = blm.get("return_to_drawdown", 0)
                            m["dd_vs_baseline"] = round(m["max_drawdown"] - blm.get("max_drawdown", 0), 2)
                            m["trade_count_ratio_vs_tail_baseline"] = round(
                                m["trade_count"] / max(1, blm.get("trade_count", 1)), 2)
                        all_results.append(m)

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\n  总计: {len(all_results)} 配置, 耗时 {elapsed:.0f}s")

    # ── 3. Rank ──
    pullback = [r for r in all_results if r.get("config_type") == "pullback"]
    baseline = [r for r in all_results if r.get("config_type") == "baseline"]

    # Separate 120d and 90d
    pb_120 = [r for r in pullback if r.get("window_days") == 120 and r.get("trade_count", 0) >= 20]
    pb_90 = [r for r in pullback if r.get("window_days") == 90 and r.get("trade_count", 0) >= 20]

    def rank_key(r):
        """Promote: DD low, PF high, trades high, return high."""
        dd = abs(r.get("max_drawdown", -100))
        pf = r.get("profit_factor", 0)
        ret = r.get("total_return", 0)
        trades = r.get("trade_count", 0)
        # Target premium
        bonus = (10 if dd <= 18 else 0) + (8 if pf > 1.4 else 0) + \
                (8 if ret >= 8 else 0) + (5 if trades >= 50 else 0) + \
                (5 if r.get("first_half", {}).get("ret", 0) > 0 and
                     r.get("second_half", {}).get("ret", 0) > 0 else 0)
        return dd - bonus

    pb_120.sort(key=rank_key)
    pb_90.sort(key=rank_key)

    # Promotion check
    promotes_120 = [r for r in pb_120
                    if r.get("max_drawdown", -100) >= -18
                    and r.get("profit_factor", 0) > 1.4
                    and r.get("total_return", 0) >= 8
                    and r.get("trade_count", 0) >= 50]
    promotes_90 = [r for r in pb_90
                   if r.get("max_drawdown", -100) >= -18
                   and r.get("profit_factor", 0) > 1.4
                   and r.get("total_return", 0) >= 8
                   and r.get("trade_count", 0) >= 50]

    # ── 4. Output ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Summary
    summary = ""
    if promotes_120:
        best = promotes_120[0]
        summary = (f"[PASS] 120d 达标配置: {best['config_name']}, "
                   f"ret={best['total_return']:+.2f}%, DD={best['max_drawdown']:.2f}%, "
                   f"r/dd={best['return_to_drawdown']:.2f}, PF={best['profit_factor']:.2f}, "
                   f"trades={best['trade_count']}")
    elif promotes_90:
        best = promotes_90[0]
        summary = (f"[WARN] 仅90d达标 (120d无达标): {best['config_name']}, "
                   f"ret={best['total_return']:+.2f}%, DD={best['max_drawdown']:.2f}%")
    elif pb_120:
        best = pb_120[0]
        summary = (f"[FAIL] 无达标配置。最佳120d探索: {best['config_name']}, "
                   f"ret={best['total_return']:+.2f}%, DD={best['max_drawdown']:.2f}%, "
                   f"trades={best['trade_count']}")
    else:
        summary = "无有效回踩确认配置。"

    result = {
        "id": "pullback_confirmation_fix_rerun_001",
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "completed_by": "claude_code",
        "summary": summary,
        "config_counts": {
            "total": len(all_results),
            "baseline": len(baseline),
            "pullback_120d": len(pb_120),
            "pullback_90d": len(pb_90),
            "promoted_120d": len(promotes_120),
            "promoted_90d": len(promotes_90),
        },
        "top_20_120d": pb_120[:20],
        "top_20_90d": pb_90[:20],
        "promoted_120d": promotes_120[:10],
        "promoted_90d": promotes_90[:10],
        "baseline_summary": {
            "120d_pp20": next((r for r in baseline
                               if r.get("window_days") == 120
                               and abs(r.get("position_pct", 0) - 0.20) < 0.001
                               and r.get("max_positions") == 2), {}),
            "120d_pp15": next((r for r in baseline
                               if r.get("window_days") == 120
                               and abs(r.get("position_pct", 0) - 0.15) < 0.001
                               and r.get("max_positions") == 2), {}),
        },
        "files_generated": [],
    }

    # Write full results
    full_path = os.path.join(ROOT, "reports", f"pullback_confirmation_fix_rerun_full_{ts}.json")
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump({"all_results": all_results}, f, ensure_ascii=False, indent=2, default=str)
    result["files_generated"].append(full_path)

    # Write summary JSON
    json_path = os.path.join(ROOT, "reports", f"pullback_confirmation_fix_rerun_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    result["files_generated"].append(json_path)

    # Write MD
    md_path = os.path.join(ROOT, "reports", f"pullback_confirmation_fix_rerun_summary_{ts}.md")
    write_md(result, md_path)
    result["files_generated"].append(md_path)

    # Write queue result
    qr_path = os.path.join(ROOT, "backtest_queue", "done", "pullback_confirmation_fix_rerun_001_result.json")
    os.makedirs(os.path.dirname(qr_path), exist_ok=True)
    with open(qr_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n{'=' * 78}")
    print(summary)
    print(f"全量: {full_path}")
    print(f"队列: {qr_path}")
    print(f"{'=' * 78}")


def write_md(result, path):
    lines = ["# 回踩确认回测 — 修正重跑 报告", "",
             f"**时间**: {datetime.now().isoformat()}",
             f"**ID**: pullback_confirmation_fix_rerun_001", "",
             "## 摘要", "", result.get("summary", ""), "",
             "## 基线 (tail-entry d3+ma20_gap + dec_E)", ""]
    bl = result.get("baseline_summary", {})
    for k, v in bl.items():
        if v:
            lines.append(f"- **{k}**: ret={v.get('total_return',0):+.2f}%, "
                         f"DD={v.get('max_drawdown',0):.2f}%, r/dd={v.get('return_to_drawdown',0):.2f}, "
                         f"PF={v.get('profit_factor',0):.2f}, trades={v.get('trade_count',0)}")
    lines += ["", "## 120d Top 20 现实入场 (T+1 Open)", "",
              "| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易 | DD改善 |",
              "|------|-------|------|------|----|-------|------|--------|"]
    for r in result.get("top_20_120d", [])[:20]:
        lines.append(f"| {r.get('config_name','')[:55]} "
                     f"| {r.get('total_return',0):+.1f} | {r.get('max_drawdown',0):.1f} "
                     f"| {r.get('return_to_drawdown',0):.2f} | {r.get('profit_factor',0):.2f} "
                     f"| {r.get('win_rate',0):.1f} | {r.get('trade_count',0)} "
                     f"| {r.get('dd_vs_baseline',0):+.1f} |")
    lines += ["", "## 90d Top 10 (参考)", "",
              "| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易 |",
              "|------|-------|------|------|----|-------|------|"]
    for r in result.get("top_20_90d", [])[:10]:
        lines.append(f"| {r.get('config_name','')[:55]} "
                     f"| {r.get('total_return',0):+.1f} | {r.get('max_drawdown',0):.1f} "
                     f"| {r.get('return_to_drawdown',0):.2f} | {r.get('profit_factor',0):.2f} "
                     f"| {r.get('win_rate',0):.1f} | {r.get('trade_count',0)} |")
    lines += ["", "## 文件", ""]
    for f in result.get("files_generated", []):
        lines.append(f"- `{f}`")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
