"""Factor combination & individual-stock risk filter search.

Extends run_tail_portfolio_backtest.py's pipeline to test factor variants
and per-stock risk filters. Target: reduce max_drawdown & worst_trade
through better stock selection, NOT market timing.

Fixed: dec_E + max_positions=2. Tests pp=15% and pp=20%.

Usage:
  python run_tail_factor_risk_search.py
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
from run_tail_entry_backtest import (                                             # noqa: E402
    add_candidate_scores, attach_execution_prices,
)
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
DAYS = 45
TOP = 60
SELECT = 5
THREADS = 8
KLINE_COUNT = 260

# ══════════════════════════════════════════════════════════════════════════
# Rule definitions
# ══════════════════════════════════════════════════════════════════════════
# Each rule has:
#   factor_formula: dict of {column: weight} for z-scored components
#   pre_filters: list of (column, op, value) applied BEFORE top-N selection
#   description: human-readable

RULES = {
    # ── Baseline ──
    "elastic_base": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [],  # uses default: atr 1.5-7, ret>=0, ma20>=-5, no limit
        "desc": "Baseline: z(atr)+z(ret20)+z(ma20_gap)",
    },
    # ── Factor variants ──
    "base_plus_d3": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1, "d3": 0.5},
        "pre_filters": [],
        "desc": "Baseline + 0.5×z(d3) 趋势维度",
    },
    "base_plus_d7": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1, "d7": -0.5},
        "pre_filters": [],
        "desc": "Baseline - 0.5×z(d7) 惩罚高风险",
    },
    "base_minus_atr_penalty": {
        "factor": {"atr_pct": -0.5, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [],
        "desc": "z(ret20)+z(ma20) - 0.5×z(atr) 低波偏好",
    },
    "base_plus_volume": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1, "volume_ratio": 0.5},
        "pre_filters": [],
        "desc": "Baseline + 0.5×z(volume_ratio) 量能确认",
    },
    "base_ret20_only": {
        "factor": {"ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [],
        "desc": "只用趋势 z(ret20)+z(ma20) 去掉波动",
    },
    # ── ATR caps (filter, not factor change) ──
    "base_atr_cap5": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("atr_pct", "<=", 5.0)],
        "desc": "Baseline + ATR<=5",
    },
    "base_atr_cap6": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("atr_pct", "<=", 6.0)],
        "desc": "Baseline + ATR<=6",
    },
    # ── Upper shadow filters ──
    "base_no_upper_shadow3": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("upper_shadow_pct", "<=", 3.0)],
        "desc": "Baseline + 排除上影线>3%",
    },
    "base_no_upper_shadow5": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("upper_shadow_pct", "<=", 5.0)],
        "desc": "Baseline + 排除上影线>5%",
    },
    # ── Daily change filters ──
    "base_no_change_gt5": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("change_pct", "<=", 5.0)],
        "desc": "Baseline + 排除单日涨幅>5%",
    },
    "base_no_change_gt7": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("change_pct", "<=", 7.0)],
        "desc": "Baseline + 排除单日涨幅>7%",
    },
    # ── Intraday range filters ──
    "base_no_range_gt8": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("intraday_range_pct", "<=", 8.0)],
        "desc": "Baseline + 排除日内振幅>8%",
    },
    "base_no_range_gt10": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("intraday_range_pct", "<=", 10.0)],
        "desc": "Baseline + 排除日内振幅>10%",
    },
    # ── Volume spike filter ──
    "base_no_vol_spike": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("vol_spike_ratio", "<=", 3.0)],
        "desc": "Baseline + 排除放量比>3",
    },
    # ── Limit move filter (already in baseline, explicit test) ──
    "base_strict_limit": {
        "factor": {"atr_pct": 1, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("limit_move_flag", "==", 0)],
        "desc": "Baseline + 显式排除涨跌停(确认)",
    },
    # ── Combined: best ideas ──
    "lowvol_no_shadow3": {
        "factor": {"atr_pct": -0.5, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("upper_shadow_pct", "<=", 3.0), ("atr_pct", "<=", 7.0)],
        "desc": "低波+排除上影线>3%",
    },
    "ret20_no_change_gt5": {
        "factor": {"ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("change_pct", "<=", 5.0)],
        "desc": "纯趋势+排除涨幅>5%",
    },
    "lowvol_atr_cap5": {
        "factor": {"atr_pct": -0.5, "ret_20d": 1, "ma20_gap": 1},
        "pre_filters": [("atr_pct", "<=", 5.0)],
        "desc": "低波因子+ATR<=5双重压制",
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Data enrichment
# ══════════════════════════════════════════════════════════════════════════
def enrich_factor_df(df, kline_dict):
    """Add per-stock daily change_pct from kline data (T vs T-1 close)."""
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
        change = (curr_close - prev_close) / prev_close * 100 if prev_close else 0.0
        changes.append(round(change, 2))
    df["change_pct"] = changes
    return df


# ══════════════════════════════════════════════════════════════════════════
# Rule-aware pick builder
# ══════════════════════════════════════════════════════════════════════════
def build_picks_for_rule(full_df, rule_config, rule_name, all_dates, kline_dict):
    """Build picks for a single rule from the pre-built factor dataframe.

    CRITICAL: Z-scores are computed on the FULL date group BEFORE any filtering,
    matching the original build_picks pipeline. This ensures scores reflect
    each stock's position relative to ALL peers, not a filtered subset.

    Returns: picks_df, filtered_stats_dict, trading_dates
    """
    df = full_df.copy()
    total_before = len(df)

    # ── Step 1: Z-score on FULL date group (before any filtering) ──
    factor_formula = rule_config["factor"]
    grouped_full = df.groupby("date", group_keys=False)

    z_cols = {}
    for col in factor_formula:
        if col in df.columns:
            z_name = f"_z_{col}"
            df[z_name] = grouped_full[col].transform(zscore_series).fillna(0)
            z_cols[col] = z_name

    # Compute combined score on FULL population
    df["_score"] = 0.0
    for col, weight in factor_formula.items():
        if col in z_cols:
            df["_score"] += df[z_cols[col]] * weight

    # ── Step 2: Apply default base filters ──
    df = df[df["limit_move_flag"] == 0]
    df = df[(df["atr_pct"] >= 1.5) & (df["atr_pct"] <= 7.0)]
    df = df[(df["ret_20d"] >= 0.0) & (df["ma20_gap"] >= -5.0)]
    after_base = len(df)

    # ── Step 3: Apply rule-specific pre-filters ──
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
        elif op == "<":
            df = df[df[col] < val]
        elif op == ">":
            df = df[df[col] > val]
    after_filters = len(df)

    # ── Step 4: Select top-N per day ──
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

    # Attach 14:00 price
    picks_df["t1_1400_price"] = picks_df.apply(_approx_1400, axis=1)

    # Build trading calendar
    all_trading_dates = set()
    for kdf in kline_dict.values():
        if kdf is not None and not kdf.empty:
            for d in kdf["date"].astype(str).str[:10]:
                all_trading_dates.add(d)
    trading_dates = sorted(all_trading_dates)
    entry_dates = sorted(df["date"].astype(str).str[:10].unique())
    if entry_dates:
        first_entry = entry_dates[0]
        last_entry = entry_dates[-1]
        trading_dates = [d for d in trading_dates if d >= first_entry and d <=
                         (pd.to_datetime(last_entry) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")]

    stats = {
        "total_before": total_before,
        "after_base": after_base,
        "after_filters": after_filters,
        "picks": len(picks_df),
        "filtered_signals": total_before - after_filters,
        "trading_dates": len(trading_dates),
    }
    return picks_df, stats, trading_dates


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
def main():
    started = time.time()
    total_rules = len(RULES)
    total_configs = total_rules * len(POSITION_PCT_LIST)

    print("=" * 80)
    print("尾盘买入 因子组合与个股风险过滤搜索")
    print(f"执行框架: {EXIT_RULE} + mp{MAX_POSITIONS} | 因子规则: {total_rules} | 仓位: {POSITION_PCT_LIST}")
    print(f"总配置数: {total_configs}")
    print("=" * 80)

    # ── Build full factor table ONCE ──
    print("\n[数据] 构建全量因子表 ...")
    codes = load_csi300_codes(os.path.join(ROOT, "data", "csi300_stocks.json"))[:TOP]
    df, cfg = build_factor_table(codes, DAYS, KLINE_COUNT, THREADS)
    kline_dict = fetch_klines(codes, KLINE_COUNT, THREADS)
    df = attach_execution_prices(df, kline_dict)
    df = df.dropna(subset=["entry_close", "t1_open", "t1_close"])
    df = enrich_factor_df(df, kline_dict)
    print(f"  全量因子表: {len(df)} 行, {len(df.columns)} 列, 区间: {cfg.get('date_range', '?')}")

    # Check available columns
    available_cols = set(df.columns)
    for rule_name, rule_config in RULES.items():
        missing = [c for c in rule_config["factor"] if c not in available_cols]
        if missing:
            print(f"  [警告] {rule_name}: 缺少因子列 {missing}")
        missing_filt = [c for c, _, _ in rule_config.get("pre_filters", []) if c not in available_cols]
        if missing_filt:
            print(f"  [警告] {rule_name}: 缺少过滤列 {missing_filt}")

    # Build trading calendar from kline data
    all_trading_dates = set()
    for kdf in kline_dict.values():
        if kdf is not None and not kdf.empty:
            for d in kdf["date"].astype(str).str[:10]:
                all_trading_dates.add(d)
    all_dates = sorted(all_trading_dates)
    entry_dates = sorted(df["date"].astype(str).str[:10].unique())
    if entry_dates:
        first_entry = entry_dates[0]
        last_entry = entry_dates[-1]
        all_dates = [d for d in all_dates if d >= first_entry and d <=
                     (pd.to_datetime(last_entry) + pd.Timedelta(days=10)).strftime("%Y-%m-%d")]

    # ── Run baseline first to get worst trades reference ──
    print("\n[Baseline] 先跑 elastic_base 获取最差交易参考 ...")
    baseline_picks, baseline_stats, base_trading_dates = build_picks_for_rule(
        df, RULES["elastic_base"], "elastic_base", all_dates, kline_dict)
    print(f"  baseline picks: {baseline_stats['picks']} 笔, 过滤: {baseline_stats['filtered_signals']} 信号")

    # Index baseline picks by date
    base_picks_by_date = defaultdict(list)
    for _, row in baseline_picks.iterrows():
        d = str(row["date"])
        base_picks_by_date[d].append({
            "code": row["code"], "date": d,
            "score": float(row.get("_score", 0)),
            "entry_close": row["entry_close"], "entry_low": row["entry_low"],
            "t1_date": str(row.get("t1_date", "")), "t2_date": str(row.get("t2_date", "")),
            "t1_close": row.get("t1_close"), "t2_close": row.get("t2_close"),
            "t1_1400_price": row.get("t1_1400_price"),
        })

    # Run baseline portfolio sim to get worst trades (pp20 only for reference)
    baseline_worst_trades = []
    for pp in [0.20]:  # Only pp20 for worst-trade reference
        sim = PortfolioSimulator(INITIAL_CASH, MAX_POSITIONS, pp, COST_BPS, SLIPPAGE_BPS)
        sim.run(base_picks_by_date, base_trading_dates, EXIT_RULE, kline_dict)
        trades = sim.closed_trades
        trades_sorted = sorted(trades, key=lambda t: t["ret_pct"])
        for t in trades_sorted[:5]:
            baseline_worst_trades.append({
                "code": t["code"], "entry_date": t["entry_date"],
                "exit_date": t["exit_date"], "exit_type": t["exit_type"],
                "ret_pct": t["ret_pct"],
            })

    # Deduplicate baseline worst trades
    seen = set()
    baseline_worst_unique = []
    for t in baseline_worst_trades:
        key = (t["code"], t["entry_date"])
        if key not in seen:
            seen.add(key)
            baseline_worst_unique.append(t)
    baseline_worst_5 = baseline_worst_unique[:5]
    print(f"  baseline worst 5 trades:")
    for t in baseline_worst_5:
        print(f"    {t['code']} {t['entry_date']} → {t['exit_date']} ({t['exit_type']}): {t['ret_pct']:+.2f}%")

    # ── Run all rules ──
    print(f"\n[回测] {total_rules} 规则 × {len(POSITION_PCT_LIST)} 仓位 = {total_configs} 配置\n")

    all_configs = []
    idx = 0

    for rule_name, rule_config in RULES.items():
        # Build picks for this rule
        picks_df, rule_stats, trading_dates = build_picks_for_rule(
            df, rule_config, rule_name, all_dates, kline_dict)

        if picks_df.empty:
            print(f"  [跳过] {rule_name}: 无有效选股")
            continue

        # Index picks by date
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

        for pp in POSITION_PCT_LIST:
            idx += 1
            label = f"{rule_name}_pp{int(pp*100)}"
            print(f"  [{idx:2d}/{total_configs}] {label:<40} ...", end=" ", flush=True)
            t0 = time.time()

            sim = PortfolioSimulator(INITIAL_CASH, MAX_POSITIONS, pp, COST_BPS, SLIPPAGE_BPS)
            sim.run(picks_by_date, trading_dates, EXIT_RULE, kline_dict)
            summ = sim.summary()

            # ── Track worst trades ──
            closed = sim.closed_trades
            closed_sorted = sorted(closed, key=lambda t: t["ret_pct"])
            worst_5 = [{"code": t["code"], "entry_date": t["entry_date"],
                        "exit_date": t["exit_date"], "ret_pct": round(t["ret_pct"], 2),
                        "exit_type": t["exit_type"]}
                       for t in closed_sorted[:5]]

            # Check which baseline worst trades were filtered out
            filtered_from_baseline = []
            baseline_codes_dates = {(t["code"], t["entry_date"]) for t in baseline_worst_5}
            picks_codes_dates = {(row["code"], str(row["date"])) for _, row in picks_df.iterrows()}
            for t in baseline_worst_5:
                key = (t["code"], t["entry_date"])
                if key not in picks_codes_dates:
                    filtered_from_baseline.append({
                        "code": t["code"], "entry_date": t["entry_date"],
                        "baseline_ret": t["ret_pct"], "status": "FILTERED_OUT",
                    })
                else:
                    # Check if still picked but result changed
                    this_trade = [ct for ct in closed if ct["code"] == t["code"]
                                  and ct["entry_date"] == t["entry_date"]]
                    if this_trade:
                        filtered_from_baseline.append({
                            "code": t["code"], "entry_date": t["entry_date"],
                            "baseline_ret": t["ret_pct"],
                            "new_ret": round(this_trade[0]["ret_pct"], 2),
                            "status": "STILL_PRESENT",
                        })

            # ── Build enriched summary ──
            enriched = {
                "rule_name": rule_name,
                "description": rule_config["desc"],
                "position_pct": pp,
                "total_return": summ["total_return"],
                "max_drawdown": summ["max_drawdown"],
                "return_to_drawdown": round(
                    abs(summ["total_return"] / summ["max_drawdown"])
                    if summ["max_drawdown"] != 0 else 0, 2),
                "trade_count": summ["trade_count"],
                "filtered_signal_count": rule_stats.get("filtered_signals", 0),
                "win_rate": summ["win_rate"],
                "avg_trade_return": summ["avg_trade_return"],
                "median_trade_return": summ["median_trade_return"],
                "profit_factor": summ["profit_factor"],
                "longest_loss_streak": summ["longest_loss_streak"],
                "worst_trade": summ["worst_trade"],
                "best_trade": summ["best_trade"],
                "worst_5_trades": worst_5,
                "filtered_worst_trades_from_baseline": filtered_from_baseline,
                "baseline_worst_filtered_count": sum(
                    1 for f in filtered_from_baseline if f["status"] == "FILTERED_OUT"),
                "avg_cash_usage": summ.get("avg_cash_usage_pct", 0),
                "max_concurrent_positions": summ.get("max_concurrent_positions", 0),
                "equity_curve_tail": summ.get("equity_curve_tail", []),
            }
            all_configs.append(enriched)

            elapsed = time.time() - t0
            print(f"trades={summ.get('trade_count',0):>3} "
                  f"ret={summ.get('total_return',0):>+6.2f}% "
                  f"dd={summ.get('max_drawdown',0):>+6.2f}% "
                  f"r/dd={enriched['return_to_drawdown']:.2f} "
                  f"win={summ.get('win_rate',0):.1f}% "
                  f"PF={str(summ.get('profit_factor','-')):>5} "
                  f"worst={summ.get('worst_trade',0):>+6.2f}% "
                  f"({elapsed:.1f}s)")

    total_elapsed = round(time.time() - started, 1)

    # ── Sort by composite score ──
    # Baseline first, then by return_to_drawdown, then by max_drawdown (less negative better)
    def composite_sort_key(cfg):
        is_baseline = 0 if cfg["rule_name"] == "elastic_base" else 1
        r_dd = -cfg.get("return_to_drawdown", 0)
        dd = cfg.get("max_drawdown", 0)  # more negative = worse
        ret = -cfg.get("total_return", 0)
        # Lower trade_count penalty
        tc_penalty = 0 if cfg.get("trade_count", 0) >= 25 else (25 - cfg["trade_count"]) * 0.5
        return (is_baseline, r_dd + tc_penalty, dd, ret)

    all_configs.sort(key=composite_sort_key)

    # ── Print summary table ──
    print("\n" + "=" * 145)
    print("因子/风险过滤回测结果汇总 (按收益/回撤比排序)")
    print(f"框架: {EXIT_RULE} + mp{MAX_POSITIONS} | 初始资金 {INITIAL_CASH:,} | 区间: {cfg.get('date_range', '?')}")
    print("=" * 145)
    header = (f"{'规则':<32} {'仓位':>5} {'笔':>4} {'总收益':>8} {'回撤':>7} "
              f"{'r/dd':>6} {'胜率':>6} {'均笔':>7} {'PF':>6} "
              f"{'连亏':>4} {'最差':>8} {'最佳':>8} {'过滤':>7} {'滤BS':>5}")
    print(header)
    print("-" * 145)

    for s in all_configs:
        marker = "[*]" if s["rule_name"] == "elastic_base" and s["position_pct"] == 0.20 else "   "
        print(f"{marker} {s['rule_name']:<30} {int(s['position_pct']*100):>3}% "
              f"{s.get('trade_count',0):>4} "
              f"{s.get('total_return',0):>+7.2f}% {s.get('max_drawdown',0):>+6.2f}% "
              f"{s.get('return_to_drawdown',0):>5.2f} "
              f"{s.get('win_rate',0):>5.1f}% {s.get('avg_trade_return',0):>+6.3f}% "
              f"{str(s.get('profit_factor','-')):>6} "
              f"{s.get('longest_loss_streak',0):>4} "
              f"{s.get('worst_trade',0):>+7.2f}% {s.get('best_trade',0):>+7.2f}% "
              f"{s.get('filtered_signal_count',0):>6} "
              f"{s.get('baseline_worst_filtered_count',0):>4}")
    print("-" * 145)

    # ── Build output ──
    result = {
        "config": {
            "date_range": cfg.get("date_range", ""),
            "exit_rule": EXIT_RULE,
            "max_positions": MAX_POSITIONS,
            "position_pct_list": POSITION_PCT_LIST,
            "initial_cash": INITIAL_CASH,
            "cost_bps_per_side": COST_BPS,
            "slippage_bps_per_side": SLIPPAGE_BPS,
            "total_rules": total_rules,
            "total_configs": total_configs,
            "note": (
                "Factor combination & individual-stock risk filter search. "
                "Fixed execution: dec_E + mp2. "
                "Each rule defines a factor formula + pre-filters applied before top-5 selection. "
                "Baseline worst trades tracked for filtering analysis. "
                "Fundamental gate: unavailable (no pre-cached financial data). "
                f"Elapsed: {total_elapsed}s."
            ),
            "generated_at": datetime.now().isoformat(),
        },
        "baseline_worst_5_trades": baseline_worst_5,
        "rules": {k: {"desc": v["desc"], "factor": v["factor"], "pre_filters": v["pre_filters"]}
                  for k, v in RULES.items()},
        "results": all_configs,
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = os.path.join(ROOT, "reports", f"tail_factor_risk_search_{ts}.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果: {out_json}")
    return result, ts, total_elapsed


if __name__ == "__main__":
    result, ts, elapsed = main()
