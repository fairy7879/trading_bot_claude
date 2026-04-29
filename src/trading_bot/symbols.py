from dataclasses import dataclass
from datetime import time
from typing import Literal

AssetClass = Literal["index", "commodity", "fx"]
ITickEndpoint = Literal["stock", "forex", "indices", "crypto", "future"]


@dataclass(frozen=True)
class SymbolSpec:
    """One row of the symbol mapping table.

    iTick organises instruments by ``region`` + ``code``, hit through one of
    several REST endpoints (``stock``, ``forex``, ``indices`` …). Gold lives
    under the ``forex`` endpoint on iTick.

    ``session_open_utc`` is the canonical intraday-anchor time for opening-
    range style strategies. For US indices it's the cash open; for gold it's
    the London AM fix; for FX it's the London open.
    """

    internal: str
    itick_endpoint: ITickEndpoint
    itick_region: str
    itick_code: str
    ostium_from: str
    ostium_to: str
    asset_class: AssetClass
    session_open_utc: time
    session_close_utc: time


SYMBOLS: dict[str, SymbolSpec] = {
    "US500":  SymbolSpec("US500",  "indices", "US", "SPX",    "SPX", "USD", "index",     time(13, 30), time(20, 0)),
    "US100":  SymbolSpec("US100",  "indices", "US", "NDX",    "NDX", "USD", "index",     time(13, 30), time(20, 0)),
    "GOLD":   SymbolSpec("GOLD",   "forex",   "GB", "XAUUSD", "XAU", "USD", "commodity", time(10, 30), time(20, 0)),
    "EURUSD": SymbolSpec("EURUSD", "forex",   "GB", "EURUSD", "EUR", "USD", "fx",        time(7, 0),  time(20, 0)),
    "GBPUSD": SymbolSpec("GBPUSD", "forex",   "GB", "GBPUSD", "GBP", "USD", "fx",        time(7, 0),  time(20, 0)),
    "USDJPY": SymbolSpec("USDJPY", "forex",   "GB", "USDJPY", "USD", "JPY", "fx",        time(7, 0),  time(20, 0)),
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
