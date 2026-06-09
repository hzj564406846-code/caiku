"""K线止跌形态识别"""
import numpy as np


def label_patterns(df):
    """
    识别止跌形态
    返回: (pattern_name, bonus_points)
    - 锤子线: +4分, 下影线 >= 实体2倍, 收盘在实体上半部
    - 十字星: +2分, 实体 < 振幅10%
    - 缩量小阴线: +3分, 跌幅<2%, 量比<0.6
    """
    if df is None or len(df) < 3:
        return "", 0
    row = df.iloc[-1]
    o, c, h, l, v = row["open"], row["close"], row["high"], row["low"], row["volume"]
    body = abs(c - o)
    upper_shadow = h - max(c, o)
    lower_shadow = min(c, o) - l
    body_pct = body / o * 100 if o > 0 else 0
    range_pct = (h - l) / o * 100 if o > 0 else 0

    # 锤子线
    if lower_shadow >= body * 2 and c > o * 0.98 and body_pct > 0.2:
        return "hammer", 4
    # 十字星
    if body_pct < range_pct * 0.15:
        return "doji", 2
    # 缩量小阴线
    if c < o and body_pct < 2:
        prev_vol = df["volume"].iloc[-2:-1].values
        if len(prev_vol) > 0 and prev_vol[0] > 0:
            vol_ratio = v / prev_vol[0]
            if vol_ratio < 0.6:
                return "shrinking_bear", 3
    return "", 0


def detect_consecutive_decline(df):
    """检测连跌和跌幅加速度"""
    if df is None or len(df) < 5:
        return {"consecutive": 0, "acceleration": 0, "penalty": 0, "bonus": 0}
    closes = df["close"].values[-5:]
    declines = 0
    for i in range(1, 5):
        if closes[-i] < closes[-i-1]:
            declines += 1
        else:
            break
    if declines < 3:
        return {"consecutive": declines, "acceleration": 0, "penalty": 0, "bonus": 0}
    # 计算跌幅加速度
    daily_drops = []
    for i in range(declines):
        drop_pct = (closes[-i-1] - closes[-i-2]) / closes[-i-2] * 100
        daily_drops.append(abs(drop_pct))
    if len(daily_drops) >= 2 and daily_drops[-1] > daily_drops[-2]:
        return {"consecutive": declines, "acceleration": 1, "penalty": -5, "bonus": 0}
    else:
        return {"consecutive": declines, "acceleration": 0, "penalty": 0, "bonus": 3}


def calc_atr_pct(df, period=14):
    """计算ATR百分比"""
    if df is None or len(df) < period + 1:
        return 0
    high = df["high"].values[-period-1:]
    low = df["low"].values[-period-1:]
    close = df["close"].values[-period-1:]
    tr = []
    for i in range(1, len(high)):
        tr.append(max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])))
    atr = np.mean(tr[-period:])
    current_close = close[-1]
    return (atr / current_close) * 100 if current_close > 0 else 0
