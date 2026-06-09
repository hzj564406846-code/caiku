"""CSI300市场状态判定 — 牛市/熊市/震荡 + 自适应权重"""
import numpy as np
from engine.constants import WEIGHTS


def calc_ma60_rising(df):
    """判断MA60是否上升：当前MA60 > 5日前MA60"""
    if df is None or len(df) < 65:
        return False, 0
    closes = df["close"].values
    ma60_now = np.mean(closes[-60:])
    ma60_5d_ago = np.mean(closes[-65:-5])
    slope = (ma60_now - ma60_5d_ago) / ma60_5d_ago * 100
    return ma60_now > ma60_5d_ago, slope


def calc_20d_return(df):
    """计算20日涨跌幅"""
    if df is None or len(df) < 20:
        return 0
    closes = df["close"].values
    return (closes[-1] - closes[-21]) / closes[-21] * 100


def get_market_regime(csi300_df):
    """
    判断市场状态 + 返回自适应权重
    牛市: CSI300 > MA60 AND MA60上升 AND 20日收益 > -5%
    熊市: CSI300 < MA60 AND NOT MA60上升 AND 20日收益 < -5%
    震荡: 其他情况

    牛市条件放宽到-5%: A股牛市初期常伴随急跌洗盘, 放宽避免误判
    """
    if csi300_df is None or len(csi300_df) < 65:
        return {
            "regime": "ranging", "tag": "震荡 [稳健]",
            "half_threshold": 65, "full_threshold": 75,
            "csi300_price": 0, "csi300_ma60": 0,
            "ma60_rising": False, "ma60_slope": 0, "return_20d": 0,
            "weights": WEIGHTS["ranging"],
        }

    closes = csi300_df["close"].values
    price = closes[-1]
    ma60 = np.mean(closes[-60:])
    ma_rising, ma_slope = calc_ma60_rising(csi300_df)
    ret_20d = calc_20d_return(csi300_df)

    # 牛市: 放宽条件，A股牛市初期常伴随急跌洗盘
    if price > ma60 and ma_rising and ret_20d > -5:
        regime = "bull"
        tag = "牛市 [激进]"
        half, full = 55, 65
        weights = WEIGHTS["bull"]
    elif price < ma60 and not ma_rising and ret_20d < -5:
        regime = "bear"
        tag = "熊市 [防御]"
        half, full = 70, 80
        weights = WEIGHTS["bear"]
    else:
        regime = "ranging"
        tag = "震荡 [稳健]"
        half, full = 60, 70
        weights = WEIGHTS["ranging"]

    return {
        "regime": regime,
        "tag": tag,
        "half_threshold": half,
        "full_threshold": full,
        "csi300_price": round(price, 2),
        "csi300_ma60": round(ma60, 2),
        "ma60_rising": ma_rising,
        "ma60_slope": round(ma_slope, 2),
        "return_20d": round(ret_20d, 2),
        "weights": weights,
    }
