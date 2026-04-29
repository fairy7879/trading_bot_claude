"""yfinance OHLCV client.

Yahoo enforces an undocumented rate limit and routinely returns 429 or empty
frames under load. This client therefore:

* serialises calls through a global lock and waits at least
  ``MIN_INTERVAL_SECONDS`` (200ms) between any two outbound requests, and
* retries failures with exponential backoff (1s, 2s, 4s, … with jitter).

Returned frame is tz-aware UTC, columns ``open, high, low, close, volume``.
"""

from __future__ import annotations

import random
import threading
import time
from pathlib import Path
from typing import Callable, Protocol

import pandas as pd

from ..config import get_settings
from ..symbols import get as get_symbol
from ..utils.logging import get_logger
from . import cache

logger = get_logger(__name__)

MIN_INTERVAL_SECONDS = 0.2  # 5 requests per second hard cap
DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 30.0


class _RateLimiter:
    """Serialise outbound calls and enforce a minimum spacing between them."""

    def __init__(self, min_interval: float = MIN_INTERVAL_SECONDS):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_for = self._last_at + self.min_interval - now
            if wait_for > 0:
                time.sleep(wait_for)
            self._last_at = time.monotonic()


_LIMITER = _RateLimiter()


def _retry_with_backoff(
    fn: Callable[[], pd.DataFrame],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    sleeper: Callable[[float], None] = time.sleep,
) -> pd.DataFrame:
    """Call ``fn`` with rate-limit + exponential backoff. Retries on either a
    raised exception or an empty result (Yahoo's silent rate-limit failure
    mode)."""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        _LIMITER.wait()
        try:
            df = fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            df = None

        if df is not None and not df.empty:
            return df

        if attempt == max_retries:
            break
        delay = min(base_delay * (2 ** attempt), max_delay)
        delay += random.uniform(0, base_delay / 2)  # jitter
        logger.warning(
            "yfinance request failed (attempt %d/%d), retrying in %.1fs: %s",
            attempt + 1, max_retries, delay,
            "empty response" if last_error is None else f"{type(last_error).__name__}: {last_error}",
        )
        sleeper(delay)

    if last_error is not None:
        raise last_error
    return pd.DataFrame()


class _YFinanceFetcher(Protocol):
    def __call__(self, symbol: str, interval: str, start: str, end: str) -> pd.DataFrame: ...


def _default_yfinance_fetcher(symbol: str, interval: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    df = yf.Ticker(symbol).history(start=start, end=end, interval=interval, auto_adjust=False)
    return df


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = df.rename(columns=str.lower).copy()
    expected = ["open", "high", "low", "close"]
    for col in expected:
        if col not in df.columns:
            raise ValueError(f"yfinance response missing column {col!r}")
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    else:
        df["volume"] = float("nan")

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.sort_index(inplace=True)
    return df[["open", "high", "low", "close", "volume"]].dropna(subset=expected)


class YFinanceClient:
    def __init__(
        self,
        cache_dir: Path | None = None,
        fetcher: _YFinanceFetcher = _default_yfinance_fetcher,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
    ):
        settings = get_settings()
        self.cache_dir = Path(cache_dir) if cache_dir is not None else settings.data_cache_dir
        self._fetcher = fetcher
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay

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

        df = _retry_with_backoff(
            lambda: self._fetcher(spec.yfinance, interval, start, end),
            max_retries=self._max_retries,
            base_delay=self._base_delay,
            max_delay=self._max_delay,
        )
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
    client: YFinanceClient | None = None,
) -> pd.DataFrame:
    return (client or YFinanceClient()).fetch(internal_symbol, interval, start, end)
