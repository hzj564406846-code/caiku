"""Factor research backtest for the stock advisor.

This is the missing research layer: build point-in-time factor rows, test
single factors, then test combinations.  V9 score is treated as one factor, not
as the whole strategy.
"""
import argparse
import itertools
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import numpy as np
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT_DIR)
sys.path.insert(0, ROOT_DIR)

from engine.backtest_engine import (  # noqa: E402
    _calc_historical_breadth,
    _calc_historical_sector_heat,
    _forward_returns,
    _kline_d1_proxy,
    _truncate_df,
)
from engine.cache_manager import CacheManager, load_csi300_codes, load_sector_cache  # noqa: E402
from engine.data_fetcher import fetch_csi300_index, fetch_tencent_kline  # noqa: E402
from engine.pattern_detector import calc_atr_pct, detect_consecutive_decline, label_patterns  # noqa: E402
from engine.score_calculator import calc_score_v9  # noqa: E402
from factor_registry import FACTOR_DIRECTIONS, PRIMITIVE_FACTORS, STRATEGY_FACTORS  # noqa: E402
from stock_advisor import calc_technical_state, safe_num  # noqa: E402


def fetch_kline_cached(cache, code, kline_count):
    df = cache.load_kline(code, max_age_hours=24 * 30)
    if df is not None and len(df) >= min(kline_count, 120):
        return df.tail(kline_count).reset_index(drop=True)
    df = fetch_tencent_kline(code, count=kline_count)
    if df is not None and len(df) > 0:
        cache.save_kline(code, df)
        return df.reset_index(drop=True)
    return None


def quote_from_history(df, idx):
    row = df.loc[idx]
    prev_close = df.loc[idx - 1, "close"] if idx > 0 else row["open"]
    price = float(row["close"])
    prev = float(prev_close)
    return {
        "price": price,
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "pre_close": prev,
        "change_pct": (price - prev) / prev * 100 if prev else 0,
        "turnover": 0,
        "pe": 0,
    }


def recent_return(df, days):
    if df is None or len(df) <= days:
        return 0.0
    close = df["close"].astype(float)
    base = close.iloc[-days - 1]
    return (close.iloc[-1] - base) / base * 100 if base else 0.0


def calc_raw_v9_features(code, truncated, quote, sector_cache, sector_hot_scores, quotes_for_date):
    closes = truncated["close"].astype(float)
    highs = truncated["high"].astype(float)
    lows = truncated["low"].astype(float)
    opens = truncated["open"].astype(float)
    volumes = truncated["volume"].astype(float)
    current = closes.iloc[-1]

    ma5 = closes.tail(5).mean()
    ma20 = closes.tail(20).mean()
    ma60 = closes.tail(60).mean() if len(closes) >= 60 else ma20

    avg_vol_5 = volumes.iloc[-6:-1].mean() if len(volumes) >= 6 else volumes.tail(5).mean()
    avg_vol_20 = volumes.iloc[-21:-1].mean() if len(volumes) >= 21 else avg_vol_5
    vol5_vs_vol20 = avg_vol_5 / avg_vol_20 if avg_vol_20 else 1.0
    vol_spike_ratio = volumes.iloc[-1] / avg_vol_20 if avg_vol_20 else 1.0

    row = truncated.iloc[-1]
    o, c, h, l = float(row["open"]), float(row["close"]), float(row["high"]), float(row["low"])
    body = abs(c - o)
    day_range = h - l
    intraday_range_pct = day_range / o * 100 if o else 0
    upper_shadow_pct = (h - max(c, o)) / o * 100 if o else 0
    lower_shadow_pct = (min(c, o) - l) / o * 100 if o else 0
    body_pct = body / o * 100 if o else 0

    pattern_name, pattern_bonus = label_patterns(truncated)
    decline = detect_consecutive_decline(truncated)

    industry = sector_cache.get(code, {}).get("industry", "") if sector_cache else ""
    peer_rank = 0.5
    sector_avg_change = 0.0
    sector_up_ratio = 0.0
    if industry:
        changes = []
        own = safe_num(quote.get("change_pct"))
        for peer_code, info in sector_cache.items():
            if info.get("industry") != industry:
                continue
            q = quotes_for_date.get(peer_code, {})
            if not q:
                continue
            changes.append(safe_num(q.get("change_pct")))
        if changes:
            peer_rank = sum(1 for chg in changes if chg < own) / len(changes)
            sector_avg_change = float(np.mean(changes))
            sector_up_ratio = sum(1 for chg in changes if chg > 0) / len(changes)

    ret_20d = recent_return(truncated, 20)
    ret_5d = recent_return(truncated, 5)
    atr = calc_atr_pct(truncated)

    return {
        "price_above_ma20": 1 if current > ma20 else 0,
        "price_above_ma60": 1 if current > ma60 else 0,
        "ma20_above_ma60": 1 if ma20 > ma60 else 0,
        "ma5_above_ma20": 1 if ma5 > ma20 else 0,
        "vol5_vs_vol20": vol5_vs_vol20,
        "intraday_range_pct": intraday_range_pct,
        "upper_shadow_pct": upper_shadow_pct,
        "lower_shadow_pct": lower_shadow_pct,
        "body_pct": body_pct,
        "hammer_flag": 1 if pattern_name == "hammer" else 0,
        "doji_flag": 1 if pattern_name == "doji" else 0,
        "shrinking_bear_flag": 1 if pattern_name == "shrinking_bear" else 0,
        "consecutive_decline_days": safe_num(decline.get("consecutive")),
        "decline_acceleration": safe_num(decline.get("acceleration")),
        "limit_move_flag": 1 if abs(safe_num(quote.get("change_pct"))) >= 9.5 else 0,
        "vol_spike_ratio": vol_spike_ratio,
        "peer_rank_in_sector": peer_rank,
        "sector_avg_change": sector_avg_change,
        "sector_up_ratio": sector_up_ratio,
        "v9_trend_raw": (
            (3 if current > ma20 else 1 if current > ma20 * 0.97 else 0)
            + (2 if current > ma60 else 0)
            + (2 if ma20 > ma60 else 0)
            + (2 if ret_20d > 8 else 1 if ret_20d > 3 else -3 if ret_20d < -10 else -1 if ret_20d < -5 else 0)
        ),
        "v9_volume_raw": (
            (4 if vol5_vs_vol20 > 2 else 2 if vol5_vs_vol20 > 1.5 else 1 if vol5_vs_vol20 > 1 else -2 if vol5_vs_vol20 < 0.4 else 0)
            + (3 if ret_5d > 5 else 1 if ret_5d > 0 else -3 if ret_5d < -5 else 0)
            + (2 if 2 <= atr <= 6 else 0)
            + (3 if safe_num(quote.get("change_pct")) > 5 else 1 if safe_num(quote.get("change_pct")) > 1 else -3 if safe_num(quote.get("change_pct")) < -5 else -1 if safe_num(quote.get("change_pct")) < -2 else 0)
        ),
        "v9_pattern_raw": safe_num(pattern_bonus) + safe_num(decline.get("bonus")) + safe_num(decline.get("penalty")),
    }


def zscore_series(s):
    s = pd.to_numeric(s, errors="coerce")
    std = s.std()
    if not std or np.isnan(std):
        return s * 0
    return (s - s.mean()) / std


def add_strategy_factors(df):
    df = df.copy()
    grouped = df.groupby("date", group_keys=False)
    z = {}
    for factor in PRIMITIVE_FACTORS:
        z[factor] = grouped[factor].transform(zscore_series).fillna(0)

    df["trend_factor"] = z["d3"] + z["d4"] + z["ret_20d"] + z["ma20_gap"]
    df["hot_money_factor"] = z["d1"] + z["d2"] + z["sector_hot"] + z["volume_ratio"]
    df["pullback_factor"] = z["d2"] + z["d3"] + z["ret_20d"] + z["oversold_5d"] - z["atr_pct"].clip(lower=0)
    df["oversold_rebound_factor"] = z["oversold_5d"] + z["oversold_20d"] + z["atr_pct"] + z["downside_risk"]
    df["quality_factor"] = z["d6"] + z["d7"] - z["atr_pct"].clip(lower=0)
    return df


def fetch_klines(codes, kline_count, threads):
    cache = CacheManager(base_dir=os.path.join(ROOT_DIR, "cache"))
    out = {}

    def one(code):
        return code, fetch_kline_cached(cache, code, kline_count)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(one, code) for code in codes]
        done = 0
        for future in as_completed(futures):
            code, df = future.result()
            done += 1
            print(f"\r获取K线: {done}/{len(codes)}", end="", flush=True)
            if df is not None and len(df) >= 100:
                out[code] = df.reset_index(drop=True)
    print()
    return out


def build_factor_table(codes, days, kline_count, threads):
    sector_cache = load_sector_cache(os.path.join(ROOT_DIR, "data", "stock_sectors_cache.json"))
    csi300_df = fetch_csi300_index(count=kline_count)
    if csi300_df is None or len(csi300_df) < days + 80:
        raise RuntimeError("CSI300 index data unavailable")

    kline_dict = fetch_klines(codes, kline_count, threads)
    if len(kline_dict) < 10:
        raise RuntimeError(f"too few valid kline series: {len(kline_dict)}")

    all_dates = sorted(csi300_df["date"].unique())
    start_idx = max(80, len(all_dates) - days - 10)
    backtest_dates = all_dates[start_idx:start_idx + days]
    rows = []

    for di, date in enumerate(backtest_dates, 1):
        breadth = _calc_historical_breadth(kline_dict, date)
        sector_hot_scores = _calc_historical_sector_heat(kline_dict, sector_cache, date)
        quotes_for_date = {}
        for q_code, q_df in kline_dict.items():
            q_match = q_df[q_df["date"] == date]
            if q_match.empty:
                continue
            q_idx = int(q_match.index[0])
            quotes_for_date[q_code] = quote_from_history(q_df, q_idx)
        for code, df in kline_dict.items():
            match = df[df["date"] == date]
            if match.empty:
                continue
            idx = int(match.index[0])
            truncated = _truncate_df(df, date)
            if truncated is None or len(truncated) < 80:
                continue

            quote = quote_from_history(df, idx)
            fund_data = _kline_d1_proxy(truncated)
            score = calc_score_v9(
                code,
                truncated,
                fund_data=fund_data,
                sector_cache=sector_cache,
                quote_info=quote,
                market_breadth=breadth,
                sector_hot_scores=sector_hot_scores,
            )
            tech = calc_technical_state(truncated, quote)
            raw_features = calc_raw_v9_features(code, truncated, quote, sector_cache, sector_hot_scores, quotes_for_date)
            ret_5d = recent_return(truncated, 5)
            ret_20d = recent_return(truncated, 20)
            atr = safe_num(score.get("atr_pct"), calc_atr_pct(truncated))
            d7 = safe_num(score.get("d7_risk"))
            industry = score.get("industry", "")
            fwd = _forward_returns(df, date, horizons=(3, 5, 10))

            row_data = {
                "date": str(date.date())[:10],
                "code": code,
                "industry": industry,
                "score": safe_num(score.get("score")),
                "d1": safe_num(score.get("d1_capital")),
                "d2": safe_num(score.get("d2_sector")),
                "d3": safe_num(score.get("d3_trend")),
                "d4": safe_num(score.get("d4_volume")),
                "d5": safe_num(score.get("d5_sentiment")),
                "d6": safe_num(score.get("d6_fundamental")),
                "d7": d7,
                "atr_pct": atr,
                "ret_5d": ret_5d,
                "ret_20d": ret_20d,
                "ma20_gap": safe_num(tech.get("ma20_gap")),
                "volume_ratio": safe_num(tech.get("volume_ratio")),
                "sector_hot": safe_num(sector_hot_scores.get(industry, 0)),
                "oversold_5d": -ret_5d,
                "oversold_20d": -ret_20d,
                "downside_risk": -d7,
                "ret_3d_fwd": fwd.get("ret_3d"),
                "ret_5d_fwd": fwd.get("ret_5d"),
                "ret_10d_fwd": fwd.get("ret_10d"),
            }
            row_data.update(raw_features)
            rows.append(row_data)
        print(f"\r生成因子表: {di}/{len(backtest_dates)}", end="", flush=True)
    print()

    df = pd.DataFrame(rows).dropna(subset=["ret_3d_fwd", "ret_5d_fwd", "ret_10d_fwd"])
    return add_strategy_factors(df), {
        "codes_total": len(codes),
        "codes_valid": len(kline_dict),
        "days": len(backtest_dates),
        "date_range": f"{backtest_dates[0].date()} ~ {backtest_dates[-1].date()}",
    }


def return_stats(vals):
    vals = pd.to_numeric(vals, errors="coerce").dropna()
    if vals.empty:
        return {}
    wins = vals[vals > 0]
    losses = vals[vals <= 0]
    return {
        "avg": round(float(vals.mean()), 2),
        "median": round(float(vals.median()), 2),
        "win_rate": round(float(len(wins) / len(vals) * 100), 1),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0,
        "n": int(len(vals)),
    }


def selected_stats(df, score_col, top_pct):
    selected = []
    for _, group in df.groupby("date"):
        n = max(1, int(len(group) * top_pct))
        selected.append(group.nlargest(n, score_col))
    pick = pd.concat(selected, ignore_index=True) if selected else pd.DataFrame()
    out = {"count": int(len(pick))}
    for h in (3, 5, 10):
        out[f"ret_{h}d"] = return_stats(pick[f"ret_{h}d_fwd"])
    return out


def factor_ic(df, factors):
    result = {}
    for factor in factors:
        rows = []
        for _, group in df.groupby("date"):
            if group[factor].nunique() < 3:
                continue
            item = {"date": group["date"].iloc[0]}
            for h in (3, 5, 10):
                # Spearman without scipy: Pearson correlation of ranks.
                item[f"ret_{h}d_ic"] = group[factor].rank().corr(group[f"ret_{h}d_fwd"].rank())
            rows.append(item)
        if not rows:
            continue
        ic_df = pd.DataFrame(rows)
        result[factor] = {
            f"ret_{h}d_ic_avg": round(float(ic_df[f"ret_{h}d_ic"].mean()), 4)
            for h in (3, 5, 10)
        }
    return result


def single_factor_tests(df, factors, top_pct):
    result = {}
    for factor in factors:
        result[factor] = selected_stats(df, factor, top_pct)
    return result


def combo_tests(df, factors, max_combo, top_pct):
    work = df.copy()
    grouped = work.groupby("date", group_keys=False)
    zcols = []
    for factor in factors:
        zcol = f"z_{factor}"
        work[zcol] = grouped[factor].transform(zscore_series).fillna(0) * FACTOR_DIRECTIONS.get(factor, 1)
        zcols.append(zcol)

    result = {}
    for size in range(2, max_combo + 1):
        for combo in itertools.combinations(factors, size):
            name = "+".join(combo)
            cols = [f"z_{c}" for c in combo]
            work[name] = work[cols].sum(axis=1)
            result[name] = selected_stats(work, name, top_pct)
            work.drop(columns=[name], inplace=True)
    return result


def rank_results(results, horizon="ret_5d", min_count=30):
    rows = []
    for name, stats in results.items():
        h = stats.get(horizon, {})
        if h.get("n", 0) < min_count:
            continue
        rows.append({
            "name": name,
            "count": stats.get("count", h.get("n", 0)),
            "avg": h.get("avg", 0),
            "median": h.get("median", 0),
            "win_rate": h.get("win_rate", 0),
            "avg_win": h.get("avg_win", 0),
            "avg_loss": h.get("avg_loss", 0),
        })
    return sorted(rows, key=lambda r: (r["avg"], r["win_rate"], r["median"]), reverse=True)


def run(args):
    started = time.time()
    codes = load_csi300_codes(os.path.join(ROOT_DIR, "data", "csi300_stocks.json"))[:args.top]
    df, cfg = build_factor_table(codes, args.days, args.kline_count, args.threads)

    factors = PRIMITIVE_FACTORS + STRATEGY_FACTORS + ["score"]
    single = single_factor_tests(df, factors, args.top_pct)
    combo_pool = PRIMITIVE_FACTORS if args.combo_factors == "ALL_PRIMITIVE" else args.combo_factors.split(",")
    combos = combo_tests(df, combo_pool, args.max_combo, args.top_pct)
    result = {
        "config": {
            **cfg,
            "generated_at": datetime.now().isoformat(),
            "records": int(len(df)),
            "top_pct": args.top_pct,
            "single_factor_count": len(factors),
            "combo_factor_pool_count": len(combo_pool),
            "combo_count": len(combos),
            "elapsed_seconds": round(time.time() - started, 1),
            "note": "Point-in-time factor table. No live Tushare enrichment.",
        },
        "factor_ic": factor_ic(df, factors),
        "single_factor": single,
        "combo_factor": combos,
        "top_single_5d": rank_results(single, "ret_5d")[:20],
        "top_combo_5d": rank_results(combos, "ret_5d")[:30],
        "top_single_10d": rank_results(single, "ret_10d")[:20],
        "top_combo_10d": rank_results(combos, "ret_10d")[:30],
    }
    return result


def print_report(result):
    cfg = result["config"]
    print("=" * 78)
    print("多因子研究回测")
    print("=" * 78)
    print(f"区间：{cfg['date_range']} | 股票：{cfg['codes_valid']}/{cfg['codes_total']} | 样本：{cfg['records']}")
    print(f"Top截面比例：{cfg['top_pct']:.0%}")
    print()
    print("单因子 Top 5D:")
    for row in result["top_single_5d"][:12]:
        print(f"- {row['name']} | n={row['count']} | 均值{row['avg']:+.2f}% | 中位{row['median']:+.2f}% | 胜率{row['win_rate']:.1f}%")
    print()
    print("组合因子 Top 5D:")
    for row in result["top_combo_5d"][:15]:
        print(f"- {row['name']} | n={row['count']} | 均值{row['avg']:+.2f}% | 中位{row['median']:+.2f}% | 胜率{row['win_rate']:.1f}%")
    print()
    print("组合因子 Top 10D:")
    for row in result["top_combo_10d"][:15]:
        print(f"- {row['name']} | n={row['count']} | 均值{row['avg']:+.2f}% | 中位{row['median']:+.2f}% | 胜率{row['win_rate']:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Point-in-time factor research backtest")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--top", type=int, default=120)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--kline-count", type=int, default=400)
    parser.add_argument("--top-pct", type=float, default=0.2)
    parser.add_argument("--max-combo", type=int, default=3)
    parser.add_argument(
        "--combo-factors",
        default="ALL_PRIMITIVE",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    result = run(args)
    print_report(result)
    output = args.output or os.path.join(
        ROOT_DIR, "reports", f"factor_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果已保存：{output}")


if __name__ == "__main__":
    main()
