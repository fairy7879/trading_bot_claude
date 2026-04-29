# trading_bot

Intraday trading strategy framework for **US500**, **US100**, **Gold (XAU/USD)**, and major **FX** pairs.

- **Data / backtesting / live bars:** [iTick](https://itick.org) REST API. Free-tier callers are capped at **5 requests per minute**, so outbound requests are spaced ≥ 12 seconds apart and retried with exponential backoff.
- **Execution:** [Ostium](https://www.ostium.com/) decentralized perpetuals on Arbitrum (defaults to **Sepolia testnet**).

The repo ships a pluggable `Strategy` interface plus four research-backed strategies, all driven by the same backtester and the same execution adapter.

## Strategies included

| Module | Source paper | Asset focus |
|---|---|---|
| `intraday_momentum_bands` | Zarattini, Aziz, Barbon — *Beat the Market* (SSRN 4824172, 2024) | US500, US100, Gold |
| `last_half_hour_momentum` | Gao, Han, Li, Zhou — *Market Intraday Momentum*, JFE 2018 | US500, US100 |
| `orb_5m` | Zarattini & Aziz — *Can Day Trading Really Be Profitable?* (SSRN 4416622, 2023) | All |
| `vwap_trend` | Zarattini & Aziz — *VWAP — The Holy Grail* (SSRN 4631351, 2023) | All (also a regime filter) |

Reported single-asset Sharpe ratios in the original papers run from ~1.3 (SPY momentum bands) up to ~2.1 (VWAP). Treat first runs on Gold / FX as out-of-sample tests, not validated alpha — peer-reviewed evidence is concentrated on US equity indices.

## Symbol map (iTick ↔ Ostium)

| Internal | iTick endpoint | iTick `region` / `code` | Ostium feed |
|---|---|---|---|
| US500  | `/indices/kline` | `US` / `SPX`    | `SPX/USD` |
| US100  | `/indices/kline` | `US` / `NDX`    | `NDX/USD` |
| GOLD   | `/forex/kline`   | `GB` / `XAUUSD` | `XAU/USD` |
| EURUSD | `/forex/kline`   | `GB` / `EURUSD` | `EUR/USD` |
| GBPUSD | `/forex/kline`   | `GB` / `GBPUSD` | `GBP/USD` |
| USDJPY | `/forex/kline`   | `GB` / `USDJPY` | `USD/JPY` |

If your iTick subscription uses a different region/code per instrument, edit `src/trading_bot/symbols.py` — that's the single source of truth for the mapping.

## Interval mapping (`kType`)

| CLI flag | iTick `kType` |
|---|---|
| `1m`  | 1 |
| `5m`  | 2 |
| `15m` | 3 |
| `30m` | 4 |
| `1h`  | 5 |
| `1d`  | 8 |
| `1w`  | 9 |
| `1mo` | 10 |

## Quickstart

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # paste ITICK_TOKEN and Ostium keys

# Run tests (offline, no network)
pytest -q

# Backtest
python -m trading_bot.runner.backtest_cli \
    --symbol US500 --interval 5m \
    --start 2025-04-01 --end 2025-04-25 \
    --strategy intraday_momentum_bands

# Live (Sepolia testnet by default)
python -m trading_bot.runner.live_cli \
    --symbol US500 --interval 5m \
    --strategy intraday_momentum_bands --bars 50
```

## Rate limiting & retry

iTick's free tier hard-caps callers at **5 requests / minute / token**. The client therefore:

- Routes every request through a **process-wide lock** that enforces ≥ 12.5 s between outbound calls. Concurrent backtests share the same budget.
- Retries on raised exceptions, HTTP 429, and HTTP 5xx with exponential backoff: **15 s → 30 s → 60 s → 120 s → 240 s** (capped at 5 min), plus jitter, up to 5 attempts.
- Walks long history backwards via the `et` query param, requesting up to 1000 bars per call. A month of 5-minute bars on one symbol is roughly 5 calls (~1 minute of real time including the throttle).
- Caches every successful page to parquet under `DATA_CACHE_DIR` keyed on `(symbol, interval, start, end)`. Re-running a backtest is offline.

A practical consequence: backtesting six symbols across many months can take **tens of minutes on the free tier**. Plan accordingly, or upgrade your iTick plan and lower `MIN_INTERVAL_SECONDS` in `data/itick_client.py`.

## Safety

- The Ostium adapter **refuses to construct against mainnet** unless both `OSTIUM_NETWORK=arbitrum` *and* `OSTIUM_ALLOW_MAINNET=true` are set.
- Backtest performance figures from the source papers are **gross of Ostium-specific costs** (oracle spread, open/close fees, perp funding, slippage). The included `backtest.metrics` module subtracts a configurable round-trip cost so reports reflect realistic net PnL.
- Position sizing is clamped to per-pair leverage caps inside `OstiumExecutionAdapter`, not in strategies.

## Layout

```
src/trading_bot/
├── config.py                 # Settings (env-driven)
├── symbols.py                # Internal <-> iTick / Ostium mapping
├── data/                     # iTick client + parquet cache + rate limit / retry / paging
├── strategy/                 # Strategy ABC + four implementations
├── backtest/                 # Bar engine + metrics
├── execution/                # Paper + Ostium adapters
└── runner/                   # backtest_cli, live_cli
```
