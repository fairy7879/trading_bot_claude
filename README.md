# trading_bot

Intraday trading strategy framework for **US500**, **US100**, **Gold (XAU/USD)**, and major **FX** pairs.

- **Data / backtesting:** [Twelve Data](https://twelvedata.com/) REST API.
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

## Quickstart

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in keys

# Run tests (offline, no network)
pytest -q

# Backtest
python -m trading_bot.runner.backtest_cli \
    --symbol US500 --interval 5min \
    --start 2025-01-02 --end 2025-04-25 \
    --strategy intraday_momentum_bands

# Live (Sepolia testnet by default)
python -m trading_bot.runner.live_cli \
    --symbol US500 --interval 5min \
    --strategy intraday_momentum_bands --bars 50
```

## Safety

- The Ostium adapter **refuses to construct against mainnet** unless both `OSTIUM_NETWORK=arbitrum` *and* `OSTIUM_ALLOW_MAINNET=true` are set. This is intentional — make a deliberate choice before risking real funds.
- Backtest performance figures from the source papers are **gross of Ostium-specific costs** (oracle spread, open/close fees, perp funding, slippage). The included `backtest.metrics` module subtracts a configurable round-trip cost so reports reflect realistic net PnL.
- Position sizing is clamped to per-pair leverage caps inside `OstiumExecutionAdapter`, not in strategies.

## Layout

```
src/trading_bot/
├── config.py                 # Settings (env-driven)
├── symbols.py                # Internal <-> Twelve Data / Ostium mapping
├── data/                     # Twelve Data client + parquet cache
├── strategy/                 # Strategy ABC + four implementations
├── backtest/                 # Bar engine + metrics
├── execution/                # Paper + Ostium adapters
└── runner/                   # backtest_cli, live_cli
```
