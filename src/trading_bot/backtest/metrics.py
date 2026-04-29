from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .engine import BacktestResult


def compute_metrics(result: "BacktestResult", *, starting_equity: float = 10_000.0) -> dict:
    trades = result.trades
    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "return_pct": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "trades_per_day": 0.0,
        }

    pnls = np.array([t.pnl for t in trades], dtype=float)
    total_pnl = float(pnls.sum())
    win_rate = float((pnls > 0).mean())

    eq = result.equity_curve
    sharpe = 0.0
    max_dd = 0.0
    if eq is not None and len(eq) > 1:
        rets = eq.pct_change().dropna()
        if len(rets) > 1 and rets.std() > 0:
            # Approximate annualisation using bar frequency.
            avg_seconds = (eq.index[-1] - eq.index[0]).total_seconds() / max(len(rets), 1)
            bars_per_year = 365 * 24 * 3600 / max(avg_seconds, 1)
            sharpe = float(rets.mean() / rets.std() * math.sqrt(bars_per_year))
        running_max = eq.cummax()
        dd = (eq - running_max) / running_max
        max_dd = float(dd.min())

    days = max((trades[-1].closed_at - trades[0].opened_at).days, 1) if trades[0].opened_at else 1
    trades_per_day = len(trades) / max(days, 1)

    return {
        "trades": len(trades),
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "return_pct": total_pnl / starting_equity,
        "sharpe": sharpe,
        "max_drawdown_pct": max_dd,
        "trades_per_day": trades_per_day,
    }
