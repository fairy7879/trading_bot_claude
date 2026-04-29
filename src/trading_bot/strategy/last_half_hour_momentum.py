"""Last-half-hour intraday momentum.

Reference: Gao, Han, Li, Zhou — *Market Intraday Momentum*, Journal of
Financial Economics 129 (2018). The first half-hour return predicts the
last half-hour return; out-of-sample R² ≈ 1.6%.

Logic for one session:
  * Capture the open price at session start.
  * After the first 30 minutes, compute r1 = close/open - 1.
  * 30 minutes before session close, take position sign(r1).
  * At session close, flatten.

The strategy is timeframe-agnostic as long as the data interval divides 30.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..symbols import get as get_symbol
from .base import Bar, Signal, Strategy, StrategyContext


def _today_at(d: datetime, t) -> datetime:
    return d.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


class LastHalfHourMomentum(Strategy):
    name = "last_half_hour_momentum"

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.spec = get_symbol(symbol)

    def _state(self, ctx: StrategyContext) -> dict:
        return ctx.extras.setdefault(
            "lhhm_state",
            {"current_date": None, "today_open": None, "r1": None, "position_side": "flat"},
        )

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> Signal | None:
        st = self._state(ctx)
        if st["current_date"] != bar.ts.date():
            st["current_date"] = bar.ts.date()
            st["today_open"] = None
            st["r1"] = None
            st["position_side"] = "flat"

        so = _today_at(bar.ts, self.spec.session_open_utc)
        sc = _today_at(bar.ts, self.spec.session_close_utc)
        thirty_in = so + timedelta(minutes=30)
        thirty_to_close = sc - timedelta(minutes=30)

        if bar.ts < so or bar.ts >= sc:
            if st["position_side"] != "flat":
                st["position_side"] = "flat"
                return Signal(side="flat", note="session close")
            return None

        if st["today_open"] is None:
            st["today_open"] = bar.open

        if st["r1"] is None and bar.ts >= thirty_in:
            st["r1"] = bar.close / st["today_open"] - 1.0

        if st["position_side"] == "flat" and st["r1"] is not None and bar.ts >= thirty_to_close:
            if st["r1"] > 0:
                st["position_side"] = "long"
                return Signal(side="long", note=f"r1={st['r1']:.4f}")
            if st["r1"] < 0:
                st["position_side"] = "short"
                return Signal(side="short", note=f"r1={st['r1']:.4f}")
        return None
