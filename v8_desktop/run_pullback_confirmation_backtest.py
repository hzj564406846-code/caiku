"""Pullback confirmation backtest for strong-trend stocks.

Tests whether waiting for a controlled pullback + confirmation signal on
strong-trend stocks (d3+ma20_gap) reduces max drawdown versus tail-entry
chasing, while retaining positive alpha.

Usage:
  python run_pullback_confirmation_backtest.py
"""
import json
import os
import sys
import time
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from engine.cache_manager import load_csi300_codes                          # noqa: E402
from engine.data_fetcher import fetch_csi300_index                           # noqa: E402
from run_factor_research import build_factor_table, fetch_klines, zscore_series  # noqa: E402

# ══════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════
INITIAL_CASH = 100_000
TOP = 60
THREADS = 8
KLINE_COUNT = 600
COST_BPS = 5.0
SLIPPAGE_BPS = 10.0
WINDOWS = [90, 120]
MAX_POSITIONS_LIST = [2, 3]
POSITION_PCT_LIST = [0.10, 0.15, 0.20]


# ══════════════════════════════════════════════════════════════════════════
# Data preparation — reuse existing pipeline
# ══════════════════════════════════════════════════════════════════════════
def build_full_factor_table(days, kline_count=KLINE_COUNT, top=TOP):
    """Build point-in-time factor table with execution prices attached."""
    codes = load_csi300_codes(os.path.join(ROOT, "data", "csi300_stocks.json"))[:top]
    print(f"[数据] 构建因子表 (days={days}, kline_count={kline_count}) ...")
    df, cfg = build_factor_table(codes, days, kline_count, THREADS)

    # Attach T+1/T+2/T+3 execution prices
    kline_dict = fetch_klines(codes, kline_count, THREADS)
    df = _attach_execution_prices(df, kline_dict)
    df = df.dropna(subset=["entry_close", "t1_open", "t1_close"])
    print(f"  因子表: {len(df)} 行, 日期: {cfg['date_range']}")
    return df, cfg, kline_dict, codes


def _attach_execution_prices(factor_df, kline_dict):
    """Attach entry_close, T+1/T+2/T+3 OHLC to each factor row."""
    rows = []
    for _, row in factor_df.iterrows():
        code = row["code"]
        kdf = kline_dict.get(code)
        if kdf is None or kdf.empty:
            continue
        dates = kdf["date"].astype(str).str[:10]
        matches = kdf.index[dates == str(row["date"])[:10]]
        if len(matches) == 0:
            continue
        idx = int(matches[0])
        if idx + 1 >= len(kdf):
            continue
        item = row.to_dict()
        item["entry_close"] = float(kdf.loc[idx, "close"])
        item["entry_open"] = float(kdf.loc[idx, "open"])
        item["entry_high"] = float(kdf.loc[idx, "high"])
        item["entry_low"] = float(kdf.loc[idx, "low"])
        # Also store kline context for pullback detection (point-in-time)
        # Truncated kline up to 'date' for computing MA20 etc.
        for offset, prefix in ((1, "t1"), (2, "t2"), (3, "t3"), (4, "t4"),
                               (5, "t5"), (6, "t6"), (7, "t7"), (8, "t8")):
            fidx = idx + offset
            if fidx >= len(kdf):
                item[f"{prefix}_date"] = ""
                item[f"{prefix}_open"] = np.nan
                item[f"{prefix}_high"] = np.nan
                item[f"{prefix}_low"] = np.nan
                item[f"{prefix}_close"] = np.nan
                continue
            item[f"{prefix}_date"] = str(pd.to_datetime(kdf.loc[fidx, "date"]).date())
            item[f"{prefix}_open"] = float(kdf.loc[fidx, "open"])
            item[f"{prefix}_high"] = float(kdf.loc[fidx, "high"])
            item[f"{prefix}_low"] = float(kdf.loc[fidx, "low"])
            item[f"{prefix}_close"] = float(kdf.loc[fidx, "close"])
        rows.append(item)
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════
# Net return with friction
# ══════════════════════════════════════════════════════════════════════════
def net_return(entry_price, exit_price, cost_bps=COST_BPS, slippage_bps=SLIPPAGE_BPS):
    if not entry_price or not exit_price or entry_price <= 0 or exit_price <= 0:
        return None
    buy = float(entry_price) * (1 + slippage_bps / 10000.0)
    sell = float(exit_price) * (1 - slippage_bps / 10000.0)
    raw = (sell - buy) / buy * 100.0
    return raw - (cost_bps * 2 / 100.0)


# ══════════════════════════════════════════════════════════════════════════
# Point-in-time context builder
# ══════════════════════════════════════════════════════════════════════════
def build_date_kline_context(kline_dict):
    """Pre-build per-code per-date kline context for pullback detection.

    Returns dict: {code: {date_str: {ma20, ma60, ret_5d, ret_20d, atr_pct,
                   vol_ratio, 20d_high, ...}}}
    """
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

        # Pre-compute rolling indicators (point-in-time: only use data up to each row)
        code_ctx = {}
        for i in range(len(kdf)):
            if i < 60:  # Need at least 60 days of history
                continue
            d = kdf.loc[i, "date_str"]
            c = closes.iloc[i]
            o = opens.iloc[i]
            h = highs.iloc[i]
            l = lows.iloc[i]
            v = volumes.iloc[i]

            # MA20 (using i as current, window up to i)
            ma20 = closes.iloc[i - 19:i + 1].mean()
            ma60 = closes.iloc[i - 59:i + 1].mean()

            # Returns
            ret_5d = (c - closes.iloc[i - 5]) / closes.iloc[i - 5] * 100 if i >= 5 else 0
            ret_20d = (c - closes.iloc[i - 20]) / closes.iloc[i - 20] * 100 if i >= 20 else 0

            # ATR (14-day)
            tr_list = []
            for j in range(max(0, i - 13), i + 1):
                tr = max(
                    highs.iloc[j] - lows.iloc[j],
                    abs(highs.iloc[j] - closes.iloc[j - 1]) if j > 0 else 0,
                    abs(lows.iloc[j] - closes.iloc[j - 1]) if j > 0 else 0,
                )
                tr_list.append(tr)
            atr = float(np.mean(tr_list))
            atr_pct = atr / c * 100 if c > 0 else 0

            # Volume ratio
            avg_vol = volumes.iloc[max(0, i - 19):i + 1].mean()
            vol_ratio = v / avg_vol if avg_vol > 0 else 1.0

            # MA20 gap
            ma20_gap = (c - ma20) / ma20 * 100

            # 20-day high
            high_20d = highs.iloc[max(0, i - 19):i + 1].max()

            # Prior day's high
            prior_high = highs.iloc[i - 1] if i >= 1 else h

            # 20-day high date (for no_chase check)
            high_5d = highs.iloc[max(0, i - 4):i + 1].max()

            code_ctx[d] = {
                "close": float(c),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "volume": float(v),
                "ma20": float(ma20),
                "ma60": float(ma60),
                "ret_5d": float(ret_5d),
                "ret_20d": float(ret_20d),
                "atr_pct": float(atr_pct),
                "vol_ratio": float(vol_ratio),
                "ma20_gap": float(ma20_gap),
                "high_20d": float(high_20d),
                "high_5d": float(high_5d),
                "prior_high": float(prior_high),
                "prior_close": float(closes.iloc[i - 1]) if i >= 1 else float(c),
            }
        if code_ctx:
            context[code] = code_ctx
    return context


# ══════════════════════════════════════════════════════════════════════════
# Trend pool definitions
# ══════════════════════════════════════════════════════════════════════════
def build_trend_pool(factor_df, pool_name):
    """Filter factor_df rows that belong to the strong-trend candidate pool.

    Returns filtered DataFrame with same columns + trend_pool_score column.
    """
    df = factor_df.copy()
    df["trend_pool_score"] = df["d3"].fillna(0) + df["ma20_gap"].fillna(0)

    if pool_name == "trend_pool_rank_d3_ma20gap_d3_ge_8_ret20_ge_0":
        df = df[(df["d3"] >= 8) & (df["ret_20d"] >= 0)]
    elif pool_name == "trend_pool_ma60_ma20_structure_d3_ge_8":
        df = df[(df["d3"] >= 8)
                & (df["price_above_ma60"] == 1)
                & (df["ma20_above_ma60"] == 1)]
    elif pool_name == "trend_pool_top20pct_d3_ma20gap":
        # Per-day top 20% by d3+ma20_gap
        sorted_dfs = []
        for date, group in df.groupby("date"):
            n = max(1, int(len(group) * 0.2))
            pool = group.nlargest(n, "trend_pool_score")
            sorted_dfs.append(pool)
        df = pd.concat(sorted_dfs, ignore_index=True) if sorted_dfs else df
    else:
        # Default (should not happen)
        pass
    return df


# ══════════════════════════════════════════════════════════════════════════
# Pullback condition checks (point-in-time)
# ══════════════════════════════════════════════════════════════════════════
def check_pullback(row, condition, context):
    """Check if a stock row satisfies the pullback condition.

    Uses pre-built context dict for point-in-time indicators.
    Returns (bool, dict of debug info).
    """
    code = row["code"]
    date = str(row["date"])[:10]
    ctx = context.get(code, {}).get(date)
    if ctx is None:
        return False, {"reason": "no_context"}

    c = ctx["close"]
    ma20 = ctx["ma20"]
    ret_5d = ctx["ret_5d"]
    ret_20d = ctx["ret_20d"]
    ma20_gap = ctx["ma20_gap"]
    vol_ratio = ctx["vol_ratio"]
    low = ctx["low"]
    high = ctx["high"]
    open_ = ctx["open"]
    prior_close = ctx["prior_close"]
    atr_pct = ctx["atr_pct"]
    high_5d = ctx["high_5d"]
    high_20d = ctx["high_20d"]

    info = {}

    if condition == "near_ma20":
        # MA20 gap between -3% and +3%
        passed = -3.0 <= ma20_gap <= 3.0
        info["ma20_gap"] = round(ma20_gap, 2)
        return passed, info

    elif condition == "shallow_pullback":
        # ret_5d between -8% and +1% while ret_20d > 0
        passed = (-8.0 <= ret_5d <= 1.0) and (ret_20d > 0)
        info["ret_5d"] = round(ret_5d, 2)
        info["ret_20d"] = round(ret_20d, 2)
        return passed, info

    elif condition == "touch_reclaim_ma20":
        # Today's low <= MA20 and close >= MA20
        passed = (low <= ma20 * 1.005) and (c >= ma20 * 0.995)
        info["low_vs_ma20"] = round(low / ma20, 3)
        info["close_vs_ma20"] = round(c / ma20, 3)
        return passed, info

    elif condition == "shrink_pullback":
        # Negative or flat 3-5d return with volume_ratio <= 1.2
        passed = (ret_5d <= 1.0) and (vol_ratio <= 1.2)
        info["ret_5d"] = round(ret_5d, 2)
        info["vol_ratio"] = round(vol_ratio, 2)
        return passed, info

    elif condition == "no_chase":
        # Exclude if close is near 20d high or daily gain is too large
        daily_gain = (c - prior_close) / prior_close * 100 if prior_close > 0 else 0
        passed = (c < high_5d * 0.98) and (daily_gain < 5.0)
        info["daily_gain"] = round(daily_gain, 2)
        info["close_vs_5d_high"] = round(c / high_5d, 3) if high_5d > 0 else 0
        return passed, info

    elif condition == "lower_shadow_reclaim":
        # Lower shadow >= 0.5% and close > open (positive close)
        lower_shadow = (min(c, open_) - low) / open_ * 100 if open_ > 0 else 0
        daily_gain = (c - prior_close) / prior_close * 100 if prior_close > 0 else 0
        passed = (lower_shadow >= 0.5) and (daily_gain >= 0)
        info["lower_shadow_pct"] = round(lower_shadow, 2)
        info["daily_gain"] = round(daily_gain, 2)
        return passed, info

    return False, {"reason": f"unknown_condition:{condition}"}


# ══════════════════════════════════════════════════════════════════════════
# Confirmation condition checks (point-in-time)
# ══════════════════════════════════════════════════════════════════════════
def check_confirmation(row, context, conf_condition):
    """Check confirmation signal on the signal/entry date.

    'none' means no confirmation required (entry as soon as pullback detected).
    Other confirmation conditions check the current day's bar.
    """
    if conf_condition == "none":
        return True, {}

    code = row["code"]
    date = str(row["date"])[:10]
    ctx = context.get(code, {}).get(date)
    if ctx is None:
        return False, {"reason": "no_context"}

    c = ctx["close"]
    h = ctx["high"]
    o = ctx["open"]
    l = ctx["low"]
    ma20 = ctx["ma20"]
    prior_high = ctx["prior_high"]
    prior_close = ctx["prior_close"]
    vol_ratio = ctx["vol_ratio"]
    open_ = ctx["open"]
    atr_pct = ctx["atr_pct"]

    info = {}

    if conf_condition == "close_above_ma20":
        passed = c > ma20
        info["close_vs_ma20"] = round(c / ma20, 3)
        return passed, info

    elif conf_condition == "close_positive_after_pullback":
        # Close > prior close (positive day after the pullback)
        daily_gain = (c - prior_close) / prior_close * 100 if prior_close > 0 else 0
        passed = daily_gain > 0
        info["daily_gain"] = round(daily_gain, 2)
        return passed, info

    elif conf_condition == "close_above_prior_high":
        # Close > prior day's high
        passed = c > prior_high
        info["close_vs_prior_high"] = round(c / prior_high, 3) if prior_high > 0 else 0
        return passed, info

    elif conf_condition == "volume_reexpand":
        # Volume ratio > 1.0 and close > open
        daily_gain = (c - prior_close) / prior_close * 100 if prior_close > 0 else 0
        passed = (vol_ratio > 1.0) and (daily_gain > 0)
        info["vol_ratio"] = round(vol_ratio, 2)
        info["daily_gain"] = round(daily_gain, 2)
        return passed, info

    elif conf_condition == "hammer_or_lower_shadow":
        # Lower shadow >= 0.8% OR hammer flag
        lower_shadow = (min(c, o) - l) / o * 100 if o > 0 else 0
        passed = (lower_shadow >= 0.8) or (row.get("hammer_flag", 0) == 1)
        info["lower_shadow_pct"] = round(lower_shadow, 2)
        info["hammer_flag"] = row.get("hammer_flag", 0)
        return passed, info

    return False, {"reason": f"unknown_confirmation:{conf_condition}"}


# ══════════════════════════════════════════════════════════════════════════
# Signal scan: trend_pool + pullback + confirmation → entry candidates
# ══════════════════════════════════════════════════════════════════════════
def build_pullback_signals(factor_df, context, trend_pool, pullback_cond, conf_cond,
                           add_extra_pullback=[]):
    """Scan factor_df for pullback + confirmation signals.

    Parameters
    ----------
    factor_df : DataFrame with all factor rows
    context : per-code per-date kline context
    trend_pool : str — trend pool name
    pullback_cond : str — pullback condition name
    conf_cond : str — confirmation condition
    add_extra_pullback : list[str] — additional pullback conditions to AND

    Returns
    -------
    DataFrame with signal rows sorted by date.
    """
    pool_df = build_trend_pool(factor_df, trend_pool)
    if pool_df.empty:
        return pool_df

    signals = []
    for _, row in pool_df.iterrows():
        # Check main pullback condition
        passed, pb_info = check_pullback(row, pullback_cond, context)
        if not passed:
            continue

        # Check additional pullback conditions
        extra_ok = True
        for extra in add_extra_pullback:
            ep, _ = check_pullback(row, extra, context)
            if not ep:
                extra_ok = False
                break
        if not extra_ok:
            continue

        # Check confirmation
        conf_passed, conf_info = check_confirmation(row, context, conf_cond)
        if not conf_passed:
            continue

        item = row.to_dict()
        item["trend_pool"] = trend_pool
        item["pullback_cond"] = pullback_cond
        item["conf_cond"] = conf_cond
        item["signal_date"] = str(row["date"])[:10]
        # Score by d3+ma20_gap for ranking within day
        item["signal_score"] = float(row.get("d3", 0)) + float(row.get("ma20_gap", 0))
        signals.append(item)

    if not signals:
        return pd.DataFrame()

    sig_df = pd.DataFrame(signals)
    sig_df = sig_df.sort_values("date")
    return sig_df


# ══════════════════════════════════════════════════════════════════════════
# Exit rules for pullback strategy
# ══════════════════════════════════════════════════════════════════════════
def get_pullback_exit(trade, current_date, kline_dict, exit_rule, context):
    """Check if a held position should exit on current_date.

    Parameters
    ----------
    trade : dict with entry info, entry_date (signal_date), code, entry_price
    current_date : str 'YYYY-MM-DD'
    exit_rule : str
    context : per-code per-date context dict

    Returns
    -------
    dict or None — {'price', 'type', 'date'} if exiting, else None
    """
    code = trade["code"]
    entry_date = trade["entry_date"]
    entry_price = trade["entry_price"]
    kdf = kline_dict.get(code)
    if kdf is None or kdf.empty:
        return None

    dates = kdf["date"].astype(str).str[:10]
    cd = str(current_date)[:10]

    try:
        entry_dt = pd.to_datetime(entry_date)
    except Exception:
        return None

    # Count holding days since entry
    trade_days = 0
    for d in sorted(dates.unique()):
        if str(d)[:10] > entry_date and str(d)[:10] <= cd:
            trade_days += 1

    # Match current_date to kline index
    matches = kdf.index[dates == cd]
    if len(matches) == 0:
        return None
    idx = int(matches[0])

    c = float(kdf.loc[idx, "close"])
    l = float(kdf.loc[idx, "low"])
    o = float(kdf.loc[idx, "open"])

    ctx = context.get(code, {}).get(cd, {})
    ma20 = ctx.get("ma20", c)

    if exit_rule == "hold_3d_close":
        if trade_days >= 3:
            return {"price": c, "type": "hold_3d", "date": cd}

    elif exit_rule == "hold_5d_close":
        if trade_days >= 5:
            return {"price": c, "type": "hold_5d", "date": cd}

    elif exit_rule == "hold_8d_close":
        if trade_days >= 8:
            return {"price": c, "type": "hold_8d", "date": cd}

    elif exit_rule == "ma20_or_pullback_low_break_then_hold5":
        # Protective stop: if close breaks MA20 by more than 2%
        # OR if low breaks the pullback low (entry_low) by more than 2%
        # Otherwise hold 5 days
        pullback_low = trade.get("pullback_low", entry_price)

        if c < ma20 * 0.98 or l < pullback_low * 0.98:
            return {"price": c, "type": "protective_stop", "date": cd}

        if trade_days >= 5:
            return {"price": c, "type": "hold_5d", "date": cd}

    return None


# ══════════════════════════════════════════════════════════════════════════
# Portfolio simulator for pullback strategy
# ══════════════════════════════════════════════════════════════════════════
class PullbackPortfolioSimulator:
    def __init__(self, initial_cash, max_positions, position_pct,
                 cost_bps=COST_BPS, slippage_bps=SLIPPAGE_BPS):
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.max_positions = max_positions
        self.position_pct = position_pct
        self.cost_bps = cost_bps
        self.slippage_bps = slippage_bps

        self.positions = []
        self.closed_trades = []
        self.equity_curve = []

    def _total_equity(self, kline_dict):
        mv = sum(self._position_value(p, kline_dict) for p in self.positions)
        return self.cash + mv

    def _position_value(self, pos, kline_dict):
        code = pos["code"]
        kdf = kline_dict.get(code)
        if kdf is None or kdf.empty:
            return pos["cost"]
        last_close = float(kdf.iloc[-1]["close"])
        return pos["shares"] * last_close

    def _open_position(self, signal, date, entry_price, entry_mode):
        code = signal["code"]
        px = float(entry_price)
        equity = self.cash + sum(p["cost"] for p in self.positions)
        target_value = equity * self.position_pct

        if target_value < px * 100:
            return False

        if self.cash < target_value:
            target_value = self.cash * 0.99

        shares = int(target_value / px / 100) * 100
        if shares < 100:
            return False

        cost = shares * px * (1 + self.slippage_bps / 10000.0)
        if cost > self.cash:
            shares = int((self.cash * 0.99) / (px * (1 + self.slippage_bps / 10000.0)) / 100) * 100
            if shares < 100:
                return False
            cost = shares * px * (1 + self.slippage_bps / 10000.0)

        self.cash -= cost
        self.positions.append({
            "code": code,
            "entry_date": str(date),
            "entry_price": px,
            "entry_mode": entry_mode,
            "shares": shares,
            "cost": cost,
            "score": float(signal.get("signal_score", 0)),
            "pullback_cond": signal.get("pullback_cond", ""),
            "conf_cond": signal.get("conf_cond", ""),
        })
        return True

    def _close_position(self, pos, exit_price, exit_date, exit_type):
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
            "entry_mode": pos.get("entry_mode", ""),
        })

    def run(self, signals_by_date, all_dates, exit_rule, kline_dict, context,
            entry_mode="t1_open_realistic"):
        """Run portfolio simulation.

        Parameters
        ----------
        signals_by_date : dict[str, list[dict]]
            Pullback signals keyed by signal_date
        all_dates : list[str]
            Sorted trading dates
        exit_rule : str
        kline_dict : dict
        context : dict
        entry_mode : str
            't_close_optimistic' or 't1_open_realistic'
        """
        for d in signals_by_date:
            signals_by_date[d].sort(key=lambda x: x.get("signal_score", 0), reverse=True)

        for di, date in enumerate(all_dates):
            cd = str(date)[:10]

            # ── 1. Process exits ──
            surviving = []
            for pos in self.positions:
                exit_info = get_pullback_exit(pos, cd, kline_dict, exit_rule, context)
                if exit_info:
                    self._close_position(pos, exit_info["price"], cd, exit_info["type"])
                else:
                    surviving.append(pos)
            self.positions = surviving

            # ── 2. Entry (only on signal dates) ──
            available = self.max_positions - len(self.positions)
            if available > 0 and cd in signals_by_date:
                held_codes = {p["code"] for p in self.positions}
                for signal in signals_by_date[cd]:
                    if available <= 0:
                        break
                    if signal["code"] in held_codes:
                        continue

                    if entry_mode == "t_close_optimistic":
                        entry_price = signal.get("entry_close")
                    else:  # T+1 open realistic
                        entry_price = signal.get("t1_open")

                    if pd.isna(entry_price) or not entry_price or entry_price <= 0:
                        continue

                    if self._open_position(signal, cd, entry_price, entry_mode):
                        available -= 1

            # ── 3. Record equity ──
            eq = self._total_equity(kline_dict)
            self.equity_curve.append({
                "date": cd,
                "equity": round(eq, 2),
                "cash": round(self.cash, 2),
                "positions": len(self.positions),
            })

    def metrics(self, window_days):
        """Compute comprehensive metrics from closed trades."""
        trades = self.closed_trades
        if not trades:
            return {
                "total_return": 0.0, "max_drawdown": 0.0, "return_to_drawdown": 0.0,
                "profit_factor": 0.0, "win_rate": 0.0, "trade_count": 0,
                "avg_trade_return": 0.0, "median_trade_return": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0, "longest_loss_streak": 0,
                "worst_trade": 0.0, "best_trade": 0.0,
                "worst_10_trades": [], "top_10_trades": [],
                "avg_cash_usage": 0.0, "max_concurrent_positions": 0,
                "first_half": {"ret": 0, "dd": 0, "win_rate": 0, "trades": 0},
                "second_half": {"ret": 0, "dd": 0, "win_rate": 0, "trades": 0},
                "window_days": window_days, "actual_date_range": "N/A",
            }

        returns = [t["ret_pct"] for t in trades]
        eq = [e["equity"] for e in self.equity_curve]
        dates = [e["date"] for e in self.equity_curve]

        total_return = (self._total_equity({}) - self.initial_cash) / self.initial_cash * 100

        # Max drawdown from equity curve
        if eq:
            peak = eq[0]
            max_dd = 0.0
            for v in eq:
                if v > peak:
                    peak = v
                dd = (v - peak) / peak * 100
                if dd < max_dd:
                    max_dd = dd
        else:
            max_dd = 0.0

        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        win_rate = len(wins) / len(returns) * 100 if returns else 0
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        pf = gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0)

        # Loss streak
        longest_loss_streak = 0
        current_streak = 0
        for r in returns:
            if r <= 0:
                current_streak += 1
                longest_loss_streak = max(longest_loss_streak, current_streak)
            else:
                current_streak = 0

        # Split half
        mid = len(trades) // 2
        first_half_trades = trades[:mid]
        second_half_trades = trades[mid:]

        def half_stats(half):
            if not half:
                return {"ret": 0, "dd": 0, "win_rate": 0, "trades": 0}
            rets = [t["ret_pct"] for t in half]
            wins_h = [r for r in rets if r > 0]
            return {
                "ret": round(sum(rets), 2),
                "dd": round(min(rets) if rets else 0, 2),
                "win_rate": round(len(wins_h) / len(rets) * 100, 1),
                "trades": len(half),
            }

        # Avg cash usage
        avg_positions = np.mean([e["positions"] for e in self.equity_curve]) if self.equity_curve else 0

        # Actual date range
        if self.equity_curve:
            actual_range = f"{self.equity_curve[0]['date']} ~ {self.equity_curve[-1]['date']}"
        else:
            actual_range = "N/A"

        return {
            "total_return": round(total_return, 2),
            "max_drawdown": round(max_dd, 2),
            "return_to_drawdown": round(total_return / abs(max_dd), 2) if max_dd != 0 else 0,
            "profit_factor": round(pf, 2),
            "win_rate": round(win_rate, 1),
            "trade_count": len(trades),
            "avg_trade_return": round(np.mean(returns), 2) if returns else 0,
            "median_trade_return": round(np.median(returns), 2) if returns else 0,
            "avg_win": round(np.mean(wins), 2) if wins else 0,
            "avg_loss": round(np.mean(losses), 2) if losses else 0,
            "longest_loss_streak": longest_loss_streak,
            "worst_trade": round(min(returns), 2) if returns else 0,
            "best_trade": round(max(returns), 2) if returns else 0,
            "worst_10_trades": sorted(returns)[:10],
            "top_10_trades": sorted(returns, reverse=True)[:10],
            "avg_cash_usage": round(avg_positions / self.max_positions * 100, 1),
            "max_concurrent_positions": max([e["positions"] for e in self.equity_curve]) if self.equity_curve else 0,
            "first_half": half_stats(first_half_trades),
            "second_half": half_stats(second_half_trades),
            "window_days": window_days,
            "actual_date_range": actual_range,
        }


# ══════════════════════════════════════════════════════════════════════════
# Build tail-entry baseline (d3+ma20_gap + dec_E + mp2)
# ══════════════════════════════════════════════════════════════════════════
def build_tail_baseline_signals(factor_df, kline_dict):
    """Build tail-entry signals using d3+ma20_gap baseline.

    This is the same logic as the tail-entry portfolio backtest:
    - Factor: d3 + ma20_gap
    - Daily top-5 by d3+ma20_gap z-score
    - Filter: atr 1.5-7, ret_20d >= 0, ma20_gap >= -5%
    """
    work = factor_df.copy()
    grouped = work.groupby("date", group_keys=False)
    work["z_d3"] = grouped["d3"].transform(zscore_series).fillna(0)
    work["z_ma20_gap"] = grouped["ma20_gap"].transform(zscore_series).fillna(0)
    work["d3_ma20_gap_score"] = work["z_d3"] + work["z_ma20_gap"]

    # Apply filters
    work = work[(work["limit_move_flag"] == 0)
                & (work["atr_pct"].between(1.5, 7.0))
                & (work["ret_20d"] >= 0.0)
                & (work["ma20_gap"] >= -5.0)]

    picks = []
    for date, group in work.groupby("date"):
        g = group.copy()
        if g.empty:
            continue
        for _, row in g.nlargest(5, "d3_ma20_gap_score").iterrows():
            picks.append(row.to_dict())

    if not picks:
        return {}

    picks_df = pd.DataFrame(picks)
    signals = defaultdict(list)
    for _, row in picks_df.iterrows():
        d = str(row["date"])[:10]
        signals[d].append(row.to_dict())
    return signals


# ══════════════════════════════════════════════════════════════════════════
# Tail-entry exit rule (dec_E) adapter
# ══════════════════════════════════════════════════════════════════════════
def get_tail_exit(pos, current_date, kline_dict, exit_rule="dec_E"):
    """Reuse tail-entry exit logic: stop at T+1 14:00 (approximated) if bad,
    else hold to T+2 close."""
    code = pos["code"]
    kdf = kline_dict.get(code)
    if kdf is None or kdf.empty:
        return None

    dates = kdf["date"].astype(str).str[:10]
    cd = str(current_date)[:10]
    t1_date = pos.get("t1_date", "")
    t2_date = pos.get("t2_date", "")

    if cd == t1_date:
        # Approximate 14:00 price
        t1_open = pos.get("t1_open")
        t1_high = pos.get("t1_high")
        t1_low = pos.get("t1_low")
        t1_close = pos.get("t1_close")
        if pd.isna(t1_open) or pd.isna(t1_close):
            return None
        mid = (float(t1_open) + float(t1_close)) / 2
        rng = float(t1_high) - float(t1_low) if pd.notna(t1_high) and pd.notna(t1_low) else 0
        t1_1400 = mid + 0.12 * rng if float(t1_close) > float(t1_open) else mid - 0.12 * rng if float(t1_close) < float(t1_open) else mid

        ret_1400 = net_return(pos["entry_price"], t1_1400, COST_BPS, SLIPPAGE_BPS)
        entry_low = pos.get("entry_low")
        below_t_low = (pd.notna(entry_low) and entry_low and float(t1_1400) < float(entry_low))

        if (ret_1400 is not None and ret_1400 <= -2.0) or below_t_low:
            return {"price": t1_1400, "type": "dec_E_1400_stop", "date": cd}
        return None  # Hold to T+2

    elif cd == t2_date:
        t2_close = pos.get("t2_close")
        if pd.notna(t2_close) and t2_close:
            return {"price": float(t2_close), "type": "dec_E_t2", "date": cd}

    return None


# ══════════════════════════════════════════════════════════════════════════
# Run baseline backtest
# ══════════════════════════════════════════════════════════════════════════
def run_baseline_backtest(factor_df, kline_dict, all_dates, max_positions, position_pct):
    """Run tail-entry d3+ma20_gap baseline."""
    signals_by_date = build_tail_baseline_signals(factor_df, kline_dict)

    sim = PullbackPortfolioSimulator(INITIAL_CASH, max_positions, position_pct)

    # Pre-load execution prices for baseline picks
    # Build picks_by_date with required fields for tail-entry positions
    picks_by_date = {}
    for d, sigs in signals_by_date.items():
        enriched = []
        for s in sigs:
            # Find matching row in factor_df with execution prices
            code = s["code"]
            matches = factor_df[(factor_df["code"] == code) & (factor_df["date"].astype(str).str[:10] == d)]
            if matches.empty:
                continue
            row = matches.iloc[0].to_dict()
            row["signal_score"] = s.get("d3_ma20_gap_score", 0)
            # For tail-entry, entry is at T close
            row["entry_price"] = row.get("entry_close")
            enriched.append(row)
        if enriched:
            picks_by_date[d] = enriched

    # Run using tail-entry exit logic manually
    sim.positions = []
    sim.closed_trades = []
    sim.equity_curve = []
    sim.cash = float(INITIAL_CASH)

    for d in picks_by_date:
        picks_by_date[d].sort(key=lambda x: x.get("signal_score", 0), reverse=True)

    for date in all_dates:
        cd = str(date)[:10]

        # Exits
        surviving = []
        for pos in sim.positions:
            exit_info = get_tail_exit(pos, cd, kline_dict)
            if exit_info:
                sim._close_position(pos, exit_info["price"], cd, exit_info["type"])
            else:
                surviving.append(pos)
        sim.positions = surviving

        # Entries
        available = max_positions - len(sim.positions)
        if available > 0 and cd in picks_by_date:
            held_codes = {p["code"] for p in sim.positions}
            for sig in picks_by_date[cd]:
                if available <= 0:
                    break
                if sig["code"] in held_codes:
                    continue
                entry_px = sig.get("entry_close")
                if pd.isna(entry_px) or not entry_px:
                    continue
                # Add T+1/T+2 for exit logic
                sig["t1_date"] = sig.get("t1_date", "")
                sig["t2_date"] = sig.get("t2_date", "")
                sig["t1_open"] = sig.get("t1_open")
                sig["t1_high"] = sig.get("t1_high")
                sig["t1_low"] = sig.get("t1_low")
                sig["t1_close"] = sig.get("t1_close")
                sig["t2_close"] = sig.get("t2_close")
                sig["entry_low"] = sig.get("entry_low")
                if sim._open_position(sig, cd, entry_px, "t_close"):
                    available -= 1

        eq = sim._total_equity(kline_dict)
        sim.equity_curve.append({"date": cd, "equity": round(eq, 2), "cash": round(sim.cash, 2),
                                 "positions": len(sim.positions)})

    return sim


# ══════════════════════════════════════════════════════════════════════════
# Running config grid
# ══════════════════════════════════════════════════════════════════════════
TREND_POOLS = [
    "trend_pool_rank_d3_ma20gap_d3_ge_8_ret20_ge_0",
    "trend_pool_ma60_ma20_structure_d3_ge_8",
    "trend_pool_top20pct_d3_ma20gap",
]

PULLBACK_CONDITIONS = [
    "near_ma20",
    "shallow_pullback",
    "touch_reclaim_ma20",
    "shrink_pullback",
    "no_chase",
    "lower_shadow_reclaim",
]

CONFIRMATION_CONDITIONS = [
    "none",
    "close_above_ma20",
    "close_positive_after_pullback",
    "close_above_prior_high",
    "volume_reexpand",
    "hammer_or_lower_shadow",
]

ENTRY_MODES = ["t_close_optimistic", "t1_open_realistic"]
EXIT_RULES = ["hold_3d_close", "hold_5d_close", "hold_8d_close",
              "ma20_or_pullback_low_break_then_hold5"]


def build_config_name(trend, pb, conf, entry, exit_, window, pp, mp):
    """Build compact config name."""
    parts = {
        "trend_pool_rank_d3_ma20gap_d3_ge_8_ret20_ge_0": "TP_RANK",
        "trend_pool_ma60_ma20_structure_d3_ge_8": "TP_MA",
        "trend_pool_top20pct_d3_ma20gap": "TP_TOP20",
    }
    return (f"{parts.get(trend, trend[:8])}|{pb}|{conf}|{entry}|{exit_}"
            f"|w{window}|pp{int(pp*100)}|mp{mp}")


# ══════════════════════════════════════════════════════════════════════════
# Main execution
# ══════════════════════════════════════════════════════════════════════════
def main():
    started = datetime.now()
    print("=" * 78)
    print("回踩确认策略回测 — Pullback Confirmation Backtest")
    print("=" * 78)

    # ── 1. Data preparation ──
    print("\n[1] 数据准备")
    max_days = max(WINDOWS) + 10  # Extra buffer for execution prices
    df, cfg, kline_dict, codes = build_full_factor_table(max_days)

    # Build trading calendar
    all_trading_dates_set = set()
    for kdf in kline_dict.values():
        if kdf is not None and not kdf.empty:
            for d in kdf["date"].astype(str).str[:10]:
                all_trading_dates_set.add(d)
    all_dates_full = sorted(all_trading_dates_set)

    # Build point-in-time context
    print("[2] 构建K线上下文（逐股逐日）")
    context = build_date_kline_context(kline_dict)

    # ── 3. Run config grid ──
    all_results = []

    # Count total configs
    total_configs = (len(TREND_POOLS) * len(PULLBACK_CONDITIONS) * len(CONFIRMATION_CONDITIONS)
                     * len(ENTRY_MODES) * len(EXIT_RULES) * len(WINDOWS)
                     * len(POSITION_PCT_LIST) * len(MAX_POSITIONS_LIST))
    print(f"\n[3] 运行配置网格 (最多 {total_configs} 个组合)\n")

    config_count = 0

    for window_days in WINDOWS:
        # Truncate factor_df to window
        all_factor_dates = sorted(df["date"].astype(str).str[:10].unique())
        window_start_idx = max(0, len(all_factor_dates) - window_days - 5)
        window_dates = set(all_factor_dates[window_start_idx:window_start_idx + window_days + 5])
        window_df = df[df["date"].astype(str).str[:10].isin(window_dates)]

        # Build baseline for this window
        print(f"  窗口 {window_days}d: 运行 tail-entry d3+ma20_gap 基线...")

        for mp in MAX_POSITIONS_LIST:
            for pp in POSITION_PCT_LIST:
                baseline = run_baseline_backtest(
                    window_df, kline_dict, all_dates_full, mp, pp)
                baseline_metrics = baseline.metrics(window_days)
                baseline_metrics["config_name"] = "BASELINE_tail_d3_ma20_gap_dec_E"
                baseline_metrics["config_type"] = "baseline"
                all_results.append(baseline_metrics)
                print(f"    基线 mp{mp} pp{int(pp*100)}: "
                      f"ret={baseline_metrics['total_return']:+.2f}% "
                      f"dd={baseline_metrics['max_drawdown']:.2f}% "
                      f"r/dd={baseline_metrics['return_to_drawdown']:.2f} "
                      f"trades={baseline_metrics['trade_count']}")

        # Run pullback configs (sample grid to avoid combinatorial explosion)
        for trend in TREND_POOLS:
            for pb in PULLBACK_CONDITIONS:
                # Sample key confirmation conditions
                for conf in ["none", "close_above_ma20", "close_positive_after_pullback"]:
                    for entry_mode in ENTRY_MODES:
                        for exit_rule in EXIT_RULES:
                            for mp in MAX_POSITIONS_LIST:
                                for pp in POSITION_PCT_LIST:
                                    config_count += 1
                                    if config_count % 20 == 0:
                                        print(f"    进度: {config_count}...")

                                    signals = build_pullback_signals(
                                        window_df, context, trend, pb, conf)

                                    if signals.empty:
                                        continue

                                    # Build signals_by_date
                                    signals_by_date = defaultdict(list)
                                    for _, row in signals.iterrows():
                                        d = str(row["date"])[:10]
                                        signals_by_date[d].append(row.to_dict())

                                    sim = PullbackPortfolioSimulator(
                                        INITIAL_CASH, mp, pp)
                                    sim.run(signals_by_date, all_dates_full,
                                            exit_rule, kline_dict, context,
                                            entry_mode=entry_mode)

                                    m = sim.metrics(window_days)
                                    m["config_name"] = build_config_name(
                                        trend, pb, conf, entry_mode, exit_rule,
                                        window_days, pp, mp)
                                    m["config_type"] = "pullback"
                                    m["trend_pool"] = trend
                                    m["pullback_rule"] = pb
                                    m["confirmation_rule"] = conf
                                    m["entry_mode"] = entry_mode
                                    m["exit_rule"] = exit_rule
                                    m["window_days"] = window_days
                                    m["position_pct"] = pp
                                    m["max_positions"] = mp

                                    # Compare against baseline
                                    bl = [r for r in all_results
                                          if r.get("config_type") == "baseline"
                                          and r.get("window_days") == window_days
                                          and r.get("max_positions", mp) == mp
                                          and abs(r.get("position_pct", pp) - pp) < 0.001]
                                    if bl:
                                        bl_m = bl[0]
                                        m["baseline_return"] = bl_m.get("total_return", 0)
                                        m["baseline_dd"] = bl_m.get("max_drawdown", 0)
                                        m["baseline_rdd"] = bl_m.get("return_to_drawdown", 0)
                                        m["dd_vs_baseline"] = round(
                                            m["max_drawdown"] - bl_m.get("max_drawdown", 0), 2)
                                        m["return_vs_baseline"] = round(
                                            m["total_return"] - bl_m.get("total_return", 0), 2)
                                        m["trade_count_ratio_vs_tail_baseline"] = round(
                                            m["trade_count"] / max(1, bl_m.get("trade_count", 1)), 2)

                                    all_results.append(m)

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\n  总计评估 {len(all_results)} 个配置, 耗时 {elapsed:.0f}s")

    # ── 4. Rank and filter results ──
    pullback_results = [r for r in all_results if r.get("config_type") == "pullback"]
    baseline_results = [r for r in all_results if r.get("config_type") == "baseline"]

    # Filter: minimum trade count
    pullback_results = [r for r in pullback_results if r.get("trade_count", 0) >= 20]

    # Sort by: realistic entry first, then by DD
    realistic = [r for r in pullback_results if r.get("entry_mode") == "t1_open_realistic"]
    optimistic = [r for r in pullback_results if r.get("entry_mode") == "t_close_optimistic"]

    # Rank: target is DD <= -18%, PF > 1.4, positive return
    def rank_score(r):
        """Lower is better. Penalize poor metrics."""
        dd = abs(r.get("max_drawdown", -100))
        ret = r.get("total_return", 0)
        pf = r.get("profit_factor", 0)
        trades = r.get("trade_count", 0)

        # Bonus for meeting targets
        dd_target_met = 1 if dd <= 18 else 0
        pf_target_met = 1 if pf > 1.4 else 0
        ret_target_met = 1 if ret >= 8 else 0

        # Score = dd (lower better) - bonus for targets
        score = dd - (dd_target_met * 5 + pf_target_met * 3 + ret_target_met * 3)
        return score

    realistic.sort(key=rank_score)
    optimistic.sort(key=rank_score)

    top_realistic = realistic[:20]
    top_optimistic = optimistic[:20]

    # Also identify common failed variants (high DD, low trades)
    failed = [r for r in pullback_results
              if r.get("max_drawdown", 0) < -30 or r.get("trade_count", 0) < 10]
    failed.sort(key=lambda r: r.get("max_drawdown", 0))

    # ── 5. Output ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON result
    result = {
        "id": "pullback_confirmation_001",
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "completed_by": "claude_code",
        "summary": "",  # Filled below
        "config_counts": {
            "total": len(all_results),
            "baseline": len(baseline_results),
            "pullback_total": len(pullback_results),
            "realistic_entry": len(realistic),
            "optimistic_entry": len(optimistic),
        },
        "top_20_realistic": top_realistic,
        "top_20_optimistic": top_optimistic,
        "rejected_failed_variants": failed[:20],
        "baseline_summary": {},
        "answers": {},
        "files_generated": [],
    }

    # Best baseline summary
    if baseline_results:
        best_bl = min(baseline_results, key=lambda r: abs(r.get("max_drawdown", -100)))
        result["baseline_summary"] = {
            "best_dd_config": best_bl.get("config_name", ""),
            "120d_pp20_dd": best_bl.get("max_drawdown", 0),
            "120d_pp20_return": best_bl.get("total_return", 0),
            "120d_pp20_rdd": best_bl.get("return_to_drawdown", 0),
            "120d_pp20_pf": best_bl.get("profit_factor", 0),
        }

    # Best pullback config (realistic entry)
    if top_realistic:
        best = top_realistic[0]
        dd_improvement = best.get("dd_vs_baseline", 0)
        result["summary"] = (
            f"回踩确认回测完成。{len(all_results)}个配置中，最佳现实入场(T+1 open)配置: "
            f"{best['config_name']}, 收益={best['total_return']:+.2f}%, "
            f"DD={best['max_drawdown']:.2f}%, r/dd={best['return_to_drawdown']:.2f}, "
            f"PF={best['profit_factor']:.2f}, trades={best['trade_count']}, "
            f"DD改善={dd_improvement:+.2f}pp vs 尾盘基线."
        )

        # Answer key questions
        target_met = any(
            r.get("max_drawdown", -100) >= -18
            and r.get("profit_factor", 0) > 1.4
            and r.get("total_return", 0) >= 8
            and r.get("trade_count", 0) >= 50
            for r in top_realistic
        )
        result["answers"]["q1_target_met"] = target_met

        dd_reduction = best.get("dd_vs_baseline", 0)
        result["answers"]["q2_dd_material_reduction"] = dd_reduction > 3.0

        # Flag best realistic
        result["best_realistic"] = best
    else:
        result["summary"] = "无有效回踩确认配置。"

    # Write JSON
    json_path = os.path.join(ROOT, "reports", f"pullback_confirmation_{timestamp}.json")
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    result["files_generated"].append(json_path)
    print(f"\nJSON 报告: {json_path}")

    # Write Markdown summary
    md_path = os.path.join(ROOT, "reports", f"pullback_confirmation_summary_{timestamp}.md")
    write_summary_md(result, md_path)
    result["files_generated"].append(md_path)
    print(f"MD 摘要: {md_path}")

    # Write queue result
    qr_path = os.path.join(ROOT, "backtest_queue", "done", "pullback_confirmation_001_result.json")
    os.makedirs(os.path.dirname(qr_path), exist_ok=True)
    with open(qr_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"队列结果: {qr_path}")

    print(f"\n{'=' * 78}")
    print(f"回测完成。总耗时 {elapsed:.0f}s, {len(all_results)} 个配置")
    print(f"最佳现实入场配置: {result.get('best_realistic', {}).get('config_name', 'N/A')}")
    print(f"DD改善: {result.get('best_realistic', {}).get('dd_vs_baseline', 0):+.2f}pp")
    print(f"{'=' * 78}")


def write_summary_md(result, path):
    """Write detailed Markdown summary."""
    lines = []
    lines.append("# 回踩确认策略回测报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().isoformat()}")
    lines.append(f"**任务ID**: pullback_confirmation_001")
    lines.append("")
    lines.append("## 摘要")
    lines.append("")
    lines.append(result.get("summary", ""))
    lines.append("")

    # Baseline
    lines.append("## 尾盘基线 (d3+ma20_gap + dec_E)")
    lines.append("")
    bl = result.get("baseline_summary", {})
    lines.append(f"- 120d pp20 DD: {bl.get('120d_pp20_dd', 'N/A')}%")
    lines.append(f"- 120d pp20 收益: {bl.get('120d_pp20_return', 'N/A')}%")
    lines.append(f"- 120d pp20 r/dd: {bl.get('120d_pp20_rdd', 'N/A')}")
    lines.append("")

    # Top realistic configs
    lines.append("## Top 20 现实入场配置 (T+1 Open)")
    lines.append("")
    lines.append("| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易数 | DD改善 |")
    lines.append("|------|-------|------|------|----|-------|--------|--------|")
    for r in result.get("top_20_realistic", [])[:20]:
        lines.append(f"| {r.get('config_name', '')[:60]} "
                     f"| {r.get('total_return', 0):+.1f} "
                     f"| {r.get('max_drawdown', 0):.1f} "
                     f"| {r.get('return_to_drawdown', 0):.2f} "
                     f"| {r.get('profit_factor', 0):.2f} "
                     f"| {r.get('win_rate', 0):.1f} "
                     f"| {r.get('trade_count', 0)} "
                     f"| {r.get('dd_vs_baseline', 0):+.1f} |")
    lines.append("")

    # Best realistic detail
    best = result.get("best_realistic", {})
    if best:
        lines.append("## 最佳现实入场配置详情")
        lines.append("")
        lines.append(f"- **配置**: {best.get('config_name', '')}")
        lines.append(f"- 收益: {best.get('total_return', 0):+.2f}%")
        lines.append(f"- 最大回撤: {best.get('max_drawdown', 0):.2f}%")
        lines.append(f"- r/dd: {best.get('return_to_drawdown', 0):.2f}")
        lines.append(f"- PF: {best.get('profit_factor', 0):.2f}")
        lines.append(f"- 胜率: {best.get('win_rate', 0):.1f}%")
        lines.append(f"- 交易数: {best.get('trade_count', 0)}")
        lines.append(f"- DD改善 vs 基线: {best.get('dd_vs_baseline', 0):+.2f}pp")
        lines.append(f"- 最差交易: {best.get('worst_trade', 0):.2f}%")
        lines.append(f"- 最佳交易: {best.get('best_trade', 0):.2f}%")
        lines.append("")

    # Answers
    lines.append("## 关键问题回答")
    lines.append("")
    answers = result.get("answers", {})
    lines.append(f"- 目标达成 (DD≤-18%, PF>1.4, ret≥8%, trades≥50): {'✅' if answers.get('q1_target_met') else '❌'}")
    lines.append(f"- DD显著改善 (>3pp): {'✅' if answers.get('q2_dd_material_reduction') else '❌'}")
    lines.append("")

    # Rejected variants
    lines.append("## 常见失败变体 (Top 10)")
    lines.append("")
    lines.append("| 配置 | DD% | 收益% | 交易数 |")
    lines.append("|------|------|-------|--------|")
    for r in result.get("rejected_failed_variants", [])[:10]:
        lines.append(f"| {r.get('config_name', '')[:60]} "
                     f"| {r.get('max_drawdown', 0):.1f} "
                     f"| {r.get('total_return', 0):+.1f} "
                     f"| {r.get('trade_count', 0)} |")
    lines.append("")

    # Files
    lines.append("## 生成文件")
    for f in result.get("files_generated", []):
        lines.append(f"- `{f}`")
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
