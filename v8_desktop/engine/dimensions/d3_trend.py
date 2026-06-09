"""D3 趋势质量评分 — 均线排列 + 20日动量"""
import numpy as np
from engine.constants import D3_NEUTRAL, D3_MAX


def _calc_mas(closes):
    """计算均线"""
    if len(closes) < 60:
        return {}
    return {
        "ma5": np.mean(closes[-5:]),
        "ma10": np.mean(closes[-10:]),
        "ma20": np.mean(closes[-20:]),
        "ma60": np.mean(closes[-60:]),
    }


def score(df):
    """趋势质量评分

    参数:
        df: K线DataFrame

    返回: 0 ~ D3_MAX 的分数
    """
    if df is None or len(df) < 60:
        return D3_NEUTRAL

    closes = df["close"].values
    current = closes[-1]
    mas = _calc_mas(closes)

    if not mas:
        return D3_NEUTRAL

    score_val = float(D3_NEUTRAL)

    if current > mas["ma20"]:
        score_val += 3
    elif current > mas["ma20"] * 0.97:
        score_val += 1

    if current > mas["ma60"]:
        score_val += 2

    if mas["ma20"] > mas["ma60"]:
        score_val += 2

    # 20日动量
    ret20 = (current - closes[-21]) / closes[-21] * 100 if len(closes) >= 21 else 0
    if ret20 > 8:
        score_val += 2
    elif ret20 > 3:
        score_val += 1
    elif ret20 < -10:
        score_val -= 3
    elif ret20 < -5:
        score_val -= 1

    return min(D3_MAX, max(0, score_val))
