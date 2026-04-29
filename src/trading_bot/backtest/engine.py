"""Bar-by-bar backtest engine.

Feeds one closed bar at a time into the strategy, applies signals through
the paper execution adapter, and enforces protective stops / targets at
the *next* bar's open (no look-ahead).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..execution.paper import PaperExecutionAdapter, Trade
from ..strategy.base import Bar, Strategy, StrategyContext
from .metrics import compute_metrics


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    trades: list[Trade]
    metrics: dict = field(default_factory=dict)
    equity_curve: pd.Series | None = None


def _bars_from_df(df: pd.DataFrame) -> list[Bar]:
    out = []
    for ts, row in df.iterrows():
        out.append(Bar(
            ts=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0) or 0.0),
        ))
    return out


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    symbol: str,
    *,
    starting_equity: float = 10_000.0,
    leverage: float = 10.0,
    risk_pct: float = 0.05,
    fee_bps: float = 4.0,
) -> BacktestResult:
    """Run ``strategy`` over ``df`` and return aggregated results."""
    if df.empty:
        empty = BacktestResult(symbol=symbol, strategy=strategy.name, trades=[])
        empty.metrics = compute_metrics(empty, starting_equity=starting_equity)
        return empty

    bars = _bars_from_df(df)
    ctx = StrategyContext(symbol=symbol)
    exec_adapter = PaperExecutionAdapter(fee_bps=fee_bps)

    equity = starting_equity
    equity_points: list[tuple] = []

    for i, bar in enumerate(bars):
        ctx.history.append(bar)
        exec_adapter.now = bar.ts

        # Apply protective levels off the prior position using THIS bar's range.
        pos = exec_adapter.position(symbol)
        if pos is not None:
            if pos.side == "long":
                if pos.sl is not None and bar.low <= pos.sl:
                    exec_adapter.close(symbol, pos.sl, reason="sl")
                elif pos.tp is not None and bar.high >= pos.tp:
                    exec_adapter.close(symbol, pos.tp, reason="tp")
            else:
                if pos.sl is not None and bar.high >= pos.sl:
                    exec_adapter.close(symbol, pos.sl, reason="sl")
                elif pos.tp is not None and bar.low <= pos.tp:
                    exec_adapter.close(symbol, pos.tp, reason="tp")

        signal = strategy.on_bar(bar, ctx)
        if signal is not None:
            current_side = exec_adapter.position_side(symbol)
            if signal.side == "flat" and current_side != "flat":
                exec_adapter.close(symbol, bar.close, reason=signal.note or "signal")
            elif signal.side in ("long", "short") and current_side == "flat":
                collateral = equity * risk_pct * signal.size_pct
                exec_adapter.open_market(
                    symbol,
                    side=signal.side,
                    collateral_usd=collateral,
                    leverage=leverage,
                    price=bar.close,
                    sl=signal.sl,
                    tp=signal.tp,
                )
            elif signal.side in ("long", "short") and current_side != signal.side:
                exec_adapter.close(symbol, bar.close, reason="flip")
                collateral = equity * risk_pct * signal.size_pct
                exec_adapter.open_market(
                    symbol,
                    side=signal.side,
                    collateral_usd=collateral,
                    leverage=leverage,
                    price=bar.close,
                    sl=signal.sl,
                    tp=signal.tp,
                )

        eos_hook = getattr(strategy, "end_of_session", None)
        if eos_hook and (i + 1 == len(bars) or bars[i + 1].ts.date() != bar.ts.date()):
            eos_hook(ctx)

        # Mark-to-market for equity curve.
        pos = exec_adapter.position(symbol)
        unrealized = 0.0
        if pos is not None:
            unrealized = pos.notional * (bar.close - pos.entry_price) / pos.entry_price
            if pos.side == "short":
                unrealized = -unrealized
        realized = sum(t.pnl for t in exec_adapter.trades)
        equity_points.append((bar.ts, starting_equity + realized + unrealized))

    # Close any open position at the very last bar.
    if exec_adapter.position_side(symbol) != "flat":
        exec_adapter.close(symbol, bars[-1].close, reason="end of data")

    eq_series = pd.Series(
        [p[1] for p in equity_points],
        index=pd.to_datetime([p[0] for p in equity_points]),
        name="equity",
    )

    result = BacktestResult(
        symbol=symbol,
        strategy=strategy.name,
        trades=exec_adapter.trades,
        equity_curve=eq_series,
    )
    result.metrics = compute_metrics(result, starting_equity=starting_equity)
    return result
