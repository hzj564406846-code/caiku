"""D7 风控扣分 — 波动风险 + 死水惩罚 + 暴跌检测 + 异常信号

返回负值或零，越负风险越高
"""
import numpy as np
from engine.pattern_detector import detect_consecutive_decline, calc_atr_pct
from engine.constants import (
    D7_MIN, D7_MAX_PENALTY,
    ATR_HIGH_RISK, ATR_ELEVATED_RISK, ATR_DEAD_MONEY,
    D7_RET5_CRASH, D7_RET5_SEVERE, D7_RET5_MODERATE,
    D7_VOL_SPIKE, D7_DEAD_RET5_FLAT,
    D7_LIMIT_UP_DOWN, D7_DECLINE_CONSECUTIVE,
)


def score(df, quote_info=None, minesweeper_result=None):
    """风控扣分

    参数:
        df: K线DataFrame
        quote_info: 实时行情 {change_pct, ...}
        minesweeper_result: 排雷结果 {status: PASS/WARN/FAIL}

    返回: D7_MAX_PENALTY ~ 0 的分数 (负值=扣分)
    """
    if df is None or len(df) < 10:
        return 0

    score_val = 0.0
    closes = df["close"].values
    volumes = df["volume"].values

    # ATR% 波动风险
    atr_pct = calc_atr_pct(df)
    if atr_pct > ATR_HIGH_RISK:
        score_val -= 8
    elif atr_pct > ATR_ELEVATED_RISK:
        score_val -= 3

    # 死水股: 波动极低 + 5日横盘
    ret5 = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
    if atr_pct < ATR_DEAD_MONEY and abs(ret5) < D7_DEAD_RET5_FLAT:
        score_val -= 4

    # 近期暴跌
    if ret5 < D7_RET5_CRASH:
        score_val -= 8
    elif ret5 < D7_RET5_SEVERE:
        score_val -= 6
    elif ret5 < D7_RET5_MODERATE:
        score_val -= 3

    # 天量见顶
    avg_vol_20 = np.mean(volumes[-21:-1]) if len(volumes) >= 21 else np.mean(volumes)
    if volumes[-1] > avg_vol_20 * D7_VOL_SPIKE:
        score_val -= 5

    # 连续加速下跌
    decline_info = detect_consecutive_decline(df)
    if decline_info["consecutive"] >= D7_DECLINE_CONSECUTIVE and decline_info["acceleration"] == 1:
        score_val -= 5

    # 涨停/跌停
    if quote_info:
        chg_pct = quote_info.get("change_pct", 0)
        if abs(chg_pct) >= D7_LIMIT_UP_DOWN:
            score_val -= 20

    # 排雷FAIL额外扣分
    if minesweeper_result and minesweeper_result.get("status") == "FAIL":
        score_val -= 10

    return max(D7_MAX_PENALTY, min(D7_MIN, score_val))
