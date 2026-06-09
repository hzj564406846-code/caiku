"""仓位管理 — 三种算法 + 风险校验

每次分析个股时调用，输出具体买多少股、多少仓位、止损价。
"""
import math


def calc_position(cash, equity, price, atr_pct, score, risk_pct=0.02,
                  max_single_pct=0.30, min_shares=100):
    """综合仓位计算（主入口）

    参数:
        cash:       可用现金
        equity:     账户总权益
        price:      当前股价
        atr_pct:    ATR波动率(%)
        score:      V9评分(0-100)
        risk_pct:   单笔最大亏损占权益比例 (默认2%)
        max_single_pct: 单票最大仓位占比 (默认30%)
        min_shares: 最小交易股数 (A股100股)

    返回: {
        shares:         建议买入股数
        cost:           买入总成本
        position_pct:   仓位占比(%)
        risk_amount:    最大亏损金额
        stop_loss:      建议止损价
        stop_loss_pct:  止损幅度(%)
        method:         使用的算法
        warnings:       风险提示列表
    }
    """
    warnings = []

    # ── 1. ATR 止损价 ──
    atr_decimal = atr_pct / 100
    stop_distance = max(atr_decimal * 2, 0.03)  # 至少3%止损距离，正常用2xATR
    stop_loss = price * (1 - stop_distance)
    stop_loss_pct = stop_distance * 100

    # ── 2. 风险金额 ──
    risk_amount = equity * risk_pct  # 单笔最多亏这么多

    # 每股风险 = 进场价 - 止损价
    risk_per_share = price - stop_loss
    if risk_per_share <= 0:
        risk_per_share = price * 0.03  # fallback

    # ── 3. 计算股数 ──
    # 方法A: 固定比例风控 — shares = risk_amount / risk_per_share
    shares_a = max(min_shares, int(risk_amount / risk_per_share / 100) * 100)

    # 方法B: Kelly调整 — 按评分离散度调节
    if score >= 80:
        confidence = 0.25   # 高置信度，允许更大仓位
    elif score >= 65:
        confidence = 0.20
    elif score >= 50:
        confidence = 0.15
    else:
        confidence = 0.10

    kelly_shares = int((equity * confidence) / price / 100) * 100
    shares_b = max(min_shares, kelly_shares)

    # 方法C: 等资金分仓 — 总权益 / N等份 / 股价
    n_slots = 5  # 最多同时持有5只
    shares_c = max(min_shares, int((equity / n_slots) / price / 100) * 100)

    # ── 4. 综合 — 取方法A(最保守)和方法B(中等)的加权平均 ──
    shares = int((shares_a * 0.6 + shares_b * 0.4) / 100) * 100
    shares = max(min_shares, shares)

    # ── 5. 上限校验 ──
    # 单票仓位上限
    max_cost = equity * max_single_pct
    cost = shares * price
    if cost > max_cost:
        shares = int(max_cost / price / 100) * 100
        shares = max(min_shares, shares)
        cost = shares * price

    # 现金上限
    if cost > cash:
        shares = int(cash / price / 100) * 100
        shares = max(min_shares, shares)
        cost = shares * price
        if cost > cash:
            warnings.append("现金不足以买入最小单位(100股)")

    # ── 6. 风控警告 ──
    position_pct = (cost / equity * 100) if equity > 0 else 0
    if position_pct > 25:
        warnings.append(f"单票仓位{position_pct:.1f}%偏高,建议不超过25%")
    if score < 50:
        warnings.append(f"评分{score:.0f}偏低,建议观望不建仓")
    if atr_pct > 7:
        warnings.append(f"ATR{atr_pct:.1f}%波动过大,止损距离较宽")
    if atr_pct < 1.5:
        warnings.append(f"ATR{atr_pct:.1f}%过低,死水股注意流动性")

    method = "ATR风控+Kelly混合"
    if len(warnings) >= 2:
        method += " [谨慎]"

    return {
        "shares": shares,
        "cost": round(cost, 2),
        "position_pct": round(position_pct, 1),
        "risk_amount": round(risk_amount, 2),
        "risk_pct": round(risk_pct * 100, 1),
        "stop_loss": round(stop_loss, 2),
        "stop_loss_pct": round(stop_loss_pct, 1),
        "method": method,
        "warnings": warnings,
        "score": score,
        "atr_pct": round(atr_pct, 2),
    }


def calc_trailing_stop(entry_price, current_price, highest_price, atr_pct,
                        profit_pct=0, method="atr"):
    """计算移动止损价

    参数:
        entry_price:    买入价
        current_price:  当前价
        highest_price:  买入后最高价
        atr_pct:        ATR波动率(%)
        profit_pct:     当前浮盈(%)
        method:         "atr" | "percent" | "moving_average"

    返回: 建议止损价
    """
    if profit_pct >= 15:
        # 盈利>15%: 收紧止损，保护利润
        stop = highest_price * (1 - atr_pct / 100 * 1.5)
    elif profit_pct >= 8:
        # 盈利>8%: 保本止损
        stop = max(entry_price * 1.01, highest_price * (1 - atr_pct / 100 * 2))
    elif profit_pct >= 3:
        # 盈利>3%: 移动止损到成本价
        stop = entry_price
    else:
        # 浮亏: 原止损不动
        stop = entry_price * (1 - atr_pct / 100 * 2)

    return round(stop, 2)
