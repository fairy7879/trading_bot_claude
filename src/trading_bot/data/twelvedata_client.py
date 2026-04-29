"""Twelve Data wrapper.

Returns a tz-aware (UTC) DataFrame indexed by timestamp with columns
``open, high, low, close, volume`` (volume may be NaN for indices / FX).
Parquet cache makes re-runs offline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd

from ..config import get_settings
from ..symbols import get as get_symbol
from . import cache


class _TDFactory(Protocol):
    def __call__(self, apikey: str): ...  # returns a TDClient-like object


def _default_td_factory(apikey: str):
    from twelvedata import TDClient

    return TDClient(apikey=apikey)


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise a Twelve Data response into our canonical OHLCV frame."""
    if df.empty:
        return df
    df = df.copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df.sort_index(inplace=True)
    expected = ["open", "high", "low", "close"]
    for col in expected:
        if col not in df.columns:
            raise ValueError(f"Twelve Data response missing column {col!r}")
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    else:
        df["volume"] = float("nan")
    return df[["open", "high", "low", "close", "volume"]].dropna(subset=expected)


class TwelveDataClient:
    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path | None = None,
        td_factory: _TDFactory = _default_td_factory,
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.twelvedata_api_key
        self.cache_dir = Path(cache_dir) if cache_dir is not None else settings.data_cache_dir
        self._td_factory = td_factory
        self._td_client = None

    def _td(self):
        if self._td_client is None:
            if not self.api_key:
                raise RuntimeError("TWELVEDATA_API_KEY is not set.")
            self._td_client = self._td_factory(self.api_key)
        return self._td_client

    def fetch(
        self,
        internal_symbol: str,
        interval: str,
        start: str,
        end: str,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        spec = get_symbol(internal_symbol)
        path = cache.cache_path(self.cache_dir, internal_symbol, interval, start, end)
        if use_cache:
            cached = cache.read(path)
            if cached is not None:
                return cached
        ts = self._td().time_series(
            symbol=spec.twelvedata,
            interval=interval,
            start_date=start,
            end_date=end,
            timezone="UTC",
            outputsize=5000,
        )
        df = ts.as_pandas()
        df = _normalise(df)
        if use_cache and not df.empty:
            cache.write(path, df)
        return df


def fetch_ohlcv(
    internal_symbol: str,
    interval: str,
    start: str,
    end: str,
    *,
    client: TwelveDataClient | None = None,
) -> pd.DataFrame:
    """Module-level shortcut used by CLIs and tests."""
    return (client or TwelveDataClient()).fetch(internal_symbol, interval, start, end)
