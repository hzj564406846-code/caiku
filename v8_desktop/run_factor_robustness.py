"""Discover and stress-test factor combinations.

This script is the next research funnel after run_factor_research.py:
1. Build the same point-in-time factor table.
2. Enumerate single factors and factor combinations from the selected pool.
3. Rank them by a simple edge score across 5d/10d forward returns.
4. Re-test the discovered candidates across breadth, limit-move filtering,
   and time splits.
"""
import argparse
import itertools
import json
import os
from datetime import datetime

import pandas as pd

from run_factor_research import (
    FACTOR_DIRECTIONS,
    PRIMITIVE_FACTORS,
    STRATEGY_FACTORS,
    build_factor_table,
    load_csi300_codes,
    selected_stats,
    zscore_series,
)


DEFAULT_SEED_CANDIDATES = [
    "score",
    "atr_pct",
    "ret_20d",
    "ma20_gap",
    "d3+atr_pct",
    "atr_pct+ma20_gap",
    "atr_pct+ret_20d",
    "atr_pct+ret_20d+ma20_gap",
    "atr_pct+v9_trend_raw",
    "atr_pct+price_above_ma60",
    "ret_20d+intraday_range_pct",
]


def parse_factor_pool(spec):
    if spec == "ALL_PRIMITIVE":
        return list(PRIMITIVE_FACTORS)
    if spec == "ALL":
        seen = []
        for factor in PRIMITIVE_FACTORS + STRATEGY_FACTORS + ["score"]:
            if factor not in seen:
                seen.append(factor)
        return seen
    return [part.strip() for part in spec.split(",") if part.strip()]


def factor_score(df, spec):
    factors = [part.strip() for part in spec.split("+") if part.strip()]
    if len(factors) == 1:
        return df[factors[0]] * FACTOR_DIRECTIONS.get(factors[0], 1)

    grouped = df.groupby("date", group_keys=False)
    score = pd.Series(0.0, index=df.index)
    for factor in factors:
        direction = FACTOR_DIRECTIONS.get(factor, 1)
        score += grouped[factor].transform(zscore_series).fillna(0) * direction
    return score


def evaluate_candidate(df, spec, top_pct):
    work = df.copy()
    col = "__candidate_score"
    work[col] = factor_score(work, spec)
    return selected_stats(work, col, top_pct)


def build_specs(factors, max_combo, include_single=True):
    specs = []
    if include_single:
        specs.extend(factors)
    for size in range(2, max_combo + 1):
        for combo in itertools.combinations(factors, size):
            specs.append("+".join(combo))
    return specs


def edge_score(stats):
    h5 = stats.get("ret_5d", {})
    h10 = stats.get("ret_10d", {})
    h3 = stats.get("ret_3d", {})
    return round(
        h5.get("avg", 0)
        + 0.60 * h10.get("avg", 0)
        + 0.25 * h5.get("median", 0)
        + 0.15 * h10.get("median", 0)
        + 0.025 * (h5.get("win_rate", 0) - 50)
        + 0.015 * (h10.get("win_rate", 0) - 50)
        + 0.20 * h3.get("avg", 0),
        4,
    )


def discover_candidates(df, specs, top_pct, min_count, keep):
    rows = []
    results = {}
    for spec in specs:
        stats = evaluate_candidate(df, spec, top_pct)
        h5 = stats.get("ret_5d", {})
        if h5.get("n", 0) < min_count:
            continue
        results[spec] = stats
        rows.append({
            "factor": spec,
            "size": len(spec.split("+")),
            "score": edge_score(stats),
            "count": h5.get("n", 0),
            "ret_5d_avg": h5.get("avg", 0),
            "ret_5d_median": h5.get("median", 0),
            "ret_5d_win_rate": h5.get("win_rate", 0),
            "ret_10d_avg": stats.get("ret_10d", {}).get("avg", 0),
            "ret_10d_median": stats.get("ret_10d", {}).get("median", 0),
            "ret_10d_win_rate": stats.get("ret_10d", {}).get("win_rate", 0),
        })
    rows.sort(key=lambda r: (r["score"], r["ret_5d_avg"], r["ret_10d_avg"], r["ret_5d_win_rate"]), reverse=True)
    return rows[:keep], results


def run_case(df, candidates, top_pcts):
    out = {}
    for spec in candidates:
        out[spec] = {}
        for top_pct in top_pcts:
            out[spec][f"top_{int(top_pct * 100)}"] = evaluate_candidate(df, spec, top_pct)
    return out


def summarize_case(case_result, horizon="ret_5d"):
    rows = []
    for spec, top_map in case_result.items():
        for top_label, stats in top_map.items():
            h = stats.get(horizon, {})
            if not h:
                continue
            rows.append({
                "factor": spec,
                "top": top_label,
                "count": h.get("n", 0),
                "avg": h.get("avg", 0),
                "median": h.get("median", 0),
                "win_rate": h.get("win_rate", 0),
            })
    return sorted(rows, key=lambda r: (r["avg"], r["win_rate"], r["median"]), reverse=True)


def stability_summary(results, horizon="ret_5d"):
    rows = []
    case_names = list(results.keys())
    all_keys = set()
    for payload in results.values():
        for spec, top_map in payload["results"].items():
            for top_label in top_map:
                all_keys.add((spec, top_label))

    for spec, top_label in sorted(all_keys):
        vals = []
        wins = []
        counts = []
        positive_cases = 0
        for case_name in case_names:
            h = results[case_name]["results"].get(spec, {}).get(top_label, {}).get(horizon, {})
            if not h:
                continue
            avg = h.get("avg", 0)
            vals.append(avg)
            wins.append(h.get("win_rate", 0))
            counts.append(h.get("n", 0))
            if avg > 0:
                positive_cases += 1
        if not vals:
            continue
        mean_avg = sum(vals) / len(vals)
        worst_avg = min(vals)
        mean_win = sum(wins) / len(wins)
        rows.append({
            "factor": spec,
            "top": top_label,
            "cases": len(vals),
            "positive_cases": positive_cases,
            "mean_avg": round(mean_avg, 2),
            "worst_avg": round(worst_avg, 2),
            "mean_win_rate": round(mean_win, 1),
            "min_count": min(counts),
            "stability_score": round(mean_avg + min(0, worst_avg) * 0.5 + 0.025 * (mean_win - 50), 4),
        })
    return sorted(
        rows,
        key=lambda r: (r["positive_cases"], r["stability_score"], r["worst_avg"], r["mean_win_rate"]),
        reverse=True,
    )


def run(args):
    root = os.path.dirname(os.path.abspath(__file__))
    codes = load_csi300_codes(os.path.join(root, "data", "csi300_stocks.json"))[:args.top]
    df, cfg = build_factor_table(codes, args.days, args.kline_count, args.threads)
    dates = sorted(df["date"].unique())
    mid = dates[len(dates) // 2]

    factor_pool = parse_factor_pool(args.combo_factors)
    specs = build_specs(factor_pool, args.max_combo, include_single=args.include_single)
    discovered, discovery_results = discover_candidates(
        df,
        specs,
        args.discovery_top_pct,
        args.min_count,
        args.keep,
    )

    seed_candidates = [c.strip() for c in args.seed_candidates.split(",") if c.strip()]
    discovered_candidates = [row["factor"] for row in discovered]
    candidates = []
    for spec in discovered_candidates + seed_candidates:
        if spec not in candidates:
            candidates.append(spec)

    top_pcts = [float(x) for x in args.top_pcts.split(",")]
    cases = {
        "all": df,
        "exclude_limit_move": df[df["limit_move_flag"] == 0].copy(),
        "first_half": df[df["date"] <= mid].copy(),
        "second_half": df[df["date"] > mid].copy(),
    }

    results = {}
    for name, case_df in cases.items():
        results[name] = {
            "rows": int(len(case_df)),
            "date_range": f"{case_df['date'].min()} ~ {case_df['date'].max()}" if len(case_df) else "",
            "results": run_case(case_df, candidates, top_pcts),
        }

    return {
        "config": {
            **cfg,
            "generated_at": datetime.now().isoformat(),
            "records": int(len(df)),
            "factor_pool": factor_pool,
            "factor_pool_count": len(factor_pool),
            "spec_count": len(specs),
            "discovery_top_pct": args.discovery_top_pct,
            "top_pcts": top_pcts,
            "max_combo": args.max_combo,
            "min_count": args.min_count,
            "keep": args.keep,
            "selected_candidates": candidates,
            "split_date": mid,
        },
        "discovery": {
            "top": discovered,
            "raw_results": {row["factor"]: discovery_results[row["factor"]] for row in discovered},
        },
        "cases": results,
        "summary_5d": {name: summarize_case(payload["results"], "ret_5d")[:20] for name, payload in results.items()},
        "summary_10d": {name: summarize_case(payload["results"], "ret_10d")[:20] for name, payload in results.items()},
        "stability_5d": stability_summary(results, "ret_5d")[:30],
        "stability_10d": stability_summary(results, "ret_10d")[:30],
    }


def print_report(result):
    cfg = result["config"]
    print("=" * 78)
    print("Factor combination discovery and robustness")
    print("=" * 78)
    print(f"Range: {cfg['date_range']} | stocks: {cfg['codes_valid']}/{cfg['codes_total']} | rows: {cfg['records']}")
    print(f"Pool: {cfg['factor_pool_count']} factors | specs tested: {cfg['spec_count']} | max_combo: {cfg['max_combo']}")
    print(f"Discovery top_pct: {cfg['discovery_top_pct']:.0%} | robustness top_pcts: {cfg['top_pcts']}")
    print()
    print("Discovered strongest candidates:")
    for row in result["discovery"]["top"][:15]:
        print(
            f"- {row['factor']} | score {row['score']:+.2f} | n={row['count']} | "
            f"5d {row['ret_5d_avg']:+.2f}%/{row['ret_5d_win_rate']:.1f}% | "
            f"10d {row['ret_10d_avg']:+.2f}%/{row['ret_10d_win_rate']:.1f}%"
        )
    print()
    print("Robustness leaders 5D:")
    for row in result["stability_5d"][:15]:
        print(
            f"- {row['factor']} {row['top']} | cases {row['positive_cases']}/{row['cases']} | "
            f"mean {row['mean_avg']:+.2f}% | worst {row['worst_avg']:+.2f}% | "
            f"win {row['mean_win_rate']:.1f}%"
        )


def main():
    parser = argparse.ArgumentParser(description="Discover and stress-test strongest factor combinations")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--top", type=int, default=120)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--kline-count", type=int, default=400)
    parser.add_argument("--top-pcts", default="0.1,0.2,0.3")
    parser.add_argument("--combo-factors", default="ALL")
    parser.add_argument("--max-combo", type=int, default=3)
    parser.add_argument("--include-single", action="store_true")
    parser.add_argument("--discovery-top-pct", type=float, default=0.2)
    parser.add_argument("--min-count", type=int, default=30)
    parser.add_argument("--keep", type=int, default=20)
    parser.add_argument("--seed-candidates", default=",".join(DEFAULT_SEED_CANDIDATES))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    result = run(args)
    print_report(result)

    root = os.path.dirname(os.path.abspath(__file__))
    output = args.output or os.path.join(root, "reports", f"factor_robustness_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nFull result saved: {output}")


if __name__ == "__main__":
    main()
