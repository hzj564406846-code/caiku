"""Factor registry for research and advisor modules.

The registry keeps factor meaning explicit so combination search does not treat
all variables as interchangeable.  Factors marked as "gate" are not alpha
signals; they are risk or eligibility checks.
"""

FACTOR_REGISTRY = {
    "score": {
        "category": "v9_composite",
        "source": "V9",
        "direction": 1,
        "description": "V9 total score, kept as benchmark and explanation only.",
        "status": "benchmark",
    },
    "d1": {"category": "v9_dimension", "source": "V9 D1", "direction": 1, "description": "Capital flow dimension.", "status": "research"},
    "d2": {"category": "v9_dimension", "source": "V9 D2", "direction": 1, "description": "Sector resonance dimension.", "status": "research"},
    "d3": {"category": "v9_dimension", "source": "V9 D3", "direction": 1, "description": "Trend quality dimension.", "status": "research"},
    "d4": {"category": "v9_dimension", "source": "V9 D4", "direction": 1, "description": "Volume-price health dimension.", "status": "research"},
    "d5": {"category": "v9_dimension", "source": "V9 D5", "direction": 1, "description": "Relative strength / sentiment dimension.", "status": "research"},
    "d6": {"category": "v9_dimension", "source": "V9 D6", "direction": 1, "description": "Fundamental / valuation dimension.", "status": "research"},
    "d7": {"category": "v9_dimension", "source": "V9 D7", "direction": 1, "description": "Risk dimension after V9 compression.", "status": "risk"},

    "atr_pct": {"category": "volatility_elasticity", "source": "Kline", "direction": 1, "description": "ATR percent, currently strong elasticity factor.", "status": "research"},
    "intraday_range_pct": {"category": "volatility_elasticity", "source": "Kline", "direction": 1, "description": "Daily high-low range percent.", "status": "research"},
    "downside_risk": {"category": "risk", "source": "Derived", "direction": 1, "description": "Oversold downside risk proxy used for rebound research.", "status": "research"},
    "limit_move_flag": {"category": "risk", "source": "Quote/Kline", "direction": 1, "description": "Limit/extreme move flag; also used for filtering.", "status": "gate"},
    "vol_spike_ratio": {"category": "risk", "source": "Kline", "direction": 1, "description": "Latest volume versus 20-day average volume.", "status": "research"},

    "ret_5d": {"category": "trend_momentum", "source": "Kline", "direction": 1, "description": "5-day return.", "status": "research"},
    "ret_20d": {"category": "trend_momentum", "source": "Kline", "direction": 1, "description": "20-day return, current strongest single trend factor.", "status": "research"},
    "ma20_gap": {"category": "trend_momentum", "source": "Kline", "direction": 1, "description": "Distance from MA20.", "status": "research"},
    "price_above_ma20": {"category": "trend_momentum", "source": "Kline", "direction": 1, "description": "Price above MA20 flag.", "status": "research"},
    "price_above_ma60": {"category": "trend_momentum", "source": "Kline", "direction": 1, "description": "Price above MA60 flag.", "status": "research"},
    "ma20_above_ma60": {"category": "trend_momentum", "source": "Kline", "direction": 1, "description": "MA20 above MA60 flag.", "status": "research"},
    "ma5_above_ma20": {"category": "trend_momentum", "source": "Kline", "direction": 1, "description": "MA5 above MA20 flag.", "status": "research"},
    "v9_trend_raw": {"category": "trend_momentum", "source": "V9 raw", "direction": 1, "description": "Raw V9 trend sub-score.", "status": "research"},

    "volume_ratio": {"category": "volume_capital_activity", "source": "Kline/Quote", "direction": 1, "description": "Volume ratio used by advisor technical state.", "status": "research"},
    "vol5_vs_vol20": {"category": "volume_capital_activity", "source": "Kline", "direction": 1, "description": "5-day average volume versus 20-day average volume.", "status": "research"},
    "v9_volume_raw": {"category": "volume_capital_activity", "source": "V9 raw", "direction": 1, "description": "Raw V9 volume-price sub-score.", "status": "research"},

    "upper_shadow_pct": {"category": "candlestick_structure", "source": "Kline", "direction": 1, "description": "Upper shadow percentage.", "status": "research"},
    "lower_shadow_pct": {"category": "candlestick_structure", "source": "Kline", "direction": 1, "description": "Lower shadow percentage.", "status": "research"},
    "body_pct": {"category": "candlestick_structure", "source": "Kline", "direction": 1, "description": "Candle body percentage.", "status": "research"},
    "hammer_flag": {"category": "candlestick_structure", "source": "pattern_detector", "direction": 1, "description": "Hammer pattern flag.", "status": "research"},
    "doji_flag": {"category": "candlestick_structure", "source": "pattern_detector", "direction": 1, "description": "Doji pattern flag.", "status": "research"},
    "shrinking_bear_flag": {"category": "candlestick_structure", "source": "pattern_detector", "direction": 1, "description": "Shrinking bearish candle flag.", "status": "research"},
    "consecutive_decline_days": {"category": "candlestick_structure", "source": "pattern_detector", "direction": 1, "description": "Consecutive decline days.", "status": "research"},
    "decline_acceleration": {"category": "candlestick_structure", "source": "pattern_detector", "direction": 1, "description": "Decline acceleration proxy.", "status": "research"},
    "v9_pattern_raw": {"category": "candlestick_structure", "source": "V9 raw", "direction": 1, "description": "Raw V9 pattern sub-score.", "status": "research"},

    "sector_hot": {"category": "sector_hot_money", "source": "Historical sector heat", "direction": 1, "description": "Historical sector heat score.", "status": "research"},
    "peer_rank_in_sector": {"category": "sector_hot_money", "source": "Sector quotes", "direction": 1, "description": "Peer rank within industry by daily change.", "status": "research"},
    "sector_avg_change": {"category": "sector_hot_money", "source": "Sector quotes", "direction": 1, "description": "Average sector change.", "status": "research"},
    "sector_up_ratio": {"category": "sector_hot_money", "source": "Sector quotes", "direction": 1, "description": "Ratio of rising stocks within sector.", "status": "research"},

    "oversold_5d": {"category": "reversal_oversold", "source": "Kline", "direction": 1, "description": "Negative 5-day return, rebound candidate factor.", "status": "research"},
    "oversold_20d": {"category": "reversal_oversold", "source": "Kline", "direction": 1, "description": "Negative 20-day return, rebound candidate factor.", "status": "research"},

    "trend_factor": {"category": "strategy_composite", "source": "Research derived", "direction": 1, "description": "z(d3)+z(d4)+z(ret_20d)+z(ma20_gap).", "status": "candidate"},
    "hot_money_factor": {"category": "strategy_composite", "source": "Research derived", "direction": 1, "description": "z(d1)+z(d2)+z(sector_hot)+z(volume_ratio).", "status": "candidate"},
    "pullback_factor": {"category": "strategy_composite", "source": "Research derived", "direction": 1, "description": "Trend pullback composite.", "status": "candidate"},
    "oversold_rebound_factor": {"category": "strategy_composite", "source": "Research derived", "direction": 1, "description": "Oversold rebound composite.", "status": "candidate"},
    "quality_factor": {"category": "strategy_composite", "source": "Research derived", "direction": 1, "description": "z(d6)+z(d7)-positive ATR.", "status": "candidate"},

    "overnight_us_tech_risk": {"category": "market_environment", "source": "AkShare US daily", "direction": -1, "description": "Overnight US tech risk gate for A-share tech/high-beta exposure.", "status": "environment_gate"},
    "theme_hot_money_radar": {"category": "sector_hot_money", "source": "AkShare sector fund flow + scan pool", "direction": 1, "description": "Front signal for sector/theme fund flow, diffusion, and daily posture; not an alpha score yet.", "status": "front_signal"},
    "fundamental_hard_gate": {"category": "fundamental_quality", "source": "Tushare fina_indicator", "direction": 1, "description": "ROE/margins/growth/debt eligibility gate, not alpha score.", "status": "gate"},
}

PRIMITIVE_FACTORS = [
    "d1", "d2", "d3", "d4", "d5", "d6", "d7",
    "atr_pct", "ret_5d", "ret_20d", "ma20_gap", "volume_ratio",
    "sector_hot", "oversold_5d", "oversold_20d", "downside_risk",
    "price_above_ma20", "price_above_ma60", "ma20_above_ma60", "ma5_above_ma20",
    "vol5_vs_vol20", "intraday_range_pct", "upper_shadow_pct", "lower_shadow_pct",
    "body_pct", "hammer_flag", "doji_flag", "shrinking_bear_flag",
    "consecutive_decline_days", "decline_acceleration", "limit_move_flag",
    "vol_spike_ratio", "peer_rank_in_sector", "sector_avg_change", "sector_up_ratio",
    "v9_trend_raw", "v9_volume_raw", "v9_pattern_raw",
]

STRATEGY_FACTORS = [
    "trend_factor",
    "hot_money_factor",
    "pullback_factor",
    "oversold_rebound_factor",
    "quality_factor",
]

ENVIRONMENT_FACTORS = ["overnight_us_tech_risk"]
FRONT_SIGNAL_FACTORS = ["theme_hot_money_radar"]
GATE_FACTORS = ["fundamental_hard_gate", "limit_move_flag"]
FACTOR_DIRECTIONS = {name: meta["direction"] for name, meta in FACTOR_REGISTRY.items()}


def factors_by_category(category):
    return [name for name, meta in FACTOR_REGISTRY.items() if meta["category"] == category]


def factor_categories():
    return sorted({meta["category"] for meta in FACTOR_REGISTRY.values()})
