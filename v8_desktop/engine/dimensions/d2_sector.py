"""D2 板块共振评分 — 行业内相对强弱 + 板块动量 + 板块资金热度"""
import numpy as np
from engine.constants import D2_NEUTRAL, D2_DEFAULT, D2_MAX


def score(code, sector_cache=None, sector_hot_scores=None, quotes=None):
    """板块共振评分

    参数:
        code: 股票代码
        sector_cache: {code: {industry, ...}}
        sector_hot_scores: {industry: hot_score}
        quotes: {code: {change_pct, ...}} 全市场实时行情

    返回: 0 ~ D2_MAX 的分数
    """
    if sector_cache is None or code not in sector_cache:
        return D2_NEUTRAL

    info = sector_cache[code]
    industry = info.get("industry", "")
    if not industry:
        return D2_NEUTRAL

    # 1. 行业内相对强弱 (0-15分)
    # 用实时涨跌幅计算行业内排名百分位
    peer_score = int(D2_DEFAULT * 0.6)  # fallback ~7
    if quotes:
        ind_changes = []
        own_chg = 0
        for c, v in sector_cache.items():
            if v.get("industry") == industry:
                q = quotes.get(c, {})
                chg = q.get("change_pct", 0)
                ind_changes.append(chg)
                if c == code:
                    own_chg = chg

        if ind_changes and len(ind_changes) >= 2:
            # 按涨跌幅排名，计算百分位
            rank = sum(1 for chg in ind_changes if chg < own_chg)
            pct = rank / len(ind_changes) * 100
            peer_score = round(pct / 100 * 15)  # 0-15分按排名百分位

    # 2. 板块动量 (0-5分)
    momentum_bonus = 0
    if quotes:
        ind_changes = []
        for c, v in sector_cache.items():
            if v.get("industry") == industry:
                q = quotes.get(c, {})
                chg = q.get("change_pct", 0)
                ind_changes.append(chg)

        if ind_changes:
            avg_chg = np.mean(ind_changes)
            if avg_chg > 3:
                momentum_bonus = 5
            elif avg_chg > 1.5:
                momentum_bonus = 3
            elif avg_chg > 0:
                momentum_bonus = 1
            elif avg_chg < -2:
                momentum_bonus = -2

    # 3. 板块热度加分 (0-5分)
    hot_bonus = 0
    if sector_hot_scores and industry in sector_hot_scores:
        hot = sector_hot_scores[industry]
        if hot > 80:
            hot_bonus = 5
        elif hot > 65:
            hot_bonus = 3
        elif hot > 50:
            hot_bonus = 2
        elif hot > 35:
            hot_bonus = 1

    return min(D2_MAX, max(0, peer_score + momentum_bonus + hot_bonus))
