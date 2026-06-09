"""Long-window validation of base_no_range_gt8 filter.

Compares baseline (elastic_base) vs range_filter (exclude intraday_range_pct > 8%)
across 90-day and 120-day windows with time-stability splits.

Fixed: dec_E + mp2. Tests pp=15% and pp=20%.

Usage:
  python run_tail_range_filter_long_window.py
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

from engine.cache_manager import load_csi300_codes                               # noqa: E402
from run_factor_research import build_factor_table, fetch_klines, zscore_series  # noqa: E402
from run_tail_entry_backtest import attach_execution_prices                       # noqa: E402
from run_tail_portfolio_backtest import (                                         # noqa: E402
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
KLINE_COUNT = 350   # Enough for 120-day window + lookback

WINDOWS = [90, 120]

# Only 2 rules
RULES = {
    "elastic_base": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [],
        "desc": "Baseline",
    },
    "base_no_range_gt8": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("intraday_range_pct", "<=", 8.0)],
        "desc": "Exclude intraday_range>8%",
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Data enrichment
# ══════════════════════════════════════════════════════════════════════════
def enrich_factor_df(df, kline_dict):
    """Add per-stock daily change_pct from kline data."""
    df = df.copy()
    changes = []
    for _, row in df.iterrows():
        code = row["code"]
        date = str(row["date"])[:10]
        kdf = kline_dict.get(code)
        if kdf is None or kdf.empty:
            changes.append(np.nan)
            continue
        kdf_dates = kdf["date"].astype(str).str[:10]
        matches = kdf[kdf_dates == date]
        if matches.empty:
            changes.append(np.nan)
            continue
        idx = int(matches.index[0])
        if idx == 0:
            changes.append(0.0)
            continue
        prev_close = float(kdf.iloc[idx - 1]["close"])
        curr_close = float(kdf.iloc[idx]["close"])
        changes.append(round((curr_close - prev_close) / prev_close * 100 if prev_close else 0.0, 2))
    df["change_pct"] = changes
    return df


# ══════════════════════════════════════════════════════════════════════════
# Rule-aware pick builder (reused from run_tail_factor_risk_search.py)
# ══════════════════════════════════════════════════════════════════════════
def build_picks_for_rule(full_df, rule_config):
    """Build picks for a single rule. Z-scores on FULL date group before filtering."""
    df = full_df.copy()
    total_before = len(df)

    # Step 1: Z-score on FULL date group (before any filtering)
    factor_formula = rule_config["factor"]
    grouped_full = df.groupby("date", group_keys=False)

    z_cols = {}
    for col in factor_formula:
        if col in df.columns:
            z_name = f"_z_{col}"
            df[z_name] = grouped_full[col].transform(zscore_series).fillna(0)
            z_cols[col] = z_name

    df["_score"] = 0.0
    for col, weight in factor_formula.items():
        if col in z_cols:
            df["_score"] += df[z_cols[col]] * weight

    # Step 2: Default base filters
    df = df[df["limit_move_flag"] == 0]
    df = df[(df["atr_pct"] >= 1.5) & (df["atr_pct"] <= 7.0)]
    df = df[(df["ret_20d"] >= 0.0) & (df["ma20_gap"] >= -5.0)]
    after_base = len(df)

    # Step 3: Rule-specific pre-filters
    pre_filters = rule_config.get("pre_filters", [])
    for col, op, val in pre_filters:
        if col not in df.columns:
            continue
        if op == "<=":
            df = df[df[col] <= val]
        elif op == ">=":
            df = df[df[col] >= val]
        elif op == "==":
            df = df[df[col] == val]
    after_filters = len(df)

    # Step 4: Select top-N per day
    picks = []
    for date, group in df.groupby("date"):
        if group.empty:
            continue
        top_n = group.nlargest(SELECT, "_score")
        picks.append(top_n)

    if not picks:
        return pd.DataFrame(), {"total_before": total_before, "after_base": after_base,
                                 "after_filters": after_filters, "picks": 0}

    picks_df = pd.concat(picks, ignore_index=True)
    picks_df["t1_1400_price"] = picks_df.apply(_approx_1400, axis=1)

    stats = {
        "total_before": total_before,
        "after_base": after_base,
        "after_filters": after_filters,
        "picks": len(picks_df),
        "filtered_signals": total_before - after_filters,
    }
    return picks_df, stats


# ══════════════════════════════════════════════════════════════════════════
# Portfolio run helper
# ══════════════════════════════════════════════════════════════════════════
def run_portfolio(picks_df, trading_dates, kline_dict, pp):
    """Run portfolio simulation and return enriched summary."""
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

    sim = PortfolioSimulator(INITIAL_CASH, MAX_POSITIONS, pp, COST_BPS, SLIPPAGE_BPS)
    sim.run(picks_by_date, trading_dates, EXIT_RULE, kline_dict)
    summ = sim.summary()

    # Worst 10 trades
    closed = sim.closed_trades
    closed_sorted = sorted(closed, key=lambda t: t["ret_pct"])
    worst_10 = [{"code": t["code"], "entry_date": t["entry_date"],
                 "exit_date": t["exit_date"], "exit_type": t["exit_type"],
                 "ret_pct": round(t["ret_pct"], 2)}
                for t in closed_sorted[:10]]

    # return_to_drawdown
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
        "max_concurrent_positions": summ.get("max_concurrent_positions", 0),
        "avg_cash_usage": summ.get("avg_cash_usage_pct", 0),
        "equity_curve": summ.get("equity_curve_tail", []),
    }


# ══════════════════════════════════════════════════════════════════════════
# Split helpers
# ══════════════════════════════════════════════════════════════════════════
def split_picks_by_date(picks_df, trading_dates, split_type):
    """Split picks and trading dates into sub-windows.

    Returns list of (split_name, sub_picks_df, sub_trading_dates)
    """
    all_dates_in_picks = sorted(picks_df["date"].astype(str).str[:10].unique())
    n_dates = len(all_dates_in_picks)

    if split_type == "full":
        return [("full", picks_df, trading_dates)]

    if split_type == "first_half":
        mid = n_dates // 2
        first_dates = set(all_dates_in_picks[:mid])
        sub = picks_df[picks_df["date"].astype(str).str[:10].isin(first_dates)]
        first_td = [d for d in trading_dates if d <= all_dates_in_picks[mid - 1]]
        return [("first_half", sub, first_td)]

    if split_type == "second_half":
        mid = n_dates // 2
        second_dates = set(all_dates_in_picks[mid:])
        sub = picks_df[picks_df["date"].astype(str).str[:10].isin(second_dates)]
        second_td = [d for d in trading_dates if d >= all_dates_in_picks[mid]]
        return [("second_half", sub, second_td)]

    if split_type == "both_halves":
        mid = n_dates // 2
        first_dates = set(all_dates_in_picks[:mid])
        second_dates = set(all_dates_in_picks[mid:])
        sub1 = picks_df[picks_df["date"].astype(str).str[:10].isin(first_dates)]
        sub2 = picks_df[picks_df["date"].astype(str).str[:10].isin(second_dates)]
        td1 = [d for d in trading_dates if d <= all_dates_in_picks[mid - 1]]
        td2 = [d for d in trading_dates if d >= all_dates_in_picks[mid]]
        return [("first_half", sub1, td1), ("second_half", sub2, td2)]

    return [("full", picks_df, trading_dates)]


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
def main():
    started = time.time()

    print("=" * 80)
    print("尾盘买入 base_no_range_gt8 长窗口验证")
    print(f"规则: baseline vs range_filter | 窗口: {WINDOWS}天 | 仓位: {POSITION_PCT_LIST}")
    print(f"执行: {EXIT_RULE} + mp{MAX_POSITIONS} | 拆分: full + both_halves")
    print("=" * 80)

    # ── Build data ONCE for the longest window ──
    max_days = max(WINDOWS)
    print(f"\n[数据] 构建 {max_days}天全量因子表 ...")
    codes = load_csi300_codes(os.path.join(ROOT, "data", "csi300_stocks.json"))[:TOP]
    full_df, cfg = build_factor_table(codes, max_days, KLINE_COUNT, THREADS)
    kline_dict = fetch_klines(codes, KLINE_COUNT, THREADS)
    full_df = attach_execution_prices(full_df, kline_dict)
    full_df = full_df.dropna(subset=["entry_close", "t1_open", "t1_close"])
    full_df = enrich_factor_df(full_df, kline_dict)
    print(f"  全量: {len(full_df)} 行, 区间: {cfg.get('date_range', '?')}")

    # Build full trading calendar
    all_trading_dates = set()
    for kdf in kline_dict.values():
        if kdf is not None and not kdf.empty:
            for d in kdf["date"].astype(str).str[:10]:
                all_trading_dates.add(d)
    all_dates_full = sorted(all_trading_dates)

    full_entry_dates = sorted(full_df["date"].astype(str).str[:10].unique())
    first_entry = full_entry_dates[0]
    last_entry = full_entry_dates[-1]
    all_td_full = [d for d in all_dates_full if d >= first_entry and d <=
                   (pd.to_datetime(last_entry) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")]

    # ── Run for each window ──
    all_results = []

    for window_days in WINDOWS:
        print(f"\n{'─'*60}")
        print(f"[窗口] {window_days} 天")
        print(f"{'─'*60}")

        # Truncate data to this window
        window_entry_dates = full_entry_dates[-window_days:] if len(full_entry_dates) >= window_days else full_entry_dates
        actual_days = len(window_entry_dates)
        date_range_str = f"{window_entry_dates[0]} ~ {window_entry_dates[-1]}"
        print(f"  实际交易日: {actual_days}, 区间: {date_range_str}")

        window_date_set = set(window_entry_dates)
        df_window = full_df[full_df["date"].astype(str).str[:10].isin(window_date_set)].copy()

        # Trading dates for this window
        td_window = [d for d in all_td_full
                     if d >= window_entry_dates[0]
                     and d <= (pd.to_datetime(window_entry_dates[-1]) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")]

        # ── Run both rules ──
        for rule_name, rule_config in RULES.items():
            print(f"\n  [{rule_name}] 构建选股 ...")
            picks_df, stats = build_picks_for_rule(df_window, rule_config)
            print(f"    选股: {stats['picks']} 笔, 过滤信号: {stats['filtered_signals']}")

            if picks_df.empty:
                print(f"    [跳过] 无有效选股")
                continue

            # ── Run splits ──
            splits = split_picks_by_date(picks_df, td_window, "both_halves")
            # Also add full
            splits_full = [("full", picks_df, td_window)]
            all_splits = splits_full + splits

            for split_name, sub_picks, sub_td in all_splits:
                if len(sub_picks) < 10:
                    print(f"    [{split_name}] 样本不足 ({len(sub_picks)}笔), 跳过")
                    continue

                for pp in POSITION_PCT_LIST:
                    result = run_portfolio(sub_picks, sub_td, kline_dict, pp)
                    entry = {
                        "window_days": window_days,
                        "actual_days": actual_days,
                        "actual_date_range": date_range_str,
                        "rule_name": rule_name,
                        "rule_desc": rule_config["desc"],
                        "position_pct": pp,
                        "split": split_name,
                        "filtered_signal_count": stats["filtered_signals"],
                    }
                    entry.update(result)
                    all_results.append(entry)

                    print(f"    [{split_name}] pp{int(pp*100)}%: "
                          f"trades={result['trade_count']} "
                          f"ret={result['total_return']:+.2f}% "
                          f"dd={result['max_drawdown']:+.2f}% "
                          f"r/dd={result['return_to_drawdown']:.2f} "
                          f"win={result['win_rate']:.1f}% "
                          f"PF={result['profit_factor']} "
                          f"worst={result['worst_trade']:+.2f}%")

    # ── Compute cross-rule comparisons ──
    # For each (window_days, split, pp), find baseline and range_filter results
    for r in all_results:
        if r["rule_name"] != "base_no_range_gt8":
            continue
        # Find matching baseline
        baseline_match = [b for b in all_results
                         if b["rule_name"] == "elastic_base"
                         and b["window_days"] == r["window_days"]
                         and b["split"] == r["split"]
                         and b["position_pct"] == r["position_pct"]]
        if not baseline_match:
            r["trade_count_ratio_vs_baseline"] = None
            r["filtered_baseline_worst_count"] = None
            r["r_dd_vs_baseline"] = None
            r["dd_vs_baseline"] = None
            continue

        bl = baseline_match[0]
        r["trade_count_ratio_vs_baseline"] = round(r["trade_count"] / bl["trade_count"], 2) if bl["trade_count"] > 0 else None
        r["r_dd_vs_baseline"] = round(r["return_to_drawdown"] - bl["return_to_drawdown"], 3)
        r["dd_vs_baseline"] = round(r["max_drawdown"] - bl["max_drawdown"], 2)

        # Count how many baseline worst trades are filtered out
        bl_worst_codes = {(t["code"], t["entry_date"]) for t in bl["worst_10_trades"][:10]}
        rf_worst_codes = {(t["code"], t["entry_date"]) for t in r["worst_10_trades"][:10]}
        filtered_out = bl_worst_codes - rf_worst_codes
        r["filtered_baseline_worst_count"] = len(filtered_out)
        r["filtered_baseline_worst_details"] = [
            {"code": c, "entry_date": d, "status": "FILTERED_OUT"}
            for c, d in filtered_out
        ]

    # Add trade_count_ratio for baseline entries too
    for r in all_results:
        if r["rule_name"] == "elastic_base":
            r["trade_count_ratio_vs_baseline"] = 1.0
            r["filtered_baseline_worst_count"] = 0
            r["r_dd_vs_baseline"] = 0.0
            r["dd_vs_baseline"] = 0.0

    # ── Print summary ──
    total_elapsed = round(time.time() - started, 1)
    print("\n" + "=" * 140)
    print(f"长窗口验证结果汇总 (full splits)")
    print(f"框架: {EXIT_RULE} + mp{MAX_POSITIONS} | 耗时: {total_elapsed}s")
    print("=" * 140)

    full_results = [r for r in all_results if r["split"] == "full"]
    # Sort: window, pp desc, rule (baseline first)
    full_results.sort(key=lambda r: (r["window_days"], -r["position_pct"],
                                      0 if "elastic" in r["rule_name"] else 1))

    header = (f"{'窗口':>5} {'规则':<22} {'仓位':>5} {'笔':>4} {'总收益':>8} {'回撤':>7} "
              f"{'r/dd':>6} {'r/ddΔ':>6} {'ddΔ':>6} {'胜率':>6} {'PF':>6} {'连亏':>4} "
              f"{'最差':>8} {'过滤BS':>6}")
    print(header)
    print("-" * 140)
    for r in full_results:
        marker = "[*]" if "elastic" in r["rule_name"] else "   "
        print(f"{marker} {r['window_days']:>3}d {r['rule_name']:<20} {int(r['position_pct']*100):>3}% "
              f"{r['trade_count']:>4} "
              f"{r['total_return']:>+7.2f}% {r['max_drawdown']:>+6.2f}% "
              f"{r['return_to_drawdown']:>5.2f} "
              f"{r.get('r_dd_vs_baseline', 0):>+5.2f} "
              f"{r.get('dd_vs_baseline', 0):>+5.1f}% "
              f"{r['win_rate']:>5.1f}% {str(r['profit_factor']):>6} "
              f"{r['longest_loss_streak']:>4} "
              f"{r['worst_trade']:>+7.2f}% "
              f"{r.get('filtered_baseline_worst_count', '-'):>5}")
    print("-" * 140)

    # Also print half splits
    print("\n── 时间稳定性 (halves) ──")
    half_results = [r for r in all_results if r["split"] in ("first_half", "second_half")]
    half_results.sort(key=lambda r: (r["window_days"], r["split"],
                                      -r["position_pct"], 0 if "elastic" in r["rule_name"] else 1))
    for r in half_results:
        marker = "[*]" if "elastic" in r["rule_name"] else "   "
        print(f"{marker} {r['window_days']:>3}d {r['split']:<12} {r['rule_name']:<20} "
              f"pp{int(r['position_pct']*100)} "
              f"trades={r['trade_count']:>3} ret={r['total_return']:>+7.2f}% "
              f"dd={r['max_drawdown']:>+6.2f}% r/dd={r['return_to_drawdown']:.2f} "
              f"PF={r['profit_factor']} worst={r['worst_trade']:>+6.2f}%")

    # ── Build output ──
    result = {
        "config": {
            "windows": WINDOWS,
            "rules": list(RULES.keys()),
            "exit_rule": EXIT_RULE,
            "max_positions": MAX_POSITIONS,
            "position_pct_list": POSITION_PCT_LIST,
            "initial_cash": INITIAL_CASH,
            "cost_bps_per_side": COST_BPS,
            "slippage_bps_per_side": SLIPPAGE_BPS,
            "splits": ["full", "first_half", "second_half"],
            "note": (
                "Long-window validation of base_no_range_gt8 (exclude intraday_range_pct > 8%). "
                "Compares baseline (elastic_base) vs range_filter. "
                "Stability tested via first_half / second_half splits. "
                f"Elapsed: {total_elapsed}s."
            ),
            "generated_at": datetime.now().isoformat(),
        },
        "results": all_results,
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = os.path.join(ROOT, "reports", f"tail_range_filter_long_window_{ts}.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果: {out_json}")
    return result, ts, total_elapsed


if __name__ == "__main__":
    result, ts, elapsed = main()
