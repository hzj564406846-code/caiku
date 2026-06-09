"""Interactive stock advisor built on top of the V9 scoring engine.

This file intentionally does not modify engine/.  V9 remains the data/scoring
layer; this module turns scan results into accountable buy-before-thinking
reports: market heat, sector candidates, per-stock reasons, odds, risk and
action.
"""
import argparse
import contextlib
import io
import json
import math
import os
import sys
import time
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT_DIR)
sys.path.insert(0, ROOT_DIR)

from engine.cache_manager import CacheManager, load_csi300_codes, load_sector_cache
from engine.data_fetcher import (
    fetch_all_quotes,
    fetch_csi300_index,
    fetch_em_fund_flow_raw,
    fetch_10jqka_fund_flow,
    fetch_tencent_kline,
    get_stock_name,
)
from engine.hot_money import calc_sector_hot_score
from engine.market_regime import get_market_regime
from engine.pattern_detector import calc_atr_pct
from engine.position_sizer import calc_position
from engine.scan_manager import ScanManager
from engine.score_calculator import calc_score_v9

try:
    from data_providers.baostock_provider import (
        fetch_kline as fetch_baostock_kline,
        fetch_stock_basic as fetch_baostock_stock_basic,
    )
except Exception:
    fetch_baostock_kline = None
    fetch_baostock_stock_basic = None

try:
    from data_providers.tushare_provider import fetch_enrichment as fetch_tushare_enrichment
except Exception:
    fetch_tushare_enrichment = None


REPORT_DIR = os.path.join(ROOT_DIR, "reports")
TUSHARE_CACHE_DIR = os.path.join(ROOT_DIR, "cache", "tushare")
US_TECH_RISK_CACHE = os.path.join(ROOT_DIR, "cache", "market", "us_tech_risk.json")
THEME_RADAR_CACHE = os.path.join(ROOT_DIR, "cache", "market", "theme_radar.json")
US_TECH_RISK_SYMBOLS = {
    "QQQ": "Nasdaq/QQQ",
    "NVDA": "NVIDIA",
    "AMD": "AMD",
    "TSM": "TSMC ADR",
    "TSLA": "Tesla",
    "KWEB": "China Internet/KWEB",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
}


def market_date_label():
    now = datetime.now()
    if now.weekday() >= 5:
        return f"{now.strftime('%Y-%m-%d %H:%M')} 非交易日，使用上一交易日数据"
    return now.strftime("%Y-%m-%d %H:%M")


def pct(value):
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "N/A"


def money(value):
    try:
        v = float(value)
    except Exception:
        return "N/A"
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.0f}万"
    return f"{v:.0f}"


def safe_num(value, default=0.0):
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except Exception:
        return default


def quiet_call(fn, *args, verbose=False, **kwargs):
    if verbose:
        return fn(*args, **kwargs)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


def load_cached_json(path, max_age_hours=6):
    if not os.path.exists(path):
        return None
    age_hours = (datetime.now().timestamp() - os.path.getmtime(path)) / 3600
    if age_hours > max_age_hours:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def save_cached_json(path, payload):
    if not isinstance(payload, dict):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


def fetch_us_quote_changes(symbols):
    import akshare as ak

    out = {}
    for symbol in symbols:
        try:
            df = ak.stock_us_daily(symbol=symbol, adjust="")
        except Exception:
            continue
        if df is None or len(df) < 2:
            continue
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        close = safe_num(latest.get("close"))
        prev_close = safe_num(prev.get("close"))
        change_pct = (close - prev_close) / prev_close * 100 if prev_close else 0.0
        out[symbol] = {
            "name": US_TECH_RISK_SYMBOLS.get(symbol, symbol),
            "price": round(close, 4),
            "change_pct": round(change_pct, 2),
            "trade_date": str(latest.get("date")),
        }
    return out


def calc_overnight_us_tech_risk(quotes):
    qqq = safe_num((quotes.get("QQQ") or {}).get("change_pct"))
    semis = [safe_num((quotes.get(s) or {}).get("change_pct")) for s in ("NVDA", "AMD", "TSM") if s in quotes]
    megacap = [safe_num((quotes.get(s) or {}).get("change_pct")) for s in ("AAPL", "MSFT", "TSLA") if s in quotes]
    china_internet = safe_num((quotes.get("KWEB") or {}).get("change_pct"))
    semi_avg = sum(semis) / len(semis) if semis else 0.0
    megacap_avg = sum(megacap) / len(megacap) if megacap else 0.0

    score = 0
    reasons = []
    if qqq <= -2.5:
        score += 3
        reasons.append(f"QQQ大跌{qqq:.2f}%")
    elif qqq <= -1.2:
        score += 2
        reasons.append(f"QQQ下跌{qqq:.2f}%")
    elif qqq >= 1.2:
        score -= 1

    if semi_avg <= -3.0:
        score += 3
        reasons.append(f"半导体映射平均{semi_avg:.2f}%")
    elif semi_avg <= -1.5:
        score += 2
        reasons.append(f"半导体映射偏弱{semi_avg:.2f}%")
    elif semi_avg >= 1.5:
        score -= 1

    if megacap_avg <= -2.0:
        score += 1
        reasons.append(f"美股大科技平均{megacap_avg:.2f}%")
    if china_internet <= -2.0:
        score += 1
        reasons.append(f"中概科技/KWEB {china_internet:.2f}%")

    if score >= 5:
        level = "high"
        advice = "今日科技高弹性方向先防守，不追高；只看低开后承接强的回踩机会，候选股评级降一级。"
    elif score >= 3:
        level = "medium"
        advice = "今日科技方向谨慎，避免开盘追高；高弹性趋势池只做小仓验证或等回踩确认。"
    elif score <= -1:
        level = "supportive"
        advice = "隔夜美股科技对风险偏好有支撑；仍按A股板块热度和个股信号执行。"
    else:
        level = "low"
        advice = "隔夜美股科技风险不突出；今日主要看A股自身板块热度和资金持续性。"

    return {
        "level": level,
        "score": score,
        "qqq_change_pct": round(qqq, 2),
        "semi_avg_change_pct": round(semi_avg, 2),
        "megacap_avg_change_pct": round(megacap_avg, 2),
        "kweb_change_pct": round(china_internet, 2),
        "reasons": reasons,
        "advice": advice,
        "quotes": quotes,
        "source": "AkShare stock_us_daily",
        "generated_at": datetime.now().isoformat(),
    }


def fetch_overnight_us_tech_risk(verbose=False):
    cached = load_cached_json(US_TECH_RISK_CACHE, max_age_hours=6)
    if cached is not None:
        return cached
    try:
        quotes = fetch_us_quote_changes(list(US_TECH_RISK_SYMBOLS))
        payload = calc_overnight_us_tech_risk(quotes)
    except Exception as exc:
        if verbose:
            print(f"US tech risk fetch failed: {exc}")
        payload = {
            "level": "unknown",
            "score": 0,
            "reasons": [str(exc)],
            "advice": "隔夜美股科技风险暂不可用，今日只按A股自身信号执行。",
            "quotes": {},
            "source": "AkShare stock_us_daily",
            "generated_at": datetime.now().isoformat(),
        }
    save_cached_json(US_TECH_RISK_CACHE, payload)
    return payload


def _pick_col(row, names, default=None):
    for name in names:
        if name in row and row.get(name) is not None:
            return row.get(name)
    return default


def _parse_fund_flow_rows(df, source, top=10):
    rows = []
    if df is None or getattr(df, "empty", True):
        return rows
    for _, raw in df.head(top).iterrows():
        row = raw.to_dict()
        name = _pick_col(row, ["名称", "板块名称", "行业", "概念", "name"], "")
        net = _pick_col(row, ["今日主力净流入-净额", "主力净流入-净额", "净额", "净流入", "资金净流入"], 0)
        net_pct = _pick_col(row, ["今日主力净流入-净占比", "主力净流入-净占比", "净占比"], 0)
        change = _pick_col(row, ["今日涨跌幅", "涨跌幅", "板块涨跌幅"], 0)
        leader = _pick_col(row, ["今日主力净流入最大股", "领涨股票", "最大股"], "")
        if not name:
            continue
        rows.append({
            "name": str(name),
            "source": source,
            "net": safe_num(net),
            "net_pct": safe_num(net_pct),
            "change_pct": safe_num(change),
            "leader": str(leader) if leader is not None else "",
            "heat": round(
                min(100, max(0, 50 + safe_num(change) * 8 + safe_num(net_pct) * 3 + (20 if safe_num(net) > 0 else -10))),
                1,
            ),
        })
    return rows


def _fetch_eastmoney_sector_fund_flow_delay(sector_type, top=12):
    import requests

    sector_type_map = {"行业资金流": "2", "概念资金流": "3", "地域资金流": "1"}
    params = {
        "pn": "1",
        "pz": "100",
        "po": "1",
        "np": "1",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
        "fltt": "2",
        "invt": "2",
        "fid0": "f62",
        "fs": f"m:90 t:{sector_type_map[sector_type]}",
        "stat": "1",
        "fields": "f12,f14,f2,f3,f62,f184,f204,f205,f124",
        "rt": "52975239",
        "_": int(time.time() * 1000),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36",
    }
    response = requests.get("https://push2delay.eastmoney.com/api/qt/clist/get", params=params, headers=headers, timeout=20)
    response.raise_for_status()
    data = response.json()
    diff = ((data or {}).get("data") or {}).get("diff") or []
    rows = []
    for item in diff:
        net = safe_num(item.get("f62"))
        net_pct = safe_num(item.get("f184"))
        change = safe_num(item.get("f3"))
        rows.append({
            "name": str(item.get("f14") or ""),
            "source": f"{sector_type}/push2delay",
            "net": net,
            "net_pct": net_pct,
            "change_pct": change,
            "leader": str(item.get("f204") or ""),
            "heat": round(min(100, max(0, 50 + change * 8 + net_pct * 3 + (20 if net > 0 else -10))), 1),
        })
    rows = [row for row in rows if row["name"]]
    rows.sort(key=lambda row: (safe_num(row.get("heat")), safe_num(row.get("net"))), reverse=True)
    return rows[:top]


def fetch_external_theme_fund_flow(verbose=False):
    cached = load_cached_json(THEME_RADAR_CACHE, max_age_hours=1)
    if cached and cached.get("external_ok"):
        return cached
    payload = {
        "external_ok": False,
        "industry_fund_flow": [],
        "concept_fund_flow": [],
        "errors": [],
    }
    try:
        import akshare as ak
    except Exception as exc:
        payload["errors"].append(f"akshare unavailable: {type(exc).__name__}: {exc}")
        return payload

    endpoints = [
        ("industry_fund_flow", "行业资金流"),
        ("concept_fund_flow", "概念资金流"),
    ]
    for key, sector_type in endpoints:
        try:
            df = quiet_call(
                ak.stock_sector_fund_flow_rank,
                indicator="今日",
                sector_type=sector_type,
                verbose=verbose,
            )
            payload[key] = _parse_fund_flow_rows(df, sector_type, top=12)
        except Exception as exc:
            payload["errors"].append(f"{sector_type}: {type(exc).__name__}: {str(exc)[:180]}")
            try:
                payload[key] = _fetch_eastmoney_sector_fund_flow_delay(sector_type, top=12)
                payload["errors"].append(f"{sector_type}: AkShare主域失败，已使用push2delay兜底")
            except Exception as fallback_exc:
                payload["errors"].append(
                    f"{sector_type}/push2delay: {type(fallback_exc).__name__}: {str(fallback_exc)[:180]}"
                )
    payload["external_ok"] = bool(payload["industry_fund_flow"] or payload["concept_fund_flow"])
    if payload["external_ok"]:
        save_cached_json(THEME_RADAR_CACHE, payload)
    return payload


def build_scan_theme_radar(scan_result, sector_cache, verbose=False):
    external = fetch_external_theme_fund_flow(verbose=verbose)
    stocks = [s for s in scan_result.get("stocks", []) if not s.get("skip")]
    scan_rows = []
    by_sector = {}
    for stock in stocks:
        industry = stock.get("industry", "")
        if industry:
            by_sector.setdefault(industry, []).append(stock)

    sector_hot_scores = scan_result.get("sector_hot_scores", {}) or {}
    for name, members in by_sector.items():
        hot = safe_num(sector_hot_scores.get(name))
        if hot == 0:
            hot = calc_sector_hot_score(stocks, name, sector_cache)
        strong_count = sum(1 for item in members if safe_num(item.get("score")) >= 60)
        diffusion = strong_count / max(len(members), 1) * 100
        scan_rows.append({
            "name": name,
            "source": "scan_pool",
            "heat": round(hot, 1),
            "stock_count": len(members),
            "strong_count": strong_count,
            "diffusion_pct": round(diffusion, 1),
        })
    scan_rows.sort(key=lambda r: (r["heat"], r["diffusion_pct"], r["stock_count"]), reverse=True)

    best_external = (external.get("industry_fund_flow") or external.get("concept_fund_flow") or [])[:5]
    best_scan = scan_rows[:8]
    external_ok = bool(external.get("external_ok"))
    strongest = best_external[0]["name"] if best_external else (best_scan[0]["name"] if best_scan else "")
    top_heat = safe_num(best_external[0].get("heat")) if best_external else (safe_num(best_scan[0].get("heat")) if best_scan else 0)
    broad = sum(1 for row in best_scan if safe_num(row.get("heat")) >= 55)
    if external_ok and top_heat >= 70 and broad >= 2:
        posture = "可小仓进攻"
        advice = "题材资金和扫描池扩散同时较强，只在龙头回踩承接时小仓参与。"
    elif external_ok and top_heat >= 65:
        posture = "轻仓试探"
        advice = "外部资金流有热点，但需要个股资金和盘口承接确认，避免追高。"
    elif best_scan and safe_num(best_scan[0].get("heat")) >= 60:
        posture = "观察等待"
        advice = "扫描池有局部热度，但外部板块资金流未确认，先等题材扩散或资金回流。"
    else:
        posture = "防守观察"
        advice = "暂无可靠题材主线，不主动扩大仓位。"

    return {
        "source": "akshare+scan_pool" if external_ok else "scan_pool_fallback",
        "external_ok": external_ok,
        "strongest_theme": strongest,
        "posture": posture,
        "advice": advice,
        "industry_fund_flow": external.get("industry_fund_flow", [])[:8],
        "concept_fund_flow": external.get("concept_fund_flow", [])[:8],
        "scan_sector_heat": best_scan,
        "data_quality": {
            "external_errors": external.get("errors", []),
            "scan_sector_count": len(scan_rows),
        },
    }


def get_tushare_enrichment(code, enabled=True, verbose=False):
    if not enabled or fetch_tushare_enrichment is None:
        return {}
    path = os.path.join(TUSHARE_CACHE_DIR, f"tushare_{code}.json")
    cached = load_cached_json(path, max_age_hours=6)
    if cached is not None:
        return cached
    try:
        payload = quiet_call(fetch_tushare_enrichment, code, verbose=verbose)
    except Exception as exc:
        if verbose:
            print(f"Tushare enrichment failed for {code}: {exc}")
        payload = {"configured": False, "error": str(exc)}
    save_cached_json(path, payload)
    return payload


def evaluate_fundamental_gate(enrichment):
    finance = (enrichment or {}).get("finance") or {}
    if not finance:
        return {
            "status": "unknown",
            "block": False,
            "reasons": ["财务数据未启用或不可用"],
            "metrics": {},
        }
    if not finance.get("ok"):
        return {
            "status": "unknown",
            "block": False,
            "reasons": [f"财务数据不可用：{finance.get('error', 'empty')}"],
            "metrics": finance,
        }

    roe = safe_num(finance.get("roe"))
    gm = safe_num(finance.get("gross_margin"))
    npm = safe_num(finance.get("netprofit_margin"))
    debt = safe_num(finance.get("debt_to_assets"))
    revenue_yoy = safe_num(finance.get("revenue_yoy"))
    profit_yoy = safe_num(finance.get("profit_yoy"))

    hard = []
    warn = []
    if roe < 0:
        hard.append(f"ROE为负：{roe:.2f}%")
    elif roe <= 1:
        warn.append(f"ROE偏低：{roe:.2f}%")

    if npm < 0:
        hard.append(f"净利率为负：{npm:.2f}%")
    elif npm <= 3:
        warn.append(f"净利率偏低：{npm:.2f}%")

    if gm > 0 and gm < 5:
        hard.append(f"毛利率过低：{gm:.2f}%")
    elif gm > 0 and gm < 15:
        warn.append(f"毛利率偏低：{gm:.2f}%")

    if debt >= 85:
        hard.append(f"资产负债率过高：{debt:.2f}%")
    elif debt >= 70:
        warn.append(f"资产负债率偏高：{debt:.2f}%")

    if abs(profit_yoy) > 0.001:
        if profit_yoy <= -30:
            hard.append(f"净利润增速大幅下滑：{profit_yoy:.2f}%")
        elif profit_yoy < 0:
            warn.append(f"净利润增速为负：{profit_yoy:.2f}%")

    if abs(revenue_yoy) > 0.001:
        if revenue_yoy <= -30:
            hard.append(f"营收增速大幅下滑：{revenue_yoy:.2f}%")
        elif revenue_yoy < 0:
            warn.append(f"营收增速为负：{revenue_yoy:.2f}%")

    metrics = {
        "period": finance.get("period", ""),
        "ann_date": finance.get("ann_date", ""),
        "roe": roe,
        "gross_margin": gm,
        "netprofit_margin": npm,
        "debt_to_assets": debt,
        "revenue_yoy": revenue_yoy,
        "profit_yoy": profit_yoy,
    }
    if hard:
        status = "block"
        reasons = hard
    elif warn:
        status = "warn"
        reasons = warn
    else:
        status = "pass"
        reasons = ["基本面硬闸门通过"]
    return {
        "status": status,
        "block": bool(hard),
        "reasons": reasons,
        "warnings": warn,
        "metrics": metrics,
    }


def load_universe(limit=None, include_growth_board=False):
    codes = load_csi300_codes(os.path.join(ROOT_DIR, "data", "csi300_stocks.json"))
    if not codes:
        codes = [
            "600519", "000858", "601318", "600036", "000333", "002594",
            "300750", "600900", "601899", "600030", "000001", "601166",
            "601088", "600276", "300059", "601012", "002415", "000651",
            "600690", "601888", "000725", "600887", "002230", "600104",
            "601211", "000338", "600031", "300124", "600050", "002142",
            "000100", "601668", "600309", "000063", "601658", "603501",
            "600183", "002050", "002600",
        ]

    seen = set()
    cleaned = []
    for code in codes:
        code = str(code).strip()
        if not code or code in seen:
            continue
        if not include_growth_board and code.startswith(("688", "300", "301", "8", "4")):
            continue
        seen.add(code)
        cleaned.append(code)
    return cleaned[:limit] if limit else cleaned


def resolve_stock(query, codes, quotes=None, sector_cache=None):
    q = str(query).strip()
    if q.isdigit() and len(q) == 6:
        return q

    quotes = quotes or fetch_all_quotes(codes)
    for code, info in quotes.items():
        name = info.get("name", "")
        if q == name or q in name:
            return code

    # Last fallback: scan cached sector keys if user typed a code-like string.
    sector_cache = sector_cache or load_sector_cache()
    for code in sector_cache:
        if q == code:
            return code
    return None


def get_cached_or_fetch(cache, code, verbose=False):
    df = cache.load_kline(code)
    if df is None:
        df = quiet_call(fetch_tencent_kline, code, verbose=verbose)
        if (df is None or len(df) < 80) and fetch_baostock_kline is not None:
            try:
                fallback_df = quiet_call(fetch_baostock_kline, code, verbose=verbose)
                if fallback_df is not None and len(fallback_df) > 0:
                    df = fallback_df
            except Exception as exc:
                if verbose:
                    print(f"BaoStock fallback failed for {code}: {exc}")
        if df is None:
            df = cache.load_kline(code, max_age_hours=240)
        if df is not None:
            cache.save_kline(code, df)

    ff = cache.load_fund_flow(code)
    if ff is None:
        ff = quiet_call(fetch_em_fund_flow_raw, code, verbose=verbose)
        if ff is None:
            ff = quiet_call(fetch_10jqka_fund_flow, code, verbose=verbose)
        if ff is not None:
            cache.save_fund_flow(code, ff)
    return df, ff


def normalize_quote(code, quote, df=None):
    quote = dict(quote or {})
    if safe_num(quote.get("price")) <= 0 and df is not None and len(df) > 0:
        last = df.iloc[-1]
        name = quiet_call(get_stock_name, code) or code
        if name == code and fetch_baostock_stock_basic is not None:
            try:
                basic = quiet_call(fetch_baostock_stock_basic, code) or {}
                name = basic.get("name") or name
            except Exception:
                pass
        quote["name"] = quote.get("name") or name
        quote["price"] = safe_num(last.get("close"))
        quote.setdefault("open", safe_num(last.get("open")))
        quote.setdefault("high", safe_num(last.get("high")))
        quote.setdefault("low", safe_num(last.get("low")))
        if len(df) >= 2:
            prev = safe_num(df.iloc[-2].get("close"))
            quote["pre_close"] = prev
            quote["change_pct"] = (quote["price"] - prev) / prev * 100 if prev else 0
        quote["_fallback"] = "last_kline_close"
    return quote


def calc_technical_state(df, quote):
    if df is None or len(df) < 30:
        return {
            "ret_5d": 0,
            "ret_20d": 0,
            "ma20_gap": 0,
            "volume_ratio": 0,
            "price_position": "数据不足",
        }
    closes = df["close"].astype(float)
    volumes = df["volume"].astype(float)
    current = safe_num(quote.get("price"), closes.iloc[-1]) if quote else closes.iloc[-1]
    ret_5d = (current - closes.iloc[-6]) / closes.iloc[-6] * 100 if len(closes) >= 6 else 0
    ret_20d = (current - closes.iloc[-21]) / closes.iloc[-21] * 100 if len(closes) >= 21 else 0
    ma20 = closes.tail(20).mean()
    ma60 = closes.tail(60).mean() if len(closes) >= 60 else ma20
    ma20_gap = (current - ma20) / ma20 * 100 if ma20 else 0
    vol_avg = volumes.tail(20).mean()
    volume_ratio = volumes.iloc[-1] / vol_avg if vol_avg else 0

    if current > ma20 > ma60 and ret_20d > 5:
        price_position = "趋势强势"
    elif current > ma20 and ret_5d > 0:
        price_position = "短线走强"
    elif current < ma20 and ret_20d > 0:
        price_position = "趋势回踩"
    elif current < ma20 and ret_20d < -5:
        price_position = "破位偏弱"
    else:
        price_position = "震荡观察"

    return {
        "ret_5d": round(ret_5d, 2),
        "ret_20d": round(ret_20d, 2),
        "ma20_gap": round(ma20_gap, 2),
        "volume_ratio": round(volume_ratio, 2),
        "price_position": price_position,
    }


def calc_elastic_raw(stock, quote, df):
    if df is None or len(df) < 60:
        return None
    tech = calc_technical_state(df, quote)
    atr = safe_num(stock.get("atr_pct"), calc_atr_pct(df))
    change_pct = safe_num((quote or {}).get("change_pct"))
    return {
        "code": stock.get("code"),
        "name": stock.get("name") or (quote or {}).get("name", ""),
        "industry": stock.get("industry", ""),
        "score": safe_num(stock.get("score")),
        "d3": safe_num(stock.get("d3_trend")),
        "d4": safe_num(stock.get("d4_volume")),
        "atr_pct": atr,
        "ret_20d": safe_num(tech.get("ret_20d")),
        "ret_5d": safe_num(tech.get("ret_5d")),
        "ma20_gap": safe_num(tech.get("ma20_gap")),
        "volume_ratio": safe_num(tech.get("volume_ratio")),
        "price_position": tech.get("price_position", ""),
        "change_pct": change_pct,
        "limit_move": abs(change_pct) >= 9.5,
    }


def _z(value, mean, std):
    return (value - mean) / std if std else 0.0


def rank_elastic_trend(rows):
    rows = [r for r in rows if r]
    if not rows:
        return []
    fields = ["atr_pct", "ret_20d", "ma20_gap", "d3"]
    stats = {}
    for field in fields:
        vals = [safe_num(r.get(field)) for r in rows]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        stats[field] = (mean, math.sqrt(var))
    for row in rows:
        row["elastic_trend_score"] = round(
            _z(row["atr_pct"], *stats["atr_pct"])
            + _z(row["ret_20d"], *stats["ret_20d"])
            + _z(row["ma20_gap"], *stats["ma20_gap"])
            + _z(row["d3"], *stats["d3"]),
            2,
        )
    return sorted(rows, key=lambda r: r["elastic_trend_score"], reverse=True)


def estimate_forward_odds(df, quote=None):
    """Find same-stock historical days with similar technical state.

    This is not a cross-market statistical model yet.  It is a conservative MVP:
    same stock, similar 5d momentum bucket, similar volume activity and same
    relation to MA20.  If sample size is small, the report says so.
    """
    empty = {
        "samples": 0,
        "quality": "样本不足",
        "horizons": {
            "3d": {"win_rate": 0, "avg": 0, "max_adverse": 0},
            "5d": {"win_rate": 0, "avg": 0, "max_adverse": 0},
            "10d": {"win_rate": 0, "avg": 0, "max_adverse": 0},
        },
    }
    if df is None or len(df) < 80:
        return empty

    closes = df["close"].astype(float).reset_index(drop=True)
    volumes = df["volume"].astype(float).reset_index(drop=True)
    current_price = safe_num((quote or {}).get("price"), closes.iloc[-1])
    current_ret5 = (current_price - closes.iloc[-6]) / closes.iloc[-6] * 100
    current_ma20 = closes.tail(20).mean()
    current_above_ma20 = current_price >= current_ma20
    current_vol_ratio = volumes.iloc[-1] / volumes.tail(20).mean()

    matches = []
    max_horizon = 10
    for i in range(30, len(closes) - max_horizon):
        ma20 = closes.iloc[i - 19:i + 1].mean()
        vol_avg = volumes.iloc[i - 19:i + 1].mean()
        if ma20 <= 0 or vol_avg <= 0:
            continue
        ret5 = (closes.iloc[i] - closes.iloc[i - 5]) / closes.iloc[i - 5] * 100
        above_ma20 = closes.iloc[i] >= ma20
        vol_ratio = volumes.iloc[i] / vol_avg

        if abs(ret5 - current_ret5) > 3.0:
            continue
        if above_ma20 != current_above_ma20:
            continue
        if abs(vol_ratio - current_vol_ratio) > 0.8:
            continue

        row = {}
        adverse = []
        for h in (3, 5, 10):
            future = (closes.iloc[i + h] - closes.iloc[i]) / closes.iloc[i] * 100
            row[f"ret_{h}d"] = future
            path_low = closes.iloc[i + 1:i + h + 1].min()
            adverse.append((path_low - closes.iloc[i]) / closes.iloc[i] * 100)
        row["max_adverse"] = min(adverse) if adverse else 0
        matches.append(row)

    if not matches:
        return empty

    horizons = {}
    for h in (3, 5, 10):
        vals = [m[f"ret_{h}d"] for m in matches]
        win_rate = sum(1 for v in vals if v > 0) / len(vals) * 100
        horizons[f"{h}d"] = {
            "win_rate": round(win_rate, 1),
            "avg": round(sum(vals) / len(vals), 2),
            "max_adverse": round(sum(m["max_adverse"] for m in matches) / len(matches), 2),
        }

    if len(matches) >= 30:
        quality = "可参考"
    elif len(matches) >= 12:
        quality = "弱参考"
    else:
        quality = "样本偏少"

    return {"samples": len(matches), "quality": quality, "horizons": horizons}


def classify_dimension(value, strong, ok, reverse=False):
    value = safe_num(value)
    if reverse:
        if value >= strong:
            return "强"
        if value >= ok:
            return "一般"
        return "弱"
    if value >= strong:
        return "强"
    if value >= ok:
        return "一般"
    return "弱"


def format_wan(value):
    try:
        v = float(value)
    except Exception:
        return "N/A"
    if abs(v) >= 10000:
        return f"{v / 10000:.2f}亿"
    return f"{v:.0f}万"


def enrichment_reasons(enrichment, fundamental_gate=None):
    positives = []
    negatives = []
    if not enrichment:
        return positives, negatives

    ths = enrichment.get("fund_flow_ths") or {}
    if ths.get("ok"):
        net_5d = safe_num(ths.get("net_5d"))
        latest_net = safe_num(ths.get("latest_net"))
        consecutive = int(safe_num(ths.get("consecutive_inflow")))
        if net_5d > 0 and latest_net > 0:
            positives.append(
                f"Tushare资金流确认：5日净流入{format_wan(net_5d)}，最近一日{format_wan(latest_net)}，连续流入{consecutive}天"
            )
        elif net_5d > 0:
            positives.append(f"Tushare资金流偏正：5日净流入{format_wan(net_5d)}")
        elif net_5d < 0 and latest_net < 0:
            negatives.append(f"Tushare资金流偏弱：5日净流出{format_wan(abs(net_5d))}，最近一日净流出{format_wan(abs(latest_net))}")
        elif net_5d < 0:
            negatives.append(f"Tushare资金流拖累：5日净流出{format_wan(abs(net_5d))}")
    elif ths:
        negatives.append(f"Tushare同花顺资金流不可用：{ths.get('error', 'empty')}")

    finance = enrichment.get("finance") or {}
    gate_status = (fundamental_gate or {}).get("status")
    if gate_status and gate_status != "pass":
        return positives, negatives

    if finance.get("ok"):
        roe = safe_num(finance.get("roe"))
        gm = safe_num(finance.get("gross_margin"))
        npm = safe_num(finance.get("netprofit_margin"))
        period = finance.get("period", "")
        if roe > 3 and gm > 20 and npm > 5:
            positives.append(f"Tushare财务指标支持：{period} ROE {roe:.2f}%，毛利率{gm:.1f}%，净利率{npm:.1f}%")
        elif roe <= 1 or npm <= 3:
            negatives.append(f"Tushare财务指标一般：{period} ROE {roe:.2f}%，净利率{npm:.1f}%")
        else:
            positives.append(f"Tushare财务指标可用：{period} ROE {roe:.2f}%，毛利率{gm:.1f}%，净利率{npm:.1f}%")
    elif finance:
        negatives.append(f"Tushare财务指标不可用：{finance.get('error', 'empty')}")

    return positives, negatives


def build_reasons(stock, quote, sector_hot, tech, odds, enrichment=None, fundamental_gate=None):
    score = safe_num(stock.get("score"))
    d1 = safe_num(stock.get("d1_capital"))
    d2 = safe_num(stock.get("d2_sector"))
    d3 = safe_num(stock.get("d3_trend"))
    d4 = safe_num(stock.get("d4_volume"))
    d5 = safe_num(stock.get("d5_sentiment"))
    d6 = safe_num(stock.get("d6_fundamental"))
    d7 = safe_num(stock.get("d7_risk"))
    atr = safe_num(stock.get("atr_pct"))
    change_pct = safe_num((quote or {}).get("change_pct"))

    positives = []
    negatives = []
    fundamental_gate = fundamental_gate or evaluate_fundamental_gate(enrichment)

    if fundamental_gate.get("status") == "block":
        negatives.append("基本面硬闸门触发：" + "；".join(fundamental_gate.get("reasons", [])[:3]))
    elif fundamental_gate.get("status") == "warn":
        negatives.append("基本面质量偏弱：" + "；".join(fundamental_gate.get("reasons", [])[:3]))
    elif fundamental_gate.get("status") == "pass":
        positives.append("基本面硬闸门通过")
    else:
        negatives.append("基本面硬闸门未知：财务数据未启用或不可用")

    if score >= 70:
        positives.append(f"V9综合分{score:.0f}，属于高分候选")
    elif score >= 60:
        positives.append(f"V9综合分{score:.0f}，达到候选线")
    else:
        negatives.append(f"V9综合分{score:.0f}不足，暂未进入强候选区")

    if sector_hot >= 70 or d2 >= 14:
        positives.append(f"板块共振较强：板块热度{sector_hot:.0f}，D2={d2:.0f}")
    elif sector_hot >= 55 or d2 >= 10:
        positives.append(f"板块有热度但不算极强：板块热度{sector_hot:.0f}，D2={d2:.0f}")
    else:
        negatives.append(f"板块热度不足：板块热度{sector_hot:.0f}，D2={d2:.0f}")

    if d1 >= 22:
        positives.append(f"资金面强：D1={d1:.0f}")
    elif d1 < 12:
        negatives.append(f"资金面弱或数据不足：D1={d1:.0f}")

    if d3 >= 10 and tech["price_position"] in ("趋势强势", "短线走强"):
        positives.append(f"趋势结构健康：D3={d3:.0f}，{tech['price_position']}")
    elif d3 < 7:
        negatives.append(f"趋势质量不足：D3={d3:.0f}，{tech['price_position']}")

    if d4 >= 10 and tech["volume_ratio"] >= 1.2:
        positives.append(f"量价配合较好：D4={d4:.0f}，量比约{tech['volume_ratio']:.2f}")
    elif d4 < 7:
        negatives.append(f"量价健康度不足：D4={d4:.0f}")

    if d6 >= 7:
        positives.append(f"基本面/估值维度较好：D6={d6:.0f}")
    elif d6 <= 3:
        negatives.append(f"基本面/估值维度拖后腿：D6={d6:.0f}")

    if d7 <= -15:
        negatives.append(f"风险扣分较重：D7={d7:.0f}")
    if atr > 7:
        negatives.append(f"ATR={atr:.1f}%超过可交易阈值，波动过大")
    elif atr < 1.5:
        negatives.append(f"ATR={atr:.1f}%偏低，可能是低弹性标的")

    if change_pct >= 7:
        negatives.append(f"当日涨幅{change_pct:.1f}%偏高，追高风险大")

    odds5 = odds["horizons"].get("5d", {})
    if odds["samples"] >= 12 and odds5.get("win_rate", 0) >= 55 and odds5.get("avg", 0) > 0:
        positives.append(
            f"历史相似样本5日胜率{odds5['win_rate']:.1f}%、均值{odds5['avg']:+.2f}%"
        )
    elif odds["samples"] >= 12:
        negatives.append(
            f"历史相似样本优势不足：5日胜率{odds5.get('win_rate', 0):.1f}%、均值{odds5.get('avg', 0):+.2f}%"
        )
    else:
        negatives.append(f"历史相似样本{odds['samples']}个，暂不足以支撑高置信胜率判断")

    ep, en = enrichment_reasons(enrichment, fundamental_gate=fundamental_gate)
    positives.extend(ep)
    negatives.extend(en)

    return positives, negatives


def decide_action(stock, quote, sector_hot, tech, odds, enrichment=None, fundamental_gate=None):
    if stock.get("skip"):
        return "禁止买", "评分引擎标记跳过：" + str(stock.get("skip_reason", ""))
    fundamental_gate = fundamental_gate or evaluate_fundamental_gate(enrichment)
    if fundamental_gate.get("block"):
        return "禁止买", "基本面硬闸门触发：" + "；".join(fundamental_gate.get("reasons", [])[:3])

    score = safe_num(stock.get("score"))
    d1 = safe_num(stock.get("d1_capital"))
    d2 = safe_num(stock.get("d2_sector"))
    d3 = safe_num(stock.get("d3_trend"))
    d4 = safe_num(stock.get("d4_volume"))
    d7 = safe_num(stock.get("d7_risk"))
    atr = safe_num(stock.get("atr_pct"))
    change_pct = safe_num((quote or {}).get("change_pct"))
    odds5 = odds["horizons"].get("5d", {})
    win5 = safe_num(odds5.get("win_rate"))
    avg5 = safe_num(odds5.get("avg"))
    ths = (enrichment or {}).get("fund_flow_ths") or {}
    ts_net_5d = safe_num(ths.get("net_5d")) if ths.get("ok") else 0
    ts_latest_net = safe_num(ths.get("latest_net")) if ths.get("ok") else 0

    if atr > 7 or d7 <= -18:
        return "禁止买", "风险维度已经触发硬过滤"
    if ts_net_5d < -8000 and ts_latest_net < 0:
        return "不建议买", "Tushare资金流连续偏弱，先不跟资金对着干"
    if score < 55:
        return "不建议买", "综合分不足，先不拿资金冒险"
    if change_pct >= 7:
        return "等回踩", "当日涨幅过高，当前追买盈亏比不好"
    if d2 < 8:
        return "只观察", "个股可能有亮点，但缺少板块共振"
    if d3 < 6:
        return "只观察", "趋势结构还没站稳"

    historical_ok = odds["samples"] >= 12 and win5 >= 55 and avg5 > 0
    if tech["price_position"] == "趋势回踩" and score >= 60 and d2 >= 8 and d3 >= 8:
        return "等回踩确认", "趋势仍在，但必须等回踩企稳或重新放量"
    if score >= 72 and d1 >= 18 and d2 >= 12 and d3 >= 9 and d4 >= 8 and historical_ok:
        return "短线可买", "资金、板块、趋势、历史相似样本同时通过"
    if score >= 70 and d1 >= 18 and d2 >= 12 and d3 >= 8 and d4 >= 8 and historical_ok:
        return "轻仓试错", "核心条件通过，但只允许小仓位验证"
    return "只观察", "有候选价值，但还没到可下手的强度"


def make_trade_plan(stock, quote, tech, action=None, account_equity=100000, cash=100000):
    price = safe_num((quote or {}).get("price"))
    atr = safe_num(stock.get("atr_pct"))
    score = safe_num(stock.get("score"))
    if price <= 0:
        return {
            "entry_zone": "价格缺失",
            "stop_loss": "N/A",
            "position": "N/A",
            "invalid": "行情价格缺失，不做买入判断",
        }
    if action not in ("短线可买", "轻仓试错"):
        return {
            "entry_zone": "暂不主动买入，等待板块热度/趋势/胜率重新确认",
            "stop_loss": "N/A",
            "position": "暂不建仓",
            "invalid": "若资金流转弱、跌破近期低点、或板块继续无共振，则维持回避",
        }

    sizing = calc_position(cash, account_equity, price, atr, score)
    pullback = price * (1 - max(0.015, min(0.04, atr / 200)))
    chase_ceiling = price * (1 + 0.01)
    return {
        "entry_zone": f"{pullback:.2f} - {chase_ceiling:.2f}",
        "stop_loss": f"{sizing['stop_loss']:.2f}",
        "position": f"{sizing['shares']}股，约{sizing['position_pct']:.1f}%仓位",
        "invalid": "跌破止损价、板块热度退潮、或V9评分跌破候选线",
    }


def analyze_stock(stock, quote, sector_hot, df, account_equity=100000, cash=100000, enrichment=None):
    tech = calc_technical_state(df, quote)
    odds = estimate_forward_odds(df, quote)
    fundamental_gate = evaluate_fundamental_gate(enrichment)
    positives, negatives = build_reasons(
        stock, quote, sector_hot, tech, odds, enrichment=enrichment, fundamental_gate=fundamental_gate
    )
    action, action_reason = decide_action(
        stock, quote, sector_hot, tech, odds, enrichment=enrichment, fundamental_gate=fundamental_gate
    )
    plan = make_trade_plan(stock, quote, tech, action=action, account_equity=account_equity, cash=cash)

    return {
        "code": stock.get("code"),
        "name": stock.get("name") or (quote or {}).get("name", ""),
        "industry": stock.get("industry", ""),
        "score": stock.get("score", 0),
        "action": action,
        "action_reason": action_reason,
        "quote": quote or {},
        "sector_hot": sector_hot,
        "tech": tech,
        "odds": odds,
        "positives": positives,
        "negatives": negatives,
        "plan": plan,
        "tushare": enrichment or {},
        "fundamental_gate": fundamental_gate,
        "dimensions": {
            "资金面D1": stock.get("d1_capital", 0),
            "板块D2": stock.get("d2_sector", 0),
            "趋势D3": stock.get("d3_trend", 0),
            "量价D4": stock.get("d4_volume", 0),
            "相对强度D5": stock.get("d5_sentiment", 0),
            "基本面D6": stock.get("d6_fundamental", 0),
            "风险D7": stock.get("d7_risk", 0),
        },
    }


def print_stock_report(report, alternatives=None):
    q = report["quote"]
    print("=" * 78)
    print(f"个股买前审查：{report['code']} {report['name']} | {market_date_label()}")
    print("=" * 78)
    print(f"结论：{report['action']} | {report['action_reason']}")
    print(f"所属板块：{report['industry'] or '未知'} | 板块热度：{report['sector_hot']:.0f}")
    print(
        f"现价：{safe_num(q.get('price')):.2f} | 今日涨跌：{pct(q.get('change_pct'))} | "
        f"换手：{safe_num(q.get('turnover')):.2f}% | PE：{safe_num(q.get('pe')):.1f}"
    )
    print()

    print("维度拆解：")
    for k, v in report["dimensions"].items():
        print(f"- {k}: {safe_num(v):.1f}")
    t = report["tech"]
    print(
        f"- 技术状态: {t['price_position']} | 5日{pct(t['ret_5d'])} | "
        f"20日{pct(t['ret_20d'])} | 距MA20 {pct(t['ma20_gap'])} | 量比{t['volume_ratio']:.2f}"
    )
    ts = report.get("tushare") or {}
    if ts:
        ths = ts.get("fund_flow_ths") or {}
        finance = ts.get("finance") or {}
        gate = report.get("fundamental_gate") or {}
        print("- Tushare增强:")
        if ths.get("ok"):
            print(
                f"  · 资金流：{ths.get('trade_date', '')} 5日净额{format_wan(ths.get('net_5d'))}，"
                f"当日净额{format_wan(ths.get('latest_net'))}，连续流入{int(safe_num(ths.get('consecutive_inflow')))}天"
            )
        else:
            print(f"  · 资金流：不可用 {ths.get('error', '')}")
        if finance.get("ok"):
            print(
                f"  · 财务：{finance.get('period', '')} ROE {safe_num(finance.get('roe')):.2f}%，"
                f"毛利率{safe_num(finance.get('gross_margin')):.1f}%，净利率{safe_num(finance.get('netprofit_margin')):.1f}%"
            )
        if gate:
            print(f"  · 基本面硬闸门：{gate.get('status', 'unknown')} | {'；'.join(gate.get('reasons', [])[:3])}")
    print()

    print("支持理由：")
    if report["positives"]:
        for r in report["positives"]:
            print(f"- {r}")
    else:
        print("- 暂无足够强的正向证据")

    print()
    print("风险/否定理由：")
    if report["negatives"]:
        for r in report["negatives"]:
            print(f"- {r}")
    else:
        print("- 暂未发现硬伤，但仍按止损执行")

    print()
    print("历史相似样本：")
    odds = report["odds"]
    print(f"- 样本数：{odds['samples']} | 质量：{odds['quality']}")
    for h in ("3d", "5d", "10d"):
        v = odds["horizons"][h]
        print(
            f"- 未来{h}: 胜率{v['win_rate']:.1f}% | 均值{v['avg']:+.2f}% | "
            f"平均最大不利波动{v['max_adverse']:+.2f}%"
        )

    print()
    print("操作计划：")
    p = report["plan"]
    print(f"- 理想买入区间：{p['entry_zone']}")
    print(f"- 建议止损价：{p['stop_loss']}")
    print(f"- 参考仓位：{p['position']}")
    print(f"- 失效条件：{p['invalid']}")

    if alternatives:
        print()
        print("同板块替代候选：")
        for item in alternatives[:5]:
            print(
                f"- {item['code']} {item['name']} | 分数{item['score']:.0f} | "
                f"建议{item['action']} | {item['action_reason']}"
            )


def print_daily_report(scan_result, reports, sector_cache, elastic_pool=None, overnight_risk=None, theme_radar=None):
    regime = scan_result.get("regime", {})
    breadth = scan_result.get("market_breadth", {})
    hot_sectors = scan_result.get("hot_sectors", [])
    print("=" * 78)
    print(f"股票顾问报告 {market_date_label()}")
    print("=" * 78)
    print(
        f"市场状态：{regime.get('tag', regime.get('regime', '未知'))} | "
        f"CSI300 20日：{pct(regime.get('return_20d', 0))} | "
        f"上涨家数：{breadth.get('up', '?')} | 下跌家数：{breadth.get('down', '?')}"
    )
    if overnight_risk:
        print(
            f"隔夜美股科技风险：{overnight_risk.get('level', 'unknown')} | "
            f"QQQ {pct(overnight_risk.get('qqq_change_pct'))} | "
            f"半导体映射 {pct(overnight_risk.get('semi_avg_change_pct'))}"
        )
        reasons = overnight_risk.get("reasons") or []
        if reasons:
            print(f"今日环境理由：{'；'.join(reasons[:3])}")
        print(f"今日操作建议：{overnight_risk.get('advice', '')}")
    print()

    if theme_radar:
        print("题材/热钱雷达：")
        print(
            f"- 当前主线：{theme_radar.get('strongest_theme') or '未确认'} | "
            f"状态：{theme_radar.get('posture', '未知')} | 数据源：{theme_radar.get('source', 'unknown')}"
        )
        print(f"- 操作建议：{theme_radar.get('advice', '')}")
        industry_flow = theme_radar.get("industry_fund_flow") or []
        concept_flow = theme_radar.get("concept_fund_flow") or []
        if industry_flow:
            print("- 行业资金流：")
            for row in industry_flow[:5]:
                leader = f" | 代表：{row.get('leader')}" if row.get("leader") else ""
                print(
                    f"  · {row.get('name')} | 热度{safe_num(row.get('heat')):.0f} | "
                    f"涨跌{pct(row.get('change_pct'))} | 净占比{safe_num(row.get('net_pct')):.2f}%{leader}"
                )
        if concept_flow:
            print("- 概念资金流：")
            for row in concept_flow[:5]:
                leader = f" | 代表：{row.get('leader')}" if row.get("leader") else ""
                print(
                    f"  · {row.get('name')} | 热度{safe_num(row.get('heat')):.0f} | "
                    f"涨跌{pct(row.get('change_pct'))} | 净占比{safe_num(row.get('net_pct')):.2f}%{leader}"
                )
        if not industry_flow and not concept_flow:
            errors = (theme_radar.get("data_quality") or {}).get("external_errors") or []
            if errors:
                print(f"- 外部板块资金流暂不可用：{errors[0]}")
            scan_rows = theme_radar.get("scan_sector_heat") or []
            for row in scan_rows[:5]:
                print(
                    f"  · {row.get('name')} | 扫描热度{safe_num(row.get('heat')):.0f} | "
                    f"强候选{row.get('strong_count', 0)}/{row.get('stock_count', 0)} | "
                    f"扩散{safe_num(row.get('diffusion_pct')):.1f}%"
                )
        print()

    print("热钱/板块方向：")
    if hot_sectors:
        for s in hot_sectors[:8]:
            print(
                f"- {s.get('name')} | 热度{s.get('score', 0):.0f} | "
                f"板块均涨{pct(s.get('avg_change', 0))} | 样本{s.get('stock_count', 0)}只"
            )
    else:
        sectors = scan_result.get("sectors", {})
        if sectors:
            for name, score in list(sectors.items())[:8]:
                print(f"- {name} | 扫描强度{score:.0f}")
        else:
            print("- 暂未识别出明确高热板块")

    print()
    print("高弹性趋势池：")
    if elastic_pool:
        for r in elastic_pool[:10]:
            flag = " | 涨跌停极端" if r.get("limit_move") else ""
            print(
                f"- {r['code']} {r['name']} | 弹性趋势分{r['elastic_trend_score']:+.2f} | "
                f"20日{pct(r['ret_20d'])} | ATR{r['atr_pct']:.2f}% | "
                f"距MA20 {pct(r['ma20_gap'])} | D3={r['d3']:.1f}{flag}"
            )
    else:
        print("- 暂无足够数据计算高弹性趋势池")

    print()
    print("短线热钱池：")
    shortlist = [r for r in reports if r["action"] in ("短线可买", "轻仓试错")]
    if not shortlist:
        print("- 今日没有达到“短线可买/轻仓试错”的高置信候选")
    for r in shortlist[:10]:
        print(
            f"- {r['code']} {r['name']} | {r['action']} | 分数{r['score']:.0f} | "
            f"{r['industry']} | 理由：{r['action_reason']}"
        )
        for reason in r["positives"][:2]:
            print(f"  · 支持：{reason}")
        for risk in r["negatives"][:1]:
            print(f"  · 风险：{risk}")

    print()
    print("波段/观察池：")
    watch = [r for r in reports if r["action"] in ("等回踩", "等回踩确认", "只观察")]
    for r in watch[:10]:
        print(
            f"- {r['code']} {r['name']} | {r['action']} | 分数{r['score']:.0f} | "
            f"{r['industry']} | 风险：{'; '.join(r['negatives'][:1]) or '等待触发'}"
        )
        for reason in r["positives"][:1]:
            print(f"  · 支持：{reason}")

    print()
    print("禁止/不建议：")
    avoid = [r for r in reports if r["action"] in ("禁止买", "不建议买")]
    if avoid:
        for r in avoid[:5]:
            print(f"- {r['code']} {r['name']} | {r['action']} | {r['action_reason']}")
    else:
        print("- 候选池前列暂无硬过滤标的")


def save_report_json(payload, prefix):
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return path


def run_scan(codes, threads, verbose=False):
    mgr = ScanManager(codes, n_threads=threads)
    return quiet_call(mgr.run_scan, verbose=verbose) or {"stocks": [], "hot_sectors": [], "sectors": {}}


def score_with_enrichment(stock, df, ff, sector_cache, quote, csi300_df, quotes, enrichment, regime=None):
    fund_data = (enrichment or {}).get("engine_fund_data") or ff
    if not fund_data:
        return stock
    try:
        updated = calc_score_v9(
            stock.get("code"),
            df,
            fund_data,
            sector_cache,
            quote,
            regime_weights=(regime or {}).get("weights", {}),
            csi300_df=csi300_df,
            quotes=quotes,
        )
        updated["_base_score"] = stock.get("score")
        updated["_enhanced_by_tushare"] = bool((enrichment or {}).get("engine_fund_data"))
        return updated
    except Exception:
        return stock


def make_reports_from_scan(scan_result, codes, top, account_equity, cash, verbose=False, use_tushare=True):
    cache = CacheManager(base_dir=os.path.join(ROOT_DIR, "cache"))
    sector_cache = load_sector_cache(os.path.join(ROOT_DIR, "data", "stock_sectors_cache.json"))
    stocks = [s for s in scan_result.get("stocks", []) if not s.get("skip")]
    stocks.sort(key=lambda s: s.get("score", 0), reverse=True)
    selected = stocks[:top]
    selected_codes = [s["code"] for s in selected]
    quotes = quiet_call(fetch_all_quotes, selected_codes, verbose=verbose) or {}
    csi300_df = quiet_call(fetch_csi300_index, verbose=verbose)
    regime = scan_result.get("regime") or get_market_regime(csi300_df)

    reports = []
    for s in selected:
        df, ff = get_cached_or_fetch(cache, s["code"], verbose=verbose)
        quote = normalize_quote(s["code"], quotes.get(s["code"], {}), df)
        enrichment = get_tushare_enrichment(s["code"], enabled=use_tushare, verbose=verbose)
        s = score_with_enrichment(s, df, ff, sector_cache, quote, csi300_df, quotes, enrichment, regime)
        industry = s.get("industry", "")
        sector_hot = scan_result.get("sector_hot_scores", {}).get(industry, 0)
        if sector_hot == 0 and industry:
            sector_hot = calc_sector_hot_score(scan_result.get("stocks", []), industry, sector_cache)
        reports.append(analyze_stock(s, quote, sector_hot, df, account_equity, cash, enrichment=enrichment))
    reports.sort(key=lambda r: safe_num(r.get("score")), reverse=True)
    return reports


def build_elastic_trend_pool(scan_result, codes, top=20, verbose=False):
    cache = CacheManager(base_dir=os.path.join(ROOT_DIR, "cache"))
    stocks = [s for s in scan_result.get("stocks", []) if s.get("code")]
    selected_codes = [s["code"] for s in stocks]
    quotes = quiet_call(fetch_all_quotes, selected_codes, verbose=verbose) or {}
    rows = []
    for stock in stocks:
        code = stock["code"]
        df, _ = get_cached_or_fetch(cache, code, verbose=verbose)
        quote = normalize_quote(code, quotes.get(code, {}), df)
        row = calc_elastic_raw(stock, quote, df)
        if row:
            rows.append(row)
    return rank_elastic_trend(rows)[:top]


def analyze_single(code, scan_result, account_equity, cash, verbose=False, use_tushare=True):
    cache = CacheManager(base_dir=os.path.join(ROOT_DIR, "cache"))
    sector_cache = load_sector_cache(os.path.join(ROOT_DIR, "data", "stock_sectors_cache.json"))
    quotes = quiet_call(fetch_all_quotes, [code], verbose=verbose) or {}
    quote = quotes.get(code, {})
    df, ff = get_cached_or_fetch(cache, code, verbose=verbose)
    quote = normalize_quote(code, quote, df)
    enrichment = get_tushare_enrichment(code, enabled=use_tushare, verbose=verbose)
    csi300_df = quiet_call(fetch_csi300_index, verbose=verbose)
    regime = get_market_regime(csi300_df)
    sector_hot_scores = scan_result.get("sector_hot_scores", {}) if scan_result else {}
    stock_in_scan = None
    for s in (scan_result or {}).get("stocks", []):
        if s.get("code") == code:
            stock_in_scan = s
            break

    if stock_in_scan:
        stock = score_with_enrichment(
            stock_in_scan, df, ff, sector_cache, quote, csi300_df, quotes, enrichment, regime
        )
    else:
        fund_data = (enrichment or {}).get("engine_fund_data") or ff
        stock = calc_score_v9(
            code,
            df,
            fund_data,
            sector_cache,
            quote,
            regime_weights=regime.get("weights", {}),
            csi300_df=csi300_df,
            quotes=quotes,
        )

    industry = stock.get("industry", "")
    sector_hot = sector_hot_scores.get(industry, 0)
    if sector_hot == 0 and scan_result and industry:
        sector_hot = calc_sector_hot_score(scan_result.get("stocks", []), industry, sector_cache)
    return analyze_stock(stock, quote, sector_hot, df, account_equity, cash, enrichment=enrichment)


def alternatives_for(report, scan_result, account_equity, cash, verbose=False, use_tushare=True):
    industry = report.get("industry", "")
    if not industry or not scan_result:
        return []
    candidates = [
        s for s in scan_result.get("stocks", [])
        if s.get("industry") == industry and s.get("code") != report.get("code") and not s.get("skip")
    ]
    candidates.sort(key=lambda s: s.get("score", 0), reverse=True)
    quotes = quiet_call(fetch_all_quotes, [s["code"] for s in candidates[:5]], verbose=verbose) or {}
    cache = CacheManager(base_dir=os.path.join(ROOT_DIR, "cache"))
    out = []
    for s in candidates[:5]:
        df, _ = get_cached_or_fetch(cache, s["code"], verbose=verbose)
        quote = normalize_quote(s["code"], quotes.get(s["code"], {}), df)
        enrichment = get_tushare_enrichment(s["code"], enabled=use_tushare, verbose=verbose)
        item = analyze_stock(
            s,
            quote,
            report.get("sector_hot", 0),
            df,
            account_equity,
            cash,
            enrichment=enrichment,
        )
        out.append(item)
    return out


def main():
    parser = argparse.ArgumentParser(description="V9 股票机会顾问：每日选股 + 个股买前审查")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--daily", action="store_true", help="生成今日全市场/候选池机会报告")
    mode.add_argument("--ask", type=str, help="审查某只股票，支持代码或名称")
    parser.add_argument("--limit", type=int, default=180, help="扫描股票数量，默认180")
    parser.add_argument("--top", type=int, default=30, help="分析扫描结果前N名，默认30")
    parser.add_argument("--threads", type=int, default=8, help="扫描线程数")
    parser.add_argument("--include-growth-board", action="store_true", help="包含科创/创业板")
    parser.add_argument("--equity", type=float, default=100000, help="用于仓位估算的账户权益")
    parser.add_argument("--cash", type=float, default=100000, help="用于仓位估算的可用现金")
    parser.add_argument("--json", action="store_true", help="保存JSON报告")
    parser.add_argument("--verbose", action="store_true", help="显示底层数据接口错误")
    parser.add_argument("--no-tushare", action="store_true", help="关闭Tushare资金流/财务增强")
    args = parser.parse_args()
    use_tushare = not args.no_tushare

    codes = load_universe(args.limit, include_growth_board=args.include_growth_board)

    if args.ask:
        # Ask mode still runs a market scan so the answer knows sector heat and alternatives.
        rough_quotes = quiet_call(fetch_all_quotes, codes, verbose=args.verbose) or {}
        code = resolve_stock(args.ask, codes, rough_quotes)
        if not code:
            print(f"无法识别股票：{args.ask}")
            sys.exit(2)
        if code not in codes:
            codes = [code] + codes
        scan_result = run_scan(codes, args.threads, verbose=args.verbose)
        report = analyze_single(code, scan_result, args.equity, args.cash, verbose=args.verbose, use_tushare=use_tushare)
        alts = alternatives_for(report, scan_result, args.equity, args.cash, verbose=args.verbose, use_tushare=use_tushare)
        print_stock_report(report, alts)
        if args.json:
            path = save_report_json({"report": report, "alternatives": alts}, "ask_report")
            print(f"\nJSON报告已保存：{path}")
        return

    overnight_risk = fetch_overnight_us_tech_risk(verbose=args.verbose)
    scan_result = run_scan(codes, args.threads, verbose=args.verbose)
    reports = make_reports_from_scan(scan_result, codes, args.top, args.equity, args.cash, verbose=args.verbose, use_tushare=use_tushare)
    elastic_pool = build_elastic_trend_pool(scan_result, codes, top=args.top, verbose=args.verbose)
    sector_cache = load_sector_cache(os.path.join(ROOT_DIR, "data", "stock_sectors_cache.json"))
    theme_radar = build_scan_theme_radar(scan_result, sector_cache, verbose=args.verbose)
    print_daily_report(
        scan_result,
        reports,
        sector_cache,
        elastic_pool=elastic_pool,
        overnight_risk=overnight_risk,
        theme_radar=theme_radar,
    )
    if args.json:
        path = save_report_json(
            {
                "scan": scan_result,
                "reports": reports,
                "elastic_trend_pool": elastic_pool,
                "overnight_us_tech_risk": overnight_risk,
                "theme_radar": theme_radar,
            },
            "daily_report",
        )
        print(f"\nJSON报告已保存：{path}")


if __name__ == "__main__":
    main()
