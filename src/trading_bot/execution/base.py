from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

OrderSide = Literal["long", "short"]


@dataclass
class OrderResult:
    ok: bool
    order_id: str | int | None = None
    detail: str = ""


class ExecutionAdapter(ABC):
    """Minimal contract used by the backtester and the live runner."""

    @abstractmethod
    def open_market(
        self,
        symbol: str,
        side: OrderSide,
        collateral_usd: float,
        leverage: float,
        price: float,
        sl: float | None = None,
        tp: float | None = None,
    ) -> OrderResult: ...

    @abstractmethod
    def close(self, symbol: str, price: float) -> OrderResult: ...

    @abstractmethod
    def position_side(self, symbol: str) -> str: ...
