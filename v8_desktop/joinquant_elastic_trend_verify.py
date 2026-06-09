"""JoinQuant web backtest template: high-elasticity trend verification.

Paste this file into JoinQuant's web strategy editor.  It is intentionally
standalone and does not import local project modules.

Purpose:
- Cross-check the local research result that ATR + 20d momentum + MA20 gap is
  a strong A-share candidate line.
- Keep the test simple before adding fundamental gates or theme radar.

Suggested JoinQuant settings:
- Backtest range: 2025-11-20 to 2026-05-22 first, then expand to 2024-01-01+.
- Initial capital: 100000.
- Frequency: daily.
- Benchmark: 000300.XSHG.
"""

import math

import pandas as pd


def initialize(context):
    set_benchmark("000300.XSHG")
    set_option("use_real_price", True)
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0.001,
            open_commission=0.0003,
            close_commission=0.0003,
            close_today_commission=0,
            min_commission=5,
        ),
        type="stock",
    )
    set_slippage(FixedSlippage(0.002))

    g.max_holdings = 10
    g.rebalance_days = 5
    g.lookback = 80
    g.min_trade_value = 1000
    g.stock_pool = get_index_stocks("000300.XSHG")

    run_daily(rebalance, time="14:50")


def before_trading_start(context):
    if context.current_dt.day == 1:
        g.stock_pool = get_index_stocks("000300.XSHG")


def rebalance(context):
    if context.current_dt.toordinal() % g.rebalance_days != 0:
        return

    candidates = rank_candidates(context, g.stock_pool)
    target_stocks = [row["code"] for row in candidates[: g.max_holdings]]
    log.info("elastic candidates: %s" % [(row["code"], round(row["score"], 3)) for row in candidates[:10]])

    for stock in list(context.portfolio.positions.keys()):
        if stock not in target_stocks:
            order_target_value(stock, 0)

    if not target_stocks:
        return

    target_value = context.portfolio.total_value / len(target_stocks)
    for stock in target_stocks:
        if target_value >= g.min_trade_value:
            order_target_value(stock, target_value)


def rank_candidates(context, stocks):
    rows = []
    for stock in stocks:
        if is_paused_or_limit(stock):
            continue
        df = get_price(
            stock,
            count=g.lookback,
            end_date=context.previous_date,
            frequency="daily",
            fields=["open", "close", "high", "low", "volume"],
            skip_paused=True,
            fq="pre",
        )
        if df is None or len(df) < 60:
            continue
        factors = calc_factors(df)
        if not factors:
            continue
        row = {"code": stock, **factors}
        rows.append(row)

    if not rows:
        return []
    factor_df = pd.DataFrame(rows)
    for col in ["atr_pct", "ret_20d", "ma20_gap"]:
        factor_df["z_" + col] = zscore(factor_df[col])
    factor_df["score"] = factor_df["z_atr_pct"] + factor_df["z_ret_20d"] + factor_df["z_ma20_gap"]

    # Basic tradability filters.  These are deliberately simple for the first
    # JoinQuant cross-check; local research handles richer gates.
    factor_df = factor_df[
        (factor_df["atr_pct"] >= 1.5)
        & (factor_df["atr_pct"] <= 7.0)
        & (factor_df["ret_20d"] > 0)
        & (factor_df["ma20_gap"] > -5)
    ]
    factor_df = factor_df.sort_values("score", ascending=False)
    return factor_df.to_dict("records")


def calc_factors(df):
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    if len(close) < 60 or close.iloc[-21] == 0:
        return None

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    price = close.iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    if not price or math.isnan(atr) or math.isnan(ma20) or not ma20:
        return None
    return {
        "atr_pct": atr / price * 100,
        "ret_20d": (price / close.iloc[-21] - 1) * 100,
        "ma20_gap": (price / ma20 - 1) * 100,
    }


def zscore(series):
    std = series.std()
    if not std or math.isnan(std):
        return series * 0
    return (series - series.mean()) / std


def is_paused_or_limit(stock):
    current = get_current_data()[stock]
    if current.paused or current.is_st:
        return True
    if current.last_price >= current.high_limit or current.last_price <= current.low_limit:
        return True
    return False
