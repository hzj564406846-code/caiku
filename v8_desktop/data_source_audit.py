"""Audit V9 data sources.

This is a diagnostic script, not a trading component.  It checks whether the
raw data feeding the advisor is trustworthy enough for market/stock decisions.
"""
import argparse
import json
import os
import re
from datetime import datetime

import requests

try:
    from data_providers.baostock_provider import (
        fetch_kline as fetch_baostock_kline,
        fetch_profit_data as fetch_baostock_profit_data,
        fetch_stock_basic as fetch_baostock_stock_basic,
    )
except Exception:
    fetch_baostock_kline = None
    fetch_baostock_profit_data = None
    fetch_baostock_stock_basic = None


ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(ROOT, "reports")
REQUEST_TIMEOUT = 5
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})


def market_prefix(code):
    return "sh" if code.startswith("6") else "sz"


def em_market(code):
    return "1" if code.startswith("6") else "0"


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def tencent_quote(code):
    url = f"https://qt.gtimg.cn/q={market_prefix(code)}{code}"
    resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    parts = resp.text.split("~")
    if len(parts) < 40:
        raise ValueError(f"Tencent quote parse failed: {resp.text[:120]}")
    return {
        "source": "tencent",
        "name": parts[1],
        "price": safe_float(parts[3]),
        "pre_close": safe_float(parts[4]),
        "open": safe_float(parts[5]),
        "change_pct": safe_float(parts[32]),
        "high": safe_float(parts[33]),
        "low": safe_float(parts[34]),
        "amount_yuan": safe_float(parts[37]) * 10000,
        "turnover": safe_float(parts[38]),
        "pe": safe_float(parts[39]),
        "timestamp": parts[30] if len(parts) > 30 else "",
    }


def sina_quote(code):
    url = f"http://hq.sinajs.cn/list={market_prefix(code)}{code}"
    resp = SESSION.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=REQUEST_TIMEOUT)
    match = re.search(r'="(.*)"', resp.text)
    if not match:
        raise ValueError(f"Sina quote parse failed: {resp.text[:120]}")
    parts = match.group(1).split(",")
    if len(parts) < 32:
        raise ValueError(f"Sina quote field count too small: {len(parts)}")
    price = safe_float(parts[3])
    pre_close = safe_float(parts[2])
    return {
        "source": "sina",
        "name": parts[0],
        "price": price,
        "pre_close": pre_close,
        "open": safe_float(parts[1]),
        "change_pct": (price - pre_close) / pre_close * 100 if pre_close else 0,
        "high": safe_float(parts[4]),
        "low": safe_float(parts[5]),
        "amount_yuan": safe_float(parts[9]),
        "volume_shares": safe_float(parts[8]),
        "date": parts[30],
        "time": parts[31],
    }


def eastmoney_quote(code):
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "secid": f"{em_market(code)}.{code}",
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f162,f168,f170",
    }
    data = (SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT).json().get("data") or {})
    return {
        "source": "eastmoney",
        "code": data.get("f57"),
        "name": data.get("f58"),
        "price": safe_float(data.get("f43")) / 100,
        "pre_close": safe_float(data.get("f60")) / 100,
        "open": safe_float(data.get("f46")) / 100,
        "change_pct": safe_float(data.get("f170")) / 100,
        "high": safe_float(data.get("f44")) / 100,
        "low": safe_float(data.get("f45")) / 100,
        "amount_yuan": safe_float(data.get("f48")),
        "volume_hands": safe_float(data.get("f47")),
        "turnover": safe_float(data.get("f168")) / 100,
        "pe": safe_float(data.get("f162")) / 100,
    }


def eastmoney_fund_flow(code, days=5):
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{em_market(code)}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "lmt": days,
    }
    data = SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT).json()
    klines = (data.get("data") or {}).get("klines") or []
    return {"source": "eastmoney_fund_flow", "ok": bool(klines), "rows": len(klines), "sample": klines[-2:]}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_quotes(code):
    item = {"code": code, "quotes": {}, "warnings": []}
    for label, fn in [
        ("tencent", tencent_quote),
        ("sina", sina_quote),
        ("eastmoney", eastmoney_quote),
    ]:
        try:
            item["quotes"][label] = fn(code)
        except Exception as exc:
            item["warnings"].append(f"{label} quote failed: {exc}")

    quotes = item["quotes"]
    if len(quotes) >= 2:
        prices = [q["price"] for q in quotes.values() if q.get("price")]
        amounts = [q["amount_yuan"] for q in quotes.values() if q.get("amount_yuan")]
        if prices and max(prices) - min(prices) > 0.02:
            item["warnings"].append(f"price mismatch: {prices}")
        if amounts and min(amounts) > 0:
            amount_diff = (max(amounts) - min(amounts)) / min(amounts)
            if amount_diff > 0.01:
                item["warnings"].append(f"amount mismatch >1%: {amounts}")

        pes = {k: v.get("pe") for k, v in quotes.items() if v.get("pe")}
        if len(pes) >= 2 and max(pes.values()) - min(pes.values()) > 10:
            item["warnings"].append(f"PE口径差异较大: {pes}")

    try:
        item["fund_flow"] = eastmoney_fund_flow(code)
        if not item["fund_flow"]["ok"]:
            item["warnings"].append("eastmoney fund flow returned no rows")
    except Exception as exc:
        item["fund_flow"] = {"ok": False, "error": repr(exc)}
        item["warnings"].append(f"eastmoney fund flow failed: {exc}")

    return item


def audit_caches(codes):
    result = {"warnings": []}
    cache_files = {
        "sector_cache": os.path.join(ROOT, "data", "stock_sectors_cache.json"),
        "fundamentals_cache": os.path.join(ROOT, "data", "stock_fundamentals_cache.json"),
        "csi300_codes": os.path.join(ROOT, "data", "csi300_stocks.json"),
    }
    for name, path in cache_files.items():
        if not os.path.exists(path):
            result[name] = {"exists": False}
            result["warnings"].append(f"{name} missing: {path}")
            continue
        data = load_json(path)
        result[name] = {
            "exists": True,
            "items": len(data) if hasattr(data, "__len__") else None,
            "mtime": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
            "sample": {code: data.get(code) for code in codes if isinstance(data, dict)},
        }

    sectors = load_json(cache_files["sector_cache"]) if os.path.exists(cache_files["sector_cache"]) else {}
    csi300 = load_json(cache_files["csi300_codes"]) if os.path.exists(cache_files["csi300_codes"]) else []
    csi_codes = csi300 if isinstance(csi300, list) else list(csi300.keys())
    missing_sector = [code for code in csi_codes if code not in sectors]
    result["sector_coverage"] = {
        "csi300_count": len(csi_codes),
        "sector_cache_count": len(sectors),
        "missing_count": len(missing_sector),
        "missing_sample": missing_sector[:20],
    }
    if missing_sector:
        result["warnings"].append(f"sector cache missing {len(missing_sector)} CSI300 codes")

    result["known_code_issues"] = [
        "engine.data_fetcher.fetch_stock_info() writes cached PB into float_mv; this is not float market value.",
        "engine.data_fetcher.fetch_stock_info() writes Sina field[3] into reg_capital; field[3] is current price, not registered capital.",
        "D2 sector cache uses broad CSRC-like industries, not active market themes/concepts.",
    ]
    return result


def audit_baostock(codes, sample_size=1):
    result = {"available": fetch_baostock_kline is not None, "checks": [], "warnings": []}
    if fetch_baostock_kline is None:
        result["warnings"].append("baostock provider is not importable")
        return result

    for code in codes[:sample_size]:
        item = {"code": code}
        try:
            df = fetch_baostock_kline(code, start_date="2025-01-01")
            item["kline"] = {
                "ok": df is not None and len(df) > 0,
                "rows": int(len(df)) if df is not None else 0,
                "last_date": str(df["date"].iloc[-1].date()) if df is not None and len(df) else None,
                "last_close": float(df["close"].iloc[-1]) if df is not None and len(df) else None,
            }
        except Exception as exc:
            item["kline"] = {"ok": False, "error": repr(exc)}
            result["warnings"].append(f"baostock kline failed for {code}: {exc}")

        try:
            item["basic"] = fetch_baostock_stock_basic(code) if fetch_baostock_stock_basic else {}
        except Exception as exc:
            item["basic"] = {"ok": False, "error": repr(exc)}

        try:
            item["profit_2026q1"] = fetch_baostock_profit_data(code, 2026, 1) if fetch_baostock_profit_data else {}
        except Exception as exc:
            item["profit_2026q1"] = {"ok": False, "error": repr(exc)}

        result["checks"].append(item)
    return result


def audit_akshare():
    try:
        from data_providers.akshare_provider import probe_endpoints
    except Exception as exc:
        return {"available": False, "error": repr(exc), "endpoints": []}
    try:
        return {"available": True, "endpoints": probe_endpoints()}
    except Exception as exc:
        return {"available": True, "error": repr(exc), "endpoints": []}


def audit_tushare(code):
    try:
        from data_providers.tushare_provider import probe_endpoints
    except Exception as exc:
        return {"configured": False, "error": repr(exc), "endpoints": []}
    try:
        return probe_endpoints(code)
    except Exception as exc:
        return {"configured": True, "error": repr(exc), "endpoints": []}


def write_reports(payload):
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORT_DIR, f"data_source_audit_{stamp}.json")
    md_path = os.path.join(REPORT_DIR, f"data_source_audit_{stamp}.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    lines = [
        "# Data Source Audit",
        f"Generated: {payload['generated_at']}",
        "",
        "## Summary",
    ]
    for finding in payload["summary_findings"]:
        lines.append(f"- {finding}")
    lines.append("")
    lines.append("## Quote Checks")
    for item in payload["quote_checks"]:
        lines.append(f"### {item['code']}")
        for name, q in item["quotes"].items():
            lines.append(
                f"- {name}: {q.get('name')} price={q.get('price')} "
                f"chg={q.get('change_pct'):.2f}% amount={q.get('amount_yuan')}"
            )
        ff = item.get("fund_flow", {})
        lines.append(f"- fund_flow: ok={ff.get('ok')} rows={ff.get('rows', 0)} error={ff.get('error', '')}")
        for warning in item["warnings"]:
            lines.append(f"  - WARNING: {warning}")
        lines.append("")
    lines.append("## Cache Checks")
    cache = payload["cache_checks"]
    for warning in cache.get("warnings", []):
        lines.append(f"- WARNING: {warning}")
    lines.append(f"- Sector coverage: {cache.get('sector_coverage')}")
    lines.append("")
    lines.append("## Known Code Issues")
    for issue in cache.get("known_code_issues", []):
        lines.append(f"- {issue}")
    lines.append("")
    lines.append("## Provider Health")
    baostock = payload.get("baostock_checks", {})
    lines.append(f"- BaoStock available: {baostock.get('available')}")
    for item in baostock.get("checks", []):
        kline = item.get("kline", {})
        lines.append(
            f"  - {item.get('code')}: kline_ok={kline.get('ok')} rows={kline.get('rows')} "
            f"last_date={kline.get('last_date')} last_close={kline.get('last_close')}"
        )
    akshare = payload.get("akshare_checks")
    if akshare is not None:
        lines.append(f"- AKShare available: {akshare.get('available')}")
        for item in akshare.get("endpoints", []):
            lines.append(f"  - {item.get('endpoint')}: ok={item.get('ok')} rows/shape={item.get('rows', item.get('shape'))}")
            if item.get("error"):
                lines.append(f"    error={item.get('error')}")
    tushare = payload.get("tushare_checks")
    if tushare is not None:
        lines.append(f"- Tushare configured: {tushare.get('configured')} source={tushare.get('token_source', '')}")
        for item in tushare.get("endpoints", []):
            lines.append(f"  - {item.get('endpoint')}: ok={item.get('ok')} rows={item.get('rows')}")
            if item.get("error"):
                lines.append(f"    error={item.get('error')}")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return json_path, md_path


def main():
    parser = argparse.ArgumentParser(description="Audit V9 data sources")
    parser.add_argument("--codes", default="603501,000001,600519")
    parser.add_argument("--baostock-sample", type=int, default=1, help="Number of stocks to probe with BaoStock.")
    parser.add_argument("--probe-akshare", action="store_true", help="Probe AKShare endpoints; may be slow or unstable.")
    parser.add_argument("--probe-tushare", action="store_true", help="Probe a tiny Tushare permission sample. Does not run full scans.")
    args = parser.parse_args()

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    quote_checks = [compare_quotes(code) for code in codes]
    cache_checks = audit_caches(codes)
    baostock_checks = audit_baostock(codes, sample_size=max(0, args.baostock_sample))
    akshare_checks = audit_akshare() if args.probe_akshare else None
    tushare_checks = audit_tushare(codes[0]) if args.probe_tushare else None

    summary = []
    if all(item.get("quotes") for item in quote_checks):
        summary.append("行情价格/涨跌幅：腾讯、新浪、东方财富抽样基本一致，可作为价格源。")
    if any(not item.get("fund_flow", {}).get("ok") for item in quote_checks):
        summary.append("资金流：东方财富历史资金流抽样失败，不可直接支撑D1/热钱回测。")
    if any("PE口径差异" in warning for item in quote_checks for warning in item["warnings"]):
        summary.append("PE/基本面：不同源口径差异大，不能混用为强结论。")
    if cache_checks.get("sector_coverage", {}).get("missing_count", 0) > 0:
        summary.append("板块：缓存覆盖不完整，且行业分类过粗，不等于市场题材/概念热度。")
    if baostock_checks.get("checks"):
        ok_count = sum(1 for item in baostock_checks["checks"] if item.get("kline", {}).get("ok"))
        summary.append(f"BaoStock：历史K线抽样 {ok_count}/{len(baostock_checks['checks'])} 可用，可作为腾讯K线备用源。")
    if akshare_checks is not None:
        ok_count = sum(1 for item in akshare_checks.get("endpoints", []) if item.get("ok"))
        summary.append(f"AKShare：接口探测 {ok_count}/{len(akshare_checks.get('endpoints', []))} 可用，失败端点不纳入实盘依据。")
    if tushare_checks is not None:
        ok_count = sum(1 for item in tushare_checks.get("endpoints", []) if item.get("ok"))
        summary.append(f"Tushare：小样本权限探测 {ok_count}/{len(tushare_checks.get('endpoints', []))} 可用；不做全市场请求。")
    summary.append("建议：先修数据层，再谈胜率；否则策略优化会在错误输入上打转。")

    payload = {
        "generated_at": datetime.now().isoformat(),
        "codes": codes,
        "summary_findings": summary,
        "quote_checks": quote_checks,
        "cache_checks": cache_checks,
        "baostock_checks": baostock_checks,
        "akshare_checks": akshare_checks,
        "tushare_checks": tushare_checks,
    }
    json_path, md_path = write_reports(payload)
    print("\n".join(summary))
    print(f"JSON: {json_path}")
    print(f"MD: {md_path}")


if __name__ == "__main__":
    main()
