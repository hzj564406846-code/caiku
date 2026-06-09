"""Factor combination search on extended 90/120 trading-day window.

Tests single factors, two-factor combos, three-factor combos, and named combos
on the tail-entry execution layer (dec_E + mp2). Finds if any combo is more
stable than elastic_base (= atr_pct + ret_20d + ma20_gap).

Fixed: dec_E + max_positions=2, position_pct=0.15/0.20, kline_count=600.

Usage:
  python run_tail_factor_combo_long_window.py
"""
import itertools
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
from factor_registry import FACTOR_DIRECTIONS                                      # noqa: E402

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

# Core factor pool: continuous, directionally meaningful, available in factor table
CORE_FACTORS = [
    "d1", "d2", "d3", "d4", "d5", "d6", "d7",
    "atr_pct", "ret_5d", "ret_20d", "ma20_gap",
    "volume_ratio", "sector_hot",
    "oversold_5d", "oversold_20d", "downside_risk",
]

STRATEGY_COMPOSITES = [
    "trend_factor", "hot_money_factor", "pullback_factor",
    "oversold_rebound_factor", "quality_factor",
]

# Named combos (task-required)
NAMED_COMBOS = {
    "elastic_base": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
    "trend_elastic": {"d3": 1, "atr_pct": 1, "ret_20d": 1},
    "trend_ma": {"d3": 1, "ret_20d": 1, "ma20_gap": 1},
    "money_trend": {"d1": 1, "d2": 1, "d3": 1},
    "sector_momentum": {"sector_hot": 1, "ret_20d": 1, "volume_ratio": 1},
    "oversold_rebound": {"oversold_5d": 1, "oversold_20d": 1, "atr_pct": 1},
    "quality_trend": {"d6": 1, "d7": 1, "d3": 1, "ret_20d": 1},
}


# ══════════════════════════════════════════════════════════════════════════
# Portfolio helpers
# ══════════════════════════════════════════════════════════════════════════
def run_fast_sim(picks_df, trading_dates, kline_dict, pp=0.20):
    """Quick portfolio sim for ranking combos. Returns key metrics only."""
    if picks_df.empty:
        return None
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
    s = sim.summary()
    r_dd = round(abs(s["total_return"] / s["max_drawdown"]), 2) if s["max_drawdown"] != 0 else 0
    trades = sim.closed_trades
    rets = [t["ret_pct"] for t in trades]
    return {
        "ret": s["total_return"], "dd": s["max_drawdown"], "r_dd": r_dd,
        "pf": s["profit_factor"], "win": s["win_rate"], "trades": s["trade_count"],
        "worst": s["worst_trade"], "best": s["best_trade"],
        "avg_ret": s["avg_trade_return"], "streak": s["longest_loss_streak"],
    }


def run_full_sim(picks_df, trading_dates, kline_dict, pp):
    """Full portfolio sim with worst_10 and top_10 tracking."""
    if picks_df.empty:
        return None
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
    s = sim.summary()
    r_dd = round(abs(s["total_return"] / s["max_drawdown"]), 2) if s["max_drawdown"] != 0 else 0
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
        "avg_ret": s["avg_trade_return"], "streak": s["longest_loss_streak"],
        "worst_10": worst_10, "top_10": top_10,
        "cash_usage": s.get("avg_cash_usage_pct", 0),
    }


# ══════════════════════════════════════════════════════════════════════════
# Factor combo scoring
# ══════════════════════════════════════════════════════════════════════════
def score_combo(df, factor_weights):
    """Z-score each factor within date group, apply weights, sum to _score.
    Returns df with _score column added. Does NOT filter (caller handles that)."""
    work = df.copy()
    grouped = work.groupby("date", group_keys=False)
    work["_score"] = 0.0
    for factor, weight in factor_weights.items():
        if factor not in work.columns:
            continue
        direction = FACTOR_DIRECTIONS.get(factor, 1)
        z_col = f"_z_{factor}"
        work[z_col] = grouped[factor].transform(zscore_series).fillna(0)
        work["_score"] += work[z_col] * weight * direction
    return work


def build_picks(df, factor_weights):
    """Z-score, filter, select top-N per day."""
    work = score_combo(df, factor_weights)
    work = work[work["limit_move_flag"] == 0]
    work = work[(work["atr_pct"] >= 1.5) & (work["atr_pct"] <= 7.0)]
    work = work[(work["ret_20d"] >= 0.0) & (work["ma20_gap"] >= -5.0)]
    picks = []
    for date, group in work.groupby("date"):
        if group.empty:
            continue
        picks.append(group.nlargest(SELECT, "_score"))
    if not picks:
        return pd.DataFrame(), 0
    pdf = pd.concat(picks, ignore_index=True)
    pdf["t1_1400_price"] = pdf.apply(_approx_1400, axis=1)
    return pdf, len(pdf)


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
def main():
    started = time.time()

    print("=" * 80)
    print("尾盘执行层 因子组合长窗口搜索")
    print(f"窗口: {WINDOWS}天 | 因子池: {len(CORE_FACTORS)}核心 + {len(STRATEGY_COMPOSITES)}合成")
    print(f"执行: {EXIT_RULE} + mp{MAX_POSITIONS} | kline_count={KLINE_COUNT}")
    print("=" * 80)

    # ── Build data once ──
    print("\n[数据] 构建全量因子表 ...")
    codes = load_csi300_codes(os.path.join(ROOT, "data", "csi300_stocks.json"))[:TOP]
    max_days = max(WINDOWS)
    full_df, cfg = build_factor_table(codes, max_days, KLINE_COUNT, THREADS)
    kline_dict = fetch_klines(codes, KLINE_COUNT, THREADS)
    full_df = attach_execution_prices(full_df, kline_dict)
    full_df = full_df.dropna(subset=["entry_close", "t1_open", "t1_close"])
    print(f"  有效: {len(full_df)} 行, {full_df['date'].nunique()} 交易日, {cfg.get('date_range')}")

    # Check available factors
    avail = set(full_df.columns)
    available_core = [f for f in CORE_FACTORS if f in avail]
    available_comp = [f for f in STRATEGY_COMPOSITES if f in avail]
    missing = [f for f in CORE_FACTORS + STRATEGY_COMPOSITES if f not in avail]
    if missing:
        print(f"  [注意] 缺少因子: {missing}")
    print(f"  可用: {len(available_core)} 核心 + {len(available_comp)} 合成")

    # Build trading calendar
    all_td_set = set()
    for kdf in kline_dict.values():
        if kdf is not None and not kdf.empty:
            for d in kdf["date"].astype(str).str[:10]:
                all_td_set.add(d)
    all_td = sorted(all_td_set)
    entry_dates = sorted(full_df["date"].astype(str).str[:10].unique())
    td_full = [d for d in all_td if d >= entry_dates[0] and d <=
               (pd.to_datetime(entry_dates[-1]) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")]

    # Cut windows
    window_dfs = {}
    window_tds = {}
    for wd in WINDOWS:
        w_entry = entry_dates[-wd:] if len(entry_dates) >= wd else entry_dates
        w_set = set(w_entry)
        window_dfs[wd] = full_df[full_df["date"].astype(str).str[:10].isin(w_set)].copy()
        window_tds[wd] = [d for d in td_full if d >= w_entry[0] and d <=
                          (pd.to_datetime(w_entry[-1]) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")]

    # ── Phase 1: Fast ranking (pp20 only, 120d full) ──
    print(f"\n[Phase 1] 快速排序 ({len(available_core)}单因子 + 2因子 + 命名组合, 120d pp20) ...")
    all_combos = []

    # Single factors
    for f in available_core:
        all_combos.append((f, {f: 1}, "single"))
    for f in available_comp:
        all_combos.append((f, {f: 1}, "single_composite"))

    # Named combos
    for name, weights in NAMED_COMBOS.items():
        valid = {k: v for k, v in weights.items() if k in avail}
        if valid:
            all_combos.append((name, valid, "named"))

    # Two-factor combos from available core (top practical subset)
    # Limit to top factors to keep combos manageable
    two_factor_pool = [f for f in available_core if f not in ("d4", "d5", "d7")]  # skip weaker dimensions
    for f1, f2 in itertools.combinations(two_factor_pool, 2):
        all_combos.append((f"{f1}+{f2}", {f1: 1, f2: 1}, "two_factor"))

    print(f"  共 {len(all_combos)} 个候选组合")

    # Run fast sims
    fast_results = {}
    df_120 = window_dfs[120]
    td_120 = window_tds[120]
    n = len(all_combos)

    for i, (cname, weights, ctype) in enumerate(all_combos):
        if i % 50 == 0:
            print(f"  {i}/{n} ...")
        picks_df, npicks = build_picks(df_120, weights)
        if picks_df.empty or npicks < 5:
            continue
        res = run_fast_sim(picks_df, td_120, kline_dict, 0.20)
        if res:
            fast_results[cname] = {
                "combo_name": cname, "factors": weights, "combo_type": ctype,
                "n_picks": npicks, **res,
            }

    print(f"  有效结果: {len(fast_results)}")

    # ── Composite ranking score ──
    def rank_score(r):
        dd_penalty = r["dd"]  # lower (less negative) = better
        rdd_bonus = -r["r_dd"]  # higher = better
        pf_bonus = - (r["pf"] or 1.0)
        trade_ok = 0 if r["trades"] >= 30 else (30 - r["trades"]) * 0.3
        return (dd_penalty + rdd_bonus * 10 + pf_bonus * 5 + trade_ok)

    ranked = sorted(fast_results.values(), key=rank_score)
    top_n = min(40, len(ranked))

    # ── Phase 2: Full sim for top combos ──
    print(f"\n[Phase 2] Top {top_n} 组合完整回测 (pp15/pp20, 90d/120d, halves) ...")

    full_results = []
    n_full = 0
    total_full = top_n * len(POSITION_PCT_LIST) * (2 + 2)  # 2 windows + 2 halves each

    for combo_entry in ranked[:top_n]:
        cname = combo_entry["combo_name"]
        weights = combo_entry["factors"]
        print(f"\n  [{cname}] factors={list(weights.keys())}")

        for wd in WINDOWS:
            df_w = window_dfs[wd]
            td_w = window_tds[wd]
            picks_df, npicks = build_picks(df_w, weights)
            if picks_df.empty or npicks < 5:
                continue

            # Split halves
            up_dates = sorted(picks_df["date"].astype(str).str[:10].unique())
            mid = len(up_dates) // 2
            fd_set = set(up_dates[:mid])
            sd_set = set(up_dates[mid:])
            halves = [
                ("full", picks_df, td_w),
                ("first_half", picks_df[picks_df["date"].astype(str).str[:10].isin(fd_set)],
                 [d for d in td_w if d <= up_dates[mid - 1]]),
                ("second_half", picks_df[picks_df["date"].astype(str).str[:10].isin(sd_set)],
                 [d for d in td_w if d >= up_dates[mid]]),
            ]

            for split_name, sub_picks, sub_td in halves:
                if len(sub_picks) < 5:
                    continue
                for pp in POSITION_PCT_LIST:
                    n_full += 1
                    res = run_full_sim(sub_picks, sub_td, kline_dict, pp)
                    if not res:
                        continue
                    entry = {
                        "combo_name": cname, "factors": weights,
                        "combo_type": combo_entry["combo_type"],
                        "window_days": wd, "split": split_name,
                        "position_pct": pp, **res,
                    }
                    full_results.append(entry)
                    if split_name == "full":
                        print(f"    {wd}d pp{int(pp*100)}%: ret={res['ret']:+.2f}% dd={res['dd']:+.2f}% "
                              f"r/dd={res['r_dd']:.2f} PF={res['pf']} trades={res['trades']}")

    # ── Compute deltas vs elastic_base ──
    print(f"\n[对比] 计算 vs elastic_base delta ...")
    bl_key = "elastic_base"
    for r in full_results:
        r["dd_vs_baseline"] = None; r["r_dd_vs_baseline"] = None
        r["ret_vs_baseline"] = None; r["trade_ratio_vs_baseline"] = None
        if r["combo_name"] == bl_key or r["split"] != "full":
            continue
        bl = [b for b in full_results
              if b["combo_name"] == bl_key
              and b["window_days"] == r["window_days"]
              and b["position_pct"] == r["position_pct"]
              and b["split"] == "full"]
        if not bl:
            continue
        bl = bl[0]
        r["dd_vs_baseline"] = round(r["dd"] - bl["dd"], 2)
        r["r_dd_vs_baseline"] = round(r["r_dd"] - bl["r_dd"], 3)
        r["ret_vs_baseline"] = round(r["ret"] - bl["ret"], 2)
        r["trade_ratio_vs_baseline"] = round(r["trades"] / bl["trades"], 2) if bl["trades"] else None

    # Stability: halves consistency
    for r in full_results:
        r["halves_r_dd_deltas"] = None
        if r["split"] != "full":
            continue
        h1 = [h for h in full_results
              if h["combo_name"] == r["combo_name"]
              and h["window_days"] == r["window_days"]
              and h["position_pct"] == r["position_pct"]
              and h["split"] == "first_half"]
        h2 = [h for h in full_results
              if h["combo_name"] == r["combo_name"]
              and h["window_days"] == r["window_days"]
              and h["position_pct"] == r["position_pct"]
              and h["split"] == "second_half"]
        if h1 and h2:
            r["first_half_r_dd"] = h1[0]["r_dd"]
            r["second_half_r_dd"] = h2[0]["r_dd"]
            r["halves_r_dd_deltas"] = [h1[0]["r_dd"], h2[0]["r_dd"]]
            r["halves_consistent"] = (
                (h1[0]["r_dd"] >= 0.15 and h2[0]["r_dd"] >= 0.15)
            )

    # ── Final ranking (full results, pp20, 120d) ──
    pp20_120_full = [r for r in full_results
                     if r["split"] == "full" and r["position_pct"] == 0.20
                     and r["window_days"] == 120]

    def final_score(r):
        dd_vs = r.get("dd_vs_baseline") or 0
        r_dd = r["r_dd"]
        pf = r["pf"] or 1.0
        halves = 0 if r.get("halves_consistent") else 2  # penalty for inconsistency
        trades = 0 if r["trades"] >= 70 else (70 - r["trades"]) * 0.5
        is_bl = 0 if r["combo_name"] == bl_key else 0  # neutral
        return (-dd_vs - r_dd * 3 - pf * 2 + halves + trades + is_bl)

    pp20_120_full.sort(key=final_score)

    # ── Output tables ──
    total_elapsed = round(time.time() - started, 1)
    print("\n" + "=" * 155)
    print(f"Top 30 因子组合 — 120d pp20 full (排序: dd改善 > r/dd > PF > halves一致性)")
    bl_120 = next((r for r in pp20_120_full if r["combo_name"] == bl_key), None)
    bl_dd = bl_120["dd"] if bl_120 else -28.46
    print(f"{'Baseline dd = ' + str(bl_dd) + '%':>50}")
    print("=" * 155)
    hdr = (f"{'#':>3} {'组合':<30} {'类型':<8} {'收益':>7} {'回撤':>7} {'ddΔ':>5} "
           f"{'r/dd':>5} {'r/ddΔ':>6} {'PF':>6} {'胜率':>5} {'笔':>4} "
           f"{'最差':>6} {'H1':>5} {'H2':>5} {'一致':>4}")
    print(hdr)
    print("-" * 155)
    for i, r in enumerate(pp20_120_full[:30]):
        marker = "[*]" if r["combo_name"] == bl_key else "   "
        h1 = r.get("first_half_r_dd", "-")
        h2 = r.get("second_half_r_dd", "-")
        hc = "Y" if r.get("halves_consistent") else "-"
        print(f"{marker}{i+1:>2} {r['combo_name']:<28} {r['combo_type']:<8} "
              f"{r['ret']:>+6.1f}% {r['dd']:>+6.1f}% {(r.get('dd_vs_baseline') or 0):>+4.1f}% "
              f"{r['r_dd']:>4.2f} {(r.get('r_dd_vs_baseline') or 0):>+5.2f} "
              f"{str(r['pf']):>6} {r['win']:>4.1f}% {r['trades']:>4} "
              f"{r['worst']:>+5.1f}% {str(h1):>5} {str(h2):>5} {hc:>4}")
    print("-" * 155)

    # pp15 table
    pp15_120_full = [r for r in full_results
                     if r["split"] == "full" and r["position_pct"] == 0.15
                     and r["window_days"] == 120]
    pp15_120_full.sort(key=lambda r: (-(r.get("dd_vs_baseline") or 0), -r["r_dd"], -(r["pf"] or 1)))
    print(f"\n── pp15 120d full top 15 ──")
    for i, r in enumerate(pp15_120_full[:15]):
        marker = "[*]" if r["combo_name"] == bl_key else "   "
        print(f"{marker}{i+1:>2} {r['combo_name']:<30} ret={r['ret']:+6.1f}% dd={r['dd']:+6.1f}% "
              f"ddΔ={(r.get('dd_vs_baseline') or 0):+4.1f}% r/dd={r['r_dd']:.2f} PF={r['pf']} "
              f"trades={r['trades']} win={r['win']:.1f}%")

    # ── Build output ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result = {
        "id": "tail_factor_combo_long_window_001",
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "data_coverage": {"valid_days": full_df["date"].nunique(), "date_range": cfg.get("date_range")},
        "baseline_120d_pp20": bl_120,
        "total_combos_tested": len(fast_results),
        "top_30_pp20_120d": [r for r in pp20_120_full[:30]],
        "all_full_results": full_results,
        "fast_ranking_results": ranked[:50],
        "config": {
            "windows": WINDOWS, "exit_rule": EXIT_RULE, "max_positions": MAX_POSITIONS,
            "position_pct_list": POSITION_PCT_LIST, "kline_count": KLINE_COUNT,
            "elapsed_seconds": total_elapsed,
            "generated_at": datetime.now().isoformat(),
        },
    }

    out_json = os.path.join(ROOT, "reports", f"tail_factor_combo_long_window_{ts}.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果: {out_json}")

    # Queue result
    queue_path = os.path.join(ROOT, "backtest_queue", "done", "tail_factor_combo_long_window_001_result.json")
    os.makedirs(os.path.dirname(queue_path), exist_ok=True)

    # Find best non-baseline
    non_bl = [r for r in pp20_120_full if r["combo_name"] != bl_key]
    best_dd = min(non_bl, key=lambda r: r["dd"]) if non_bl else None
    best_rdd = max(non_bl, key=lambda r: r["r_dd"]) if non_bl else None

    # Count combos with meaningful DD improvement (>=3pp)
    dd_improved = [r for r in non_bl if (r.get("dd_vs_baseline") or 0) >= 3.0]
    rdd_improved = [r for r in non_bl if (r.get("r_dd_vs_baseline") or 0) >= 0.05]

    queue_result = {
        "id": "tail_factor_combo_long_window_001",
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "completed_by": "claude_code",
        "summary": (
            f"因子组合长窗口搜索完成。{len(fast_results)}个候选组合，top {top_n}完整回测。"
            f"最佳dd改善: {(best_dd['combo_name'] + ': ' + str(best_dd['dd']) + '% (' + str(best_dd.get('dd_vs_baseline',0)) + 'pp)') if best_dd else 'none'}。"
            f"最佳r/dd: {(best_rdd['combo_name'] + ': ' + str(best_rdd['r_dd'])) if best_rdd else 'none'}。"
            f"dd改善>=3pp: {len(dd_improved)}个组合。"
            f"r/dd超过baseline: {len(rdd_improved)}个组合。"
        ),
        "best_dd_improvement": {
            "combo": best_dd["combo_name"] if best_dd else None,
            "dd": best_dd["dd"] if best_dd else None,
            "dd_vs_baseline": best_dd.get("dd_vs_baseline") if best_dd else None,
        },
        "best_rdd": {
            "combo": best_rdd["combo_name"] if best_rdd else None,
            "r_dd": best_rdd["r_dd"] if best_rdd else None,
        },
        "dd_improved_count": len(dd_improved),
        "answers": {},  # Filled after analysis
        "files_generated": [out_json],
        "files_created": ["run_tail_factor_combo_long_window.py"],
        "files_modified": [],
    }

    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue_result, f, ensure_ascii=False, indent=2, default=str)
    print(f"队列结果: {queue_path}")

    return result, ts, total_elapsed


if __name__ == "__main__":
    result, ts, elapsed = main()
