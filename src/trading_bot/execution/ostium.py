"""Ostium execution adapter.

Wraps `ostium-python-sdk` so strategies see only the generic
``ExecutionAdapter`` interface. Network defaults to Arbitrum Sepolia
(testnet); mainnet construction requires both an explicit
``OSTIUM_NETWORK=arbitrum`` env and ``OSTIUM_ALLOW_MAINNET=true``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import Settings, get_settings
from ..symbols import get as get_symbol
from ..utils.logging import get_logger
from .base import ExecutionAdapter, OrderResult, OrderSide

logger = get_logger(__name__)


@dataclass
class _Trade:
    side: OrderSide
    pair_id: int | str
    trade_index: int | None
    entry_price: float


class OstiumExecutionAdapter(ExecutionAdapter):
    def __init__(self, settings: Settings | None = None, sdk: Any | None = None):
        self.settings = settings or get_settings()
        self._guard_network()
        self.sdk = sdk if sdk is not None else self._build_sdk()
        self._open: dict[str, _Trade] = {}

    def _guard_network(self) -> None:
        if self.settings.ostium_network == "arbitrum" and not self.settings.ostium_allow_mainnet:
            raise RuntimeError(
                "OSTIUM_NETWORK=arbitrum requires OSTIUM_ALLOW_MAINNET=true. "
                "Refusing to construct mainnet adapter."
            )

    def _build_sdk(self):
        if not self.settings.ostium_private_key or not self.settings.ostium_rpc_url:
            raise RuntimeError("OSTIUM_PRIVATE_KEY and OSTIUM_RPC_URL must be set.")
        from ostium_python_sdk import OstiumSDK  # imported lazily

        return OstiumSDK(
            network=self.settings.ostium_network,
            private_key=self.settings.ostium_private_key,
            rpc_url=self.settings.ostium_rpc_url,
        )

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
        spec = get_symbol(symbol)
        params = {
            "collateral": collateral_usd,
            "leverage": leverage,
            "asset_type": _asset_type_from(spec.asset_class),
            "direction": side == "long",
            "order_type": "MARKET",
        }
        try:
            receipt = self.sdk.ostium.perform_trade(params, at_price=price)
        except Exception as exc:  # pragma: no cover - integration only
            logger.exception("Ostium open_market failed")
            return OrderResult(ok=False, detail=str(exc))

        pair_id = receipt.get("pair_id") if isinstance(receipt, dict) else None
        trade_index = receipt.get("trade_index") if isinstance(receipt, dict) else None
        self._open[symbol] = _Trade(side=side, pair_id=pair_id, trade_index=trade_index, entry_price=price)

        if pair_id is not None and trade_index is not None:
            try:
                if tp is not None:
                    self.sdk.ostium.update_tp(pair_id, trade_index, tp)
                if sl is not None:
                    self.sdk.ostium.update_sl(pair_id, trade_index, sl)
            except Exception:  # pragma: no cover - integration only
                logger.exception("Ostium TP/SL update failed (position remains open)")

        return OrderResult(ok=True, order_id=str(receipt))

    def close(self, symbol: str, price: float) -> OrderResult:
        trade = self._open.pop(symbol, None)
        if trade is None:
            return OrderResult(ok=False, detail="no position")
        try:
            self.sdk.ostium.close_trade(trade.pair_id, trade.trade_index)
            return OrderResult(ok=True)
        except Exception as exc:  # pragma: no cover - integration only
            logger.exception("Ostium close failed")
            return OrderResult(ok=False, detail=str(exc))

    def position_side(self, symbol: str) -> str:
        t = self._open.get(symbol)
        return t.side if t else "flat"


def _asset_type_from(asset_class: str) -> int:
    """Map our internal asset class onto Ostium's `asset_type` enum.

    Ostium's exact integer mapping is documented per release; defaults
    here are educated guesses to be confirmed against the live SDK.
    """
    return {"index": 1, "commodity": 2, "fx": 3}.get(asset_class, 0)
