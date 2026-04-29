"""VWAP trend.

Reference: Zarattini & Aziz — *VWAP — The Holy Grail for Day Trading
Systems*. SSRN 4631351 (2023). Long when close is above the session VWAP;
short when below. Re-evaluate every bar; flatten at session close.

Twelve Data does not provide volume for indices or FX. When volume is
missing we fall back to a typical-price TWAP, which is operationally
equivalent for these instruments.
"""

from __future__ import annotations

from datetime import datetime
from math import isnan

from ..symbols import get as get_symbol
from .base import Bar, Signal, Strategy, StrategyContext


def _today_at(d: datetime, t) -> datetime:
    return d.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


class VwapTrend(Strategy):
    name = "vwap_trend"

    def __init__(self, symbol: str, deadband_bps: float = 5.0):
        self.symbol = symbol
        self.spec = get_symbol(symbol)
        self.deadband_bps = deadband_bps  # avoid flip-flop on tiny crossings

    def _state(self, ctx: StrategyContext) -> dict:
        return ctx.extras.setdefault(
            "vwap_state",
            {"current_date": None, "cum_pv": 0.0, "cum_v": 0.0, "position_side": "flat"},
        )

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> Signal | None:
        st = self._state(ctx)
        if st["current_date"] != bar.ts.date():
            st["current_date"] = bar.ts.date()
            st["cum_pv"] = 0.0
            st["cum_v"] = 0.0
            st["position_side"] = "flat"

        so = _today_at(bar.ts, self.spec.session_open_utc)
        sc = _today_at(bar.ts, self.spec.session_close_utc)
        if bar.ts >= sc:
            if st["position_side"] != "flat":
                st["position_side"] = "flat"
                return Signal(side="flat", note="session close")
            return None
        if bar.ts < so:
            return None

        typical = (bar.high + bar.low + bar.close) / 3.0
        v = bar.volume if (bar.volume and not isnan(bar.volume)) else 1.0
        st["cum_pv"] += typical * v
        st["cum_v"] += v
        if st["cum_v"] <= 0:
            return None
        vwap = st["cum_pv"] / st["cum_v"]
        deadband = vwap * self.deadband_bps / 1e4

        side = st["position_side"]
        if bar.close > vwap + deadband and side != "long":
            st["position_side"] = "long"
            return Signal(side="long", note=f"close>{vwap:.4f}")
        if bar.close < vwap - deadband and side != "short":
            st["position_side"] = "short"
            return Signal(side="short", note=f"close<{vwap:.4f}")
        return None
