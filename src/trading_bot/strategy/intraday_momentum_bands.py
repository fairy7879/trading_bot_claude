"""Intraday Momentum Bands.

Reference: Zarattini, Aziz, Barbon — *Beat the Market: An Effective Intraday
Momentum Strategy for S&P500 ETF (SPY)*. SSRN 4824172 (2024).

For each bar at session-minute *m*, the upper / lower noise bands are::

    band(m) = today_open × (1 ± mean_abs_return_from_open(m, last 14 sessions))

At every HH:00 / HH:30 boundary, a close above the upper band opens a long; a
close below the lower band opens a short. We use a fixed trailing-stop drawdown
in lieu of the paper's dynamic trailing logic — equivalent in spirit, simpler.
The position is flattened at session close.
"""

from __future__ import annotations

from collections import deque
from datetime import time

from ..symbols import get as get_symbol
from .base import Bar, Signal, Strategy, StrategyContext


def _session_minute(bar: Bar, session_open: time) -> int:
    """Whole minutes since the session open (negative if before)."""
    so = bar.ts.replace(hour=session_open.hour, minute=session_open.minute, second=0, microsecond=0)
    return int((bar.ts - so).total_seconds() // 60)


class IntradayMomentumBands(Strategy):
    name = "intraday_momentum_bands"

    def __init__(
        self,
        symbol: str,
        lookback_days: int = 14,
        trail_pct: float = 0.005,
        check_only_on_half_hour: bool = True,
    ):
        self.symbol = symbol
        self.spec = get_symbol(symbol)
        self.lookback_days = lookback_days
        self.trail_pct = trail_pct
        self.check_only_on_half_hour = check_only_on_half_hour

    def _state(self, ctx: StrategyContext) -> dict:
        st = ctx.extras.setdefault(
            "imb_state",
            {
                "current_date": None,
                "today_open": None,
                "history": {},  # session_minute -> deque[abs_return]
                "position_side": "flat",
                "peak": None,  # high-water close for trailing stop
                "trough": None,
            },
        )
        return st

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> Signal | None:
        st = self._state(ctx)
        d = bar.ts.date()
        sm = _session_minute(bar, self.spec.session_open_utc)

        # New session: roll bookkeeping, ignore until we see a bar in-session.
        if st["current_date"] != d:
            st["current_date"] = d
            st["today_open"] = None
            st["position_side"] = "flat"
            st["peak"] = st["trough"] = None

        # Outside the session window — flatten if needed.
        sclose = self.spec.session_close_utc
        if bar.ts.time() >= sclose:
            if st["position_side"] != "flat":
                st["position_side"] = "flat"
                return Signal(side="flat", note="session close")
            return None
        if sm < 0:
            return None

        if st["today_open"] is None:
            st["today_open"] = bar.open

        # Update lookback history with today's bar (abs return from today's open).
        ret_from_open = abs(bar.close - st["today_open"]) / st["today_open"]
        bucket = st["history"].setdefault(sm, deque(maxlen=self.lookback_days))
        # Each session contributes one observation per session-minute. Append
        # today's value only at end-of-session below — for now use the running
        # observation as an estimate of today.
        st.setdefault("today_buckets", {})[sm] = ret_from_open

        # Trailing stop: applied per bar.
        side = st["position_side"]
        if side == "long":
            st["peak"] = max(st["peak"] or bar.close, bar.close)
            if bar.close <= st["peak"] * (1.0 - self.trail_pct):
                st["position_side"] = "flat"
                return Signal(side="flat", note="trail stop")
        elif side == "short":
            st["trough"] = min(st["trough"] or bar.close, bar.close)
            if bar.close >= st["trough"] * (1.0 + self.trail_pct):
                st["position_side"] = "flat"
                return Signal(side="flat", note="trail stop")

        # Decide entries only at HH:00 / HH:30.
        if self.check_only_on_half_hour and bar.ts.minute not in (0, 30):
            return None

        # Need at least one prior session of data for a band estimate.
        prior = list(bucket)
        if len(prior) < 1:
            # End-of-session housekeeping pushes today's value into the buffer.
            return None
        noise = sum(prior) / len(prior)
        upper = st["today_open"] * (1.0 + noise)
        lower = st["today_open"] * (1.0 - noise)

        if side == "flat":
            if bar.close > upper:
                st["position_side"] = "long"
                st["peak"] = bar.close
                return Signal(side="long", sl=lower, note=f"break upper {upper:.4f}")
            if bar.close < lower:
                st["position_side"] = "short"
                st["trough"] = bar.close
                return Signal(side="short", sl=upper, note=f"break lower {lower:.4f}")
        return None

    def end_of_session(self, ctx: StrategyContext) -> None:
        """Optional hook the engine calls at session close to roll lookback."""
        st = self._state(ctx)
        for sm, val in st.get("today_buckets", {}).items():
            st["history"].setdefault(sm, deque(maxlen=self.lookback_days)).append(val)
        st["today_buckets"] = {}
