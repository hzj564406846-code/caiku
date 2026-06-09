"""V9 7维评分引擎 — 纯调度层，策略逻辑全部在 dimensions/ 和 constants.py 中

D1 资金面 + D2 板块共振 + D3 趋势质量 + D4 量价健康
+ D5 市场情绪 + D6 基本面 + D7 风控

权重根据市场状态自适应调整 (牛市激进/熊市防御)
"""
from engine.pattern_detector import label_patterns, calc_atr_pct
from engine.constants import (
    get_adaptive_weights,
    DIMENSION_MAX,
    ATR_SKIP_THRESHOLD,
    GROWTH_KEYWORDS, DEFENSIVE_KEYWORDS,
    ACTIVITY_GROWTH_BONUS, ACTIVITY_DEFENSIVE_PENALTY,
)
from engine.dimensions import (
    d1_capital, d2_sector, d3_trend, d4_volume,
    d5_sentiment, d6_fundamental, d7_risk,
)


def atr_skip(df, threshold=ATR_SKIP_THRESHOLD):
    """波动率闸门: ATR > threshold → 跳过该股票"""
    return calc_atr_pct(df) > threshold


def _apply_weights(raw_scores, regime_weights):
    """将各维度原始分按自适应权重缩放"""
    w = regime_weights
    max_scores = DIMENSION_MAX

    return {
        "d1": raw_scores["d1"] * (w["d1_capital"] / max_scores["d1_capital"]),
        "d2": raw_scores["d2"] * (w["d2_sector"] / max_scores["d2_sector"]),
        "d3": raw_scores["d3"] * (w["d3_trend"] / max_scores["d3_trend"]),
        "d4": raw_scores["d4"] * (w["d4_volume"] / max_scores["d4_volume"]),
        "d5": raw_scores["d5"] * (w["d5_sentiment"] / max_scores["d5_sentiment"]),
        "d6": raw_scores["d6"] * (w["d6_fundamental"] / max_scores["d6_fundamental"]),
        # D7风控: 负值惩罚幅度由权重绝对值决定
        "d7": raw_scores["d7"] * (abs(w["d7_risk"]) / max_scores["d7_risk"]),
    }


def _calc_activity_adjust(industry, sector_hot_scores=None):
    """板块活性调整: 科技成长+3, 防御死水-3, 热点额外加分"""
    adjust = 0
    for kw in GROWTH_KEYWORDS:
        if kw in industry:
            adjust = ACTIVITY_GROWTH_BONUS
            break
    if adjust == 0:
        for kw in DEFENSIVE_KEYWORDS:
            if kw in industry:
                adjust = ACTIVITY_DEFENSIVE_PENALTY
                break

    # 热点板块额外加分
    if sector_hot_scores and industry in sector_hot_scores:
        hot = sector_hot_scores[industry]
        if hot > 80:
            adjust += 3
        elif hot > 60:
            adjust += 1

    return adjust


def calc_score_v9(code, df, fund_data=None, sector_cache=None, quote_info=None,
                  regime_weights=None, market_breadth=None, stock_info=None,
                  sector_hot_scores=None, minesweeper_result=None,
                  csi300_df=None, quotes=None):
    """V9 7维评分引擎

    参数:
        code:       股票代码
        df:         K线DataFrame
        fund_data:  资金流向数据 (同花顺/东方财富)
        sector_cache: 板块缓存 {code: {industry, score}}
        quote_info: 实时行情 {name, price, change_pct, turnover, volume_amount, pe}
        regime_weights: 市场自适应权重 (来自 get_adaptive_weights)
        market_breadth: 市场宽度 {up, down, total_amount}
        stock_info: 基本面 {total_mv, pe, ...}
        sector_hot_scores: 板块热度 {industry: hot_score}
        minesweeper_result: 排雷结果 {status: PASS/WARN/FAIL}
        csi300_df: CSI300指数K线 (用于D5相对强度)
        quotes: 全市场行情 {code: {change_pct, ...}} (用于D2板块动量)

    返回: {
        code, name, score,
        d1_capital ... d7_risk (加权后),
        atr_pct, pattern, pattern_bonus,
        volume_amount, industry,
        skip, skip_reason
    }
    """
    if regime_weights is None:
        regime_weights = get_adaptive_weights("ranging")

    name = quote_info.get("name", "") if quote_info else ""

    # 数据不足
    if df is None or len(df) < 10:
        return {
            "code": code, "name": name, "score": 0,
            "d1_capital": 0, "d2_sector": 0, "d3_trend": 0,
            "d4_volume": 0, "d5_sentiment": 0, "d6_fundamental": 0, "d7_risk": 0,
            "atr_pct": 0, "pattern": "", "pattern_bonus": 0,
            "volume_amount": 0, "industry": "", "skip": True, "skip_reason": "数据不足",
        }

    atr_pct = calc_atr_pct(df)

    # 提前提取行业 (D2/D5/活性调整都需要)
    industry = ""
    if sector_cache and code in sector_cache:
        industry = sector_cache[code].get("industry", "")

    # ── 调用各维度评分 ──
    raw = {
        "d1": d1_capital(fund_data, df),
        "d2": d2_sector(code, sector_cache, sector_hot_scores, quotes),
        "d3": d3_trend(df),
        "d4": d4_volume(df, quote_info),
        "d5": d5_sentiment(df, quote_info, csi300_df, sector_hot_scores, industry),
        "d6": d6_fundamental(quote_info, stock_info, minesweeper_result),
        "d7": d7_risk(df, quote_info, minesweeper_result),
    }

    # ── 应用自适应权重 ──
    w = _apply_weights(raw, regime_weights)

    pattern_name, pattern_bonus = label_patterns(df)

    # ── ATR闸门: 极端波动跳过 ──
    if atr_skip(df):
        return {
            "code": code, "name": name, "score": 0,
            "d1_capital": round(w["d1"], 1), "d2_sector": round(w["d2"], 1),
            "d3_trend": round(w["d3"], 1), "d4_volume": round(w["d4"], 1),
            "d5_sentiment": round(w["d5"], 1), "d6_fundamental": round(w["d6"], 1),
            "d7_risk": round(w["d7"], 1),
            "atr_pct": round(atr_pct, 2), "pattern": pattern_name, "pattern_bonus": pattern_bonus,
            "volume_amount": quote_info.get("volume_amount", 0) if quote_info else 0,
            "industry": "", "skip": True, "skip_reason": f"ATR>{ATR_SKIP_THRESHOLD}%",
        }

    # ── 汇总总分 ──
    total = w["d1"] + w["d2"] + w["d3"] + w["d4"] + w["d5"] + w["d6"] + w["d7"]

    # ── 板块活性调整 ──
    total += _calc_activity_adjust(industry, sector_hot_scores)
    total = max(0, total)

    result = {
        "code": code, "name": name, "score": round(total, 1),
        "d1_capital": round(w["d1"], 1), "d2_sector": round(w["d2"], 1),
        "d3_trend": round(w["d3"], 1), "d4_volume": round(w["d4"], 1),
        "d5_sentiment": round(w["d5"], 1), "d6_fundamental": round(w["d6"], 1),
        "d7_risk": round(w["d7"], 1),
        "atr_pct": round(atr_pct, 2),
        "pattern": pattern_name, "pattern_bonus": pattern_bonus,
        "volume_amount": quote_info.get("volume_amount", 0) if quote_info else 0,
        "industry": industry,
        "skip": False, "skip_reason": "",
    }

    if fund_data:
        result["fund_flow"] = {
            "main_net_inflow": fund_data.get("main_net_inflow", 0),
            "super_large_inflow": fund_data.get("super_large_inflow", 0),
            "large_inflow": fund_data.get("large_inflow", 0),
            "middle_inflow": fund_data.get("middle_inflow", 0),
            "small_inflow": fund_data.get("small_inflow", 0),
            "main_net_ratio": fund_data.get("main_net_ratio", 0),
        }

    return result
