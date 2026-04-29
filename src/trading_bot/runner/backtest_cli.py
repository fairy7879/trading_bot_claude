"""Run a single-symbol backtest from the command line.

Example::

    python -m trading_bot.runner.backtest_cli \\
        --symbol US500 --interval 5min \\
        --start 2025-01-02 --end 2025-04-25 \\
        --strategy intraday_momentum_bands
"""

from __future__ import annotations

import argparse
import json

from ..backtest import run_backtest
from ..data import fetch_ohlcv
from ..strategy import get_strategy


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--interval", default="5min")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--strategy", required=True)
    p.add_argument("--starting-equity", type=float, default=10_000.0)
    p.add_argument("--leverage", type=float, default=10.0)
    p.add_argument("--risk-pct", type=float, default=0.05)
    p.add_argument("--fee-bps", type=float, default=4.0)
    return p.parse_args()


def main() -> None:
    args = _parse()
    df = fetch_ohlcv(args.symbol, args.interval, args.start, args.end)
    strat = get_strategy(args.strategy, symbol=args.symbol)
    result = run_backtest(
        df,
        strat,
        symbol=args.symbol,
        starting_equity=args.starting_equity,
        leverage=args.leverage,
        risk_pct=args.risk_pct,
        fee_bps=args.fee_bps,
    )
    report = {
        "symbol": result.symbol,
        "strategy": result.strategy,
        "bars": int(len(df)),
        **result.metrics,
    }
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
