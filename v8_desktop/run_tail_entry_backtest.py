"""Tail-entry execution backtest for candidate factor lines.

This script is an execution-layer test, not a replacement for factor research.
It uses factors known at T close, enters at T close with friction, then measures
T+1/T+2 exits.  The goal is to see whether factors that worked in 3/5/10-day
research survive a more realistic tail-buy / next-day handling path.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from datetime import timedelta

import numpy as np
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT_DIR)
sys.path.insert(0, ROOT_DIR)

from engine.cache_manager import load_csi300_codes  # noqa: E402
from run_factor_research import build_factor_table, fetch_klines, zscore_series  # noqa: E402


FACTOR_SPECS = {
    "elastic_base": ["atr_pct", "ret_20d", "ma20_gap"],
    "elastic_d3": ["atr_pct", "ret_20d", "ma20_gap", "d3"],
    "elastic_d3_sector": ["atr_pct", "ret_20d", "ma20_gap", "d3", "sector_hot"],
}


def add_candidate_scores(df):
    work = df.copy()
    grouped = work.groupby("date", group_keys=False)
    for factor in sorted({f for factors in FACTOR_SPECS.values() for f in factors}):
        work[f"z_{factor}"] = grouped[factor].transform(zscore_series).fillna(0)
    for name, factors in FACTOR_SPECS.items():
        work[name] = work[[f"z_{f}" for f in factors]].sum(axis=1)
    return work


def attach_execution_prices(factor_df, kline_dict):
    rows = []
    for _, row in factor_df.iterrows():
        code = row["code"]
        df = kline_dict.get(code)
        if df is None or df.empty:
            continue
        dates = df["date"].astype(str).str[:10]
        matches = df.index[dates == str(row["date"])[:10]]
        if len(matches) == 0:
            continue
        idx = int(matches[0])
        if idx + 1 >= len(df):
            continue
        item = row.to_dict()
        item["entry_close"] = float(df.loc[idx, "close"])
        item["entry_low"] = float(df.loc[idx, "low"])
        for offset, prefix in ((1, "t1"), (2, "t2"), (3, "t3")):
            fidx = idx + offset
            if fidx >= len(df):
                item[f"{prefix}_date"] = ""
                item[f"{prefix}_open"] = np.nan
                item[f"{prefix}_high"] = np.nan
                item[f"{prefix}_low"] = np.nan
                item[f"{prefix}_close"] = np.nan
                continue
            item[f"{prefix}_date"] = str(pd.to_datetime(df.loc[fidx, "date"]).date())
            item[f"{prefix}_open"] = float(df.loc[fidx, "open"])
            item[f"{prefix}_high"] = float(df.loc[fidx, "high"])
            item[f"{prefix}_low"] = float(df.loc[fidx, "low"])
            item[f"{prefix}_close"] = float(df.loc[fidx, "close"])
        rows.append(item)
    return pd.DataFrame(rows)


def fetch_baostock_5m(code, start_date, end_date):
    import baostock as bs

    bs_code = ("sh." if str(code).startswith("6") else "sz.") + str(code)
    fields = "date,time,code,open,high,low,close,volume,amount"
    rs = bs.query_history_k_data_plus(
        bs_code,
        fields,
        start_date=start_date,
        end_date=end_date,
        frequency="5",
        adjustflag="2",
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if rs.error_code != "0" or not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=rs.fields)
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["clock"] = df["time"].astype(str).str[8:12].str.replace(r"(\d{2})(\d{2})", r"\1:\2", regex=True)
    df = df.dropna(subset=["date", "close"])
    return df


def attach_minute_exit_prices(picks, exit_time, cache):
    if picks.empty:
        return picks
    work = picks.copy()
    work["t1_minute_exit"] = np.nan
    work["t1_1400_price"] = np.nan  # Always fetch 14:00 for conditional decision rules
    valid_dates = pd.to_datetime(work["t1_date"], errors="coerce").dropna()
    if valid_dates.empty:
        return work
    start = (valid_dates.min() - timedelta(days=3)).strftime("%Y-%m-%d")
    end = (valid_dates.max() + timedelta(days=3)).strftime("%Y-%m-%d")

    import baostock as bs
    from contextlib import redirect_stderr, redirect_stdout
    import io

    sink = io.StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        login = bs.login()
    if login.error_code != "0":
        work["_minute_error"] = f"baostock login failed: {login.error_msg}"
        return work
    try:
        for code in sorted(work["code"].unique()):
            key = (code, start, end)
            if key not in cache:
                cache[key] = fetch_baostock_5m(code, start, end)
            mdf = cache[key]
            if mdf.empty:
                continue
            sub_idx = work.index[work["code"] == code].tolist()
            for idx in sub_idx:
                date = str(work.at[idx, "t1_date"])
                day = mdf[mdf["date"] == date]
                if day.empty:
                    continue
                # User-specified minute exit time
                exact = day[day["clock"] == exit_time]
                if exact.empty:
                    exact = day[day["clock"] >= exit_time].head(1)
                if not exact.empty:
                    work.at[idx, "t1_minute_exit"] = float(exact.iloc[0]["close"])
                # Always fetch 14:00 for conditional decision rules
                exact14 = day[day["clock"] == "14:00"]
                if exact14.empty:
                    exact14 = day[day["clock"] >= "14:00"].head(1)
                if not exact14.empty:
                    work.at[idx, "t1_1400_price"] = float(exact14.iloc[0]["close"])
    finally:
        with redirect_stdout(sink), redirect_stderr(sink):
            bs.logout()
    return work


def net_return(entry_price, exit_price, cost_bps, slippage_bps):
    if not entry_price or not exit_price:
        return None
    buy = float(entry_price) * (1 + slippage_bps / 10000.0)
    sell = float(exit_price) * (1 - slippage_bps / 10000.0)
    raw = (sell - buy) / buy * 100.0
    return raw - (cost_bps * 2 / 100.0)


def compute_decision_returns(row, cost_bps, slippage_bps):
    """Compute conditional 14:00 decision returns.

    Rules (the letter codes match the task spec):
      B — 14:00 return <= -2%  → sell at 14:00;  else → T+1 close
      C — 14:00 < T day low    → sell at 14:00;  else → T+1 close
      D — 14:00 return > 0 AND 14:00 >= T day low → hold to T+2 close;
          else → sell at 14:00
      E — 14:00 return <= -2% OR 14:00 < T day low → sell at 14:00;
          else → hold to T+2 close
    """
    entry = row.get("entry_close")
    t1_1400 = row.get("t1_1400_price")
    entry_low = row.get("entry_low")
    t1_close = row.get("t1_close")
    t2_close = row.get("t2_close")

    out = {}
    if pd.isna(entry) or not entry or pd.isna(t1_1400) or not t1_1400:
        return out

    ret_1400 = net_return(entry, t1_1400, cost_bps, slippage_bps)
    if ret_1400 is None:
        return out

    below_t_low = (
        pd.notna(entry_low) and entry_low
        and float(t1_1400) < float(entry_low)
    )

    # ── Rule B: 14:00 <= -2% → sell at 14:00, else T+1 close ──
    if ret_1400 <= -2.0:
        out["t1_1400_dec_b"] = ret_1400
    elif pd.notna(t1_close) and t1_close:
        out["t1_1400_dec_b"] = net_return(entry, t1_close, cost_bps, slippage_bps)

    # ── Rule C: 14:00 < T day low → sell at 14:00, else T+1 close ──
    if below_t_low:
        out["t1_1400_dec_c"] = ret_1400
    elif pd.notna(t1_close) and t1_close:
        out["t1_1400_dec_c"] = net_return(entry, t1_close, cost_bps, slippage_bps)

    # ── Rule D: 14:00 > 0 AND not below T day low → T+2; else 14:00 ──
    if ret_1400 > 0 and not below_t_low:
        if pd.notna(t2_close) and t2_close:
            out["t1_1400_dec_d"] = net_return(entry, t2_close, cost_bps, slippage_bps)
    else:
        out["t1_1400_dec_d"] = ret_1400

    # ── Rule E: 14:00 <= -2% OR below T day low → 14:00; else T+2 ──
    if ret_1400 <= -2.0 or below_t_low:
        out["t1_1400_dec_e"] = ret_1400
    elif pd.notna(t2_close) and t2_close:
        out["t1_1400_dec_e"] = net_return(entry, t2_close, cost_bps, slippage_bps)

    return out


def stop_take_exit(row, fallback_col, stop_pct, take_profit_pct, cost_bps, slippage_bps):
    entry = row.get("entry_close")
    if pd.isna(entry) or not entry:
        return None
    low = row.get("t1_low")
    high = row.get("t1_high")
    stop_price = float(entry) * (1 - stop_pct / 100.0) if stop_pct > 0 else None
    take_price = float(entry) * (1 + take_profit_pct / 100.0) if take_profit_pct > 0 else None

    # Daily bars do not tell intraday order. Be conservative: if both stop and
    # take-profit are touched, assume the stop was hit first.
    if stop_price and pd.notna(low) and float(low) <= stop_price:
        return net_return(entry, stop_price, cost_bps, slippage_bps)
    if take_price and pd.notna(high) and float(high) >= take_price:
        return net_return(entry, take_price, cost_bps, slippage_bps)
    return net_return(entry, row.get(fallback_col), cost_bps, slippage_bps)


def build_exec_returns(row, stop_pct, take_profit_pct, cost_bps, slippage_bps):
    """Compute tail-entry returns from point-in-time row.

    The entry is T close.  T+1 stop/take-profit uses daily high/low.  If both
    are touched in one day, assume stop first because daily bars cannot resolve
    intraday order.
    """
    entry = row.get("entry_close")
    out = {
        "t1_open": net_return(entry, row.get("t1_open"), cost_bps, slippage_bps),
        "t1_minute": net_return(entry, row.get("t1_minute_exit"), cost_bps, slippage_bps),
        "t1_close": net_return(entry, row.get("t1_close"), cost_bps, slippage_bps),
        "t1_stop_take_close": stop_take_exit(row, "t1_close", stop_pct, take_profit_pct, cost_bps, slippage_bps),
        "t2_close": net_return(entry, row.get("t2_close"), cost_bps, slippage_bps),
        "t3_close": net_return(entry, row.get("t3_close"), cost_bps, slippage_bps),
    }
    # Merge conditional 14:00 decision returns
    dec_rets = compute_decision_returns(row, cost_bps, slippage_bps)
    out.update(dec_rets)
    out = {k: v for k, v in out.items() if v is not None and pd.notna(v)}
    return out


def stats(vals):
    vals = pd.to_numeric(pd.Series(vals), errors="coerce").dropna()
    if vals.empty:
        return {"n": 0}
    wins = vals[vals > 0]
    losses = vals[vals <= 0]
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = abs(float(losses.sum())) if len(losses) else 0.0
    return {
        "n": int(len(vals)),
        "avg": round(float(vals.mean()), 3),
        "median": round(float(vals.median()), 3),
        "win_rate": round(float(len(wins) / len(vals) * 100), 1),
        "avg_win": round(float(wins.mean()), 3) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 3) if len(losses) else 0.0,
        "worst": round(float(vals.min()), 3),
        "best": round(float(vals.max()), 3),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
    }


def equity_stats(trades):
    if not trades:
        return {}
    daily = {}
    for trade in trades:
        daily.setdefault(trade["date"], []).append(trade["ret"])
    curve = []
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for date in sorted(daily):
        day_ret = float(np.mean(daily[date])) / 100.0
        equity *= (1 + day_ret)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1)
        curve.append({"date": date, "equity": round(equity, 6), "day_ret": round(day_ret * 100, 3)})
    return {
        "days": len(curve),
        "total_return": round((equity - 1) * 100, 3),
        "max_drawdown": round(max_dd * 100, 3),
        "curve_tail": curve[-10:],
    }


def select_trades(df, score_col, args):
    selected = []
    for date, group in df.groupby("date"):
        g = group.copy()
        if args.exclude_limit:
            g = g[g["limit_move_flag"] == 0]
        g = g[
            (g["atr_pct"] >= args.min_atr)
            & (g["atr_pct"] <= args.max_atr)
            & (g["ret_20d"] >= args.min_ret20)
            & (g["ma20_gap"] >= args.min_ma20_gap)
        ]
        if args.min_d3 is not None:
            g = g[g["d3"] >= args.min_d3]
        if g.empty:
            continue
        selected.append(g.nlargest(args.select, score_col))
    return pd.concat(selected, ignore_index=True) if selected else pd.DataFrame()


def evaluate_spec(df, score_col, args, minute_cache):
    picks = select_trades(df, score_col, args)
    if args.minute_exit:
        picks = attach_minute_exit_prices(picks, args.minute_exit_time, minute_cache)
    result = {"selected": int(len(picks)), "exits": {}, "equity": {}}
    if picks.empty:
        return result

    exit_returns = {
        "t1_open": [], "t1_minute": [], "t1_close": [],
        "t1_stop_take_close": [], "t2_close": [], "t3_close": [],
        "t1_1400_dec_b": [], "t1_1400_dec_c": [],
        "t1_1400_dec_d": [], "t1_1400_dec_e": [],
    }
    exit_trades = {k: [] for k in exit_returns}
    for _, row in picks.iterrows():
        rets = build_exec_returns(row, args.stop_pct, args.take_profit_pct, args.cost_bps, args.slippage_bps)
        for exit_name, ret in rets.items():
            exit_returns[exit_name].append(ret)
            exit_trades[exit_name].append({
                "date": row["date"],
                "code": row["code"],
                "industry": row.get("industry", ""),
                "ret": ret,
                "score": float(row[score_col]),
                "atr_pct": float(row["atr_pct"]),
                "ret_20d": float(row["ret_20d"]),
                "ma20_gap": float(row["ma20_gap"]),
                "d3": float(row["d3"]),
                "sector_hot": float(row["sector_hot"]),
            })

    for exit_name, vals in exit_returns.items():
        result["exits"][exit_name] = stats(vals)
        result["equity"][exit_name] = equity_stats(exit_trades[exit_name])
    result["sample_trades"] = {k: v[:20] for k, v in exit_trades.items()}
    return result


def run(args):
    started = time.time()
    codes = load_csi300_codes(os.path.join(ROOT_DIR, "data", "csi300_stocks.json"))[:args.top]
    df, cfg = build_factor_table(codes, args.days, args.kline_count, args.threads)
    kline_dict = fetch_klines(codes, args.kline_count, args.threads)
    df = attach_execution_prices(df, kline_dict)
    df = df.dropna(subset=["entry_close", "t1_open", "t1_close"])
    df = add_candidate_scores(df)

    specs = {}
    minute_cache = {}
    for spec_name in FACTOR_SPECS:
        specs[spec_name] = evaluate_spec(df, spec_name, args, minute_cache)

    return {
        "config": {
            **cfg,
            "generated_at": datetime.now().isoformat(),
            "records": int(len(df)),
            "factor_specs": FACTOR_SPECS,
            "select_per_day": args.select,
            "filters": {
                "min_atr": args.min_atr,
                "max_atr": args.max_atr,
                "min_ret20": args.min_ret20,
                "min_ma20_gap": args.min_ma20_gap,
                "min_d3": args.min_d3,
                "exclude_limit": args.exclude_limit,
            },
            "cost_bps_per_side": args.cost_bps,
            "slippage_bps_per_side": args.slippage_bps,
            "stop_pct": args.stop_pct,
            "take_profit_pct": args.take_profit_pct,
            "minute_exit": args.minute_exit,
            "minute_exit_time": args.minute_exit_time,
            "note": "Entry uses T close. T+1 stop/take uses daily high/low; if both touched, stop is assumed first.",
            "elapsed_seconds": round(time.time() - started, 1),
        },
        "results": specs,
    }


def print_report(result):
    cfg = result["config"]
    print("=" * 78)
    print("尾盘买入/短线退出执行层回测")
    print("=" * 78)
    print(f"区间: {cfg['date_range']} | 股票: {cfg['codes_valid']}/{cfg['codes_total']} | 样本: {cfg['records']}")
    print(
        f"每日选 {cfg['select_per_day']} | ATR {cfg['filters']['min_atr']}~{cfg['filters']['max_atr']} | "
        f"ret20>={cfg['filters']['min_ret20']} | ma20_gap>={cfg['filters']['min_ma20_gap']}"
    )
    print(f"摩擦: 手续费{cfg['cost_bps_per_side']}bps/边 + 滑点{cfg['slippage_bps_per_side']}bps/边")
    print("说明: 入场按 T 日收盘近似尾盘买入；T+1 止盈/止损使用日线高低点，双触发时按先止损保守处理。")
    print()
    for name, res in result["results"].items():
        print(f"{name} | selected={res.get('selected', 0)}")
        for exit_name, st in res.get("exits", {}).items():
            if not st.get("n"):
                continue
            eq = res.get("equity", {}).get(exit_name, {})
            print(
                f"- {exit_name}: n={st['n']} avg={st['avg']:+.3f}% med={st['median']:+.3f}% "
                f"win={st['win_rate']:.1f}% pf={st['profit_factor']} worst={st['worst']:+.3f}% "
                f"curve={eq.get('total_return', 0):+.2f}% dd={eq.get('max_drawdown', 0):+.2f}%"
            )
        print()


def main():
    parser = argparse.ArgumentParser(description="Tail-entry execution-layer backtest")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--top", type=int, default=120)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--kline-count", type=int, default=420)
    parser.add_argument("--select", type=int, default=10, help="stocks selected per day")
    parser.add_argument("--min-atr", type=float, default=1.5)
    parser.add_argument("--max-atr", type=float, default=7.0)
    parser.add_argument("--min-ret20", type=float, default=0.0)
    parser.add_argument("--min-ma20-gap", type=float, default=-5.0)
    parser.add_argument("--min-d3", type=float, default=None)
    parser.add_argument("--exclude-limit", action="store_true", default=True)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=10.0)
    parser.add_argument("--stop-pct", type=float, default=3.0)
    parser.add_argument("--take-profit-pct", type=float, default=0.0)
    parser.add_argument("--minute-exit", action="store_true", default=True)
    parser.add_argument("--minute-exit-time", default="10:30")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    result = run(args)
    print_report(result)
    output = args.output or os.path.join(
        ROOT_DIR, "reports", f"tail_entry_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果已保存: {output}")


if __name__ == "__main__":
    main()
