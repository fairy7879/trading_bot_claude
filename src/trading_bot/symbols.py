from dataclasses import dataclass
from datetime import time
from typing import Literal

AssetClass = Literal["index", "commodity", "fx"]


@dataclass(frozen=True)
class SymbolSpec:
    """One row of the symbol mapping table.

    ``yfinance`` is the ticker accepted by ``yfinance.Ticker(...)``. We prefer
    the front-month futures contract for indices and gold because Yahoo's
    intraday data for cash indices (``^GSPC``, ``^NDX``) is unreliable.

    ``session_open_utc`` is the canonical intraday-anchor time for opening-
    range style strategies. For US indices it's the cash open; for gold it's
    the London AM fix; for FX it's the London open.
    """

    internal: str
    yfinance: str
    ostium_from: str
    ostium_to: str
    asset_class: AssetClass
    session_open_utc: time
    session_close_utc: time


SYMBOLS: dict[str, SymbolSpec] = {
    "US500": SymbolSpec("US500", "ES=F", "SPX", "USD", "index", time(13, 30), time(20, 0)),
    "US100": SymbolSpec("US100", "NQ=F", "NDX", "USD", "index", time(13, 30), time(20, 0)),
    "GOLD":  SymbolSpec("GOLD",  "GC=F", "XAU", "USD", "commodity", time(10, 30), time(20, 0)),
    "EURUSD": SymbolSpec("EURUSD", "EURUSD=X", "EUR", "USD", "fx", time(7, 0), time(20, 0)),
    "GBPUSD": SymbolSpec("GBPUSD", "GBPUSD=X", "GBP", "USD", "fx", time(7, 0), time(20, 0)),
    "USDJPY": SymbolSpec("USDJPY", "USDJPY=X", "USD", "JPY", "fx", time(7, 0), time(20, 0)),
}


def get(internal: str) -> SymbolSpec:
    key = internal.upper()
    if key not in SYMBOLS:
        raise KeyError(
            f"Unknown internal symbol {internal!r}. Known: {sorted(SYMBOLS)}"
        )
    return SYMBOLS[key]


def all_symbols() -> list[SymbolSpec]:
    return list(SYMBOLS.values())
