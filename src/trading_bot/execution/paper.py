"""In-memory execution adapter used by the backtester and dry-runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .base import ExecutionAdapter, OrderResult, OrderSide


@dataclass
class _OpenPosition:
    side: OrderSide
    entry_price: float
    notional: float  # collateral * leverage, in quote currency
    sl: float | None
    tp: float | None
    opened_at: datetime | None = None


@dataclass
class Trade:
    symbol: str
    side: OrderSide
    entry_price: float
    exit_price: float
    notional: float
    pnl: float
    opened_at: datetime | None
    closed_at: datetime | None
    reason: str = ""


@dataclass
class PaperExecutionAdapter(ExecutionAdapter):
    """Tracks one open position per symbol. Caller passes execution prices."""

    fee_bps: float = 4.0  # round-trip charged proportional to notional
    _positions: dict[str, _OpenPosition] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    now: datetime | None = None  # set by engine each bar

    def open_market(
        self,
        symbol: str,
        side: OrderSide,
        collateral_usd: float,
        leverage: float,
        price: float,
        sl: float | None = None,
        tp: float | None = None,
    ) -> OrderResult:
        if symbol in self._positions:
            return OrderResult(ok=False, detail="position already open")
        notional = collateral_usd * leverage
        self._positions[symbol] = _OpenPosition(
            side=side, entry_price=price, notional=notional, sl=sl, tp=tp, opened_at=self.now,
        )
        return OrderResult(ok=True, order_id=f"paper-{symbol}-{len(self.trades)}")

    def close(self, symbol: str, price: float, reason: str = "") -> OrderResult:
        pos = self._positions.pop(symbol, None)
        if pos is None:
            return OrderResult(ok=False, detail="no position")
        gross = pos.notional * (price - pos.entry_price) / pos.entry_price
        if pos.side == "short":
            gross = -gross
        fee = pos.notional * self.fee_bps / 1e4
        pnl = gross - fee
        self.trades.append(
            Trade(
                symbol=symbol,
                side=pos.side,
                entry_price=pos.entry_price,
                exit_price=price,
                notional=pos.notional,
                pnl=pnl,
                opened_at=pos.opened_at,
                closed_at=self.now,
                reason=reason,
            )
        )
        return OrderResult(ok=True, detail=f"pnl={pnl:.2f}")

    def position_side(self, symbol: str) -> str:
        pos = self._positions.get(symbol)
        return pos.side if pos else "flat"

    def position(self, symbol: str) -> _OpenPosition | None:
        return self._positions.get(symbol)
