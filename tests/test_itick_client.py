import time
from pathlib import Path

import pandas as pd
import pytest

from trading_bot.data import itick_client as ic
from trading_bot.data.itick_client import (
    INTERVAL_TO_KTYPE,
    ITickClient,
    IticKError,
    _RateLimiter,
    _retry_with_backoff,
)


def _bar(t_ms: int, price: float) -> dict:
    return {"t": t_ms, "o": price, "h": price + 0.5, "l": price - 0.5, "c": price, "v": 100}


def _ok(bars: list[dict]) -> dict:
    return {"code": 0, "msg": "ok", "data": bars}


def _ms(s: str) -> int:
    return int(pd.Timestamp(s, tz="UTC").timestamp() * 1000)


def _no_wait_limiter() -> _RateLimiter:
    return _RateLimiter(min_interval=0.0)


def _client(http, **kwargs) -> ITickClient:
    """Test factory: zero-wait limiter + tiny backoff so tests run instantly."""
    return ITickClient(
        token=kwargs.pop("token", "abc"),
        http_get=http,
        limiter=_no_wait_limiter(),
        max_retries=kwargs.pop("max_retries", 0),
        base_delay=kwargs.pop("base_delay", 0.001),
        max_delay=kwargs.pop("max_delay", 0.001),
        **kwargs,
    )


def test_kType_mapping_covers_required_intervals():
    for iv in ["1m", "5m", "15m", "30m", "1h", "1d"]:
        assert iv in INTERVAL_TO_KTYPE
    assert INTERVAL_TO_KTYPE["5m"] == 2


def test_fetch_normalises_payload_and_caches(tmp_path: Path):
    bars = [_bar(_ms("2025-04-01 13:30") + i * 300_000, 4500 + i) for i in range(4)]
    calls: list[dict] = []

    def http(url, params, headers):
        calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
        return _ok(bars)

    client = _client(http, cache_dir=tmp_path)
    df = client.fetch("US500", "5m", "2025-04-01", "2025-04-02")

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 4
    assert df.index.tz is not None
    assert calls[0]["url"].endswith("/indices/kline")
    assert calls[0]["params"]["region"] == "US"
    assert calls[0]["params"]["code"] == "SPX"
    assert calls[0]["params"]["kType"] == 2
    assert calls[0]["headers"]["token"] == "abc"

    n_before = len(calls)
    client.fetch("US500", "5m", "2025-04-01", "2025-04-02")
    assert len(calls) == n_before  # cache hit


def test_forex_endpoint_used_for_gold(tmp_path: Path):
    bars = [_bar(_ms("2025-04-01 10:30") + i * 300_000, 2300 + i) for i in range(2)]
    calls: list[dict] = []

    def http(url, params, headers):
        calls.append({"url": url, "params": dict(params)})
        return _ok(bars)

    client = _client(http, cache_dir=tmp_path)
    client.fetch("GOLD", "5m", "2025-04-01", "2025-04-02")

    assert calls[0]["url"].endswith("/forex/kline")
    assert calls[0]["params"]["code"] == "XAUUSD"


def test_fetch_pages_backwards_via_et(tmp_path: Path):
    page1 = [_bar(_ms("2025-04-02") - i * 300_000, 100 - i) for i in range(1000)]
    page2 = [_bar(_ms("2025-04-02") - (1000 + i) * 300_000, 90 - i) for i in range(50)]
    queue = [page1, page2, []]
    seen_params: list[dict] = []

    def http(url, params, headers):
        seen_params.append(dict(params))
        return _ok(queue.pop(0))

    client = _client(http, cache_dir=tmp_path)
    df = client.fetch("US500", "5m", "2025-03-25", "2025-04-02")

    assert len(seen_params) >= 2
    # Second page walks BACK in time relative to the first page's window.
    assert seen_params[1]["et"] < seen_params[0]["et"]
    assert seen_params[1]["et"] < min(b["t"] for b in page1)
    assert not df.empty


def test_retry_recovers_from_transient_429():
    n = {"i": 0}

    def call():
        n["i"] += 1
        if n["i"] < 3:
            raise IticKError("rate limited (HTTP 429)")
        return _ok([_bar(_ms("2025-04-01"), 100)])

    sleeps: list[float] = []
    payload = _retry_with_backoff(
        call, limiter=None,
        max_retries=4, base_delay=0.01, max_delay=0.05, sleeper=sleeps.append,
    )
    assert payload["data"][0]["c"] == 100
    assert n["i"] == 3
    assert len(sleeps) == 2


def test_retry_raises_after_max_attempts():
    def call():
        raise IticKError("server error (HTTP 500)")

    with pytest.raises(IticKError):
        _retry_with_backoff(
            call, limiter=None,
            max_retries=2, base_delay=0.001, max_delay=0.005, sleeper=lambda _: None,
        )


def test_rate_limiter_enforces_minimum_spacing():
    limiter = _RateLimiter(min_interval=0.05)
    t0 = time.monotonic()
    limiter.wait()
    limiter.wait()
    limiter.wait()
    assert time.monotonic() - t0 >= 0.10


def test_module_default_min_interval_is_at_least_12_seconds():
    """Hard floor: must respect 5 req/min => 12s spacing for any client that
    doesn't override the limiter."""
    assert ic.MIN_INTERVAL_SECONDS >= 12.0
    assert ic._LIMITER.min_interval >= 12.0


def test_default_client_uses_module_limiter():
    """Concurrent client instances share one limiter so combined throughput
    can never exceed iTick's 5-rpm cap."""
    a = ITickClient(token="x", http_get=lambda *a, **k: _ok([]))
    b = ITickClient(token="x", http_get=lambda *a, **k: _ok([]))
    assert a._limiter is ic._LIMITER
    assert b._limiter is ic._LIMITER


def test_error_code_in_payload_raises():
    def http(url, params, headers):
        return {"code": 401, "msg": "invalid token", "data": []}

    client = _client(http)
    with pytest.raises(IticKError, match="iTick error"):
        client.fetch("US500", "5m", "2025-04-01", "2025-04-02", use_cache=False)
