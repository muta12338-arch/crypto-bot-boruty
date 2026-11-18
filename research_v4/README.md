# Crypto BOT boruty 4.0 — research only

This directory is isolated research code. It is **not imported by bot_engine.py**, does not read or write portfolio-state.json, does not call exchange APIs, and cannot place orders.

## Input
CSV columns (UTC timestamps, one row per candle):
`timestamp,symbol,open,high,low,close,volume`

Use closed OHLCV candles. Provide enough history (at least 60 rows per symbol). Keep symbols and time ranges consistent when comparing candidates.

## Run
```bash
python3 research_v4/backtest.py data/ohlcv.csv --out research_v4/report.json
python3 -m unittest discover -s research_v4 -v
```

## Baseline candidate
- EMA20/EMA50 direction filter
- RSI confirmation (LONG 52–68; SHORT 32–48)
- ATR-based stop (2 ATR) and target (3 ATR)
- Volume and volatility filters
- Risk 0.5% per trade; aggregate open risk cap 2%
- At most 4 positions, max leverage 2x, daily loss circuit breaker 2%
- 0.10% fee and 0.05% slippage per fill
- Conservative same-candle ambiguity: stop is assumed before target

## Important limitations
This is a first research harness, not a profitability claim. It currently uses a single-symbol-per-timestamp event model, approximate EMA-smoothed RSI/ADX, no funding costs, and does not yet model exchange outages or intrabar execution beyond conservative stop/target ordering. Validate with out-of-sample and walk-forward data before considering paper deployment. Do not compare a strategy to the old bot unless both use identical timestamps, assets, costs, and execution assumptions.

A candidate passes only after out-of-sample results show positive expectancy, profit factor above 1.2, drawdown within the agreed limit, and sufficient trade count across multiple market regimes. A backtest is not a guarantee of future returns.
