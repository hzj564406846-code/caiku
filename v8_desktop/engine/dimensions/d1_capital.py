"""D1 资金面评分 — 核心驱动力

支持两种数据源:
- 同花顺: 5日净额 + 连续流入天数 + 资金强度归一化
- 东方财富: 大单/超大单/小单分解 (API被封，保留兼容)
"""
import numpy as np
from engine.constants import (
    D1_NEUTRAL, D1_MAX,
    D1_NET_5D_STRONG, D1_NET_5D_MODERATE, D1_NET_5D_WEAK,
    D1_NET_5D_STRONG_OUT, D1_NET_5D_MODERATE_OUT, D1_NET_5D_WEAK_OUT,
    D1_CONSECUTIVE_STRONG, D1_CONSECUTIVE_MODERATE,
    D1_AVG_DAILY_STRONG,
    D1_INTENSITY_HIGH, D1_INTENSITY_MODERATE,
)


def score(fund_data, df=None):
    """主力资金面评分

    参数:
        fund_data: 资金流向数据 (同花顺或东方财富格式)
        df: K线DataFrame (用于资金强度归一化)

    返回: 0 ~ D1_MAX 的分数
    """
    if fund_data is None:
        return D1_NEUTRAL

    score_val = float(D1_NEUTRAL)
    source = fund_data.get("_source", "")

    if source == "10jqka":
        score_val = _score_10jqka(fund_data, df, score_val)
    else:
        score_val = _score_eastmoney(fund_data, score_val)

    return min(D1_MAX, max(0, score_val))


def _calc_intensity(fund_data, df):
    """资金强度 = 5日净流入(万) / 近5日日均成交额(万) * 100

    消除大市值偏差：中国电信(5000亿)11亿流入 vs 中小盘股同样流入
    """
    if df is None or len(df) < 5:
        return 0

    net_5d = fund_data.get("net_5d", 0)
    if net_5d <= 0:
        return 0

    try:
        # 近5日日均成交额 (万元)
        if "amount" in df.columns:
            recent_amounts = df["amount"].values[-5:]
            avg_daily_amount = np.mean(recent_amounts) / 10000  # 元→万元
        else:
            # Tencent K线无amount列，用 volume(手) * close * 100 推算
            recent_vols = df["volume"].values[-5:]
            recent_closes = df["close"].values[-5:]
            avg_daily_amount = np.mean(recent_vols * recent_closes * 100) / 10000
    except Exception:
        return 0

    if avg_daily_amount <= 0:
        return 0

    return (net_5d / avg_daily_amount) * 100


def _score_10jqka(fund_data, df, score_val):
    """同花顺数据源评分"""
    net_5d = fund_data.get("net_5d", 0)
    consecutive = int(fund_data.get("consecutive_inflow", 0))

    # 5日净流入方向 + 强度
    if net_5d > D1_NET_5D_STRONG:
        score_val += 10
    elif net_5d > D1_NET_5D_MODERATE:
        score_val += 7
    elif net_5d > D1_NET_5D_WEAK:
        score_val += 4
    elif net_5d > 0:
        score_val += 2
    elif net_5d < D1_NET_5D_STRONG_OUT:
        score_val -= 10
    elif net_5d < D1_NET_5D_MODERATE_OUT:
        score_val -= 6
    elif net_5d < D1_NET_5D_WEAK_OUT:
        score_val -= 3

    # 资金强度归一化 (核心新增)
    intensity = _calc_intensity(fund_data, df)
    if intensity > D1_INTENSITY_HIGH:
        score_val += 6
    elif intensity > D1_INTENSITY_MODERATE:
        score_val += 3
    elif intensity < 2 and net_5d > D1_NET_5D_STRONG:
        # 绝对流入大但相对成交额很小 → 大象股，资金效率低
        score_val -= 2

    # 连续流入: 趋势更可靠
    if net_5d > 0 and consecutive >= D1_CONSECUTIVE_STRONG:
        score_val += 5
    elif net_5d > 0 and consecutive >= D1_CONSECUTIVE_MODERATE:
        score_val += 3
    elif net_5d < 0 and consecutive >= D1_CONSECUTIVE_MODERATE:
        score_val -= 3

    # 日均净流入强度
    avg_daily = fund_data.get("avg_daily_net", 0)
    if net_5d > 0 and avg_daily > D1_AVG_DAILY_STRONG:
        score_val += 2

    return score_val


def _score_eastmoney(fund_data, score_val):
    """东方财富数据源评分 (大单/小单分解)"""
    ratio = fund_data.get("main_net_ratio", 0)
    if ratio > 8:
        score_val += 15
    elif ratio > 5:
        score_val += 10
    elif ratio > 2:
        score_val += 5
    elif ratio > 0:
        score_val += 2
    elif ratio < -8:
        score_val -= 10
    elif ratio < -5:
        score_val -= 8
    elif ratio < -2:
        score_val -= 3

    # 大单 vs 小单背离
    large = fund_data.get("large_inflow", 0) + fund_data.get("super_large_inflow", 0)
    small = fund_data.get("small_inflow", 0)
    if large > 0 and small < 0:
        score_val += 5
    elif large < 0 and small > 0:
        score_val -= 3

    # 超大单共振
    if fund_data.get("super_large_inflow", 0) > 0 and large > 0:
        score_val += 2

    return score_val
