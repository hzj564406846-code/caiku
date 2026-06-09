"""Backtest stock_advisor recommendation labels.

This validates the output users actually see: 短线可买 / 轻仓试错 / 等回踩 /
只观察 / 不建议买.  It intentionally does not use live Tushare enrichment,
because recommendation backtests must not depend on current API state or
non-point-in-time data.
"""
import argparse
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
from engine.cache_manager import load_csi300_codes, load_sector_cache  # noqa: E402
from engine.data_fetcher import fetch_csi300_index, fetch_tencent_kline  # noqa: E402
from engine.pattern_detector import calc_atr_pct  # noqa: E402
from engine.score_calculator import calc_score_v9  # noqa: E402
from stock_advisor import calc_technical_state, decide_action, estimate_forward_odds, safe_num  # noqa: E402


def quote_from_history(df, idx):
    row = df.loc[idx]
    prev_close = df.loc[idx - 1, "close"] if idx > 0 else row["open"]
    return {
        "price": float(row["close"]),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "pre_close": float(prev_close),
        "change_pct": (float(row["close"]) - float(prev_close)) / float(prev_close) * 100 if prev_close else 0,
        "turnover": 0,
        "pe": 0,
    }


def recent_return(df, days):
    if df is None or len(df) <= days:
        return 0.0
    close = df["close"].astype(float)
    return (close.iloc[-1] - close.iloc[-days - 1]) / close.iloc[-days - 1] * 100


def classify_ban_reason(score, quote, tech, truncated):
    atr = safe_num(score.get("atr_pct"), calc_atr_pct(truncated))
    d7 = safe_num(score.get("d7_risk"))
    ret_5d = recent_return(truncated, 5)
    ret_20d = recent_return(truncated, 20)
    change_pct = safe_num(quote.get("change_pct"))
    price_position = tech.get("price_position", "")
    volume_ratio = safe_num(tech.get("volume_ratio"))
    skip_reason = str(score.get("skip_reason", ""))

    if score.get("skip") and "数据不足" in skip_reason:
        return "数据不足"
    if score.get("skip") and "ATR>" in skip_reason and ret_5d <= -8:
        return "ATR高波动+超跌"
    if score.get("skip") and "ATR>" in skip_reason:
        return "ATR高波动"

    if abs(change_pct) >= 9.5:
        return "涨跌停/单日极端"
    if ret_5d <= -8 or (ret_20d <= -15 and price_position == "破位偏弱"):
        return "超跌反弹候选"
    if atr > 7:
        return "ATR高波动"
    if d7 <= -18 and ret_5d < 0:
        return "风控超跌混合"
    if d7 <= -18 and volume_ratio >= 2.5:
        return "天量/异常波动"
    if d7 <= -18:
        return "其他硬风控"
    return "未知禁止"


def fetch_klines(codes, kline_count, threads):
    out = {}

    def one(code):
        return code, fetch_tencent_kline(code, count=kline_count)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(one, code) for code in codes]
        done = 0
        for future in as_completed(futures):
            code, df = future.result()
            done += 1
            print(f"\r获取K线: {done}/{len(codes)}", end="", flush=True)
            if df is not None and len(df) >= 90:
                out[code] = df.reset_index(drop=True)
    print()
    return out


def action_stats(records):
    df = pd.DataFrame(records)
    if df.empty:
        return {}
    result = {}
    action_order = ["短线可买", "轻仓试错", "等回踩", "等回踩确认", "只观察", "不建议买", "禁止买"]
    for action in action_order:
        group = df[df["action"] == action]
        if group.empty:
            continue
        item = {
            "count": int(len(group)),
            "avg_score": round(float(group["score"].mean()), 2),
        }
        for h in (3, 5, 10):
            col = f"ret_{h}d"
            vals = group[col].dropna()
            if vals.empty:
                continue
            wins = vals[vals > 0]
            losses = vals[vals <= 0]
            item[col] = {
                "avg": round(float(vals.mean()), 2),
                "median": round(float(vals.median()), 2),
                "win_rate": round(float(len(wins) / len(vals) * 100), 1),
                "avg_win": round(float(wins.mean()), 2) if len(wins) else 0,
                "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0,
                "n": int(len(vals)),
            }
        result[action] = item
    return result


def group_stats(records, field, action_filter=None):
    rows = records
    if action_filter is not None:
        rows = [r for r in rows if r.get("action") == action_filter]
    df = pd.DataFrame(rows)
    if df.empty or field not in df.columns:
        return {}
    result = {}
    for key, group in df.groupby(field):
        if not key:
            continue
        item = {"count": int(len(group))}
        for h in (3, 5, 10):
            col = f"ret_{h}d"
            vals = group[col].dropna()
            if vals.empty:
                continue
            wins = vals[vals > 0]
            losses = vals[vals <= 0]
            item[col] = {
                "avg": round(float(vals.mean()), 2),
                "median": round(float(vals.median()), 2),
                "win_rate": round(float(len(wins) / len(vals) * 100), 1),
                "avg_win": round(float(wins.mean()), 2) if len(wins) else 0,
                "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0,
                "n": int(len(vals)),
            }
        result[str(key)] = item
    return dict(sorted(result.items(), key=lambda kv: kv[1]["count"], reverse=True))


def run(codes, days, kline_count, threads):
    started = time.time()
    sector_cache = load_sector_cache(os.path.join(ROOT_DIR, "data", "stock_sectors_cache.json"))
    csi300_df = fetch_csi300_index(count=kline_count)
    if csi300_df is None or len(csi300_df) < days + 80:
        return {"error": "CSI300 index data unavailable"}

    kline_dict = fetch_klines(codes, kline_count, threads)
    if len(kline_dict) < 5:
        return {"error": f"too few valid kline series: {len(kline_dict)}"}

    all_dates = sorted(csi300_df["date"].unique())
    start_idx = max(80, len(all_dates) - days - 10)
    backtest_dates = all_dates[start_idx:start_idx + days]
    records = []

    for di, date in enumerate(backtest_dates, 1):
        breadth = _calc_historical_breadth(kline_dict, date)
        sector_hot_scores = _calc_historical_sector_heat(kline_dict, sector_cache, date)
        for code, df in kline_dict.items():
            rows = df[df["date"] == date]
            if rows.empty:
                continue
            idx = int(rows.index[0])
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
            industry = score.get("industry", "")
            sector_hot = sector_hot_scores.get(industry, 0)
            tech = calc_technical_state(truncated, quote)
            odds = estimate_forward_odds(truncated, quote)
            action, reason = decide_action(score, quote, sector_hot, tech, odds)
            ban_bucket = classify_ban_reason(score, quote, tech, truncated) if action == "禁止买" else ""
            fwd = _forward_returns(df, date, horizons=(3, 5, 10))
            records.append({
                "date": str(date.date())[:10],
                "code": code,
                "industry": industry,
                "score": safe_num(score.get("score")),
                "d1": safe_num(score.get("d1_capital")),
                "d2": safe_num(score.get("d2_sector")),
                "d3": safe_num(score.get("d3_trend")),
                "d4": safe_num(score.get("d4_volume")),
                "d7": safe_num(score.get("d7_risk")),
                "atr_pct": safe_num(score.get("atr_pct"), calc_atr_pct(truncated)),
                "ret_5d_now": round(recent_return(truncated, 5), 2),
                "ret_20d_now": round(recent_return(truncated, 20), 2),
                "price_position": tech.get("price_position", ""),
                "volume_ratio": tech.get("volume_ratio", 0),
                "action": action,
                "reason": reason,
                "ban_bucket": ban_bucket,
                "ret_3d": fwd.get("ret_3d"),
                "ret_5d": fwd.get("ret_5d"),
                "ret_10d": fwd.get("ret_10d"),
            })
        print(f"\r逐日推荐: {di}/{len(backtest_dates)}", end="", flush=True)
    print()

    return {
        "config": {
            "generated_at": datetime.now().isoformat(),
            "codes_total": len(codes),
            "codes_valid": len(kline_dict),
            "days": days,
            "date_range": f"{backtest_dates[0].date()} ~ {backtest_dates[-1].date()}",
            "records": len(records),
            "elapsed_seconds": round(time.time() - started, 1),
            "note": "No live Tushare enrichment; uses point-in-time K-line proxy for D1.",
        },
        "action_stats": action_stats(records),
        "ban_bucket_stats": group_stats(records, "ban_bucket", action_filter="禁止买"),
        "records_sample": records[:50],
    }


def print_report(result):
    cfg = result.get("config", {})
    print("=" * 78)
    print("推荐级回测报告")
    print("=" * 78)
    print(f"区间：{cfg.get('date_range')} | 股票：{cfg.get('codes_valid')}/{cfg.get('codes_total')} | 样本：{cfg.get('records')}")
    print(f"说明：{cfg.get('note')}")
    print()
    for action, stats in result.get("action_stats", {}).items():
        print(f"- {action} | n={stats['count']} | avg_score={stats['avg_score']}")
        for h in (3, 5, 10):
            item = stats.get(f"ret_{h}d")
            if not item:
                continue
            print(
                f"  {h}日: 均值{item['avg']:+.2f}% | 中位{item['median']:+.2f}% | "
                f"胜率{item['win_rate']:.1f}% | n={item['n']}"
            )
    ban_stats = result.get("ban_bucket_stats", {})
    if ban_stats:
        print()
        print("禁止买拆分：")
        for bucket, stats in ban_stats.items():
            print(f"- {bucket} | n={stats['count']}")
            for h in (3, 5, 10):
                item = stats.get(f"ret_{h}d")
                if not item:
                    continue
                print(
                    f"  {h}日: 均值{item['avg']:+.2f}% | 中位{item['median']:+.2f}% | "
                    f"胜率{item['win_rate']:.1f}% | n={item['n']}"
                )


def main():
    parser = argparse.ArgumentParser(description="Backtest stock_advisor recommendation labels")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--top", type=int, default=60)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--kline-count", type=int, default=400)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    codes = load_csi300_codes(os.path.join(ROOT_DIR, "data", "csi300_stocks.json"))[:args.top]
    result = run(codes, args.days, args.kline_count, args.threads)
    if "error" in result:
        print(result["error"])
        sys.exit(1)
    print_report(result)

    output = args.output or os.path.join(
        ROOT_DIR, "reports", f"recommendation_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果已保存：{output}")


if __name__ == "__main__":
    main()
