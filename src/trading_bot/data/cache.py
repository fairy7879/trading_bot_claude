from pathlib import Path

import pandas as pd


def cache_path(base: Path, internal_symbol: str, interval: str, start: str, end: str) -> Path:
    safe_symbol = internal_symbol.replace("/", "_")
    return base / safe_symbol / f"{interval}__{start}__{end}.parquet"


def read(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_parquet(path)


def write(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
