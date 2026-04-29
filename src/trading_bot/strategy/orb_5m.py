"""5-minute Opening Range Breakout (ORB).

Reference: Zarattini & Aziz — *Can Day Trading Really Be Profitable?* SSRN
4416622 (2023). The first 5 minutes of the session define the opening
range. A break above its high opens a long; a break below its low opens a
short. Stop is the opposite side of the range; profit target is 10× risk.
The position is flattened at session close.

For instruments other than US equity indices we use the per-symbol session
anchor in ``symbols.py`` (London AM fix for gold, London open for FX).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..symbols import get as get_symbol
from .base import Bar, Signal, Strategy, StrategyContext


def _today_at(d: datetime, t) -> datetime:
    return d.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


class OpeningRangeBreakout5m(Strategy):
    name = "orb_5m"

    def __init__(
        self,
        symbol: str,
        opening_range_minutes: int = 5,
        rr_target: float = 10.0,
    ):
        self.symbol = symbol
        self.spec = get_symbol(symbol)
        self.opening_range_minutes = opening_range_minutes
        self.rr_target = rr_target

    def _state(self, ctx: StrategyContext) -> dict:
        return ctx.extras.setdefault(
            "orb_state",
            {
                "current_date": None,
                "or_high": None,
                "or_low": None,
                "or_locked": False,
                "position_side": "flat",
            },
        )

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> Signal | None:
        st = self._state(ctx)
        if st["current_date"] != bar.ts.date():
            st["current_date"] = bar.ts.date()
            st["or_high"] = st["or_low"] = None
            st["or_locked"] = False
            st["position_side"] = "flat"

        so = _today_at(bar.ts, self.spec.session_open_utc)
        sc = _today_at(bar.ts, self.spec.session_close_utc)
        or_end = so + timedelta(minutes=self.opening_range_minutes)

        if bar.ts >= sc:
            if st["position_side"] != "flat":
                st["position_side"] = "flat"
                return Signal(side="flat", note="session close")
            return None
        if bar.ts < so:
            return None

        # Build the opening range.
        if not st["or_locked"]:
            st["or_high"] = bar.high if st["or_high"] is None else max(st["or_high"], bar.high)
            st["or_low"] = bar.low if st["or_low"] is None else min(st["or_low"], bar.low)
            if bar.ts >= or_end - timedelta(seconds=1):
                st["or_locked"] = True
            return None

        if st["position_side"] != "flat":
            return None

        if bar.close > st["or_high"]:
            entry = bar.close
            stop = st["or_low"]
            risk = entry - stop
            if risk > 0:
                st["position_side"] = "long"
                return Signal(side="long", sl=stop, tp=entry + self.rr_target * risk, note="ORB long")
        elif bar.close < st["or_low"]:
            entry = bar.close
            stop = st["or_high"]
            risk = stop - entry
            if risk > 0:
                st["position_side"] = "short"
                return Signal(side="short", sl=stop, tp=entry - self.rr_target * risk, note="ORB short")
        return None
