# Crypto BOT boruty 4.0 — research only

This directory is isolated research code. It is **not imported by bot_engine.py**, does not read or write portfolio-state.json, does not call exchange APIs, and cannot place orders.

## Input
CSV columns (UTC timestamps, one row per candle):
`timestamp,symbol,open,high,low,close,volume`

Use closed OHLCV candles. Provide enough history (at least 100 rows per symbol for the selector). Keep symbols and time ranges consistent when comparing candidates.

## Run
```bash
python3 research_v4/backtest.py data/ohlcv.csv --out research_v4/report.json
python3 research_v4/strategy_selector.py data/ohlcv.csv --out research_v4/selection-report.json
python3 -m unittest discover -s research_v4 -v
```

## Automatic strategy tournament
The selector compares four conservative variations of the EMA trend-following setup. It:
1. Sorts each asset's candles chronologically and splits them 60% train / 20% validation / 20% untouched holdout (no random shuffle).
2. Requires positive net PnL, positive average trade, minimum trade count, profit factor >= 1.20, and max drawdown <= 10% on both train and validation.
3. Ranks eligible candidates by validation profit factor, then validation net PnL.
4. Tests only the top-ranked candidate once on the untouched holdout. If that final gate fails, the result is **NO_STRATEGY_APPROVED**. No candidate is approved if none qualifies.
5. Emits the chosen configuration and metrics to JSON. This is a research report only; it does not change the live bot.

Thresholds are initial research filters, not evidence of an edge and not guarantees. The holdout should remain untouched until the candidate and evaluation rules are frozen. Repeatedly changing rules after inspecting holdout results turns it into training data.

## Baseline candidate
- EMA20/EMA50 direction filter
- RSI confirmation (LONG 52–68; SHORT 32–48)
- ATR-based stop and target
- Volume and volatility filters
- Risk 0.4–0.5% per trade; aggregate open risk cap 1.5–2%
- At most 3–4 positions, max leverage 1.5–2x, daily loss circuit breaker 1.5–2%
- 0.10% fee and 0.05% slippage per fill
- Conservative same-candle ambiguity: stop is assumed before target

## Important limitations — not ready for deployment
The current backtester is a prototype. It uses an approximate EMA-smoothed RSI/ADX, has no funding costs, does not model exchange outages, and has simplified multi-symbol mark-to-market and intrabar execution. Indicators are recalculated at split boundaries, so the first part of each split is effectively a warm-up. The current selector is a preliminary chronological gate, **not a complete walk-forward validation**. It does not yet test multiple independent strategy families or market-regime robustness.

Before paper deployment, improve the event/accounting model, add realistic funding and fills, test across more assets and market regimes, run rolling walk-forward tests, and validate on a separate forward paper period. Do not compare a strategy to the old bot unless both use identical timestamps, assets, costs, and execution assumptions.

A historical pass does not imply future profitability. If no strategy passes, the correct action is no trade.
