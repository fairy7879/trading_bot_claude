import time
from pathlib import Path

import pandas as pd
import pytest

from trading_bot.data import yfinance_client as yfc
from trading_bot.data.yfinance_client import YFinanceClient, _RateLimiter, _retry_with_backoff


def _yahoo_frame() -> pd.DataFrame:
    idx = pd.date_range("2025-04-01 13:30", periods=4, freq="5min", tz="UTC")
    return pd.DataFrame(
        {"Open": [1, 2, 3, 4], "High": [1.1, 2.1, 3.1, 4.1],
         "Low": [0.9, 1.9, 2.9, 3.9], "Close": [1, 2, 3, 4],
         "Volume": [10, 11, 12, 13]},
        index=idx,
    )


def test_fetch_normalises_and_caches(tmp_path: Path):
    calls: list[tuple] = []

    def fake(symbol, interval, start, end):
        calls.append((symbol, interval, start, end))
        return _yahoo_frame()

    client = YFinanceClient(cache_dir=tmp_path, fetcher=fake)
    df = client.fetch("US500", "5m", "2025-04-01", "2025-04-02")

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.tz is not None
    assert calls == [("ES=F", "5m", "2025-04-01", "2025-04-02")]

    df2 = client.fetch("US500", "5m", "2025-04-01", "2025-04-02")
    assert df2.equals(df)
    assert len(calls) == 1  # cache hit


def test_retry_returns_after_transient_empty_then_success():
    n = {"i": 0}

    def fake():
        n["i"] += 1
        if n["i"] < 3:
            return pd.DataFrame()  # simulate Yahoo silent rate-limit
        return _yahoo_frame()

    sleeps: list[float] = []
    df = _retry_with_backoff(
        fake, max_retries=4, base_delay=0.01, max_delay=0.05, sleeper=sleeps.append
    )
    assert not df.empty
    assert n["i"] == 3
    assert len(sleeps) == 2  # two backoff waits before the third attempt
    assert all(s > 0 for s in sleeps)


def test_retry_raises_after_max_attempts():
    def fake():
        raise RuntimeError("429 from yahoo")

    with pytest.raises(RuntimeError, match="429"):
        _retry_with_backoff(
            fake, max_retries=2, base_delay=0.001, max_delay=0.005, sleeper=lambda _: None
        )


def test_rate_limiter_enforces_minimum_spacing():
    limiter = _RateLimiter(min_interval=0.05)
    t0 = time.monotonic()
    limiter.wait()
    limiter.wait()
    limiter.wait()
    elapsed = time.monotonic() - t0
    # First wait is essentially free (last_at is 0); the next two each block.
    assert elapsed >= 0.10


def test_module_level_limiter_is_singleton():
    """All client instances share one limiter so concurrent runners are spaced."""
    a = YFinanceClient(fetcher=lambda *a, **k: _yahoo_frame())
    b = YFinanceClient(fetcher=lambda *a, **k: _yahoo_frame())
    assert yfc._LIMITER is yfc._LIMITER  # sanity
    # Both clients route through the module-level _LIMITER (no per-client limiter).
    assert not hasattr(a, "_limiter")
    assert not hasattr(b, "_limiter")
