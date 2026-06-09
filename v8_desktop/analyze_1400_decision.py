"""Quick analysis: compute 14:00 conditional decision rules.

This script re-runs the fast parts of the tail-entry backtest (factor table,
daily execution prices) and approximates 14:00 prices from daily OHLCV to avoid
slow baostock 5-min fetches.  Results are directional — exact values will differ
from a full minute-data run, but the RELATIVE ranking of decision rules should
hold.

Usage:
  python analyze_1400_decision.py
"""
import json
import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from engine.cache_manager import load_csi300_codes
from run_factor_research import build_factor_table, fetch_klines, zscore_series

FACTOR_SPECS = {
    "elastic_base": ["atr_pct", "ret_20d", "ma20_gap"],
    "elastic_d3": ["atr_pct", "ret_20d", "ma20_gap", "d3"],
    "elastic_d3_sector": ["atr_pct", "ret_20d", "ma20_gap", "d3", "sector_hot"],
}

# ── CLI args (hard-coded for speed) ──
DAYS = 45
TOP = 60
SELECT = 5
THREADS = 8
KLINE_COUNT = 260
COST_BPS = 5.0
SLIPPAGE_BPS = 10.0
STOP_PCT = 3.0


def add_candidate_scores(df):
    work = df.copy()
    grouped = work.groupby("date", group_keys=False)
    for factor in sorted({f for factors in FACTOR_SPECS.values() for f in factors}):
        work[f"z_{factor}"] = grouped[factor].transform(zscore_series).fillna(0)
    for name, factors in FACTOR_SPECS.items():
        work[name] = work[[f"z_{f}" for f in factors]].sum(axis=1)
    return work


def attach_execution_prices(factor_df, kline_dict):
    rows = []
    for _, row in factor_df.iterrows():
        code = row["code"]
        df = kline_dict.get(code)
        if df is None or df.empty:
            continue
        dates = df["date"].astype(str).str[:10]
        matches = df.index[dates == str(row["date"])[:10]]
        if len(matches) == 0:
            continue
        idx = int(matches[0])
        if idx + 1 >= len(df):
            continue
        item = row.to_dict()
        item["entry_close"] = float(df.loc[idx, "close"])
        item["entry_low"] = float(df.loc[idx, "low"])
        for offset, prefix in ((1, "t1"), (2, "t2"), (3, "t3")):
            fidx = idx + offset
            if fidx >= len(df):
                item[f"{prefix}_date"] = ""
                item[f"{prefix}_open"] = np.nan
                item[f"{prefix}_high"] = np.nan
                item[f"{prefix}_low"] = np.nan
                item[f"{prefix}_close"] = np.nan
                continue
            item[f"{prefix}_date"] = str(pd.to_datetime(df.loc[fidx, "date"]).date())
            item[f"{prefix}_open"] = float(df.loc[fidx, "open"])
            item[f"{prefix}_high"] = float(df.loc[fidx, "high"])
            item[f"{prefix}_low"] = float(df.loc[fidx, "low"])
            item[f"{prefix}_close"] = float(df.loc[fidx, "close"])
        rows.append(item)
    return pd.DataFrame(rows)


def approx_1400_price(row):
    """Approximate 14:00 price from daily OHLCV.

    Uses a simple intraday model:
    - Up day (close > open): price tends to recover after morning, 14:00 ≈ (open + close) / 2 + 0.15 * range
    - Down day: 14:00 ≈ (open + close) / 2 - 0.15 * range
    - Flat: 14:00 ≈ (open + close) / 2

    This is a CRUDE approximation. The report must note this limitation.
    """
    o = row.get("t1_open")
    h = row.get("t1_high")
    l = row.get("t1_low")
    c = row.get("t1_close")
    if pd.isna(o) or pd.isna(c):
        return np.nan
    mid = (float(o) + float(c)) / 2.0
    if pd.notna(h) and pd.notna(l):
        rng = float(h) - float(l)
        if float(c) > float(o):
            return mid + 0.12 * rng
        elif float(c) < float(o):
            return mid - 0.12 * rng
    return mid


def net_return(entry_price, exit_price):
    if not entry_price or not exit_price:
        return None
    buy = float(entry_price) * (1 + SLIPPAGE_BPS / 10000.0)
    sell = float(exit_price) * (1 - SLIPPAGE_BPS / 10000.0)
    raw = (sell - buy) / buy * 100.0
    return raw - (COST_BPS * 2 / 100.0)


def compute_all_returns(row):
    """Compute all exit returns including decision rules."""
    entry = row.get("entry_close")
    entry_low = row.get("entry_low")
    t1_1400_approx = approx_1400_price(row)

    out = {}

    # Standard exits
    for col, key in [("t1_open", "t1_open"), ("t1_close", "t1_close"),
                     ("t2_close", "t2_close"), ("t3_close", "t3_close")]:
        r = net_return(entry, row.get(col))
        if r is not None:
            out[key] = r

    # Fixed 14:00 sell (approximated)
    r_1400 = net_return(entry, t1_1400_approx)
    if r_1400 is not None:
        out["t1_1400_fixed"] = r_1400

    # Need 14:00 return for decision rules
    if r_1400 is None or pd.isna(entry_low) or not entry_low:
        return out

    below_t_low = float(t1_1400_approx) < float(entry_low)

    # Rule B: 14:00 <= -2% → sell at 14:00; else → T+1 close
    t1c = net_return(entry, row.get("t1_close"))
    if r_1400 <= -2.0:
        out["dec_B"] = r_1400
    elif t1c is not None:
        out["dec_B"] = t1c

    # Rule C: 14:00 < T day low → sell at 14:00; else → T+1 close
    if below_t_low:
        out["dec_C"] = r_1400
    elif t1c is not None:
        out["dec_C"] = t1c

    # Rule D: 14:00 > 0 AND not below T low → T+2; else 14:00
    t2c = net_return(entry, row.get("t2_close"))
    if r_1400 > 0 and not below_t_low:
        if t2c is not None:
            out["dec_D"] = t2c
    else:
        out["dec_D"] = r_1400

    # Rule E: 14:00 <= -2% OR below T low → 14:00; else T+2
    if r_1400 <= -2.0 or below_t_low:
        out["dec_E"] = r_1400
    elif t2c is not None:
        out["dec_E"] = t2c

    return out


def stats(vals):
    vals = pd.to_numeric(pd.Series(vals), errors="coerce").dropna()
    if vals.empty:
        return {"n": 0}
    wins = vals[vals > 0]
    losses = vals[vals <= 0]
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = abs(float(losses.sum())) if len(losses) else 0.0
    return {
        "n": int(len(vals)),
        "avg": round(float(vals.mean()), 3),
        "median": round(float(vals.median()), 3),
        "win_rate": round(float(len(wins) / len(vals) * 100), 1),
        "avg_win": round(float(wins.mean()), 3) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 3) if len(losses) else 0.0,
        "worst": round(float(vals.min()), 3),
        "best": round(float(vals.max()), 3),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
    }


def equity_stats(trades):
    if not trades:
        return {}
    daily = {}
    for t in trades:
        daily.setdefault(t["date"], []).append(t["ret"])
    curve = []
    eq = 1.0
    peak = 1.0
    max_dd = 0.0
    for date in sorted(daily):
        day_ret = float(np.mean(daily[date])) / 100.0
        eq *= (1 + day_ret)
        peak = max(peak, eq)
        max_dd = min(max_dd, eq / peak - 1)
        curve.append({"date": date, "equity": round(eq, 6), "day_ret": round(day_ret * 100, 3)})
    return {
        "days": len(curve),
        "total_return": round((eq - 1) * 100, 3),
        "max_drawdown": round(max_dd * 100, 3),
        "curve_tail": curve[-10:],
    }


def select_trades(df, score_col):
    selected = []
    for date, group in df.groupby("date"):
        g = group.copy()
        g = g[g["limit_move_flag"] == 0]
        g = g[(g["atr_pct"] >= 1.5) & (g["atr_pct"] <= 7.0)
              & (g["ret_20d"] >= 0.0) & (g["ma20_gap"] >= -5.0)]
        if g.empty:
            continue
        selected.append(g.nlargest(SELECT, score_col))
    return pd.concat(selected, ignore_index=True) if selected else pd.DataFrame()


def main():
    started = time.time()
    print("=" * 70)
    print("14:00 条件决策规则分析 (14:00价格由日线估算)")
    print("=" * 70)

    # ── Step 1: Build factor table ──
    print("\n[1/3] 构建因子表 ...")
    codes = load_csi300_codes(os.path.join(ROOT, "data", "csi300_stocks.json"))[:TOP]
    df, cfg = build_factor_table(codes, DAYS, KLINE_COUNT, THREADS)
    print(f"  因子样本: {len(df)} 条, 日期范围: {cfg['date_range']}")

    # ── Step 2: Attach execution prices ──
    print("[2/3] 附加执行价格 ...")
    kline_dict = fetch_klines(codes, KLINE_COUNT, THREADS)
    df = attach_execution_prices(df, kline_dict)
    df = df.dropna(subset=["entry_close", "t1_open", "t1_close"])
    df = add_candidate_scores(df)
    print(f"  有效样本: {len(df)} 条")

    # ── Step 3: Select & compute ──
    print("[3/3] 选股 + 计算决策规则 ...")
    all_results = {}
    for spec_name in FACTOR_SPECS:
        picks = select_trades(df, spec_name)
        if picks.empty:
            all_results[spec_name] = {"selected": 0}
            continue

        exit_returns = {
            "t1_open": [], "t1_1400_fixed": [], "t1_close": [],
            "t2_close": [], "t3_close": [],
            "dec_B": [], "dec_C": [], "dec_D": [], "dec_E": [],
        }
        exit_trades = {k: [] for k in exit_returns}

        for _, row in picks.iterrows():
            rets = compute_all_returns(row)
            for k, v in rets.items():
                if k in exit_returns:
                    exit_returns[k].append(v)
                    exit_trades[k].append({
                        "date": row["date"], "code": row["code"],
                        "ret": v,
                    })

        spec_result = {"selected": int(len(picks)), "exits": {}, "equity": {}}
        for exit_name, vals in exit_returns.items():
            spec_result["exits"][exit_name] = stats(vals)
            spec_result["equity"][exit_name] = equity_stats(exit_trades[exit_name])
        all_results[spec_name] = spec_result

    elapsed = round(time.time() - started, 1)
    print(f"\n完成, 耗时 {elapsed}s\n")

    # ── Print table ──
    for spec_name, res in all_results.items():
        print(f"── {spec_name} | selected={res.get('selected', 0)} ──")
        print(f"{'Exit':<22} {'n':>4} {'avg':>8} {'med':>8} {'win%':>6} {'PF':>7} {'worst':>8} {'best':>8} {'curve':>8} {'dd':>7}")
        print("-" * 95)
        for exit_name, st in res.get("exits", {}).items():
            if not st.get("n"):
                continue
            eq = res.get("equity", {}).get(exit_name, {})
            print(f"  {exit_name:<20} {st['n']:>4} {st['avg']:>+7.3f}% {st['median']:>+7.3f}% "
                  f"{st['win_rate']:>5.1f}% {str(st['profit_factor']):>7} "
                  f"{st['worst']:>+7.3f}% {st['best']:>+7.3f}% "
                  f"{eq.get('total_return', 0):>+7.2f}% {eq.get('max_drawdown', 0):>+6.2f}%")
        print()

    # ── Build output ──
    result = {
        "config": {
            **cfg,
            "generated_at": datetime.now().isoformat(),
            "records": int(len(df)),
            "factor_specs": FACTOR_SPECS,
            "select_per_day": SELECT,
            "cost_bps_per_side": COST_BPS,
            "slippage_bps_per_side": SLIPPAGE_BPS,
            "note_1400_approx": "14:00 prices are ESTIMATED from daily OHLCV, NOT from minute data. "
                               "Directional ranking is valid; exact values may differ from a full minute-data run.",
            "note_method": "14:00 ≈ mid + 0.12*range for up days; mid - 0.12*range for down days",
            "elapsed_seconds": elapsed,
        },
        "results": all_results,
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = os.path.join(ROOT, "reports", f"tail_1400_decision_{ts}.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"JSON 报告: {out_json}")
    return result, ts


if __name__ == "__main__":
    main()
