#!/usr/bin/env python3
"""Research-only OHLCV backtester. Does not connect to exchanges or alter live state."""
import argparse
import csv
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CONFIG = {
    "initial_capital": 30000.0,
    "risk_per_trade": 0.005,
    "max_open_positions": 4,
    "max_total_open_risk": 0.02,
    "max_leverage": 2.0,
    "daily_loss_limit": 0.02,
    "fee_rate": 0.001,
    "slippage_rate": 0.0005,
    "atr_stop_multiple": 2.0,
    "atr_target_multiple": 3.0,
    "min_atr_pct": 0.002,
    "min_volume_ratio": 1.0,
    "min_trend_strength": 0.0,
}

@dataclass
class Position:
    symbol: str
    side: int
    entry: float
    qty: float
    stop: float
    target: float
    risk_cash: float
    entry_fee: float
    opened: str

def ema(values, period):
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(out[-1] + alpha * (float(value) - out[-1]))
    return out

def indicators(rows):
    closes = [r["close"] for r in rows]
    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    volumes = [r["volume"] for r in rows]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    tr, plus_dm, minus_dm = [], [], []
    for i in range(len(rows)):
        if i == 0:
            tr.append(highs[i] - lows[i]); plus_dm.append(0.0); minus_dm.append(0.0)
        else:
            up, down = highs[i] - highs[i-1], lows[i-1] - lows[i]
            plus_dm.append(up if up > down and up > 0 else 0.0)
            minus_dm.append(down if down > up and down > 0 else 0.0)
            tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    atr = ema(tr, 14)
    gains, losses = [0.0], [0.0]
    for a, b in zip(closes, closes[1:]):
        gains.append(max(b-a, 0.0)); losses.append(max(a-b, 0.0))
    avg_gain, avg_loss = ema(gains, 14), ema(losses, 14)
    rsi = [50.0 if g == 0 and l == 0 else (100.0 if l == 0 else 100-100/(1+g/l)) for g,l in zip(avg_gain,avg_loss)]
    pdi = [100*ema(plus_dm,14)[i]/atr[i] if atr[i] else 0 for i in range(len(rows))]
    mdi = [100*ema(minus_dm,14)[i]/atr[i] if atr[i] else 0 for i in range(len(rows))]
    dx = [100*abs(p-m)/(p+m) if p+m else 0 for p,m in zip(pdi,mdi)]
    adx = ema(dx, 14)
    vol_avg = ema(volumes, 20)
    return {"ema20":e20,"ema50":e50,"atr":atr,"rsi":rsi,"adx":adx,"vol_avg":vol_avg}

def load_csv(path):
    grouped = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            row = {k: raw[k] for k in ("timestamp","symbol")}
            for k in ("open","high","low","close","volume"):
                row[k] = float(raw[k])
            if min(row["open"],row["high"],row["low"],row["close"]) <= 0 or row["volume"] < 0:
                raise ValueError("OHLC musi być dodatnie, a wolumen nieujemny")
            if row["high"] < max(row["open"],row["close"],row["low"]) or row["low"] > min(row["open"],row["close"]):
                raise ValueError("Nieprawidłowy zakres OHLC")
            grouped[row["symbol"]].append(row)
    for symbol in grouped:
        grouped[symbol].sort(key=lambda x:x["timestamp"])
    return grouped

def run_backtest(grouped, overrides=None):
    cfg = dict(CONFIG); cfg.update(overrides or {})
    if cfg["risk_per_trade"] <= 0 or cfg["max_leverage"] <= 0 or cfg["fee_rate"] < 0 or cfg["slippage_rate"] < 0:
        raise ValueError("Nieprawidłowe parametry ryzyka/kosztów")
    series = {}
    timeline = defaultdict(list)
    for symbol, rows in grouped.items():
        if len(rows) < 60:
            continue
        ind = indicators(rows)
        series[symbol] = (rows, ind)
        for i,row in enumerate(rows):
            timeline[row["timestamp"]].append((symbol,i))
    cash = cfg["initial_capital"]
    positions, trades = {}, []
    daily_start, current_day, halted = cash, None, False
    equity_curve = []

    def marked_equity(prices):
        return cash + sum(p.qty*p.entry/cfg["max_leverage"] + p.side*(prices.get(s,p.entry)-p.entry)*p.qty for s,p in positions.items())

    for stamp in sorted(timeline):
        bars = {sym:series[sym][0][i] for sym,i in timeline[stamp]}
        prices = {sym:b["close"] for sym,b in bars.items()}
        day = stamp[:10]
        if day != current_day:
            current_day, daily_start, halted = day, marked_equity(prices), False
        # Exit first. If stop and target are both touched in one candle, assume the stop was hit first.
        for symbol in list(positions):
            if symbol not in bars: continue
            p, bar = positions[symbol], bars[symbol]
            stop_hit = bar["low"] <= p.stop if p.side == 1 else bar["high"] >= p.stop
            target_hit = bar["high"] >= p.target if p.side == 1 else bar["low"] <= p.target
            exit_price = p.stop if stop_hit else (p.target if target_hit else None)
            if exit_price is None: continue
            fill = exit_price*(1-cfg["slippage_rate"] if p.side==1 else 1+cfg["slippage_rate"])
            gross = p.side*(fill-p.entry)*p.qty
            fee = fill*p.qty*cfg["fee_rate"]
            net = gross-fee-p.entry_fee
            cash += p.qty*p.entry/cfg["max_leverage"] + gross-fee
            trades.append({"symbol":symbol,"side":"LONG" if p.side==1 else "SHORT","opened":p.opened,"closed":stamp,"entry":p.entry,"exit":fill,"qty":p.qty,"pnl":net,"fees":p.entry_fee+fee,"reason":"STOP" if stop_hit else "TARGET"})
            del positions[symbol]
        eq = marked_equity(prices)
        if eq <= daily_start*(1-cfg["daily_loss_limit"]): halted=True
        # Entries only on fully formed bars; signals use this bar's close, fills include slippage.
        for symbol,i in timeline[stamp]:
            if halted or symbol in positions or len(positions)>=cfg["max_open_positions"]: continue
            rows, ind = series[symbol]
            if i < 55: continue
            close, atr = rows[i]["close"], ind["atr"][i]
            if not atr or atr/close < cfg["min_atr_pct"]: continue
            if ind["vol_avg"][i] <= 0 or rows[i]["volume"] < ind["vol_avg"][i]*cfg["min_volume_ratio"]: continue
            long_signal = ind["ema20"][i] > ind["ema50"][i] and ind["rsi"][i] >= 52 and ind["rsi"][i] <= 68 and ind["adx"][i] >= cfg["min_trend_strength"]
            short_signal = ind["ema20"][i] < ind["ema50"][i] and ind["rsi"][i] >= 32 and ind["rsi"][i] <= 48 and ind["adx"][i] >= cfg["min_trend_strength"]
            if not (long_signal or short_signal): continue
            side = 1 if long_signal else -1
            entry = close*(1+cfg["slippage_rate"] if side==1 else 1-cfg["slippage_rate"])
            distance = atr*cfg["atr_stop_multiple"]
            risk_cash = eq*cfg["risk_per_trade"]
            qty = min(risk_cash/distance, eq*cfg["max_leverage"]/entry)
            used_risk = sum(x.risk_cash for x in positions.values())
            qty = min(qty, max(0, eq*cfg["max_total_open_risk"]-used_risk)/distance)
            notional = qty*entry
            margin = notional/cfg["max_leverage"]
            entry_fee = notional*cfg["fee_rate"]
            if qty <= 0 or margin+entry_fee > cash: continue
            cash -= margin+entry_fee
            positions[symbol] = Position(symbol,side,entry,qty,entry-distance if side==1 else entry+distance,entry+atr*cfg["atr_target_multiple"] if side==1 else entry-atr*cfg["atr_target_multiple"],qty*distance,entry_fee,stamp)
        prices.update({s:series[s][0][i]["close"] for s,i in timeline[stamp]})
        equity_curve.append({"timestamp":stamp,"equity":round(marked_equity(prices),2)})
    # Close remaining positions at final available close; no look-ahead.
    final_prices = {s:rows[-1]["close"] for s,(rows,_) in series.items()}
    for symbol,p in list(positions.items()):
        fill=final_prices[symbol]*(1-cfg["slippage_rate"] if p.side==1 else 1+cfg["slippage_rate"])
        gross=p.side*(fill-p.entry)*p.qty; fee=fill*p.qty*cfg["fee_rate"]; net=gross-fee-p.entry_fee
        cash += p.qty*p.entry/cfg["max_leverage"]+gross-fee
        trades.append({"symbol":symbol,"side":"LONG" if p.side==1 else "SHORT","opened":p.opened,"closed":"END","entry":p.entry,"exit":fill,"qty":p.qty,"pnl":net,"fees":p.entry_fee+fee,"reason":"END_OF_DATA"})
    wins=[t for t in trades if t["pnl"]>0]; losses=[t for t in trades if t["pnl"]<0]
    gross_profit=sum(t["pnl"] for t in wins); gross_loss=-sum(t["pnl"] for t in losses)
    net=sum(t["pnl"] for t in trades)
    return {"config":cfg,"initial_capital":cfg["initial_capital"],"final_equity":round(cfg["initial_capital"]+net,2),"net_pnl":round(net,2),"return_pct":round(net/cfg["initial_capital"]*100,3),"trades":len(trades),"wins":len(wins),"losses":len(losses),"win_rate_pct":round(100*len(wins)/len(trades),2) if trades else 0,"profit_factor":round(gross_profit/gross_loss,3) if gross_loss else (None if not gross_profit else "infinity"),"avg_trade":round(net/len(trades),2) if trades else 0,"fees":round(sum(t["fees"] for t in trades),2),"max_drawdown_pct":max_drawdown(equity_curve,cfg["initial_capital"]),"trade_log":trades,"equity_curve":equity_curve}

def max_drawdown(curve, initial):
    peak=initial; worst=0.0
    for point in curve:
        value=point["equity"]; peak=max(peak,value)
        if peak: worst=max(worst,(peak-value)/peak)
    return round(worst*100,3)

def main():
    parser=argparse.ArgumentParser(description="Research-only Crypto BOT boruty 4.0 backtest")
    parser.add_argument("csv",help="OHLCV CSV: timestamp,symbol,open,high,low,close,volume (UTC)")
    parser.add_argument("--out",default="research_v4/report.json")
    args=parser.parse_args()
    result=run_backtest(load_csv(args.csv))
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("trade_log","equity_curve")},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
