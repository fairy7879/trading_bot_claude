"""Run a strategy against live(-ish) Twelve Data bars and route signals to Ostium.

Defaults to Sepolia testnet. The ``--bars`` flag caps how many historical
bars we replay before stopping; in production you'd loop on a schedule.

Example::

    python -m trading_bot.runner.live_cli \\
        --symbol US500 --interval 5m \\
        --strategy intraday_momentum_bands --bars 50
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from ..config import get_settings
from ..data import fetch_ohlcv
from ..execution.ostium import OstiumExecutionAdapter
from ..execution.paper import PaperExecutionAdapter
from ..strategy import get_strategy
from ..strategy.base import Bar, StrategyContext
from ..utils.logging import get_logger

logger = get_logger(__name__)


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--interval", default="5m")
    p.add_argument("--strategy", required=True)
    p.add_argument("--bars", type=int, default=20, help="Number of recent bars to replay.")
    p.add_argument("--collateral-usd", type=float, default=10.0)
    p.add_argument("--leverage", type=float, default=5.0)
    p.add_argument("--dry-run", action="store_true", help="Print signals; do not call Ostium.")
    return p.parse_args()


def _recent_window(bars: int, interval: str) -> tuple[str, str]:
    minutes = {
        "1m": 1, "2m": 2, "5m": 5, "15m": 15, "30m": 30,
        "60m": 60, "90m": 90, "1h": 60,
    }.get(interval, 5)
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes * (bars + 5))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def main() -> None:
    args = _parse()
    settings = get_settings()
    start, end = _recent_window(args.bars, args.interval)

    df = fetch_ohlcv(args.symbol, args.interval, start, end).tail(args.bars)
    strat = get_strategy(args.strategy, symbol=args.symbol)
    ctx = StrategyContext(symbol=args.symbol)

    exec_adapter = (
        PaperExecutionAdapter()
        if args.dry_run
        else OstiumExecutionAdapter(settings=settings)
    )
    logger.info("network=%s dry_run=%s bars=%d", settings.ostium_network, args.dry_run, len(df))

    for ts, row in df.iterrows():
        bar = Bar(
            ts=ts.to_pydatetime(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0) or 0.0),
        )
        ctx.history.append(bar)
        sig = strat.on_bar(bar, ctx)
        if sig is None:
            continue

        cur = exec_adapter.position_side(args.symbol)
        if sig.side == "flat" and cur != "flat":
            logger.info("close %s @ %.4f (%s)", args.symbol, bar.close, sig.note)
            exec_adapter.close(args.symbol, bar.close)
        elif sig.side in ("long", "short") and cur == "flat":
            logger.info("open %s %s @ %.4f sl=%s tp=%s", sig.side, args.symbol, bar.close, sig.sl, sig.tp)
            exec_adapter.open_market(
                args.symbol,
                side=sig.side,
                collateral_usd=args.collateral_usd,
                leverage=args.leverage,
                price=bar.close,
                sl=sig.sl,
                tp=sig.tp,
            )

    logger.info("done")


if __name__ == "__main__":
    main()
