"""Stop-loss & risk-control backtest for tail-entry elastic_base strategy.

Tests single-trade stops, ATR adaptive stops, shorter holding, and portfolio-level
risk controls on top of the fixed execution framework (dec_E + mp2).

Fixed: elastic_base + dec_E + max_positions=2.  Tests pp=15% and pp=20%.
Windows: 90 and 120 trading days.  kline_count=600 (reuses coverage fix from R6).

Usage:
  python run_tail_stop_risk_control.py
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

from engine.cache_manager import load_csi300_codes                               # noqa: E402
from run_factor_research import build_factor_table, fetch_klines, zscore_series  # noqa: E402
from run_tail_entry_backtest import attach_execution_prices, net_return           # noqa: E402
from run_tail_portfolio_backtest import _approx_1400                               # noqa: E402

# ══════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════
INITIAL_CASH = 100_000
MAX_POSITIONS = 2
POSITION_PCT_LIST = [0.15, 0.20]
TOP = 60
SELECT = 5
THREADS = 8
KLINE_COUNT = 600
COST_BPS = 5.0
SLIPPAGE_BPS = 10.0

WINDOWS = [90, 120]

# ══════════════════════════════════════════════════════════════════════════
# Risk rule definitions
# ══════════════════════════════════════════════════════════════════════════
# Each rule has a 'type' that determines how it modifies the simulator.
#
# Types:
#   baseline           — original dec_E, no changes
#   pct_stop           — add per-trade % stop at 14:00 (overrides dec_E threshold)
#   t_low_stop         — pure T-day low break stop (dec_E without the -2% part)
#   pct_low_combo      — % stop OR T-day low break stop
#   open_stop          — stop at T+1 open if return <= threshold
#   atr_stop           — stop at 14:00 if price < entry * (1 - k * atr_pct/100)
#   short_hold         — modify holding period
#   portfolio_pause    — portfolio-level pause on loss streak or DD
#   combo              — single-trade stop + portfolio pause

RISK_RULES = {
    # ── A. Baseline ──
    "baseline_dec_e": {
        "type": "baseline",
        "group": "baseline",
        "desc": "Original dec_E: 14:00 <= -2% OR < T low -> 14:00; else T+2",
    },

    # ── B. Single-trade percent stops at 14:00 ──
    "pct14_stop_1.0": {
        "type": "pct_stop",
        "group": "single_trade_pct_stop",
        "stop_14_pct": -1.0,
        "desc": "14:00 ret <= -1.0% -> stop at 14:00; else -> T+2",
    },
    "pct14_stop_1.5": {
        "type": "pct_stop",
        "group": "single_trade_pct_stop",
        "stop_14_pct": -1.5,
        "desc": "14:00 ret <= -1.5% -> stop at 14:00; else -> T+2",
    },
    "pct14_stop_2.0": {
        "type": "pct_stop",
        "group": "single_trade_pct_stop",
        "stop_14_pct": -2.0,
        "desc": "14:00 ret <= -2.0% -> stop at 14:00; else -> T+2",
    },
    "pct14_stop_3.0": {
        "type": "pct_stop",
        "group": "single_trade_pct_stop",
        "stop_14_pct": -3.0,
        "desc": "14:00 ret <= -3.0% -> stop at 14:00; else -> T+2",
    },

    # ── C. T-day low break stop (no % condition) ──
    "t_low_stop_only": {
        "type": "t_low_stop",
        "group": "t_day_low_break_stop",
        "desc": "14:00 < T low -> stop at 14:00; else -> T+2 (no % condition)",
    },

    # ── D. Combined: % stop OR T-day low break ──
    "pct1.5_or_low": {
        "type": "pct_low_combo",
        "group": "t_day_low_break_stop",
        "stop_14_pct": -1.5,
        "use_low_break": True,
        "desc": "14:00 <= -1.5% OR < T low -> stop; else -> T+2",
    },
    "pct2.0_or_low": {
        "type": "pct_low_combo",
        "group": "t_day_low_break_stop",
        "stop_14_pct": -2.0,
        "use_low_break": True,
        "desc": "14:00 <= -2.0% OR < T low -> stop; else -> T+2 (same as dec_E)",
    },

    # ── E. T+1 open stops ──
    "open_stop_1.0": {
        "type": "open_stop",
        "group": "single_trade_pct_stop",
        "open_stop_pct": -1.0,
        "desc": "T+1 open ret <= -1.0% -> sell at open; else -> dec_E (14:00 check + T+2)",
    },
    "open_stop_1.5": {
        "type": "open_stop",
        "group": "single_trade_pct_stop",
        "open_stop_pct": -1.5,
        "desc": "T+1 open ret <= -1.5% -> sell at open; else -> dec_E",
    },
    "open_stop_2.0": {
        "type": "open_stop",
        "group": "single_trade_pct_stop",
        "open_stop_pct": -2.0,
        "desc": "T+1 open ret <= -2.0% -> sell at open; else -> dec_E",
    },

    # ── F. ATR adaptive stops ──
    "atr_stop_0.5": {
        "type": "atr_stop",
        "group": "atr_adaptive_stop",
        "atr_k": 0.5,
        "desc": "14:00 price < entry * (1 - 0.5*ATR%) -> stop at 14:00; else -> T+2",
    },
    "atr_stop_0.8": {
        "type": "atr_stop",
        "group": "atr_adaptive_stop",
        "atr_k": 0.8,
        "desc": "14:00 price < entry * (1 - 0.8*ATR%) -> stop at 14:00; else -> T+2",
    },
    "atr_stop_1.0": {
        "type": "atr_stop",
        "group": "atr_adaptive_stop",
        "atr_k": 1.0,
        "desc": "14:00 price < entry * (1 - 1.0*ATR%) -> stop at 14:00; else -> T+2",
    },

    # ── G. Shorter holding ──
    "t1_close_only": {
        "type": "short_hold",
        "group": "shorter_holding_time",
        "hold_mode": "t1_close",
        "desc": "Always exit at T+1 close (skip T+2 entirely)",
    },
    "t2_only_if_strong": {
        "type": "short_hold",
        "group": "shorter_holding_time",
        "hold_mode": "t2_if_strong",
        "desc": "T+2 only if T+1 close > 0 AND T+1 14:00 >= T low; else exit T+1 close",
    },
    "t1_if_lose_t2_if_win": {
        "type": "short_hold",
        "group": "shorter_holding_time",
        "hold_mode": "t1_if_lose",
        "desc": "T+1 close <= 0 -> exit T+1 close; else dec_E (hold to T+2)",
    },

    # ── H. Portfolio loss-streak pause ──
    "streak2_pause2": {
        "type": "portfolio_pause",
        "group": "loss_streak_pause",
        "pause_mode": "streak",
        "streak_n": 2,
        "pause_days": 2,
        "desc": "连续2笔亏损 → 暂停开仓2天",
    },
    "streak2_pause3": {
        "type": "portfolio_pause",
        "group": "loss_streak_pause",
        "pause_mode": "streak",
        "streak_n": 2,
        "pause_days": 3,
        "desc": "连续2笔亏损 → 暂停开仓3天",
    },
    "streak3_pause3": {
        "type": "portfolio_pause",
        "group": "loss_streak_pause",
        "pause_mode": "streak",
        "streak_n": 3,
        "pause_days": 3,
        "desc": "连续3笔亏损 → 暂停开仓3天",
    },
    "streak3_pause5": {
        "type": "portfolio_pause",
        "group": "loss_streak_pause",
        "pause_mode": "streak",
        "streak_n": 3,
        "pause_days": 5,
        "desc": "连续3笔亏损 → 暂停开仓5天",
    },

    # ── I. Portfolio drawdown pause ──
    "dd5_pause3": {
        "type": "portfolio_pause",
        "group": "portfolio_drawdown_kill_switch",
        "pause_mode": "drawdown",
        "dd_threshold": -5.0,
        "pause_days": 3,
        "desc": "组合回撤 > 5% → 暂停开仓3天",
    },
    "dd8_pause5": {
        "type": "portfolio_pause",
        "group": "portfolio_drawdown_kill_switch",
        "pause_mode": "drawdown",
        "dd_threshold": -8.0,
        "pause_days": 5,
        "desc": "组合回撤 > 8% → 暂停开仓5天",
    },
    "dd8_pause3": {
        "type": "portfolio_pause",
        "group": "portfolio_drawdown_kill_switch",
        "pause_mode": "drawdown",
        "dd_threshold": -8.0,
        "pause_days": 3,
        "desc": "组合回撤 > 8% → 暂停开仓3天",
    },

    # ── J. Combined: best single-trade stop + portfolio control ──
    "pct1.5_streak2_p2": {
        "type": "combo",
        "group": "loss_streak_pause",
        "stop_14_pct": -1.5,
        "pause_mode": "streak",
        "streak_n": 2,
        "pause_days": 2,
        "desc": "14:00 <= -1.5% stop + 连亏2笔暂停2天",
    },
    "pct1.5_dd8_p3": {
        "type": "combo",
        "group": "portfolio_drawdown_kill_switch",
        "stop_14_pct": -1.5,
        "pause_mode": "drawdown",
        "dd_threshold": -8.0,
        "pause_days": 3,
        "desc": "14:00 <= -1.5% stop + 组合回撤>8%暂停3天",
    },
    "atr0.8_streak2_p2": {
        "type": "combo",
        "group": "loss_streak_pause",
        "atr_k": 0.8,
        "pause_mode": "streak",
        "streak_n": 2,
        "pause_days": 2,
        "desc": "ATR 0.8x stop + 连亏2笔暂停2天",
    },
    "open1.5_dd8_p3": {
        "type": "combo",
        "group": "portfolio_drawdown_kill_switch",
        "open_stop_pct": -1.5,
        "pause_mode": "drawdown",
        "dd_threshold": -8.0,
        "pause_days": 3,
        "desc": "T+1 open <= -1.5% stop + DD>8%暂停3天",
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Data enrichment
# ══════════════════════════════════════════════════════════════════════════
def enrich_factor_df(df, kline_dict):
    """Add per-stock daily change_pct."""
    df = df.copy()
    changes = []
    for _, row in df.iterrows():
        code = row["code"]
        date = str(row["date"])[:10]
        kdf = kline_dict.get(code)
        if kdf is None or kdf.empty:
            changes.append(np.nan); continue
        kdf_dates = kdf["date"].astype(str).str[:10]
        matches = kdf[kdf_dates == date]
        if matches.empty:
            changes.append(np.nan); continue
        idx = int(matches.index[0])
        if idx == 0:
            changes.append(0.0); continue
        prev_close = float(kdf.iloc[idx - 1]["close"])
        curr_close = float(kdf.iloc[idx]["close"])
        changes.append(round((curr_close - prev_close) / prev_close * 100 if prev_close else 0.0, 2))
    df["change_pct"] = changes
    return df


# ══════════════════════════════════════════════════════════════════════════
# Pick builder (elastic_base only, fixed)
# ══════════════════════════════════════════════════════════════════════════
def build_baseline_picks(full_df):
    """Z-score elastic_base on FULL date group, filter, select top-N per day."""
    df = full_df.copy()
    total_before = len(df)

    grouped_full = df.groupby("date", group_keys=False)
    for col in ["atr_pct", "ret_20d", "ma20_gap"]:
        df[f"_z_{col}"] = grouped_full[col].transform(zscore_series).fillna(0)

    df["_score"] = df["_z_atr_pct"] + df["_z_ret_20d"] + df["_z_ma20_gap"]

    df = df[df["limit_move_flag"] == 0]
    df = df[(df["atr_pct"] >= 1.5) & (df["atr_pct"] <= 7.0)]
    df = df[(df["ret_20d"] >= 0.0) & (df["ma20_gap"] >= -5.0)]
    after_base = len(df)

    picks = []
    for date, group in df.groupby("date"):
        if group.empty:
            continue
        top_n = group.nlargest(SELECT, "_score")
        picks.append(top_n)

    if not picks:
        return pd.DataFrame(), {"total_before": total_before, "after_base": after_base, "picks": 0}

    picks_df = pd.concat(picks, ignore_index=True)
    picks_df["t1_1400_price"] = picks_df.apply(_approx_1400, axis=1)

    return picks_df, {"total_before": total_before, "after_base": after_base,
                       "picks": len(picks_df)}


# ══════════════════════════════════════════════════════════════════════════
# Risk-aware get-exit function
# ══════════════════════════════════════════════════════════════════════════
def get_exit_with_risk(pos, pick_row, current_date, risk_config):
    """Check exit for a position under risk rule.

    Returns dict or None, just like get_exit_for_rule.

    risk_config keys used:
      type, stop_14_pct, open_stop_pct, atr_k, hold_mode, use_low_break
    """
    entry = pos.get("entry_price")
    entry_low = pos.get("entry_low")
    entry_atr_pct = pos.get("entry_atr_pct", 5.0)  # from pick data
    t1_date = str(pos.get("t1_date", ""))[:10]
    t2_date = str(pos.get("t2_date", ""))[:10]
    t1_close = pos.get("t1_close")
    t2_close = pos.get("t2_close")
    t1_open = pos.get("t1_open")
    t1_1400 = pos.get("t1_1400_price")
    has_open_stopped = pos.get("_open_stopped", False)

    if pd.isna(entry) or not entry:
        return None

    cd = str(current_date)[:10]
    rule_type = risk_config.get("type", "baseline")

    # ── T+1 open stop (checked at T+1 date, using open price) ──
    if rule_type == "open_stop" and cd == t1_date and not has_open_stopped:
        open_threshold = risk_config.get("open_stop_pct", -2.0)
        if pd.notna(t1_open) and t1_open:
            ret_open = net_return(entry, t1_open, COST_BPS, SLIPPAGE_BPS)
            if ret_open is not None and ret_open <= open_threshold:
                pos["_open_stopped"] = True
                return {"price": float(t1_open), "type": "open_stop", "date": cd}

    # ── Handle short_hold type (different holding logic) ──
    if rule_type == "short_hold":
        hold_mode = risk_config.get("hold_mode", "t1_close")
        if hold_mode == "t1_close":
            # Always exit at T+1 close
            if cd == t1_date and pd.notna(t1_close) and t1_close:
                return {"price": float(t1_close), "type": "t1_close", "date": cd}
            return None

        if hold_mode == "t2_if_strong":
            if cd == t1_date:
                if pd.notna(t1_1400) and t1_1400:
                    ret_1400 = net_return(entry, t1_1400, COST_BPS, SLIPPAGE_BPS)
                    below_low = (pd.notna(entry_low) and entry_low
                                 and float(t1_1400) < float(entry_low))
                    if (ret_1400 is not None and ret_1400 <= -2.0) or below_low:
                        return {"price": float(t1_1400), "type": "dec_E_1400_stop", "date": cd}
                if pd.notna(t1_close) and t1_close:
                    ret_t1 = net_return(entry, t1_close, COST_BPS, SLIPPAGE_BPS)
                    if ret_t1 is not None and ret_t1 <= 0:
                        return {"price": float(t1_close), "type": "t1_close_unprofitable", "date": cd}
                    # else: hold to T+2 (will be caught below)
            elif cd == t2_date:
                if pd.notna(t2_close) and t2_close:
                    return {"price": float(t2_close), "type": "dec_E_t2", "date": cd}
            return None

        if hold_mode == "t1_if_lose":
            if cd == t1_date:
                if pd.notna(t1_1400) and t1_1400:
                    ret_1400 = net_return(entry, t1_1400, COST_BPS, SLIPPAGE_BPS)
                    below_low = (pd.notna(entry_low) and entry_low
                                 and float(t1_1400) < float(entry_low))
                    if (ret_1400 is not None and ret_1400 <= -2.0) or below_low:
                        return {"price": float(t1_1400), "type": "dec_E_1400_stop", "date": cd}
                if pd.notna(t1_close) and t1_close:
                    ret_t1 = net_return(entry, t1_close, COST_BPS, SLIPPAGE_BPS)
                    if ret_t1 is not None and ret_t1 <= 0:
                        return {"price": float(t1_close), "type": "t1_close_unprofitable", "date": cd}
                    # Profitable T+1 → hold to T+2
            elif cd == t2_date:
                if pd.notna(t2_close) and t2_close:
                    return {"price": float(t2_close), "type": "dec_E_t2", "date": cd}
            return None

    # ── All other types: check on T+1 date ──
    if cd != t1_date:
        # Check T+2 for non-open-stop types
        if cd == t2_date:
            if rule_type in ("pct_stop", "t_low_stop", "pct_low_combo", "atr_stop"):
                if pd.notna(t2_close) and t2_close:
                    return {"price": float(t2_close), "type": "dec_E_t2", "date": cd}
            elif rule_type == "open_stop":
                if pd.notna(t2_close) and t2_close:
                    return {"price": float(t2_close), "type": "dec_E_t2", "date": cd}
            elif rule_type in ("baseline", "portfolio_pause", "combo"):
                if pd.notna(t2_close) and t2_close:
                    return {"price": float(t2_close), "type": "dec_E_t2", "date": cd}
        return None

    # ── On T+1 date, apply stop logic ──
    if pd.isna(t1_1400) or not t1_1400:
        return None

    ret_1400 = net_return(entry, t1_1400, COST_BPS, SLIPPAGE_BPS)
    if ret_1400 is None:
        return None

    below_t_low = (pd.notna(entry_low) and entry_low
                   and float(t1_1400) < float(entry_low))

    # -- baseline dec_E --
    if rule_type == "baseline":
        if ret_1400 <= -2.0 or below_t_low:
            return {"price": float(t1_1400), "type": "dec_E_1400_stop", "date": cd}
        return None  # Will be caught on T+2

    # -- pct_stop --
    if rule_type == "pct_stop":
        threshold = risk_config.get("stop_14_pct", -2.0)
        if ret_1400 <= threshold:
            return {"price": float(t1_1400), "type": f"pct_stop_{abs(threshold)}", "date": cd}
        return None

    # -- t_low_stop --
    if rule_type == "t_low_stop":
        if below_t_low:
            return {"price": float(t1_1400), "type": "t_low_stop", "date": cd}
        return None

    # -- pct_low_combo --
    if rule_type == "pct_low_combo":
        threshold = risk_config.get("stop_14_pct", -2.0)
        use_low = risk_config.get("use_low_break", True)
        triggered = ret_1400 <= threshold
        if use_low and below_t_low:
            triggered = True
        if triggered:
            return {"price": float(t1_1400), "type": f"stop_{abs(threshold)}_or_low", "date": cd}
        return None

    # -- atr_stop --
    if rule_type == "atr_stop":
        k = risk_config.get("atr_k", 0.8)
        atr_stop_price = float(entry) * (1 - k * entry_atr_pct / 100.0)
        if float(t1_1400) < atr_stop_price:
            return {"price": float(t1_1400), "type": f"atr_{k}_stop", "date": cd}
        return None

    # -- portfolio_pause / combo (same single-trade exit as pct_stop with -1.5 or atr) --
    if rule_type in ("portfolio_pause", "combo"):
        # Single-trade stop logic
        stop_14_pct = risk_config.get("stop_14_pct", None)
        atr_k = risk_config.get("atr_k", None)
        open_stop_pct = risk_config.get("open_stop_pct", None)
        stopped = False
        stop_type = ""

        if open_stop_pct is not None:
            # open_stop was already checked above
            pass

        if stop_14_pct is not None:
            if ret_1400 <= stop_14_pct:
                stopped = True
                stop_type = f"pct_{abs(stop_14_pct)}"
        elif atr_k is not None:
            atr_stop_price = float(entry) * (1 - atr_k * entry_atr_pct / 100.0)
            if float(t1_1400) < atr_stop_price:
                stopped = True
                stop_type = f"atr_{atr_k}"
        else:
            # Default to dec_E threshold
            if ret_1400 <= -2.0 or below_t_low:
                stopped = True
                stop_type = "dec_E"

        # Also check low break
        if not stopped and below_t_low and pd.notna(entry_low):
            stopped = True
            stop_type = "low_break"

        if stopped:
            return {"price": float(t1_1400), "type": f"stop_{stop_type}", "date": cd}
        return None

    return None


# ══════════════════════════════════════════════════════════════════════════
# Risk-aware portfolio simulator
# ══════════════════════════════════════════════════════════════════════════
class RiskPortfolioSimulator:
    def __init__(self, initial_cash, max_positions, position_pct,
                 risk_config, cost_bps=COST_BPS, slippage_bps=SLIPPAGE_BPS):
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.max_positions = max_positions
        self.position_pct = position_pct
        self.risk_config = risk_config
        self.cost_bps = cost_bps
        self.slippage_bps = slippage_bps

        self.positions = []
        self.closed_trades = []
        self.equity_curve = []
        self._daily_cash_used = []

        # Portfolio-level state
        self._consecutive_losses = 0
        self._pause_until_date = None
        self._peak_equity = float(initial_cash)
        self._stopped_today = False

    def _total_equity(self, kline_dict):
        mv = 0
        for p in self.positions:
            code = p["code"]
            kdf = kline_dict.get(code)
            if kdf is not None and not kdf.empty:
                mv += p["shares"] * float(kdf.iloc[-1]["close"])
            else:
                mv += p["cost"]
        return self.cash + mv

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
            "was_stopped": "stop" in str(exit_type).lower(),
        })

        # Update loss streak
        if ret_pct <= 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def _open_position(self, pick, date):
        entry_price = float(pick["entry_close"])
        gross_equity = self.cash + sum(p["cost"] for p in self.positions)
        target_value = gross_equity * self.position_pct

        if target_value < entry_price * 100:
            return False
        if self.cash < target_value:
            target_value = self.cash * 0.99

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
            "entry_atr_pct": float(pick.get("atr_pct", 5.0)),
            "t1_date": str(pick.get("t1_date", "")),
            "t2_date": str(pick.get("t2_date", "")),
            "t1_close": pick.get("t1_close"),
            "t2_close": pick.get("t2_close"),
            "t1_open": pick.get("t1_open"),
            "t1_1400_price": pick.get("t1_1400_price"),
            "shares": shares,
            "cost": cost,
            "score": float(pick.get("_score", 0)),
            "_open_stopped": False,
        })
        return True

    def _should_pause_entries(self, date):
        """Check portfolio-level pause conditions."""
        rule_type = self.risk_config.get("type", "baseline")
        pause_mode = self.risk_config.get("pause_mode")

        if rule_type not in ("portfolio_pause", "combo"):
            return False
        if pause_mode is None:
            return False

        # Check if we're in a pause period
        if self._pause_until_date is not None and str(date) <= self._pause_until_date:
            return True

        # Check streak trigger
        if pause_mode == "streak":
            streak_n = self.risk_config.get("streak_n", 2)
            if self._consecutive_losses >= streak_n:
                pause_days = self.risk_config.get("pause_days", 2)
                self._pause_until_date = str(date)
                self._consecutive_losses = 0  # reset counter after triggering
                return True

        # Check drawdown trigger
        if pause_mode == "drawdown":
            dd_threshold = self.risk_config.get("dd_threshold", -5.0)
            current_eq = self._total_equity({})
            current_dd = (current_eq / self._peak_equity - 1) * 100
            if current_dd <= dd_threshold:  # more negative than threshold
                pause_days = self.risk_config.get("pause_days", 3)
                self._pause_until_date = str(date)
                return True

        return False

    def run(self, picks_by_date, all_dates, kline_dict):
        for d in picks_by_date:
            picks_by_date[d].sort(key=lambda x: x.get("score", 0), reverse=True)

        prev_pause_until = None
        for i, date in enumerate(all_dates):
            # ── 1. Process exits ──
            self._stopped_today = False
            surviving = []
            for pos in self.positions:
                exit_info = get_exit_with_risk(pos, pos, date, self.risk_config)
                if exit_info:
                    hold_days = (pd.to_datetime(date) - pd.to_datetime(pos["entry_date"])).days
                    pos["hold_days"] = max(hold_days, 1)
                    self._sell_position(pos, exit_info["price"], date, exit_info["type"])
                    if pos.get("_open_stopped") or "stop" in str(exit_info.get("type", "")).lower():
                        self._stopped_today = True
                else:
                    surviving.append(pos)
            self.positions = surviving

            # ── 2. Update peak equity ──
            eq_now = self._total_equity(kline_dict)
            self._peak_equity = max(self._peak_equity, eq_now)

            # ── 3. Check portfolio pause ──
            should_pause = self._should_pause_entries(date)

            # ── 4. Fill empty slots if not paused ──
            if not should_pause:
                available = self.max_positions - len(self.positions)
                if available > 0 and date in picks_by_date:
                    candidates = picks_by_date[date]
                    held_codes = {p["code"] for p in self.positions}
                    for pick in candidates:
                        if available <= 0:
                            break
                        if pick["code"] in held_codes:
                            continue
                        if pd.isna(pick.get("t1_1400_price")) or not pick.get("t1_1400_price"):
                            continue
                        if self._open_position(pick, date):
                            available -= 1
                            held_codes.add(pick["code"])

            # ── 5. Manage pause duration ──
            if self._pause_until_date is not None and str(date) >= self._pause_until_date:
                # Apply the pause: skip entries for pause_days
                # The pause_until_date is set to the trigger date; entries resume after
                # pause_days from trigger
                if should_pause:
                    pause_days = self.risk_config.get("pause_days", 2)
                    # Find the index of the next trading date after pause_days
                    trigger_idx = all_dates.index(date) if date in all_dates else i
                    resume_idx = min(trigger_idx + pause_days, len(all_dates) - 1)
                    self._pause_until_date = all_dates[resume_idx]

            # ── 6. Record daily equity ──
            eq = self._total_equity(kline_dict)
            self.equity_curve.append({
                "date": date,
                "equity": round(eq, 2),
                "cash": round(self.cash, 2),
                "positions": len(self.positions),
                "paused": should_pause,
            })
            self._daily_cash_used.append(eq - self.cash)
            prev_pause_until = self._pause_until_date

        # ── Force-close remaining ──
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

        streak = 0; max_streak = 0
        for r in rets:
            if r <= 0:
                streak += 1; max_streak = max(max_streak, streak)
            else:
                streak = 0

        exposure_days = len([d for d in self.equity_curve if d["positions"] > 0])
        avg_positions = (sum(d["positions"] for d in self.equity_curve) /
                         len(self.equity_curve)) if self.equity_curve else 0
        max_concurrent = max((d["positions"] for d in self.equity_curve), default=0)
        avg_cash_used = (sum(self._daily_cash_used) / len(self._daily_cash_used)
                         / self.initial_cash * 100) if self._daily_cash_used else 0
        final_eq = self.equity_curve[-1]["equity"] if self.equity_curve else self.initial_cash
        peak = self.initial_cash; max_dd = 0.0
        for d in self.equity_curve:
            peak = max(peak, d["equity"])
            dd = d["equity"] / peak - 1
            max_dd = min(max_dd, dd)

        stopped_count = sum(1 for t in trades if t.get("was_stopped", False))
        pause_days = sum(1 for d in self.equity_curve if d.get("paused", False))

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
            "stopped_trade_count": stopped_count,
            "pause_days": pause_days,
            "equity_curve_tail": self.equity_curve[-10:],
        }


# ══════════════════════════════════════════════════════════════════════════
# Portfolio run helper
# ══════════════════════════════════════════════════════════════════════════
def run_portfolio(picks_df, trading_dates, kline_dict, pp, risk_rule):
    picks_by_date = defaultdict(list)
    for _, row in picks_df.iterrows():
        d = str(row["date"])
        picks_by_date[d].append({
            "code": row["code"], "date": d,
            "_score": float(row.get("_score", 0)),
            "entry_close": row["entry_close"],
            "entry_low": row["entry_low"],
            "atr_pct": row.get("atr_pct", 5.0),
            "t1_date": str(row.get("t1_date", "")),
            "t2_date": str(row.get("t2_date", "")),
            "t1_close": row.get("t1_close"),
            "t2_close": row.get("t2_close"),
            "t1_open": row.get("t1_open"),
            "t1_1400_price": row.get("t1_1400_price"),
        })

    sim = RiskPortfolioSimulator(INITIAL_CASH, MAX_POSITIONS, pp, risk_rule)
    sim.run(picks_by_date, trading_dates, kline_dict)
    summ = sim.summary()

    closed = sim.closed_trades
    closed_sorted = sorted(closed, key=lambda t: t["ret_pct"])
    worst_10 = [{"code": t["code"], "entry_date": t["entry_date"],
                 "exit_date": t["exit_date"], "exit_type": t["exit_type"],
                 "ret_pct": round(t["ret_pct"], 2), "was_stopped": t.get("was_stopped", False)}
                for t in closed_sorted[:10]]
    top_10 = sorted(closed, key=lambda t: t["ret_pct"], reverse=True)[:10]
    top_10_out = [{"code": t["code"], "entry_date": t["entry_date"],
                   "ret_pct": round(t["ret_pct"], 2), "exit_type": t["exit_type"]}
                  for t in top_10]

    r_dd = round(abs(summ["total_return"] / summ["max_drawdown"])
                 if summ["max_drawdown"] != 0 else 0, 2)

    return {
        "total_return": summ["total_return"],
        "max_drawdown": summ["max_drawdown"],
        "return_to_drawdown": r_dd,
        "trade_count": summ["trade_count"],
        "win_rate": summ["win_rate"],
        "avg_trade_return": summ["avg_trade_return"],
        "median_trade_return": summ["median_trade_return"],
        "profit_factor": summ["profit_factor"],
        "longest_loss_streak": summ["longest_loss_streak"],
        "worst_trade": summ["worst_trade"],
        "best_trade": summ["best_trade"],
        "worst_10_trades": worst_10,
        "top_10_trades": top_10_out,
        "stopped_trade_count": summ.get("stopped_trade_count", 0),
        "pause_days": summ.get("pause_days", 0),
        "avg_cash_usage": summ.get("avg_cash_usage_pct", 0),
        "max_concurrent_positions": summ.get("max_concurrent_positions", 0),
    }


# ══════════════════════════════════════════════════════════════════════════
# Split helpers
# ══════════════════════════════════════════════════════════════════════════
def split_picks(picks_df, trading_dates):
    all_dates = sorted(picks_df["date"].astype(str).str[:10].unique())
    n = len(all_dates); mid = n // 2
    fd = set(all_dates[:mid]); sd = set(all_dates[mid:])
    return [
        ("full", picks_df, trading_dates),
        ("first_half", picks_df[picks_df["date"].astype(str).str[:10].isin(fd)],
         [d for d in trading_dates if d <= all_dates[mid - 1]]),
        ("second_half", picks_df[picks_df["date"].astype(str).str[:10].isin(sd)],
         [d for d in trading_dates if d >= all_dates[mid]]),
    ]


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
def main():
    started = time.time()

    print("=" * 80)
    print("尾盘高弹性趋势 止损/风控机制回测")
    print(f"规则: {len(RISK_RULES)} 个 | 窗口: {WINDOWS}天 | 仓位: {POSITION_PCT_LIST}")
    print(f"执行: dec_E + mp{MAX_POSITIONS} | kline_count={KLINE_COUNT}")
    print("=" * 80)

    # ── Build data once ──
    max_days = max(WINDOWS)
    print(f"\n[数据] 构建 {max_days}天全量因子表 (kline_count={KLINE_COUNT}) ...")
    codes = load_csi300_codes(os.path.join(ROOT, "data", "csi300_stocks.json"))[:TOP]
    full_df, cfg = build_factor_table(codes, max_days, KLINE_COUNT, THREADS)
    kline_dict = fetch_klines(codes, KLINE_COUNT, THREADS)
    full_df = attach_execution_prices(full_df, kline_dict)
    full_df = full_df.dropna(subset=["entry_close", "t1_open", "t1_close"])
    full_df = enrich_factor_df(full_df, kline_dict)
    print(f"  有效: {len(full_df)} 行, {full_df['date'].nunique()} 个交易日, 区间: {cfg.get('date_range')}")

    all_trading_dates = set()
    for kdf in kline_dict.values():
        if kdf is not None and not kdf.empty:
            for d in kdf["date"].astype(str).str[:10]:
                all_trading_dates.add(d)
    all_dates_full = sorted(all_trading_dates)
    full_entry_dates = sorted(full_df["date"].astype(str).str[:10].unique())
    all_td_full = [d for d in all_dates_full if d >= full_entry_dates[0] and d <=
                   (pd.to_datetime(full_entry_dates[-1]) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")]

    # ── Run ──
    all_results = []
    total_configs = len(WINDOWS) * len(POSITION_PCT_LIST) * len(RISK_RULES) * 3  # *3 splits
    idx = 0

    for window_days in WINDOWS:
        window_entry_dates = (full_entry_dates[-window_days:]
                             if len(full_entry_dates) >= window_days
                             else full_entry_dates)
        actual_days = len(window_entry_dates)
        date_range_str = f"{window_entry_dates[0]} ~ {window_entry_dates[-1]}"
        window_date_set = set(window_entry_dates)
        df_window = full_df[full_df["date"].astype(str).str[:10].isin(window_date_set)].copy()
        td_window = [d for d in all_td_full
                     if d >= window_entry_dates[0]
                     and d <= (pd.to_datetime(window_entry_dates[-1]) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")]

        print(f"\n{'='*60}")
        print(f"[窗口] {window_days}天  ({actual_days} 交易日, {date_range_str})")
        print(f"{'='*60}")

        picks_df, pick_stats = build_baseline_picks(df_window)
        if picks_df.empty:
            print("  [失败] 无选股数据")
            continue

        for rule_name, risk_rule in RISK_RULES.items():
            print(f"\n  [{risk_rule['group']}] {rule_name}: {risk_rule['desc']}")

            splits = split_picks(picks_df, td_window)
            for split_name, sub_picks, sub_td in splits:
                if len(sub_picks) < 5:
                    continue

                for pp in POSITION_PCT_LIST:
                    idx += 1
                    result = run_portfolio(sub_picks, sub_td, kline_dict, pp, risk_rule)
                    entry = {
                        "window_days": window_days,
                        "actual_days": actual_days,
                        "actual_date_range": date_range_str,
                        "rule_name": rule_name,
                        "rule_group": risk_rule["group"],
                        "rule_desc": risk_rule["desc"],
                        "position_pct": pp,
                        "split": split_name,
                    }
                    entry.update(result)
                    all_results.append(entry)

                    # Compact progress
                    if split_name == "full":
                        stopped = result.get("stopped_trade_count", 0)
                        pause = result.get("pause_days", 0)
                        r_dd = result["return_to_drawdown"]
                        print(f"    pp{int(pp*100)}%: trades={result['trade_count']:>3} "
                              f"ret={result['total_return']:>+7.2f}% dd={result['max_drawdown']:>+7.2f}% "
                              f"r/dd={r_dd:.2f} PF={result['profit_factor']} "
                              f"win={result['win_rate']:.1f}% "
                              f"stopped={stopped} pause={pause} | "
                              f"worst={result['worst_trade']:>+6.2f}% best={result['best_trade']:>+6.2f}%")

    # ── Compute deltas vs baseline ──
    print(f"\n{'='*80}")
    print("计算 baseline 差值 ...")
    for r in all_results:
        r["trade_count_ratio_vs_baseline"] = None
        r["avoided_baseline_worst_count"] = None
        r["missed_big_winner_count"] = None

        if r["split"] != "full" or r["rule_name"] == "baseline_dec_e":
            continue

        bl = [b for b in all_results
              if b["rule_name"] == "baseline_dec_e"
              and b["window_days"] == r["window_days"]
              and b["position_pct"] == r["position_pct"]
              and b["split"] == "full"]
        if not bl:
            continue
        bl = bl[0]

        r["trade_count_ratio_vs_baseline"] = round(r["trade_count"] / bl["trade_count"], 2) if bl["trade_count"] > 0 else None
        r["r_dd_vs_baseline"] = round(r["return_to_drawdown"] - bl["return_to_drawdown"], 3)
        r["dd_vs_baseline"] = round(r["max_drawdown"] - bl["max_drawdown"], 2)
        r["ret_vs_baseline"] = round(r["total_return"] - bl["total_return"], 2)

        # Count avoided worst trades
        bl_worst_set = {(t["code"], t["entry_date"]) for t in bl["worst_10_trades"]}
        rf_worst_set = {(t["code"], t["entry_date"]) for t in r["worst_10_trades"]}
        avoided = bl_worst_set - rf_worst_set
        r["avoided_baseline_worst_count"] = len(avoided)

        # Count missed big winners (baseline top 10 that are no longer in rule's top 10 or absent)
        bl_top_set = {(t["code"], t["entry_date"]) for t in bl["top_10_trades"]}
        rf_top_set = {(t["code"], t["entry_date"]) for t in r["top_10_trades"]}
        missed_winners = bl_top_set - rf_top_set
        r["missed_big_winner_count"] = len(missed_winners)

    for r in all_results:
        if r["rule_name"] == "baseline_dec_e":
            r["trade_count_ratio_vs_baseline"] = 1.0
            r["avoided_baseline_worst_count"] = 0
            r["missed_big_winner_count"] = 0
            r["r_dd_vs_baseline"] = 0.0
            r["dd_vs_baseline"] = 0.0
            r["ret_vs_baseline"] = 0.0

    # ── Sort & print top rules ──
    total_elapsed = round(time.time() - started, 1)

    full_rules = [r for r in all_results
                  if r["split"] == "full" and r["position_pct"] == 0.20]
    # Composite score: prioritize dd improvement + maintain r_dd + adequate trades
    bl_120_pp20 = [r for r in full_rules
                   if r["rule_name"] == "baseline_dec_e" and r["window_days"] == 120]
    baseline_dd = bl_120_pp20[0]["max_drawdown"] if bl_120_pp20 else -28.46

    def score_rule(r):
        dd_improvement = r["max_drawdown"] - baseline_dd  # positive = better
        ret_ok = 1 if r["total_return"] >= 8 else 0.5 if r["total_return"] > 0 else 0
        pf_ok = 1 if (r["profit_factor"] or 0) >= 1.3 else 0.5 if (r["profit_factor"] or 0) > 1.0 else 0
        trades_ok = 1 if r.get("trade_count_ratio_vs_baseline", 0) >= 0.6 else 0
        is_baseline = 0 if r["rule_name"] == "baseline_dec_e" else 1
        return (-dd_improvement, -r["return_to_drawdown"], -ret_ok - pf_ok - trades_ok, is_baseline)

    full_rules.sort(key=score_rule)

    print("\n" + "=" * 150)
    print(f"止损/风控回测结果 — pp20 full (排序: dd改善 > r/dd > 收益质量)")
    print(f"{'120d baseline dd = ' + str(baseline_dd) + '%':>50}")
    print("=" * 150)
    header = (f"{'规则':<28} {'窗口':>4} {'笔':>4} {'总收益':>8} {'回撤':>7} {'ddΔ':>6} "
              f"{'r/dd':>6} {'r/ddΔ':>6} {'PF':>6} {'胜率':>6} "
              f"{'最差':>7} {'最佳':>7} {'止损':>4} {'避BS':>4} {'杀赢':>4}")
    print(header)
    print("-" * 150)
    for r in full_rules[:30]:
        marker = "[*]" if r["rule_name"] == "baseline_dec_e" else "   "
        print(f"{marker} {r['rule_name']:<26} {r['window_days']:>3}d "
              f"{r['trade_count']:>4} "
              f"{r['total_return']:>+7.2f}% {r['max_drawdown']:>+6.2f}% "
              f"{r.get('dd_vs_baseline', 0):>+5.1f}% "
              f"{r['return_to_drawdown']:>5.2f} {r.get('r_dd_vs_baseline', 0):>+5.2f} "
              f"{str(r['profit_factor']):>6} {r['win_rate']:>5.1f}% "
              f"{r['worst_trade']:>+6.2f}% {r['best_trade']:>+6.2f}% "
              f"{r.get('stopped_trade_count', 0):>4} "
              f"{r.get('avoided_baseline_worst_count', '-'):>4} "
              f"{r.get('missed_big_winner_count', '-'):>4}")
    print("-" * 150)

    # Also show pp15 top
    full_pp15 = [r for r in all_results
                 if r["split"] == "full" and r["position_pct"] == 0.15]
    full_pp15.sort(key=score_rule)
    print(f"\n── pp15 full ──")
    for r in full_pp15[:15]:
        marker = "[*]" if r["rule_name"] == "baseline_dec_e" else "   "
        print(f"{marker} {r['rule_name']:<26} {r['window_days']:>3}d "
              f"trades={r['trade_count']:>3} ret={r['total_return']:>+7.2f}% "
              f"dd={r['max_drawdown']:>+6.2f}% ddΔ={r.get('dd_vs_baseline', 0):>+5.1f}% "
              f"r/dd={r['return_to_drawdown']:.2f} PF={r['profit_factor']} "
              f"stopped={r.get('stopped_trade_count', 0)} "
              f"avoided={r.get('avoided_baseline_worst_count', '-')} "
              f"missed={r.get('missed_big_winner_count', '-')}")

    # ── Build output ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Find best non-baseline rule
    non_baseline = [r for r in full_rules if r["rule_name"] != "baseline_dec_e" and r["window_days"] == 120]
    best_dd = min(non_baseline, key=lambda r: r["max_drawdown"]) if non_baseline else None
    best_rdd = max(non_baseline, key=lambda r: r["return_to_drawdown"]) if non_baseline else None

    # Count rules meeting target
    target_met = [r for r in full_rules
                  if r["rule_name"] != "baseline_dec_e" and r["window_days"] == 120
                  and r["max_drawdown"] > -18.0  # less drawdown
                  and r["total_return"] >= 8.0
                  and (r["profit_factor"] or 0) > 1.4]

    result = {
        "id": "tail_stop_risk_control_001",
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "completed_by": "claude_code",
        "data_coverage": {
            "valid_trading_days": full_df["date"].nunique(),
            "date_range": cfg.get("date_range", ""),
            "kline_count": KLINE_COUNT,
        },
        "baseline_results": {
            str(bl["window_days"]) + "d_pp" + str(int(bl["position_pct"] * 100)): {
                "ret": bl["total_return"], "dd": bl["max_drawdown"],
                "r_dd": bl["return_to_drawdown"], "pf": bl["profit_factor"],
                "trades": bl["trade_count"], "win": bl["win_rate"],
            }
            for bl in all_results
            if bl["rule_name"] == "baseline_dec_e" and bl["split"] == "full"
        },
        "target_met_count": len(target_met),
        "target_met_rules": [r["rule_name"] for r in target_met],
        "best_dd_rule": best_dd["rule_name"] if best_dd else None,
        "best_rdd_rule": best_rdd["rule_name"] if best_rdd else None,
        "top_rules_summary": [
            {
                "rank": i + 1,
                "rule_name": r["rule_name"],
                "window_days": r["window_days"],
                "position_pct": r["position_pct"],
                "total_return": r["total_return"],
                "max_drawdown": r["max_drawdown"],
                "return_to_drawdown": r["return_to_drawdown"],
                "profit_factor": r["profit_factor"],
                "win_rate": r["win_rate"],
                "trade_count": r["trade_count"],
                "dd_vs_baseline": r.get("dd_vs_baseline"),
                "stopped_trade_count": r.get("stopped_trade_count", 0),
                "avoided_baseline_worst_count": r.get("avoided_baseline_worst_count"),
                "missed_big_winner_count": r.get("missed_big_winner_count"),
            }
            for i, r in enumerate(full_rules[:15])
        ],
        "config": {
            "windows": WINDOWS,
            "risk_rules": list(RISK_RULES.keys()),
            "position_pct_list": POSITION_PCT_LIST,
            "initial_cash": INITIAL_CASH,
            "cost_bps": COST_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "kline_count": KLINE_COUNT,
            "factor": "elastic_base",
            "base_exit": "dec_E",
            "max_positions": MAX_POSITIONS,
            "splits": ["full", "first_half", "second_half"],
            "elapsed_seconds": total_elapsed,
            "generated_at": datetime.now().isoformat(),
        },
        "results": all_results,
    }

    out_json = os.path.join(ROOT, "reports", f"tail_stop_risk_control_{ts}.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果: {out_json}")

    # ── Write queue result ──
    queue_path = os.path.join(ROOT, "backtest_queue", "done", "tail_stop_risk_control_001_result.json")
    os.makedirs(os.path.dirname(queue_path), exist_ok=True)

    answers = {}
    if target_met:
        answers["q1_best_rule"] = f"有{len(target_met)}个规则满足目标。最佳: {target_met[0]['rule_name'] if target_met else 'none'}"
    else:
        answers["q1_best_rule"] = "没有规则能把pp20 120d回撤压到-18%以内并保留+8%收益+PF>1.4。将在摘要中分析最接近的规则。"

    # Find best approach per group
    groups = {}
    for r in full_rules:
        g = r["rule_group"]
        if g not in groups:
            groups[g] = r
        elif r["max_drawdown"] > groups[g]["max_drawdown"]:  # less negative = better
            groups[g] = r

    answers["q_group_summary"] = {
        g: f"{r['rule_name']}: ret={r['total_return']:+.1f}%, dd={r['max_drawdown']:+.1f}%, r/dd={r['return_to_drawdown']:.2f}, PF={r['profit_factor']}"
        for g, r in sorted(groups.items())
    }

    queue_result = {
        "id": "tail_stop_risk_control_001",
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "completed_by": "claude_code",
        "summary": (
            f"止损/风控回测完成。{len(RISK_RULES)}个规则 × 2窗口 × 2仓位 = "
            f"{len(RISK_RULES)*2*2}核心配置。"
            f"目标(120d pp20 dd<=-18%, ret>=+8%, PF>1.4): "
            f"{'有' + str(len(target_met)) + '个规则满足' if target_met else '无规则满足'}。"
        ),
        "answers": answers,
        "files_generated": [out_json],
        "files_created": ["C:\\Users\\56440\\v8_desktop\\run_tail_stop_risk_control.py"],
        "files_modified": [],
    }

    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue_result, f, ensure_ascii=False, indent=2, default=str)
    print(f"队列结果: {queue_path}")

    return result, ts, total_elapsed


if __name__ == "__main__":
    result, ts, elapsed = main()
