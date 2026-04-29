from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import pandas as pd

Side = Literal["long", "short", "flat"]


@dataclass(frozen=True)
class Bar:
    ts: datetime  # tz-aware UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    """A target position. ``size_pct`` is fraction of equity to allocate.

    A ``flat`` signal closes any open position. ``sl`` and ``tp`` are absolute
    prices; either or both may be None.
    """

    side: Side
    size_pct: float = 1.0
    sl: float | None = None
    tp: float | None = None
    note: str = ""


@dataclass
class StrategyContext:
    """Per-symbol mutable scratch space the engine hands to the strategy."""

    symbol: str
    history: list[Bar] = field(default_factory=list)
    extras: dict = field(default_factory=dict)

    def df(self, lookback: int | None = None) -> pd.DataFrame:
        bars = self.history if lookback is None else self.history[-lookback:]
        if not bars:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        idx = [b.ts for b in bars]
        rows = [(b.open, b.high, b.low, b.close, b.volume) for b in bars]
        return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])


class Strategy(ABC):
    """Pure function of (bar, ctx) -> Optional[Signal].

    The engine guarantees ``bar`` is the just-closed bar and that ``ctx.history``
    already contains it. Strategies must not look at any future data.
    """

    name: str = "base"

    @abstractmethod
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> Signal | None: ...
