"""Market timing filter backtest for d3+ma20_gap tail-entry strategy.

Tests whether CSI300 trend/momentum/breadth/drawdown gates can reduce structural DD
by only trading in favorable market environments. Uses the new baseline d3+ma20_gap.

Fixed: d3+ma20_gap + dec_E + max_positions=2.  Test pp=0.15 and pp=0.20.
Windows: 90 and 120 trading days.  kline_count=600.

Usage:
  python run_tail_market_timing_filter.py
"""
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from engine.cache_manager import load_csi300_codes                                 # noqa: E402
from engine.data_fetcher import fetch_csi300_index                                  # noqa: E402
from run_factor_research import build_factor_table, fetch_klines, zscore_series    # noqa: E402
from run_tail_entry_backtest import attach_execution_prices                         # noqa: E402
from run_tail_portfolio_backtest import (                                           # noqa: E402
    PortfolioSimulator, get_exit_for_rule, _approx_1400,
    COST_BPS, SLIPPAGE_BPS,
)

# ══════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════
INITIAL_CASH = 100_000
MAX_POSITIONS = 2
POSITION_PCT_LIST = [0.15, 0.20]
EXIT_RULE = "dec_E"
TOP = 60
SELECT = 5
THREADS = 8
KLINE_COUNT = 600
WINDOWS = [90, 120]

# ══════════════════════════════════════════════════════════════════════════
# Market gate definitions
# ══════════════════════════════════════════════════════════════════════════
GATES = {
    # ── Baseline (no gate) ──
    "always_on": {"group": "baseline", "desc": "No market filter (baseline)"},

    # ── Single CSI trend ──
    "csi_above_ma20": {"group": "single_csi_trend", "desc": "CSI300 close >= MA20"},
    "csi_above_ma60": {"group": "single_csi_trend", "desc": "CSI300 close >= MA60"},
    "csi_ret20_pos": {"group": "single_csi_trend", "desc": "CSI300 20d return >= 0"},
    "csi_ret5_pos": {"group": "single_csi_trend", "desc": "CSI300 5d return >= 0"},
    "csi_ma20_slope_up": {"group": "single_csi_trend", "desc": "CSI300 MA20 slope > 0"},
    "csi_ma60_slope_up": {"group": "single_csi_trend", "desc": "CSI300 MA60 slope > 0"},

    # ── Single breadth ──
    "breadth_ge_45": {"group": "single_breadth", "desc": "Market breadth >= 45%"},
    "breadth_ge_50": {"group": "single_breadth", "desc": "Market breadth >= 50%"},
    "breadth_ge_55": {"group": "single_breadth", "desc": "Market breadth >= 55%"},
    "breadth_ge_60": {"group": "single_breadth", "desc": "Market breadth >= 60%"},
    "breadth_rising": {"group": "single_breadth", "desc": "Breadth increasing vs prior day"},

    # ── Single drawdown ──
    "csi_dd20_le_3": {"group": "single_drawdown", "desc": "CSI300 DD from 20d high <= 3%"},
    "csi_dd20_le_5": {"group": "single_drawdown", "desc": "CSI300 DD from 20d high <= 5%"},
    "csi_dd20_le_8": {"group": "single_drawdown", "desc": "CSI300 DD from 20d high <= 8%"},

    # ── Combined risk-on ──
    "risk_on_loose": {"group": "combined_risk_on", "desc": "CSI>=MA20 OR breadth>=50%"},
    "risk_on_core": {"group": "combined_risk_on", "desc": "CSI>=MA20 AND ret20>=0 AND breadth>=50%"},
    "trend_confirmed": {"group": "combined_risk_on", "desc": "CSI>=MA20 AND MA20 slope>0"},
    "breadth_confirmed": {"group": "combined_risk_on", "desc": "Breadth>=55% AND breadth rising"},
    "anti_crash": {"group": "combined_risk_on", "desc": "CSI DD20<=5% AND breadth>=45%"},
    "strong_risk_on": {"group": "combined_risk_on", "desc": "CSI>=MA20 AND CSI>=MA60 AND ret20>=0 AND breadth>=55%"},

    # ── Scaled exposure ──
    "scaled_risk_on": {"group": "regime_scaled", "desc": "Full pp when risk_on_core; half when risk_on_loose; zero otherwise"},
}


# ══════════════════════════════════════════════════════════════════════════
# Market feature builder
# ══════════════════════════════════════════════════════════════════════════
def build_market_features(csi300_df, kline_dict):
    """Compute point-in-time market features for each trading date.

    Uses ONLY data visible on or before each date.

    Returns DataFrame with columns: date, csi_close, csi_ma20, csi_ma60,
    csi_ret5, csi_ret20, csi_ma20_slope, csi_ma60_slope, csi_dd20,
    breadth, breadth_prev, breadth_delta, ...
    """
    csi = csi300_df.copy()
    csi["date_str"] = csi["date"].astype(str).str[:10]
    csi = csi.sort_values("date").reset_index(drop=True)

    # Compute rolling indicators
    csi["ma20"] = csi["close"].rolling(20).mean()
    csi["ma60"] = csi["close"].rolling(60).mean()
    csi["ret_5"] = csi["close"].pct_change(5) * 100
    csi["ret_20"] = csi["close"].pct_change(20) * 100
    csi["ma20_slope"] = csi["ma20"].diff(5) / csi["ma20"].shift(5) * 100  # 5-day slope of MA20
    csi["ma60_slope"] = csi["ma60"].diff(5) / csi["ma60"].shift(5) * 100
    csi["high_20d"] = csi["high"].rolling(20).max()
    csi["dd_20d"] = (csi["close"] - csi["high_20d"]) / csi["high_20d"] * 100

    # Build date-indexed dict
    csi_features = {}
    for i, row in csi.iterrows():
        d = row["date_str"]
        csi_features[d] = {
            "close": float(row["close"]),
            "ma20": float(row["ma20"]) if pd.notna(row["ma20"]) else None,
            "ma60": float(row["ma60"]) if pd.notna(row["ma60"]) else None,
            "ret5": float(row["ret_5"]) if pd.notna(row["ret_5"]) else None,
            "ret20": float(row["ret_20"]) if pd.notna(row["ret_20"]) else None,
            "ma20_slope": float(row["ma20_slope"]) if pd.notna(row["ma20_slope"]) else None,
            "ma60_slope": float(row["ma60_slope"]) if pd.notna(row["ma60_slope"]) else None,
            "dd20": float(row["dd_20d"]) if pd.notna(row["dd_20d"]) else None,
        }

    # Compute breadth for each date using kline_dict
    # Collect all trading dates from kline_dict
    date_codes = defaultdict(list)
    for code, kdf in kline_dict.items():
        if kdf is None or kdf.empty:
            continue
        for _, krow in kdf.iterrows():
            d = str(krow["date"])[:10]
            o = float(krow["open"])
            c = float(krow["close"])
            date_codes[d].append(1 if c >= o else 0)  # 1=up, 0=down

    breadth_series = {}
    for d, ups in sorted(date_codes.items()):
        if len(ups) > 0:
            breadth_series[d] = round(sum(ups) / len(ups) * 100, 2)
        else:
            breadth_series[d] = None

    # Merge breadth into features
    dates_sorted = sorted(set(list(csi_features.keys()) + list(breadth_series.keys())))
    prev_breadth = None
    features_out = {}
    for d in dates_sorted:
        feat = csi_features.get(d, {})
        b = breadth_series.get(d)
        feat["breadth"] = b
        feat["breadth_prev"] = prev_breadth
        feat["breadth_delta"] = round(b - prev_breadth, 2) if b is not None and prev_breadth is not None else None
        features_out[d] = feat
        if b is not None:
            prev_breadth = b

    return features_out


# ══════════════════════════════════════════════════════════════════════════
# Gate checker
# ══════════════════════════════════════════════════════════════════════════
def check_gate(gate_name, date_str, features):
    """Check if a gate allows trading on this date."""
    f = features.get(date_str, {})
    if not f:
        return None  # no data = unknown

    if gate_name == "always_on":
        return True

    # Single CSI trend
    if gate_name == "csi_above_ma20":
        return f.get("close") is not None and f.get("ma20") is not None and f["close"] >= f["ma20"]
    if gate_name == "csi_above_ma60":
        return f.get("close") is not None and f.get("ma60") is not None and f["close"] >= f["ma60"]
    if gate_name == "csi_ret20_pos":
        return f.get("ret20") is not None and f["ret20"] >= 0
    if gate_name == "csi_ret5_pos":
        return f.get("ret5") is not None and f["ret5"] >= 0
    if gate_name == "csi_ma20_slope_up":
        return f.get("ma20_slope") is not None and f["ma20_slope"] > 0
    if gate_name == "csi_ma60_slope_up":
        return f.get("ma60_slope") is not None and f["ma60_slope"] > 0

    # Single breadth
    b = f.get("breadth")
    if gate_name == "breadth_ge_45":
        return b is not None and b >= 45
    if gate_name == "breadth_ge_50":
        return b is not None and b >= 50
    if gate_name == "breadth_ge_55":
        return b is not None and b >= 55
    if gate_name == "breadth_ge_60":
        return b is not None and b >= 60
    if gate_name == "breadth_rising":
        return f.get("breadth_delta") is not None and f["breadth_delta"] > 0

    # Single DD
    dd = f.get("dd20")
    if gate_name == "csi_dd20_le_3":
        return dd is not None and dd >= -3.0
    if gate_name == "csi_dd20_le_5":
        return dd is not None and dd >= -5.0
    if gate_name == "csi_dd20_le_8":
        return dd is not None and dd >= -8.0

    # Combined risk-on
    if gate_name == "risk_on_loose":
        csi_ok = f.get("close") is not None and f.get("ma20") is not None and f["close"] >= f["ma20"]
        b_ok = b is not None and b >= 50
        return csi_ok or b_ok
    if gate_name == "risk_on_core":
        csi_ok = f.get("close") is not None and f.get("ma20") is not None and f["close"] >= f["ma20"]
        ret_ok = f.get("ret20") is not None and f["ret20"] >= 0
        b_ok = b is not None and b >= 50
        return csi_ok and ret_ok and b_ok
    if gate_name == "trend_confirmed":
        csi_ok = f.get("close") is not None and f.get("ma20") is not None and f["close"] >= f["ma20"]
        slope_ok = f.get("ma20_slope") is not None and f["ma20_slope"] > 0
        return csi_ok and slope_ok
    if gate_name == "breadth_confirmed":
        b_ok = b is not None and b >= 55
        rising = f.get("breadth_delta") is not None and f["breadth_delta"] > 0
        return b_ok and rising
    if gate_name == "anti_crash":
        dd_ok = dd is not None and dd >= -5.0
        b_ok = b is not None and b >= 45
        return dd_ok and b_ok
    if gate_name == "strong_risk_on":
        csi20 = f.get("close") is not None and f.get("ma20") is not None and f["close"] >= f["ma20"]
        csi60 = f.get("close") is not None and f.get("ma60") is not None and f["close"] >= f["ma60"]
        ret20 = f.get("ret20") is not None and f["ret20"] >= 0
        b55 = b is not None and b >= 55
        return csi20 and csi60 and ret20 and b55

    return None


def get_scaled_pp(gate_name, date_str, features, base_pp):
    """For scaled_risk_on, return the scaled position_pct."""
    if gate_name != "scaled_risk_on":
        return base_pp
    f = features.get(date_str, {})
    if not f:
        return 0
    b = f.get("breadth")
    is_risk_on_core = (
        f.get("close") is not None and f.get("ma20") is not None and f["close"] >= f["ma20"]
        and f.get("ret20") is not None and f["ret20"] >= 0
        and b is not None and b >= 50
    )
    is_risk_on_loose = (
        (f.get("close") is not None and f.get("ma20") is not None and f["close"] >= f["ma20"])
        or (b is not None and b >= 50)
    )
    if is_risk_on_core:
        return base_pp  # full position
    elif is_risk_on_loose:
        return base_pp / 2  # half position
    else:
        return 0  # no trading


# ══════════════════════════════════════════════════════════════════════════
# Portfolio helpers
# ══════════════════════════════════════════════════════════════════════════
def build_baseline_picks(full_df):
    """Build picks using z(d3) + z(ma20_gap)."""
    df = full_df.copy()
    grouped = df.groupby("date", group_keys=False)
    for col in ["d3", "ma20_gap"]:
        df[f"_z_{col}"] = grouped[col].transform(zscore_series).fillna(0)
    df["_score"] = df["_z_d3"] + df["_z_ma20_gap"]
    df = df[df["limit_move_flag"] == 0]
    df = df[(df["atr_pct"] >= 1.5) & (df["atr_pct"] <= 7.0)]
    df = df[(df["ret_20d"] >= 0.0) & (df["ma20_gap"] >= -5.0)]
    picks = []
    for date, group in df.groupby("date"):
        if group.empty:
            continue
        picks.append(group.nlargest(SELECT, "_score"))
    if not picks:
        return pd.DataFrame(), {}
    pdf = pd.concat(picks, ignore_index=True)
    pdf["t1_1400_price"] = pdf.apply(_approx_1400, axis=1)
    return pdf, {"picks": len(pdf)}


def run_portfolio(picks_df, trading_dates, kline_dict, pp, gate_name, features):
    """Run portfolio sim with market gate filtering."""
    picks_by_date = defaultdict(list)
    for _, row in picks_df.iterrows():
        d = str(row["date"])
        picks_by_date[d].append({
            "code": row["code"], "date": d,
            "score": float(row.get("_score", 0)),
            "entry_close": row["entry_close"], "entry_low": row["entry_low"],
            "t1_date": str(row.get("t1_date", "")), "t2_date": str(row.get("t2_date", "")),
            "t1_close": row.get("t1_close"), "t2_close": row.get("t2_close"),
            "t1_1400_price": row.get("t1_1400_price"),
        })

    # Filter picks by gate
    total_picks_before = sum(len(v) for v in picks_by_date.values())
    if gate_name != "always_on":
        gated_picks = {}
        for d, plist in picks_by_date.items():
            result = check_gate(gate_name, d, features)
            if result is True:
                gated_picks[d] = plist
        picks_by_date = gated_picks
    total_picks_after = sum(len(v) for v in picks_by_date.values())

    # For scaled: adjust pp per date
    if gate_name == "scaled_risk_on":
        scaled_picks = {}
        for d, plist in picks_by_date.items():
            spp = get_scaled_pp(gate_name, d, features, pp)
            if spp > 0:
                # Store adjusted pp in pick metadata
                for p in plist:
                    p["_scaled_pp"] = spp
                scaled_picks[d] = plist
        picks_by_date = scaled_picks

    # Custom simulator for scaled exposure
    class GatedSimulator(PortfolioSimulator):
        def _open_position(self, pick, date):
            # Use scaled pp if available
            if "_scaled_pp" in pick:
                orig_pp = self.position_pct
                self.position_pct = pick["_scaled_pp"]
                result = super()._open_position(pick, date)
                self.position_pct = orig_pp
                return result
            return super()._open_position(pick, date)

    sim = GatedSimulator(INITIAL_CASH, MAX_POSITIONS, pp, COST_BPS, SLIPPAGE_BPS)
    sim.run(picks_by_date, trading_dates, EXIT_RULE, kline_dict)
    s = sim.summary()
    total_dates = len(trading_dates)
    traded_dates = len(picks_by_date)
    pass_rate = round(traded_dates / total_dates * 100, 1) if total_dates > 0 else 0
    skipped = total_picks_before - total_picks_after
    if s.get("trade_count", 0) == 0:
        return {"ret": 0, "dd": 0, "r_dd": 0, "pf": None, "win": 0, "trades": 0,
                "worst": 0, "best": 0, "avg_ret": 0, "streak": 0, "cash_usage": 0,
                "worst_10": [], "top_10": [],
                "pass_rate": pass_rate, "skipped": skipped,
                "dates_traded": traded_dates, "dates_total": total_dates,
                "exposure": 0, "total_days": 0}
    r_dd = round(abs(s["total_return"] / s["max_drawdown"]), 2) if s.get("max_drawdown", 0) != 0 else 0
    closed = sorted(sim.closed_trades, key=lambda t: t["ret_pct"])
    worst_10 = [{"code": t["code"], "entry_date": t["entry_date"],
                 "ret_pct": round(t["ret_pct"], 2), "exit_type": t["exit_type"]}
                for t in closed[:10]]
    top_10 = [{"code": t["code"], "entry_date": t["entry_date"],
               "ret_pct": round(t["ret_pct"], 2)} for t in closed[-10:][::-1]]

    return {
        "ret": s["total_return"], "dd": s["max_drawdown"], "r_dd": r_dd,
        "pf": s["profit_factor"], "win": s["win_rate"], "trades": s["trade_count"],
        "worst": s["worst_trade"], "best": s["best_trade"],
        "avg_ret": s["avg_trade_return"],
        "streak": s["longest_loss_streak"], "cash_usage": s.get("avg_cash_usage_pct", 0),
        "worst_10": worst_10, "top_10": top_10,
        "pass_rate": pass_rate, "skipped": skipped,
        "dates_traded": traded_dates, "dates_total": total_dates,
        "exposure": s.get("exposure_days", 0), "total_days": s.get("total_days", 0),
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
    total_gates = len(GATES)

    print("=" * 80)
    print("尾盘 d3+ma20_gap 市场择时过滤回测")
    print(f"Gates: {total_gates} | 窗口: {WINDOWS}天 | 基线: {EXIT_RULE}+mp{MAX_POSITIONS}")
    print("=" * 80)

    # ── Build data ──
    print("\n[数据] 构建因子表 + CSI300 + 市场特征 ...")
    codes = load_csi300_codes(os.path.join(ROOT, "data", "csi300_stocks.json"))[:TOP]
    max_days = max(WINDOWS)
    full_df, cfg = build_factor_table(codes, max_days, KLINE_COUNT, THREADS)
    kline_dict = fetch_klines(codes, KLINE_COUNT, THREADS)
    full_df = attach_execution_prices(full_df, kline_dict)
    full_df = full_df.dropna(subset=["entry_close", "t1_open", "t1_close"])
    csi300_df = fetch_csi300_index(count=KLINE_COUNT)
    features = build_market_features(csi300_df, kline_dict)
    print(f"  有效: {len(full_df)} 行, {full_df['date'].nunique()} 交易日, 特征日期: {len(features)}")

    # Check gate pass rates
    all_entry_dates = sorted(full_df["date"].astype(str).str[:10].unique())
    print(f"\n[Gate Pass Rates]")
    for gname in sorted(GATES.keys()):
        if gname == "always_on":
            continue
        passes = sum(1 for d in all_entry_dates if check_gate(gname, d, features) is True)
        unknowns = sum(1 for d in all_entry_dates if check_gate(gname, d, features) is None)
        pct = round(passes / len(all_entry_dates) * 100, 1) if all_entry_dates else 0
        print(f"  {gname:<24}: {pct:>5.1f}% pass ({passes}/{len(all_entry_dates)}), {unknowns} unknown")

    # Build trading calendar
    all_td_set = set()
    for kdf in kline_dict.values():
        if kdf is not None and not kdf.empty:
            for d in kdf["date"].astype(str).str[:10]:
                all_td_set.add(d)
    all_td = sorted(all_td_set)
    entry_dates_all = sorted(full_df["date"].astype(str).str[:10].unique())
    td_full = [d for d in all_td if d >= entry_dates_all[0] and d <=
               (pd.to_datetime(entry_dates_all[-1]) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")]

    # Cut windows
    window_info = {}
    for wd in WINDOWS:
        wentry = entry_dates_all[-wd:] if len(entry_dates_all) >= wd else entry_dates_all
        wset = set(wentry)
        window_info[wd] = {
            "df": full_df[full_df["date"].astype(str).str[:10].isin(wset)].copy(),
            "td": [d for d in td_full if d >= wentry[0] and d <=
                   (pd.to_datetime(wentry[-1]) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")],
            "entry_dates": wentry,
            "n_dates": len(wentry),
        }

    # ── Run ──
    all_results = []
    baseline_key = {"always_on": {}}

    for wd in WINDOWS:
        winfo = window_info[wd]
        print(f"\n{'='*60}")
        print(f"[窗口] {wd}天 ({winfo['n_dates']} 交易日)")
        print(f"{'='*60}")

        picks_df, _ = build_baseline_picks(winfo["df"])
        if picks_df.empty:
            continue

        # Baseline first
        for gname, ginfo in GATES.items():
            splits = split_picks(picks_df, winfo["td"])
            for split_name, sub_picks, sub_td in splits:
                if len(sub_picks) < 5:
                    continue
                for pp in POSITION_PCT_LIST:
                    res = run_portfolio(sub_picks, sub_td, kline_dict, pp, gname, features)
                    if not res:
                        continue
                    entry = {
                        "gate_name": gname, "gate_group": ginfo.get("group", ""),
                        "gate_desc": ginfo.get("desc", ""),
                        "window_days": wd, "split": split_name, "position_pct": pp,
                        **res,
                    }
                    all_results.append(entry)
                    if split_name == "full" and gname == "always_on":
                        baseline_key[(wd, pp)] = entry
                    elif split_name == "full":
                        bl = baseline_key.get((wd, pp))
                        if bl:
                            entry["dd_vs_baseline"] = round(res["dd"] - bl["dd"], 2)
                            entry["r_dd_vs_baseline"] = round(res["r_dd"] - bl["r_dd"], 3)
                            entry["ret_vs_baseline"] = round(res["ret"] - bl["ret"], 2)
                            entry["trade_ratio"] = round(res["trades"] / bl["trades"], 2) if bl["trades"] else None
                    # Compact print
                    if split_name == "full":
                        dd_d = entry.get("dd_vs_baseline")
                        dd_str = f"ddΔ={dd_d:+.1f}%" if dd_d is not None else ""
                        print(f"  {gname:<24} pp{int(pp*100)}%: trades={res['trades']:>3} "
                              f"ret={res['ret']:>+7.2f}% dd={res['dd']:>+7.2f}% "
                              f"{dd_str} r/dd={res['r_dd']:.2f} PF={res['pf']} "
                              f"pass={res['pass_rate']:.0f}%")

    # ── Rank gates (120d pp20) ──
    bl_120_20 = baseline_key.get((120, 0.20))
    bl_dd = bl_120_20["dd"] if bl_120_20 else -27.65

    gates_120 = [r for r in all_results
                 if r["window_days"] == 120 and r["position_pct"] == 0.20
                 and r["split"] == "full" and r["gate_name"] != "always_on"]

    for g in gates_120:
        g["_score_rank"] = -(g.get("dd_vs_baseline") or 0)

    gates_120.sort(key=lambda g: (-(g.get("dd_vs_baseline") or -99), -g["r_dd"], -(g["pf"] or 0)))

    # ── Output table ──
    total_elapsed = round(time.time() - started, 1)
    print("\n" + "=" * 145)
    print(f"市场择时过滤结果 — 120d pp20 (排序: DD改善 > r/dd)")
    print(f"Baseline (无过滤): dd={bl_dd}%, r/dd={bl_120_20['r_dd']:.2f}, PF={bl_120_20['pf']}")
    print("=" * 145)
    hdr = (f"{'Gate':<24} {'组':<16} {'通过':>5} {'跳过':>5} {'笔':>4} {'收益':>8} {'回撤':>7} "
           f"{'ddΔ':>6} {'r/dd':>5} {'r/ddΔ':>6} {'PF':>6} {'胜率':>5}")
    print(hdr)
    print("-" * 145)
    for g in gates_120:
        dd_d = g.get("dd_vs_baseline")
        rdd_d = g.get("r_dd_vs_baseline")
        print(f"  {g['gate_name']:<22} {g['gate_group']:<16} {g['pass_rate']:>4.0f}% {g['skipped']:>5} "
              f"{g['trades']:>4} "
              f"{g['ret']:>+7.2f}% {g['dd']:>+7.2f}% "
              f"{dd_d:>+5.1f}% " if dd_d is not None else f"  {'?':>5} ",
              end="")
        print(f"{g['r_dd']:>5.2f} {rdd_d:>+5.2f} " if rdd_d is not None else f"{g['r_dd']:>5.2f} {'?':>5} ",
              end="")
        print(f"{str(g['pf']):>6} {g['win']:>4.1f}%")

    print("-" * 145)

    # pp15
    gates_15 = [r for r in all_results
                if r["window_days"] == 120 and r["position_pct"] == 0.15
                and r["split"] == "full" and r["gate_name"] != "always_on"]
    gates_15.sort(key=lambda g: (-(g.get("dd_vs_baseline") or -99), -g["r_dd"]))
    print(f"\n── 120d pp15 top 10 ──")
    for g in gates_15[:10]:
        dd_d = g.get("dd_vs_baseline")
        print(f"  {g['gate_name']:<22} trades={g['trades']:>3} ret={g['ret']:>+7.2f}% "
              f"dd={(g['dd']):>+7.2f}% ddΔ={(dd_d or 0):>+5.1f}% r/dd={g['r_dd']:.2f} PF={g['pf']}")

    # ── Halves check ──
    halves_gates = [r for r in all_results
                    if r["window_days"] == 120 and r["position_pct"] == 0.20
                    and r["split"] in ("first_half", "second_half")]
    print(f"\n── Halves一致性 (120d pp20) ──")
    for gname in sorted(set(r["gate_name"] for r in halves_gates)):
        h1 = [r for r in halves_gates if r["gate_name"] == gname and r["split"] == "first_half"]
        h2 = [r for r in halves_gates if r["gate_name"] == gname and r["split"] == "second_half"]
        if h1 and h2:
            h1c = "Y" if h1[0]["r_dd"] >= 0.15 else "-"
            h2c = "Y" if h2[0]["r_dd"] >= 0.15 else "-"
            both_ok = "PASS" if (h1c == "Y" and h2c == "Y") else "FAIL"
            dd_d = h1[0].get("dd_vs_baseline")
            dd_h1 = dd_d if dd_d is not None else "?"
            dd_d = h2[0].get("dd_vs_baseline")
            dd_h2 = dd_d if dd_d is not None else "?"
            print(f"  {gname:<24} H1: r/dd={h1[0]['r_dd']:.2f} ddΔ={dd_h1} | H2: r/dd={h2[0]['r_dd']:.2f} ddΔ={dd_h2} | {both_ok}")

    # ── Promotion check ──
    promoted = []
    for g in gates_120:
        dd_improve = g.get("dd_vs_baseline")
        if dd_improve is None:
            continue
        if dd_improve >= 5.0 and g["ret"] >= 10 and (g["pf"] or 0) > 1.4 and g["trades"] >= 60:
            promoted.append(g["gate_name"])

    print(f"\n── 达标检查 (120d pp20: ddΔ>=5pp, ret>=10%, PF>1.4, trades>=60) ──")
    if promoted:
        print(f"  达标: {promoted}")
    else:
        best_dd_g = max(gates_120, key=lambda g: g.get("dd_vs_baseline") or -99)
        best_rdd_g = max(gates_120, key=lambda g: g["r_dd"])
        print(f"  无达标。最佳DD改善: {best_dd_g['gate_name']} ({best_dd_g.get('dd_vs_baseline'):+.1f}pp)")
        print(f"  最佳r/dd: {best_rdd_g['gate_name']} ({best_rdd_g['r_dd']:.2f})")

    # ── Output ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result = {
        "id": "tail_market_timing_filter_001",
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "baseline_120d_pp20": bl_120_20,
        "total_gates": total_gates,
        "promoted_gates": promoted,
        "all_results": all_results,
        "top_120d_pp20": gates_120[:20],
        "config": {
            "windows": WINDOWS, "baseline_factor": "d3+ma20_gap", "exit_rule": EXIT_RULE,
            "max_positions": MAX_POSITIONS, "position_pct_list": POSITION_PCT_LIST,
            "kline_count": KLINE_COUNT, "elapsed_seconds": total_elapsed,
            "generated_at": datetime.now().isoformat(),
        },
    }

    out_json = os.path.join(ROOT, "reports", f"tail_market_timing_filter_{ts}.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果: {out_json}")

    queue_path = os.path.join(ROOT, "backtest_queue", "done", "tail_market_timing_filter_001_result.json")
    os.makedirs(os.path.dirname(queue_path), exist_ok=True)

    qr = {
        "id": "tail_market_timing_filter_001",
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "completed_by": "claude_code",
        "summary": f"市场择时过滤回测完成。{total_gates}个gate × 2窗口 × 2仓位。达标(120d pp20 ddΔ>=5pp): {len(promoted)}个。",
        "promoted": promoted,
        "answers": {},
        "files_generated": [out_json],
        "files_created": ["run_tail_market_timing_filter.py"],
        "files_modified": [],
    }

    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(qr, f, ensure_ascii=False, indent=2, default=str)
    print(f"队列结果: {queue_path}")

    return result, ts, total_elapsed


if __name__ == "__main__":
    result, ts, elapsed = main()
