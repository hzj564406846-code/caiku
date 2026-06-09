"""AKShare provider health probes.

On this machine many AKShare A-share endpoints currently fail because they use
Eastmoney push2 under the hood.  This module keeps the dependency isolated and
lets audits record exactly which endpoints are usable before we trust them.
"""
from __future__ import annotations


def probe_endpoints() -> list[dict]:
    import akshare as ak

    probes = [
        ("stock_zh_a_spot_em", lambda: ak.stock_zh_a_spot_em()),
        ("stock_zh_a_hist", lambda: ak.stock_zh_a_hist(symbol="603501", period="daily", start_date="20250501", end_date="20260606", adjust="qfq")),
        ("stock_individual_fund_flow", lambda: ak.stock_individual_fund_flow(stock="603501", market="sh")),
        ("stock_sector_fund_flow_rank_industry", lambda: ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")),
        ("stock_sector_fund_flow_rank_concept", lambda: ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="概念资金流")),
        ("stock_board_concept_name_em", lambda: ak.stock_board_concept_name_em()),
    ]
    results = []
    for name, fn in probes:
        try:
            df = fn()
            results.append({
                "endpoint": name,
                "ok": True,
                "shape": list(getattr(df, "shape", [])),
                "columns": list(getattr(df, "columns", []))[:20],
            })
        except Exception as exc:
            results.append({
                "endpoint": name,
                "ok": False,
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            })
    return results
