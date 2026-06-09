"""BaoStock provider.

BaoStock is useful here because it is not routed through Eastmoney push2, which
is currently unstable on this machine.  We use it as a historical K-line and
financial-metric backup, not as the primary real-time quote source.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout, redirect_stderr
import io

import pandas as pd


def _bs_code(code: str) -> str:
    code = str(code).strip()
    prefix = "sh" if code.startswith("6") else "sz"
    return f"{prefix}.{code}"


@contextmanager
def _session():
    import baostock as bs

    sink = io.StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login.error_msg}")
    try:
        yield bs
    finally:
        with redirect_stdout(sink), redirect_stderr(sink):
            bs.logout()


def _to_frame(rs) -> pd.DataFrame:
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if rs.error_code != "0":
        raise RuntimeError(rs.error_msg)
    return pd.DataFrame(rows, columns=rs.fields)


def fetch_kline(code: str, start_date: str = "2025-01-01", end_date: str | None = None,
                adjust: str = "qfq") -> pd.DataFrame | None:
    """Return daily K-line with engine-compatible columns.

    BaoStock adjustflag: 2 is forward-adjusted, 1 backward-adjusted, 3 none.
    """
    from datetime import datetime

    end_date = end_date or datetime.now().strftime("%Y-%m-%d")
    adjustflag = {"qfq": "2", "hfq": "1", "none": "3"}.get(adjust, "2")
    fields = "date,code,open,high,low,close,preclose,volume,amount,pctChg,turn"
    with _session() as bs:
        rs = bs.query_history_k_data_plus(
            _bs_code(code),
            fields,
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag=adjustflag,
        )
        df = _to_frame(rs)

    if df.empty:
        return None

    for col in ["open", "high", "low", "close", "preclose", "volume", "amount", "pctChg", "turn"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "open", "high", "low", "close"])
    return df[["date", "open", "close", "high", "low", "volume", "amount", "pctChg", "turn"]]


def fetch_stock_basic(code: str) -> dict:
    with _session() as bs:
        rs = bs.query_stock_basic(code=_bs_code(code))
        df = _to_frame(rs)
    if df.empty:
        return {}
    row = df.iloc[0].to_dict()
    return {
        "code": code,
        "name": row.get("code_name", ""),
        "ipo_date": row.get("ipoDate", ""),
        "out_date": row.get("outDate", ""),
        "type": row.get("type", ""),
        "status": row.get("status", ""),
        "_source": "baostock",
    }


def fetch_profit_data(code: str, year: int, quarter: int) -> dict:
    with _session() as bs:
        rs = bs.query_profit_data(code=_bs_code(code), year=year, quarter=quarter)
        df = _to_frame(rs)
    if df.empty:
        return {}
    row = df.iloc[0].to_dict()
    numeric_fields = [
        "roeAvg", "npMargin", "gpMargin", "netProfit", "epsTTM",
        "totalShare", "liqaShare",
    ]
    out = {"code": code, "pubDate": row.get("pubDate"), "statDate": row.get("statDate"), "_source": "baostock"}
    for field in numeric_fields:
        out[field] = pd.to_numeric(row.get(field), errors="coerce")
        if pd.isna(out[field]):
            out[field] = None
    return out
