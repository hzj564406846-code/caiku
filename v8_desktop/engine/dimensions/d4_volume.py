"""D4 量价健康评分 — 量比 + 动量 + 换手活性 + 形态"""
import numpy as np
from engine.pattern_detector import label_patterns, detect_consecutive_decline, calc_atr_pct
from engine.constants import (
    D4_NEUTRAL, D4_MAX,
    D4_VOL_RATIO_HIGH, D4_VOL_RATIO_MODERATE, D4_VOL_RATIO_LOW,
    D4_RET5_STRONG, D4_RET5_WEAK,
    ATR_HEALTHY_MIN, ATR_HEALTHY_MAX,
)


def score(df, quote_info=None):
    """量价健康评分

    参数:
        df: K线DataFrame
        quote_info: 实时行情 {change_pct, ...}

    返回: 0 ~ D4_MAX 的分数
    """
    if df is None or len(df) < 10:
        return D4_NEUTRAL

    score_val = float(D4_NEUTRAL)
    closes = df["close"].values
    volumes = df["volume"].values

    # 量比: 5日均量 vs 20日均量
    avg_vol_5 = np.mean(volumes[-6:-1])
    avg_vol_20 = np.mean(volumes[-21:-1]) if len(volumes) >= 21 else avg_vol_5
    vol_ratio = avg_vol_5 / avg_vol_20 if avg_vol_20 > 0 else 1

    if vol_ratio > D4_VOL_RATIO_HIGH:
        score_val += 4
    elif vol_ratio > D4_VOL_RATIO_MODERATE:
        score_val += 2
    elif vol_ratio > 1.0:
        score_val += 1
    elif vol_ratio < D4_VOL_RATIO_LOW:
        score_val -= 2

    # 5日动量
    ret5 = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
    if ret5 > D4_RET5_STRONG:
        score_val += 3
    elif ret5 > 0:
        score_val += 1
    elif ret5 < D4_RET5_WEAK:
        score_val -= 3

    # 活性奖励: 波动率在健康区间(2-6%)
    atr_pct = calc_atr_pct(df)
    if ATR_HEALTHY_MIN <= atr_pct <= ATR_HEALTHY_MAX:
        score_val += 2

    # 今日涨跌
    if quote_info:
        chg_pct = quote_info.get("change_pct", 0)
        if chg_pct > 5:
            score_val += 3
        elif chg_pct > 1:
            score_val += 1
        elif chg_pct < -5:
            score_val -= 3
        elif chg_pct < -2:
            score_val -= 1

    # 形态加分
    pattern_name, bonus = label_patterns(df)
    score_val += bonus

    # 连跌检查
    decline_info = detect_consecutive_decline(df)
    score_val += decline_info["bonus"]
    score_val += decline_info["penalty"]

    return min(D4_MAX, max(0, score_val))
