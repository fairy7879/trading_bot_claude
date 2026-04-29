import numpy as np
import pandas as pd

from trading_bot.backtest import run_backtest
from trading_bot.strategy.base import Signal, Strategy


class _FlipFlop(Strategy):
    """Goes long on the 3rd bar, flat on the 6th. Deterministic for the engine."""

    name = "flipflop"

    def __init__(self):
        self.i = 0

    def on_bar(self, bar, ctx):
        self.i += 1
        if self.i == 3:
            return Signal(side="long")
        if self.i == 6:
            return Signal(side="flat")
        return None


def _ramp(n: int = 10) -> pd.DataFrame:
    idx = pd.date_range("2025-01-02 13:30", periods=n, freq="5min", tz="UTC")
    closes = np.linspace(100, 110, n)
    df = pd.DataFrame({
        "open": closes - 0.1,
        "high": closes + 0.2,
        "low": closes - 0.2,
        "close": closes,
        "volume": np.ones(n),
    }, index=idx)
    return df


def test_engine_records_a_winning_long():
    df = _ramp()
    res = run_backtest(df, _FlipFlop(), symbol="US500", risk_pct=0.1, leverage=10, fee_bps=0.0)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.side == "long"
    assert t.exit_price > t.entry_price
    assert t.pnl > 0
    assert res.metrics["trades"] == 1
    assert res.metrics["win_rate"] == 1.0


def test_empty_data_returns_empty_result():
    df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    res = run_backtest(df, _FlipFlop(), symbol="US500")
    assert res.trades == []
    assert res.metrics["trades"] == 0
