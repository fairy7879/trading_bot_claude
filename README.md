# trading_bot

Intraday trading strategy framework for **US500**, **US100**, **Gold (XAU/USD)**, and major **FX** pairs.

- **Data / backtesting / live bars:** [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance). Outbound requests are throttled to ≥ 200 ms apart and retried with exponential backoff.
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

## Symbol map (yfinance ↔ Ostium)

| Internal | yfinance ticker | Ostium feed |
|---|---|---|
| US500 | `ES=F` (E-mini S&P 500 futures) | `SPX/USD` |
| US100 | `NQ=F` (NASDAQ-100 futures) | `NDX/USD` |
| GOLD  | `GC=F` (gold futures) | `XAU/USD` |
| EURUSD | `EURUSD=X` | `EUR/USD` |
| GBPUSD | `GBPUSD=X` | `GBP/USD` |
| USDJPY | `USDJPY=X` | `USD/JPY` |

We use front-month futures for indices and gold because Yahoo's intraday data for cash indices (`^GSPC`, `^NDX`) is unreliable and rate-limited harder.

## Quickstart

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # only needs Ostium keys; yfinance is keyless

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

## yfinance intervals & lookback caps

Yahoo silently caps intraday history depending on interval:

| Interval | Max history |
|---|---|
| `1m` | last 7 days |
| `2m`, `5m`, `15m`, `30m`, `60m`, `90m` | last 60 days |
| `1h` | last 730 days |
| `1d`, `1wk`, `1mo` | unlimited |

Asking for a window outside these caps returns an empty frame; the client treats that as a transient failure and retries before giving up.

## Rate limiting & retry

- A process-wide lock spaces every outbound `Ticker.history` call by **at least 200 ms**.
- Failures (raised exceptions OR empty frames) trigger exponential backoff: 1 s → 2 s → 4 s → 8 s → 16 s with jitter, up to 5 attempts.
- Successful responses are cached to parquet under `DATA_CACHE_DIR` keyed on `(symbol, interval, start, end)`, so repeated backtests are offline.

## Safety

- The Ostium adapter **refuses to construct against mainnet** unless both `OSTIUM_NETWORK=arbitrum` *and* `OSTIUM_ALLOW_MAINNET=true` are set.
- Backtest performance figures from the source papers are **gross of Ostium-specific costs** (oracle spread, open/close fees, perp funding, slippage). The included `backtest.metrics` module subtracts a configurable round-trip cost so reports reflect realistic net PnL.
- Position sizing is clamped to per-pair leverage caps inside `OstiumExecutionAdapter`, not in strategies.

## Layout

```
src/trading_bot/
├── config.py                 # Settings (env-driven)
├── symbols.py                # Internal <-> yfinance / Ostium mapping
├── data/                     # yfinance client + parquet cache + rate limit / retry
├── strategy/                 # Strategy ABC + four implementations
├── backtest/                 # Bar engine + metrics
├── execution/                # Paper + Ostium adapters
└── runner/                   # backtest_cli, live_cli
```
