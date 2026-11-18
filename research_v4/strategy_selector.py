#!/usr/bin/env python3
"""Chronological strategy tournament; selects only candidates that pass validation and holdout."""
import argparse
import json
from pathlib import Path
from backtest import CONFIG, load_csv, run_backtest

CANDIDATES = [
    {"name":"trend_ema_rsi_atr_conservative","risk_per_trade":0.004,"max_open_positions":3,"max_total_open_risk":0.015,"max_leverage":1.5,"daily_loss_limit":0.015,"atr_stop_multiple":2.2,"atr_target_multiple":3.3,"min_atr_pct":0.002,"min_volume_ratio":1.0,"min_trend_strength":15},
    {"name":"trend_ema_rsi_atr_balanced","risk_per_trade":0.005,"max_open_positions":4,"max_total_open_risk":0.02,"max_leverage":2.0,"daily_loss_limit":0.02,"atr_stop_multiple":2.0,"atr_target_multiple":3.0,"min_atr_pct":0.002,"min_volume_ratio":1.0,"min_trend_strength":18},
    {"name":"trend_strict_volume","risk_per_trade":0.004,"max_open_positions":3,"max_total_open_risk":0.015,"max_leverage":1.5,"daily_loss_limit":0.015,"atr_stop_multiple":2.5,"atr_target_multiple":3.5,"min_atr_pct":0.003,"min_volume_ratio":1.2,"min_trend_strength":20},
    {"name":"trend_wide_target","risk_per_trade":0.005,"max_open_positions":4,"max_total_open_risk":0.02,"max_leverage":2.0,"daily_loss_limit":0.02,"atr_stop_multiple":2.0,"atr_target_multiple":4.0,"min_atr_pct":0.002,"min_volume_ratio":1.0,"min_trend_strength":22},
]

MIN_TRAIN_TRADES = 30
MIN_VALIDATION_TRADES = 15
MIN_HOLDOUT_TRADES = 10
MIN_PROFIT_FACTOR = 1.20
MAX_DRAWDOWN_PCT = 10.0

def chronological_split(grouped, train_ratio=0.60, validation_ratio=0.20):
    """Split each symbol independently by time; never shuffle candle rows."""
    train, validation, holdout = {}, {}, {}
    for symbol, rows in grouped.items():
        rows = sorted(rows, key=lambda r:r["timestamp"])
        n = len(rows)
        a, b = int(n*train_ratio), int(n*(train_ratio+validation_ratio))
        if a < 60 or b-a < 20 or n-b < 20:
            raise ValueError(f"{symbol}: za mało danych na podział train/validation/holdout")
        train[symbol], validation[symbol], holdout[symbol] = rows[:a], rows[a:b], rows[b:]
    return train, validation, holdout

def passes(report, minimum_trades):
    pf = report["profit_factor"]
    return (
        report["trades"] >= minimum_trades
        and report["net_pnl"] > 0
        and isinstance(pf, (int,float)) and pf >= MIN_PROFIT_FACTOR
        and report["max_drawdown_pct"] <= MAX_DRAWDOWN_PCT
        and report["avg_trade"] > 0
    )

def tournament(grouped):
    train, validation, holdout = chronological_split(grouped)
    results = []
    for candidate in CANDIDATES:
        overrides = {k:v for k,v in candidate.items() if k != "name"}
        train_report = run_backtest(train, overrides)
        validation_report = run_backtest(validation, overrides)
        train_ok = passes(train_report, MIN_TRAIN_TRADES)
        validation_ok = passes(validation_report, MIN_VALIDATION_TRADES)
        results.append({
            "name":candidate["name"],
            "train_pass":train_ok,
            "validation_pass":validation_ok,
            "train":{"trades":train_report["trades"],"net_pnl":train_report["net_pnl"],"profit_factor":train_report["profit_factor"],"max_drawdown_pct":train_report["max_drawdown_pct"]},
            "validation":{"trades":validation_report["trades"],"net_pnl":validation_report["net_pnl"],"profit_factor":validation_report["profit_factor"],"max_drawdown_pct":validation_report["max_drawdown_pct"]},
            "config":overrides,
        })
    eligible = [r for r in results if r["train_pass"] and r["validation_pass"]]
    eligible.sort(key=lambda r:(r["validation"]["profit_factor"],r["validation"]["net_pnl"]),reverse=True)
    selected = eligible[0] if eligible else None
    holdout_report = None
    if selected:
        holdout_report = run_backtest(holdout, selected["config"])
        selected["holdout_pass"] = passes(holdout_report, MIN_HOLDOUT_TRADES)
        selected["holdout"] = {k:holdout_report[k] for k in ("trades","net_pnl","return_pct","profit_factor","max_drawdown_pct","avg_trade","fees")}
        # A candidate is not deployable unless the untouched holdout also passes.
        if not selected["holdout_pass"]:
            selected = None
    return {
        "status":"CANDIDATE_PASSED_ALL_GATES" if selected else "NO_STRATEGY_APPROVED",
        "selection_policy":"train + validation gates; rank by validation PF; final untouched holdout gate",
        "thresholds":{"min_train_trades":MIN_TRAIN_TRADES,"min_validation_trades":MIN_VALIDATION_TRADES,"min_holdout_trades":MIN_HOLDOUT_TRADES,"min_profit_factor":MIN_PROFIT_FACTOR,"max_drawdown_pct":MAX_DRAWDOWN_PCT},
        "selected":selected,
        "candidates":results,
        "note":"Research result only. Passing a historical holdout is not a guarantee of future profitability; require walk-forward and paper forward testing before deployment."
    }

def main():
    parser=argparse.ArgumentParser(description="Crypto BOT boruty 4.0 strategy tournament")
    parser.add_argument("csv")
    parser.add_argument("--out",default="research_v4/selection-report.json")
    args=parser.parse_args()
    report=tournament(load_csv(args.csv))
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":report["status"],"selected":report["selected"]["name"] if report["selected"] else None,"candidates_tested":len(report["candidates"])},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
