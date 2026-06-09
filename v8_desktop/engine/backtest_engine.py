"""Walk-forward 回测引擎 — 验证 v9 7维评分对未来收益的预测力

方法: 在每个历史交易日，仅用当时已知数据评分，追踪未来1/3/5/10日收益，
按评分分4档统计胜率、平均收益、盈亏比。

数据可用性:
  D1资金 — 从东方财富历史资金流向API获取(近200天)
  D2板块 — 从CSI300成分股当日表现近似板块热度
  D3趋势/D4量价/D7风控 — 从K线完整计算
  D5情绪 — 从CSI300成分股当日涨跌比近似
  D6基本面 — 中性值(无法获取历史PE)
"""
import time
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from engine.data_fetcher import fetch_tencent_kline, fetch_csi300_index, fetch_fund_flow_history, fetch_10jqka_fund_flow
from engine.score_calculator import calc_score_v9
from engine.cache_manager import load_sector_cache


def _truncate_df(df, date):
    """截断DataFrame到指定日期(含), 模拟当时已知数据"""
    if df is None:
        return None
    truncated = df[df["date"] <= date].copy()
    if len(truncated) < 10:
        return None
    return truncated


def _forward_returns(df, date, horizons=(1, 3, 5, 10)):
    """计算指定日期后的未来收益(%)"""
    if df is None:
        return {}
    rows = df[df["date"] == date]
    if len(rows) == 0:
        return {}
    idx = rows.index[0]
    current_close = df.loc[idx, "close"]
    result = {}
    for h in horizons:
        future_idx = idx + h
        if future_idx < len(df):
            result[f"ret_{h}d"] = (df.loc[future_idx, "close"] - current_close) / current_close * 100
        else:
            result[f"ret_{h}d"] = None
    return result


def _calc_historical_breadth(kline_dict, date):
    """从CSI300成分股当日涨跌近似计算市场宽度"""
    up, down, total_amount = 0, 0, 0.0
    for code, df in kline_dict.items():
        if df is None:
            continue
        rows = df[df["date"] == date]
        if len(rows) == 0:
            continue
        row = rows.iloc[0]
        if row["close"] >= row["open"]:
            up += 1
        else:
            down += 1
        total_amount += row["volume"]
    return {"up": up, "down": down, "total_amount": total_amount * 100}


def _calc_historical_sector_heat(kline_dict, sector_cache, date):
    """从CSI300成分股当日表现近似计算板块热度"""
    industry_returns = {}
    for code, df in kline_dict.items():
        if df is None or code not in sector_cache:
            continue
        rows = df[df["date"] == date]
        if len(rows) == 0:
            continue
        row = rows.iloc[0]
        ret = (row["close"] - row["open"]) / row["open"] * 100 if row["open"] > 0 else 0
        industry = sector_cache[code].get("industry", "")
        if industry:
            if industry not in industry_returns:
                industry_returns[industry] = []
            industry_returns[industry].append(ret)

    sector_hot = {}
    for ind, returns in industry_returns.items():
        if len(returns) >= 2:
            avg_ret = np.mean(returns)
            up_ratio = sum(1 for r in returns if r > 0) / len(returns)
            sector_hot[ind] = round(avg_ret * 5 + up_ratio * 50)
    return sector_hot


def _history_to_d1(history_entry):
    """将fetch_fund_flow_history返回格式转为_d1_capital期望格式"""
    if history_entry is None:
        return None
    return {
        "main_net_inflow": history_entry.get("main_net", 0) * 1e8,
        "super_large_inflow": history_entry.get("super_large", 0) * 1e8,
        "large_inflow": history_entry.get("large", 0) * 1e8,
        "middle_inflow": history_entry.get("middle", 0) * 1e8,
        "small_inflow": history_entry.get("small", 0) * 1e8,
        "main_net_ratio": history_entry.get("main_ratio", 0),
    }


def _kline_d1_proxy(df):
    """从K线近似推算主力资金流向 (Chaikin Money Flow)

    每根K线: 资金流向 = 成交量 * ((收盘-最低) - (最高-收盘)) / (最高-最低)
    正数 = 买方主导, 负数 = 卖方主导
    汇总近5日, 计算净流向比例

    Returns dict with same keys as fetch_em_fund_flow_raw
    """
    if df is None or len(df) < 6:
        return None

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].values

    # 近5日资金流
    recent_indices = range(max(0, len(closes) - 5), len(closes))
    total_mf = 0.0
    total_vol = 0.0
    large_buy = 0.0
    large_sell = 0.0
    small_buy = 0.0
    small_sell = 0.0

    for i in recent_indices:
        h, l, c, v = highs[i], lows[i], lows[i], volumes[i]  # placeholder
        h, l, c, v = highs[i], lows[i], closes[i], volumes[i]
        hl_range = h - l
        if hl_range > 0 and v > 0:
            # MF Multiplier: ((close-low)-(high-close)) / (high-low), 范围 [-1, 1]
            mf_multiplier = ((c - l) - (h - c)) / hl_range
            mf_volume = mf_multiplier * v
            total_mf += mf_volume
            total_vol += v

            # 模拟大单vs小单: 当日振幅>3%且量比>1.5时视为大单主导
            daily_range = (h - l) / l * 100 if l > 0 else 0
            if i > 5:
                avg_vol_5 = float(np.mean(volumes[max(0, i - 6):i]))
                vol_ratio = v / avg_vol_5 if avg_vol_5 > 0 else 1
            else:
                vol_ratio = 1

            if daily_range > 3 and vol_ratio > 1.5:
                if mf_multiplier > 0:
                    large_buy += mf_volume
                else:
                    large_sell += abs(mf_volume)
            else:
                if mf_multiplier > 0:
                    small_buy += mf_volume
                else:
                    small_sell += abs(mf_volume)

    if total_vol <= 0:
        return None

    # 主力净占比: MF比例转为百分比
    main_net_ratio = round((total_mf / total_vol) * 20, 1)  # 缩放到合理范围

    return {
        "main_net_inflow": total_mf,
        "super_large_inflow": large_buy * 0.6,
        "large_inflow": large_buy * 0.4,
        "middle_inflow": 0,
        "small_inflow": small_buy - small_sell,
        "main_net_ratio": main_net_ratio,
    }


class BacktestEngine:
    """Walk-forward 回测引擎 — v9 7维 + 历史D1资金"""

    def __init__(self, codes, backtest_days=60, kline_count=400, n_threads=8):
        self.codes = codes
        self.backtest_days = backtest_days
        self.kline_count = kline_count
        self.n_threads = n_threads

    def run(self, progress_callback=None):
        t0 = time.time()

        # 1. 加载板块缓存和CSI300指数
        sector_cache = load_sector_cache()
        csi300_df = fetch_csi300_index(count=self.kline_count)
        if csi300_df is None or len(csi300_df) < 80:
            return {"error": "无法获取CSI300指数数据"}

        # 从CSI300指数确定回测日期范围
        all_dates = sorted(csi300_df["date"].unique())
        start_idx = max(60, len(all_dates) - self.backtest_days - 10)
        backtest_dates = all_dates[start_idx:start_idx + self.backtest_days]

        if len(backtest_dates) < 10:
            return {"error": f"回测日期不足: 仅{len(backtest_dates)}天"}

        # 2. 并行获取K线 + 历史资金流向
        kline_dict = {}
        fund_flow_by_code = {}  # {code: {date_str: fund_data}}
        done = 0
        total = len(self.codes)

        def _fetch_one(code):
            df = fetch_tencent_kline(code, count=self.kline_count)
            # 拉取200天资金流向历史
            ff_hist = fetch_fund_flow_history(code, days=200)
            ff_index = {}
            if ff_hist:
                for entry in ff_hist:
                    ff_index[entry["date"]] = entry
            return code, df, ff_index

        with ThreadPoolExecutor(max_workers=self.n_threads) as executor:
            futures = [executor.submit(_fetch_one, c) for c in self.codes]
            for future in as_completed(futures):
                code, df, ff_index = future.result()
                if df is not None and len(df) >= 70:
                    kline_dict[code] = df
                if ff_index:
                    fund_flow_by_code[code] = ff_index
                done += 1
                if progress_callback:
                    progress_callback("fetch", done, total)

        valid_codes = list(kline_dict.keys())
        if len(valid_codes) < 10:
            return {"error": f"K线数据不足: 仅{len(valid_codes)}只有效数据"}

        # 3. Walk-forward: 逐日评分 + 记录前向收益
        records = []
        date_done = 0

        for date in backtest_dates:
            date_str = str(date.date())[:10]  # "2026-01-23"
            breadth = _calc_historical_breadth(kline_dict, date)
            sector_hot = _calc_historical_sector_heat(kline_dict, sector_cache, date)

            for code in valid_codes:
                df = kline_dict[code]
                truncated = _truncate_df(df, date)
                if truncated is None:
                    continue

                # 查找当日资金流向 (优先API, 回退K线近似)
                ff_index = fund_flow_by_code.get(code, {})
                ff_entry = ff_index.get(date_str)
                fund_data = _history_to_d1(ff_entry) if ff_entry else None
                if fund_data is None:
                    fund_data = _kline_d1_proxy(truncated)

                # 计算v9评分(仅用当日及之前数据)
                score = calc_score_v9(
                    code, truncated,
                    fund_data=fund_data,  # D1: 历史资金流向
                    sector_cache=sector_cache,
                    quote_info=None,
                    regime_weights=None,
                    market_breadth=breadth,
                    stock_info=None,
                    sector_hot_scores=sector_hot,
                )

                fwd = _forward_returns(df, date)

                records.append({
                    "date": date_str,
                    "code": code,
                    "score": score["score"],
                    "d1_capital": score["d1_capital"],
                    "d2_sector": score["d2_sector"],
                    "d3_trend": score["d3_trend"],
                    "d4_volume": score["d4_volume"],
                    "d5_sentiment": score["d5_sentiment"],
                    "d6_fundamental": score["d6_fundamental"],
                    "d7_risk": score["d7_risk"],
                    "ret_1d": fwd.get("ret_1d"),
                    "ret_3d": fwd.get("ret_3d"),
                    "ret_5d": fwd.get("ret_5d"),
                    "ret_10d": fwd.get("ret_10d"),
                })

            date_done += 1
            if progress_callback:
                progress_callback("score", date_done, len(backtest_dates))

        # 4. 聚合统计
        df_records = pd.DataFrame(records)
        df_records = df_records.dropna(subset=["ret_1d"])

        def tier(score):
            if score >= 70:
                return "满仓(>=70)"
            elif score >= 60:
                return "半仓(60-69)"
            elif score >= 40:
                return "观望(40-59)"
            else:
                return "弱势(<40)"

        df_records["tier"] = df_records["score"].apply(tier)

        stats = {}
        tier_order = ["满仓(>=70)", "半仓(60-69)", "观望(40-59)", "弱势(<40)"]
        for t in tier_order:
            tier_df = df_records[df_records["tier"] == t]
            if len(tier_df) == 0:
                stats[t] = {"count": 0}
                continue

            tier_stats = {"count": len(tier_df),
                          "avg_score": round(tier_df["score"].mean(), 1)}
            for h in [1, 3, 5, 10]:
                col = f"ret_{h}d"
                vals = tier_df[col].dropna()
                if len(vals) == 0:
                    tier_stats[f"ret_{h}d"] = None
                    continue
                wins = (vals > 0).sum()
                tier_stats[f"ret_{h}d"] = {
                    "avg": round(vals.mean(), 2),
                    "median": round(vals.median(), 2),
                    "win_rate": round(wins / len(vals) * 100, 1),
                    "best": round(vals.max(), 2),
                    "worst": round(vals.min(), 2),
                    "std": round(vals.std(), 2),
                    "n": len(vals),
                }
            stats[t] = tier_stats

        # 全体统计
        all_rets = {}
        for h in [1, 3, 5, 10]:
            col = f"ret_{h}d"
            vals = df_records[col].dropna()
            if len(vals) > 0:
                wins = (vals > 0).sum()
                all_rets[f"ret_{h}d"] = {
                    "avg": round(vals.mean(), 2),
                    "win_rate": round(wins / len(vals) * 100, 1),
                    "n": len(vals),
                }

        # 评分-收益相关性
        corr = {}
        for h in [1, 3, 5, 10]:
            col = f"ret_{h}d"
            valid = df_records.dropna(subset=[col])
            if len(valid) > 10:
                corr[f"ret_{h}d"] = round(valid["score"].corr(valid[col]), 4)

        # 按分数十分位统计(更细粒度的分布)
        decile_stats = {}
        if len(df_records) >= 20:
            df_records["decile"] = pd.qcut(df_records["score"], q=5, labels=["Q1(最低)", "Q2", "Q3", "Q4", "Q5(最高)"],
                                           duplicates="drop")
            for dec_label in df_records["decile"].cat.categories:
                dec_df = df_records[df_records["decile"] == dec_label]
                if len(dec_df) < 5:
                    continue
                d_stats = {"count": len(dec_df), "score_range": f"{dec_df['score'].min():.0f}-{dec_df['score'].max():.0f}"}
                for h in [1, 3, 5, 10]:
                    col = f"ret_{h}d"
                    vals = dec_df[col].dropna()
                    if len(vals) > 0:
                        wins = (vals > 0).sum()
                        d_stats[f"ret_{h}d"] = {
                            "avg": round(vals.mean(), 2),
                            "win_rate": round(wins / len(vals) * 100, 1),
                        }
                decile_stats[dec_label] = d_stats

        elapsed = round(time.time() - t0, 1)

        return {
            "config": {
                "codes_total": len(self.codes),
                "codes_valid": len(valid_codes),
                "codes_with_d1": len(fund_flow_by_code),
                "backtest_dates": len(backtest_dates),
                "date_range": f"{backtest_dates[0].date()} ~ {backtest_dates[-1].date()}",
                "total_records": len(df_records),
                "elapsed_seconds": elapsed,
            },
            "tier_stats": stats,
            "all_returns": all_rets,
            "score_return_correlation": corr,
            "decile_stats": decile_stats,
        }
