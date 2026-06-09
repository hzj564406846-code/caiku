"""个股详细分析引擎 — v9 7维评分 + 8模块报告"""
import numpy as np
from engine.data_fetcher import (
    fetch_tencent_kline, fetch_em_fund_flow_raw, fetch_10jqka_fund_flow, fetch_stock_info,
    fetch_fund_flow_history, fetch_all_quotes, fetch_csi300_index, pattern_backtest
)
from engine.score_calculator import calc_score_v9
from engine.market_regime import get_market_regime
from engine.pattern_detector import label_patterns, calc_atr_pct
from engine.cache_manager import load_sector_cache


def generate_signals(result, df):
    """从v9评分结果和K线生成信号详情列表"""
    signals = []
    s = result

    # D1 资金面信号
    if s.get("d1_capital", 0) >= 24:
        signals.append(("+", "D1资金", "主力资金大幅流入，大单积极，资金面强劲"))
    elif s.get("d1_capital", 0) >= 18:
        signals.append(("+", "D1资金", "主力资金温和流入，资金面偏暖"))
    elif s.get("d1_capital", 0) <= 10:
        signals.append(("-", "D1资金", "主力资金流出或参与不足，资金面偏冷"))

    # D2 板块共振信号
    if s.get("d2_sector", 0) >= 17:
        signals.append(("+", "D2板块", "所属板块热度高，行业共振向上"))
    elif s.get("d2_sector", 0) >= 14:
        signals.append(("+", "D2板块", "板块热度中等偏上，有一定板块效应"))
    elif s.get("d2_sector", 0) <= 8:
        signals.append(("-", "D2板块", "板块偏冷，缺乏板块支撑"))

    # D3 趋势信号
    if s.get("d3_trend", 0) >= 12:
        signals.append(("+", "D3趋势", "均线多头排列，趋势向好"))
    elif s.get("d3_trend", 0) <= 5:
        signals.append(("-", "D3趋势", "趋势偏弱，均线空头或价格承压"))

    # D4 量价信号
    if s.get("d4_volume", 0) >= 12:
        signals.append(("+", "D4量价", "量价配合良好，资金积极参与"))
    elif s.get("d4_volume", 0) <= 6:
        signals.append(("-", "D4量价", "量能不足或量价背离"))

    if s.get("pattern_bonus", 0) > 0:
        names = {"hammer": "锤子线", "doji": "十字星", "shrinking_bear": "缩量小阴线"}
        signals.append(("+", "D4量价", f"{names.get(s['pattern'], s['pattern'])}止跌形态 (+{s['pattern_bonus']})"))

    # D5 市场情绪
    if s.get("d5_sentiment", 0) >= 8:
        signals.append(("+", "D5情绪", "市场情绪乐观，上涨家数占优"))
    elif s.get("d5_sentiment", 0) <= 3:
        signals.append(("-", "D5情绪", "市场情绪悲观，注意系统性风险"))

    # D6 基本面
    if s.get("d6_fundamental", 0) >= 8:
        signals.append(("+", "D6基本面", "基本面稳健，估值合理"))
    elif s.get("d6_fundamental", 0) <= 3:
        signals.append(("-", "D6基本面", "估值偏高或基本面存疑"))

    # D7 风控
    if s.get("d7_risk", 0) <= -8:
        signals.append(("-", "D7风控", f"风险信号较强({s['d7_risk']:.0f})，需严控仓位"))
    elif s.get("d7_risk", 0) >= -2:
        signals.append(("+", "D7风控", "无明显风险信号"))

    # ATR
    atr = s.get("atr_pct", 0)
    if atr > 5:
        signals.append(("-", "风控", f"ATR%={atr:.1f}%，波动率过高，不宜重仓"))
    elif atr < 2:
        signals.append(("+", "风控", f"ATR%={atr:.1f}%，波动率低，适合稳健建仓"))

    return signals


def run_analysis(code):
    """执行个股完整分析，返回8模块数据"""
    df = fetch_tencent_kline(code, count=200)
    quotes = fetch_all_quotes([code])
    quote = quotes.get(code, {})
    ff = fetch_em_fund_flow_raw(code)
    if ff is None:
        ff = fetch_10jqka_fund_flow(code)
    info = fetch_stock_info(code)
    ff_hist = fetch_fund_flow_history(code, 5)
    csi300_df = fetch_csi300_index()
    regime = get_market_regime(csi300_df)
    weights = regime.get("weights", {})
    sector_cache = load_sector_cache()

    # v9 评分
    stock_info = {"total_mv": info.get("total_mv", 0), "pe": info.get("pe", 0)}
    score = calc_score_v9(code, df, ff, sector_cache, quote,
                          regime_weights=weights, stock_info=stock_info,
                          csi300_df=csi300_df)
    signals = generate_signals(score, df) if df is not None else []
    pattern_name, pattern_bonus = label_patterns(df) if df is not None else ("", 0)
    atr_pct = calc_atr_pct(df) if df is not None else 0

    backtest = pattern_backtest(df) if df is not None else {"pattern": "", "samples": 0}

    half_th = regime.get("half_threshold", 60)
    full_th = regime.get("full_threshold", 70)
    total_s = score.get("score", 0)

    if total_s >= full_th:
        grade = "跟庄买点"
        grade_color = "#00ff88"
    elif total_s >= half_th:
        grade = "关注蓄势"
        grade_color = "#ffaa00"
    elif total_s >= 40:
        grade = "观望"
        grade_color = "#ff8800"
    elif total_s >= 25:
        grade = "偏弱"
        grade_color = "#ff4444"
    else:
        grade = "回避"
        grade_color = "#aa0000"

    return {
        "code": code,
        "name": info.get("name") or quote.get("name", ""),
        "regime": regime,
        "half_th": half_th,
        "full_th": full_th,
        "grade": grade,
        "grade_color": grade_color,
        "fundamentals": {
            "industry": info.get("industry", ""),
            "business": info.get("business", ""),
            "total_mv": info.get("total_mv", 0),
            "float_mv": info.get("float_mv", 0),
            "pe": info.get("pe", 0),
            "exchange": info.get("exchange", ""),
            "reg_capital": info.get("reg_capital", 0),
        },
        "quote": quote,
        "score": score,
        "signals": signals,
        "fund_flow_history": ff_hist,
        "pattern": {
            "name": pattern_name,
            "bonus": pattern_bonus,
            "atr_pct": atr_pct,
        },
        "backtest": backtest,
    }
