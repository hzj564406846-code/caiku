"""D6 基本面评分 — PE估值 + 市值 + 排雷信号"""
from engine.constants import (
    D6_NEUTRAL, D6_MAX,
    D6_PE_LOW, D6_PE_HIGH,
    D6_MV_LARGE, D6_MV_SMALL,
)


def score(quote_info=None, stock_info=None, minesweeper_result=None):
    """基本面评分 (安全边际，非收益来源)

    参数:
        quote_info: 实时行情 {pe, ...}
        stock_info: 基本面 {total_mv, ...}
        minesweeper_result: 排雷结果 {status: PASS/WARN/FAIL}

    返回: 0 ~ D6_MAX 的分数
    """
    score_val = float(D6_NEUTRAL)

    if quote_info:
        pe = quote_info.get("pe", 0)
        if 0 < pe < D6_PE_LOW:
            score_val += 3
        elif D6_PE_LOW <= pe < 40:
            score_val += 1
        elif pe >= D6_PE_HIGH:
            score_val -= 2

    if stock_info:
        total_mv = stock_info.get("total_mv", 0)
        if total_mv > D6_MV_LARGE:
            score_val += 1
        elif total_mv < D6_MV_SMALL:
            score_val -= 1

    # 排雷结果
    if minesweeper_result:
        status = minesweeper_result.get("status", "")
        if status == "PASS":
            score_val += 2
        elif status == "WARN":
            score_val -= 2
        elif status == "FAIL":
            score_val -= 5

    return min(D6_MAX, max(0, score_val))
