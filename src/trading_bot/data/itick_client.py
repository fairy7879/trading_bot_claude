"""iTick REST client.

iTick caps free-tier callers at **5 requests per minute** per token. This
client therefore:

* serialises outbound calls through a process-wide lock and waits at least
  ``MIN_INTERVAL_SECONDS`` (12 seconds) between any two requests, and
* retries failures with exponential backoff (15 s → 30 s → 60 s → … capped
  at 5 minutes) since hitting the cap means we must wait for the rolling
  window to clear.

Endpoints used::

    GET https://api.itick.org/{stock|forex|indices}/kline
        ?region=&code=&kType=&limit=&et=

Headers::

    accept: application/json
    token:  <ITICK_TOKEN>

``kType`` mapping (per docs):

    1=1m, 2=5m, 3=15m, 4=30m, 5=1h, 8=1d, 9=1w, 10=1mo

Bars in the JSON ``data`` array use one-letter keys: ``t`` (epoch ms),
``o, h, l, c, v``.
"""

from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from ..config import get_settings
from ..symbols import get as get_symbol
from ..utils.logging import get_logger
from . import cache

logger = get_logger(__name__)

ITICK_BASE_URL = "https://api.itick.org"

# 5 req/min => one every 12s. Add a small safety margin.
MIN_INTERVAL_SECONDS = 12.5
DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY = 15.0   # seconds
DEFAULT_MAX_DELAY = 300.0   # 5 minutes

INTERVAL_TO_KTYPE: dict[str, int] = {
    "1m": 1,
    "5m": 2,
    "15m": 3,
    "30m": 4,
    "1h": 5,
    "1d": 8,
    "1w": 9,
    "1mo": 10,
}

# Approximate bar duration in seconds — used for backward paging.
INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "1d": 86_400, "1w": 604_800, "1mo": 2_592_000,
}

ENDPOINT_FOR_ASSET: dict[str, str] = {
    # Default endpoint chosen per asset_class. Per-symbol overrides live in
    # ``symbols.SymbolSpec.itick_endpoint``.
    "index": "indices",
    "commodity": "forex",
    "fx": "forex",
}

# iTick caps `limit` at 1000 per request on most plans.
MAX_LIMIT_PER_REQUEST = 1000


class _RateLimiter:
    def __init__(self, min_interval: float = MIN_INTERVAL_SECONDS):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_for = self._last_at + self.min_interval - now
            if wait_for > 0:
                logger.info("iTick rate limiter sleeping %.1fs", wait_for)
                time.sleep(wait_for)
            self._last_at = time.monotonic()


_LIMITER = _RateLimiter()


class IticKError(RuntimeError):
    """Raised when iTick returns a non-OK code or an unexpected payload."""


def _retry_with_backoff(
    fn: Callable[[], dict],
    *,
    limiter: _RateLimiter | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Call ``fn`` with rate-limit + exponential backoff. Retries on raised
    exceptions and on iTick error codes that look transient (rate limit, 5xx)."""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        if limiter is not None:
            limiter.wait()
        try:
            payload = fn()
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = exc

        if attempt == max_retries:
            break
        delay = min(base_delay * (2 ** attempt), max_delay)
        delay += random.uniform(0, base_delay / 4)
        logger.warning(
            "iTick request failed (attempt %d/%d), backing off %.1fs: %s",
            attempt + 1, max_retries, delay,
            f"{type(last_error).__name__}: {last_error}",
        )
        sleeper(delay)

    raise last_error  # type: ignore[misc]


def _normalise(bars: Iterable[dict]) -> pd.DataFrame:
    rows: list[tuple] = []
    for bar in bars:
        t = bar.get("t")
        if t is None:
            continue
        # iTick returns timestamps in ms.
        ts = pd.Timestamp(int(t), unit="ms", tz="UTC")
        rows.append((ts,
                     float(bar.get("o", "nan")), float(bar.get("h", "nan")),
                     float(bar.get("l", "nan")), float(bar.get("c", "nan")),
                     float(bar.get("v", 0) or 0)))
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    return df


HttpGet = Callable[[str, dict, dict], dict]
"""Signature: (url, params, headers) -> json dict. Pluggable for tests."""


def _default_http_get(url: str, params: dict, headers: dict) -> dict:
    import requests

    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if resp.status_code == 429:
        raise IticKError("rate limited (HTTP 429)")
    if resp.status_code >= 500:
        raise IticKError(f"server error (HTTP {resp.status_code})")
    if resp.status_code != 200:
        raise IticKError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


class ITickClient:
    def __init__(
        self,
        token: str | None = None,
        cache_dir: Path | None = None,
        http_get: HttpGet = _default_http_get,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        limiter: _RateLimiter | None = None,
    ):
        settings = get_settings()
        self.token = token if token is not None else settings.itick_token
        self.cache_dir = Path(cache_dir) if cache_dir is not None else settings.data_cache_dir
        self._http_get = http_get
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._limiter = limiter if limiter is not None else _LIMITER

    def _headers(self) -> dict:
        if not self.token:
            raise RuntimeError("ITICK_TOKEN is not set.")
        return {"accept": "application/json", "token": self.token}

    def _one_request(self, endpoint: str, region: str, code: str, kType: int,
                     limit: int, et: int | None) -> list[dict]:
        url = f"{ITICK_BASE_URL}/{endpoint}/kline"
        params: dict = {"region": region, "code": code, "kType": kType, "limit": limit}
        if et is not None:
            params["et"] = et
        payload = _retry_with_backoff(
            lambda: self._http_get(url, params, self._headers()),
            limiter=self._limiter,
            max_retries=self._max_retries,
            base_delay=self._base_delay,
            max_delay=self._max_delay,
        )
        if not isinstance(payload, dict):
            raise IticKError(f"unexpected payload type: {type(payload).__name__}")
        # iTick uses {"code": 0|<err>, "msg": ..., "data": [...]}
        code_field = payload.get("code")
        if code_field not in (0, "0", None):
            raise IticKError(f"iTick error code={code_field} msg={payload.get('msg')!r}")
        data = payload.get("data") or []
        if not isinstance(data, list):
            raise IticKError(f"`data` was not a list: {type(data).__name__}")
        return data

    def fetch(
        self,
        internal_symbol: str,
        interval: str,
        start: str,
        end: str,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        if interval not in INTERVAL_TO_KTYPE:
            raise ValueError(f"Unsupported interval {interval!r}. Known: {sorted(INTERVAL_TO_KTYPE)}")
        spec = get_symbol(internal_symbol)
        endpoint = spec.itick_endpoint or ENDPOINT_FOR_ASSET[spec.asset_class]
        kType = INTERVAL_TO_KTYPE[interval]

        path = cache.cache_path(self.cache_dir, internal_symbol, interval, start, end)
        if use_cache:
            cached = cache.read(path)
            if cached is not None:
                return cached

        start_ts = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)
        end_ts = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp() * 1000)

        all_bars: list[dict] = []
        et: int | None = end_ts
        bar_ms = INTERVAL_SECONDS[interval] * 1000
        # Defensive cap on number of pages so we never loop forever on a stuck API.
        max_pages = 200
        for page in range(max_pages):
            bars = self._one_request(
                endpoint=endpoint,
                region=spec.itick_region,
                code=spec.itick_code,
                kType=kType,
                limit=MAX_LIMIT_PER_REQUEST,
                et=et,
            )
            if not bars:
                break
            all_bars.extend(bars)
            oldest = min(int(b["t"]) for b in bars)
            if oldest <= start_ts:
                break
            # Walk backward by the oldest seen timestamp (minus one bar) so the
            # next page returns the bars that come BEFORE this batch.
            et = oldest - bar_ms
            if et <= start_ts:
                break

        df = _normalise(all_bars)
        if not df.empty:
            df = df[(df.index >= pd.Timestamp(start_ts, unit="ms", tz="UTC")) &
                    (df.index <= pd.Timestamp(end_ts, unit="ms", tz="UTC"))]

        if use_cache and not df.empty:
            cache.write(path, df)
        return df


def fetch_ohlcv(
    internal_symbol: str,
    interval: str,
    start: str,
    end: str,
    *,
    client: ITickClient | None = None,
) -> pd.DataFrame:
    return (client or ITickClient()).fetch(internal_symbol, interval, start, end)
