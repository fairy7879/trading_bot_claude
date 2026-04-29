from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from trading_bot.data.twelvedata_client import TwelveDataClient


class _FakeTimeSeries:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def as_pandas(self) -> pd.DataFrame:
        return self._df


class _FakeTDClient:
    def __init__(self):
        self.calls: list[dict] = []

    def time_series(self, **kwargs):
        self.calls.append(kwargs)
        idx = pd.date_range("2025-01-02 13:30", periods=5, freq="5min", tz="UTC")
        df = pd.DataFrame(
            {"open": [1, 2, 3, 4, 5], "high": [1.1, 2.1, 3.1, 4.1, 5.1],
             "low": [0.9, 1.9, 2.9, 3.9, 4.9], "close": [1, 2, 3, 4, 5],
             "volume": [10, 11, 12, 13, 14]},
            index=idx,
        )
        return _FakeTimeSeries(df)


def test_fetch_returns_normalised_frame_and_caches(tmp_path: Path):
    fake = _FakeTDClient()
    client = TwelveDataClient(api_key="x", cache_dir=tmp_path, td_factory=lambda apikey: fake)

    df = client.fetch("US500", "5min", "2025-01-02", "2025-01-03")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 5
    assert df.index.tz is not None  # tz-aware
    assert len(fake.calls) == 1

    # Second call should hit parquet cache, not the underlying client.
    df2 = client.fetch("US500", "5min", "2025-01-02", "2025-01-03")
    assert df2.equals(df)
    assert len(fake.calls) == 1
