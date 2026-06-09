"""板块热点追踪引擎：热度评分 + 热门板块检测 + 1-5天拉升预测"""
import numpy as np


def calc_sector_hot_score(stock_results, sector_name, sector_cache, quotes=None):
    """
    计算单个板块的热度评分 (0-100)
    量比×0.4 + 涨跌幅×0.3 + 主力净流入得分×0.3
    """
    # 找出该板块的所有股票
    sector_codes = [
        c for c, v in sector_cache.items()
        if v.get("industry", "") == sector_name
    ]
    if len(sector_codes) < 2:
        return 0

    # 从扫描结果中提取该板块股票的数据
    sector_results = [r for r in stock_results if r["code"] in sector_codes]
    if len(sector_results) < 2:
        return 0

    # 量比得分: 板块内平均量比
    vol_ratios = []
    changes = []
    fund_scores = []
    for r in sector_results:
        quote = (quotes or {}).get(r["code"], {})
        if quote:
            changes.append(quote.get("change_pct", 0))
        # 从资金流数据估算主力态度
        ff = r.get("fund_flow", {})
        if ff:
            ratio = ff.get("main_net_ratio", 0)
            if ratio > 5:
                fund_scores.append(100)
            elif ratio > 2:
                fund_scores.append(70)
            elif ratio > 0:
                fund_scores.append(50)
            elif ratio > -2:
                fund_scores.append(30)
            elif ratio > -5:
                fund_scores.append(15)
            else:
                fund_scores.append(0)

    avg_change = np.mean(changes) if changes else 0
    avg_fund = np.mean(fund_scores) if fund_scores else 30

    # 板块涨跌幅归一化到0-100: 平均涨3%以上=高分
    change_score = min(100, max(0, 50 + avg_change * 10))

    # 板块内上涨比例作为量比代理
    up_ratio = sum(1 for c in changes if c > 0) / len(changes) * 100 if changes else 50

    hot_score = up_ratio * 0.4 + change_score * 0.3 + avg_fund * 0.3
    return round(hot_score, 1)


def detect_hot_sectors(all_stock_results, sector_cache, quotes=None, top_n=5):
    """
    从全市场扫描结果中检测热门板块
    返回: [{"name": str, "score": float, "stock_count": int, "avg_change": float}, ...]
    """
    # 收集所有行业
    industries = set()
    for v in sector_cache.values():
        ind = v.get("industry", "")
        if ind:
            industries.add(ind)

    sector_hot_list = []
    for ind in industries:
        # 统计该行业股票
        sector_codes = [
            c for c, v in sector_cache.items()
            if v.get("industry", "") == ind
        ]
        sector_results = [r for r in all_stock_results if r["code"] in sector_codes]

        if len(sector_results) < 2:
            continue

        hot_score = calc_sector_hot_score(all_stock_results, ind, sector_cache, quotes)

        changes = []
        for r in sector_results:
            q = (quotes or {}).get(r["code"], {})
            if q:
                changes.append(q.get("change_pct", 0))
        avg_change = round(np.mean(changes), 2) if changes else 0

        sector_hot_list.append({
            "name": ind,
            "score": hot_score,
            "stock_count": len(sector_results),
            "avg_change": avg_change,
        })

    sector_hot_list.sort(key=lambda x: x["score"], reverse=True)
    return sector_hot_list[:top_n]


def predict_pump_stocks(hot_sectors, all_results, sector_cache, quotes=None, kline_data=None):
    """
    基于热门板块 + 量价形态，预测1-5天内可能拉升的个股
    条件: 板块热度>60 + 个股量比>1.2 + 主力净流入为正 + 非涨停

    返回: [{"code": str, "name": str, "sector": str, "confidence": float, "signals": [str]}, ...]
    """
    hot_sector_names = {s["name"] for s in hot_sectors if s["score"] > 60}
    if not hot_sector_names:
        return []

    predictions = []
    for r in all_results:
        if r.get("skip"):
            continue

        code = r["code"]
        industry = r.get("industry", "")
        if industry not in hot_sector_names:
            continue

        quote = (quotes or {}).get(code, {})
        chg = quote.get("change_pct", 0)
        if abs(chg) >= 9.5:
            continue  # 已涨停的不预测

        ff = r.get("fund_flow", {})
        main_ratio = ff.get("main_net_ratio", 0)

        signals = []
        confidence = 0

        # 条件1: 主力净流入
        if main_ratio > 2:
            confidence += 30
            signals.append(f"主力净流入{main_ratio:+.1f}%")
        elif main_ratio > 0:
            confidence += 15
            signals.append(f"主力微幅流入{main_ratio:+.1f}%")
        else:
            continue  # 主力流出，跳过

        # 条件2: 板块热度加分
        sector_score = next((s["score"] for s in hot_sectors if s["name"] == industry), 0)
        if sector_score > 80:
            confidence += 25
            signals.append(f"板块{industry}热度{sector_score:.0f}")
        elif sector_score > 60:
            confidence += 15
            signals.append(f"板块{industry}偏热({sector_score:.0f})")

        # 条件3: 量比
        if quote:
            turnover = quote.get("turnover", 0)
            if turnover > 3:
                confidence += 20
                signals.append(f"换手率{turnover:.1f}%活跃")
            elif turnover > 1.5:
                confidence += 10
                signals.append(f"换手率{turnover:.1f}%适中")

        # 条件4: 技术形态加分
        pattern = r.get("pattern", "")
        if pattern in ("hammer", "doji", "shrinking_bear"):
            confidence += 10
            pattern_names = {"hammer": "锤子线", "doji": "十字星", "shrinking_bear": "缩量小阴"}
            signals.append(f"止跌形态:{pattern_names.get(pattern, pattern)}")

        # 条件5: 大单vs小单背离
        large = ff.get("large_inflow", 0) + ff.get("super_large_inflow", 0)
        small = ff.get("small_inflow", 0)
        if large > 0 and small < 0:
            confidence += 10
            signals.append("大单买入/小单卖出(主力吸筹)")

        if confidence >= 30:
            predictions.append({
                "code": code,
                "name": r.get("name", ""),
                "sector": industry,
                "confidence": round(confidence, 1),
                "score": r.get("score", 0),
                "atr_pct": r.get("atr_pct", 0),
                "signals": signals,
            })

    predictions.sort(key=lambda x: x["confidence"], reverse=True)
    return predictions[:10]
