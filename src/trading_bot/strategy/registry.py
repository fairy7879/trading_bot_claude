from .base import Strategy
from .intraday_momentum_bands import IntradayMomentumBands
from .last_half_hour_momentum import LastHalfHourMomentum
from .orb_5m import OpeningRangeBreakout5m
from .vwap_trend import VwapTrend

REGISTRY: dict[str, type[Strategy]] = {
    "intraday_momentum_bands": IntradayMomentumBands,
    "last_half_hour_momentum": LastHalfHourMomentum,
    "orb_5m": OpeningRangeBreakout5m,
    "vwap_trend": VwapTrend,
}


def get_strategy(name: str, **kwargs) -> Strategy:
    if name not in REGISTRY:
        raise KeyError(f"Unknown strategy {name!r}. Known: {sorted(REGISTRY)}")
    return REGISTRY[name](**kwargs)
