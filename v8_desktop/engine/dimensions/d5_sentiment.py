"""D5 市场情绪评分 — 个股相对市场强度 + 换手活跃度 + 热点板块

从"全市场统一打分"改为"个股差异化评估"，解决区分度0%问题。
"""
import numpy as np
from engine.constants import (
    D5_NEUTRAL, D5_MAX,
    D5_REL_STRONG, D5_REL_OK, D5_REL_WEAK,
    D5_TURNOVER_HIGH, D5_TURNOVER_OK, D5_TURNOVER_LOW,
)


def score(df=None, quote_info=None, csi300_df=None,
          sector_hot_scores=None, industry=""):
    """个股相对市场情绪评分

    参数:
        df: K线DataFrame (计算个股5日涨幅)
        quote_info: 实时行情 {change_pct, turnover, ...}
        csi300_df: CSI300指数K线 (计算市场5日涨幅)
        sector_hot_scores: 板块热度 {industry: hot_score}
        industry: 个股所属行业

    返回: 0 ~ D5_MAX 的分数
    """
    if df is None or len(df) < 6:
        return D5_NEUTRAL

    score_val = float(D5_NEUTRAL)

    # 1. 相对强度: 个股5日涨幅 vs CSI300 5日涨幅
    closes = df["close"].values
    stock_ret5 = (closes[-1] - closes[-6]) / closes[-6] * 100

    csi300_ret5 = 0
    if csi300_df is not None and len(csi300_df) >= 6:
        csi_closes = csi300_df["close"].values
        csi300_ret5 = (csi_closes[-1] - csi_closes[-6]) / csi_closes[-6] * 100

    rel_strength = stock_ret5 - csi300_ret5
    if rel_strength > D5_REL_STRONG:
        score_val += 4
    elif rel_strength > D5_REL_OK:
        score_val += 2
    elif rel_strength < D5_REL_WEAK:
        score_val -= 2

    # 2. 换手活跃度
    if quote_info:
        turnover = quote_info.get("turnover", 0)
        if turnover > D5_TURNOVER_HIGH:
            score_val += 2
        elif turnover > D5_TURNOVER_OK:
            score_val += 1
        elif turnover < D5_TURNOVER_LOW:
            score_val -= 1

    # 3. 热点板块加分
    if sector_hot_scores and industry:
        hot = sector_hot_scores.get(industry, 0)
        if hot > 80:
            score_val += 3
        elif hot > 60:
            score_val += 1

    return min(D5_MAX, max(0, score_val))
