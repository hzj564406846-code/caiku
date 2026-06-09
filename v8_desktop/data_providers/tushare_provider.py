"""Tushare provider probes.

The token is read from the local Codex config or TUSHARE_TOKEN.  This module
never prints the token; it only reports which endpoints are usable.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd


def _read_token_from_codex_config() -> str | None:
    path = Path.home() / ".codex" / "config.toml"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"api\.tushare\.pro/mcp/\?token=([^\"'\s]+)", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"TUSHARE_TOKEN\s*=\s*[\"']([^\"']+)[\"']", text)
    if match:
        return match.group(1).strip()
    return None


def get_token() -> str | None:
    token = os.environ.get("TUSHARE_TOKEN")
    if token:
        return token.strip()
    return _read_token_from_codex_config()


def _ts_code(code: str) -> str:
    code = str(code).strip()
    suffix = "SH" if code.startswith("6") else "SZ"
    return f"{code}.{suffix}"


def _date_range(days: int) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=max(days * 3, 15))
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _safe_float(value, default=0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _first_non_null(row, *fields):
    for field in fields:
        if field not in row:
            continue
        value = row.get(field)
        if value is not None and not pd.isna(value):
            return value
    return None


def _latest_periods(limit: int = 6) -> list[str]:
    today = datetime.now()
    periods = []
    year = today.year
    for y in range(year, year - 3, -1):
        for md in ("1231", "0930", "0630", "0331"):
            period = f"{y}{md}"
            if period <= today.strftime("%Y%m%d"):
                periods.append(period)
    return periods[:limit]


def _get_pro():
    token = get_token()
    if not token:
        return None
    import tushare as ts

    return ts.pro_api(token)


def fetch_moneyflow_ths(code: str, days: int = 5) -> dict:
    pro = _get_pro()
    if pro is None:
        return {"ok": False, "error": "Tushare token not configured"}

    start, end = _date_range(days)
    df = pro.moneyflow_ths(ts_code=_ts_code(code), start_date=start, end_date=end)
    if df is None or df.empty:
        return {"ok": False, "source": "tushare.moneyflow_ths", "rows": 0}

    df = df.sort_values("trade_date")
    tail = df.tail(days)
    latest = tail.iloc[-1]
    net_values = [_safe_float(v) for v in tail.get("net_amount", [])]
    net_5d = _safe_float(latest.get("net_d5_amount"), sum(net_values))
    consecutive = 0
    for value in reversed(net_values):
        if value > 0:
            consecutive += 1
        else:
            break

    return {
        "ok": True,
        "source": "tushare.moneyflow_ths",
        "rows": int(len(df)),
        "trade_date": str(latest.get("trade_date", "")),
        "latest_net": _safe_float(latest.get("net_amount")),
        "net_5d": net_5d,
        "avg_daily_net": net_5d / max(len(tail), 1),
        "consecutive_inflow": consecutive,
        "large_buy_amount": _safe_float(latest.get("buy_lg_amount")),
        "large_buy_rate": _safe_float(latest.get("buy_lg_amount_rate")),
        "pct_change": _safe_float(latest.get("pct_change")),
        "latest_price": _safe_float(latest.get("latest")),
    }


def fetch_moneyflow(code: str, days: int = 5) -> dict:
    pro = _get_pro()
    if pro is None:
        return {"ok": False, "error": "Tushare token not configured"}

    start, end = _date_range(days)
    df = pro.moneyflow(ts_code=_ts_code(code), start_date=start, end_date=end)
    if df is None or df.empty:
        return {"ok": False, "source": "tushare.moneyflow", "rows": 0}

    df = df.sort_values("trade_date")
    tail = df.tail(days)
    latest = tail.iloc[-1]
    large_net = (
        _safe_float(latest.get("buy_lg_amount")) - _safe_float(latest.get("sell_lg_amount"))
        + _safe_float(latest.get("buy_elg_amount")) - _safe_float(latest.get("sell_elg_amount"))
    )
    small_net = _safe_float(latest.get("buy_sm_amount")) - _safe_float(latest.get("sell_sm_amount"))
    return {
        "ok": True,
        "source": "tushare.moneyflow",
        "rows": int(len(df)),
        "trade_date": str(latest.get("trade_date", "")),
        "net_mf_amount": _safe_float(latest.get("net_mf_amount")),
        "large_net_amount": large_net,
        "small_net_amount": small_net,
    }


def fetch_fina_indicator(code: str) -> dict:
    pro = _get_pro()
    if pro is None:
        return {"ok": False, "error": "Tushare token not configured"}

    last_error = None
    for period in _latest_periods():
        try:
            df = pro.fina_indicator(ts_code=_ts_code(code), period=period)
        except Exception as exc:
            last_error = exc
            continue
        if df is None or df.empty:
            continue
        row = df.sort_values("end_date").iloc[-1]
        return {
            "ok": True,
            "source": "tushare.fina_indicator",
            "period": str(row.get("end_date", period)),
            "ann_date": str(row.get("ann_date", "")),
            "eps": _safe_float(row.get("eps")),
            "roe": _safe_float(row.get("roe")),
            "gross_margin": _safe_float(row.get("grossprofit_margin")),
            "netprofit_margin": _safe_float(row.get("netprofit_margin")),
            "debt_to_assets": _safe_float(row.get("debt_to_assets")),
            "revenue_yoy": _safe_float(_first_non_null(row, "or_yoy", "q_sales_yoy")),
            "profit_yoy": _safe_float(_first_non_null(row, "q_netprofit_yoy", "q_profit_yoy", "netprofit_yoy")),
        }

    return {"ok": False, "source": "tushare.fina_indicator", "error": repr(last_error) if last_error else "empty"}


def to_engine_fund_data(ths_flow: dict) -> dict | None:
    if not ths_flow or not ths_flow.get("ok"):
        return None
    return {
        "_source": "10jqka",
        "_provider": "tushare.moneyflow_ths",
        "net_5d": ths_flow.get("net_5d", 0),
        "avg_daily_net": ths_flow.get("avg_daily_net", 0),
        "consecutive_inflow": ths_flow.get("consecutive_inflow", 0),
    }


def fetch_enrichment(code: str, days: int = 5) -> dict:
    configured = bool(get_token())
    if not configured:
        return {"configured": False, "fund_flow_ths": {}, "moneyflow": {}, "finance": {}}

    result = {"configured": True}
    for key, fn in (
        ("fund_flow_ths", lambda: fetch_moneyflow_ths(code, days=days)),
        ("moneyflow", lambda: fetch_moneyflow(code, days=days)),
        ("finance", lambda: fetch_fina_indicator(code)),
    ):
        try:
            result[key] = fn()
        except Exception as exc:
            result[key] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:240]}"}
    result["engine_fund_data"] = to_engine_fund_data(result.get("fund_flow_ths", {}))
    return result


def _probe_call(name: str, fn) -> dict:
    try:
        df = fn()
        return {
            "endpoint": name,
            "ok": True,
            "rows": int(len(df)) if df is not None else 0,
            "columns": list(getattr(df, "columns", []))[:20],
        }
    except Exception as exc:
        return {
            "endpoint": name,
            "ok": False,
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }


def probe_endpoints(code: str = "603501") -> dict:
    token = get_token()
    if not token:
        return {"configured": False, "endpoints": []}

    import tushare as ts

    pro = ts.pro_api(token)
    ts_code = _ts_code(code)
    endpoints = [
        ("stock_basic", lambda: pro.stock_basic(ts_code=ts_code, fields="ts_code,symbol,name,area,industry,market,list_date")),
        ("daily", lambda: pro.daily(ts_code=ts_code, start_date="20260601", end_date="20260605")),
        ("daily_basic", lambda: pro.daily_basic(ts_code=ts_code, start_date="20260601", end_date="20260605")),
        ("moneyflow", lambda: pro.moneyflow(ts_code=ts_code, start_date="20260601", end_date="20260605")),
        ("moneyflow_ths", lambda: pro.moneyflow_ths(ts_code=ts_code, start_date="20260601", end_date="20260605")),
        ("fina_indicator", lambda: pro.fina_indicator(ts_code=ts_code, period="20260331")),
    ]
    return {
        "configured": True,
        "token_source": "TUSHARE_TOKEN" if os.environ.get("TUSHARE_TOKEN") else "codex_config",
        "endpoints": [_probe_call(name, fn) for name, fn in endpoints],
    }
