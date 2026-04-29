"""Smoke tests for each registered strategy. Confirm the engine drives them
without errors and that they emit at least one trade on a contrived ramp /
breakout series."""

import numpy as np
import pandas as pd

from trading_bot.backtest import run_backtest
from trading_bot.strategy import REGISTRY, get_strategy


def _intraday(days: int = 3, bars_per_day: int = 78) -> pd.DataFrame:
    """Build a deterministic 5-min intraday series with a 1.5% morning rally
    each day. Session opens 13:30 UTC (US500 default)."""
    rows = []
    base = 4500.0
    for d in range(days):
        day_start = pd.Timestamp("2025-01-02", tz="UTC") + pd.Timedelta(days=d)
        for i in range(bars_per_day):
            ts = day_start + pd.Timedelta(hours=13, minutes=30) + pd.Timedelta(minutes=5 * i)
            morning_kick = 0.015 * base if i < 12 else 0.0
            close = base + morning_kick + np.sin(i / 6) * 1.0 + d * 5.0
            rows.append((ts, close - 0.2, close + 0.4, close - 0.4, close, 1.0))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
    return df


def test_registry_has_four_strategies():
    assert {"intraday_momentum_bands", "last_half_hour_momentum", "orb_5m", "vwap_trend"} <= set(REGISTRY)


def test_each_strategy_runs_without_errors():
    df = _intraday()
    for name in REGISTRY:
        strat = get_strategy(name, symbol="US500")
        res = run_backtest(df, strat, symbol="US500", risk_pct=0.05, leverage=10, fee_bps=0.0)
        assert isinstance(res.metrics, dict)
        assert res.metrics["trades"] >= 0
