import json, os, time, urllib.request
from datetime import datetime, timezone

STATE_FILE = "portfolio-state.json"
START, FEE = 30000.0, 0.001
STOP, TAKE, RISK = 0.025, 0.04, 0.01
MAX_POS, DAILY_LIMIT, LEVERAGE, MARGIN_PER_POSITION = 10, 0.05, 3, 0.10
ASSETS = {"BTC":"XBTUSD", "ETH":"ETHUSD", "SOL":"SOLUSD", "XRP":"XRPUSD", "ADA":"ADAUSD", "LINK":"LINKUSD", "LTC":"LTCUSD", "DOGE":"XDGUSD", "AVAX":"AVAXUSD", "DOT":"DOTUSD"}

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent":"CryptoBOT-boruty-paper/3.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def ema(values, period):
    k = 2 / (period + 1)
    out = values[0]
    for x in values[1:]:
        out += (x - out) * k
    return out

def indicators(closes):
    e20 = ema(closes[-80:], 20)
    e50 = ema(closes[-120:], 50)
    changes = [b-a for a,b in zip(closes[-15:-1], closes[-14:])]
    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]
    ag, al = sum(gains)/14, sum(losses)/14
    rsi = 50 if ag == 0 and al == 0 else 100 if al == 0 else 100 - 100/(1 + ag/al)
    return e20, e50, rsi

def position_pnl(position, price):
    direction = 1 if position.get('side', 'LONG') == 'LONG' else -1
    return direction * (price - position['entry']) * position['qty']

def exit_reason(position, price, candle_changed, market):
    side = position.get('side', 'LONG')
    stop_price = float(position.get('stop_price', position['entry'] * (1 - STOP if side == 'LONG' else 1 + STOP)))
    take_price = float(position.get('take_price', position['entry'] * (1 + TAKE if side == 'LONG' else 1 - TAKE)))
    liq_distance = max(0.01, 1 / float(position.get('leverage', LEVERAGE)) - 0.005)
    liq_price = position['entry'] * (1 - liq_distance if side == 'LONG' else 1 + liq_distance)
    if (side == 'LONG' and price <= stop_price) or (side == 'SHORT' and price >= stop_price): return 'Stop Loss'
    if (side == 'LONG' and price >= take_price) or (side == 'SHORT' and price <= take_price): return 'Take Profit'
    if (side == 'LONG' and price <= liq_price) or (side == 'SHORT' and price >= liq_price): return 'Symulowana likwidacja'
    if candle_changed:
        if side == 'LONG' and (market['ema20'] < market['ema50'] or market['rsi'] >= 78): return 'Wyjście techniczne LONG'
        if side == 'SHORT' and (market['ema20'] > market['ema50'] or market['rsi'] <= 22): return 'Wyjście techniczne SHORT'
    return None

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
        for k, v in {"positions": {}, "trades": [], "last_candles": {}, "history": [], "cash": START, "day_start_equity": START, "enabled": True}.items():
            s.setdefault(k, v)
        return s
    return {"cash": START, "positions": {}, "trades": [], "last_candles": {}, "day": None, "day_start_equity": START, "enabled": True, "last_run": None, "prices": {}, "history": []}

def main():
    s = load_state()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    fx = get_json("https://api.nbp.pl/api/exchangerates/rates/a/usd/?format=json")["rates"][0]["mid"]
    data = {}
    for asset, pair in ASSETS.items():
        ohlc = get_json(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval=15")
        if ohlc.get("error"):
            raise RuntimeError(f"Kraken OHLC {asset}: {ohlc['error']}")
        result = ohlc["result"]
        pair_key = next(k for k in result if k != "last")
        closed = result[pair_key][:-1]
        if len(closed) < 120:
            raise RuntimeError(f"Za mało zamkniętych świec Kraken dla {asset}")
        closes = [float(c[4]) for c in closed]
        ticker_data = get_json(f"https://api.kraken.com/0/public/Ticker?pair={pair}")
        if ticker_data.get("error"):
            raise RuntimeError(f"Kraken ticker {asset}: {ticker_data['error']}")
        ticker_key = next(iter(ticker_data["result"]))
        ticker = float(ticker_data["result"][ticker_key]["c"][0])
        e20, e50, rsi = indicators(closes)
        data[asset] = {"price": ticker * fx, "candle": int(closed[-1][0]) * 1000, "ema20": e20, "ema50": e50, "rsi": rsi}

    def equity():
        return float(s["cash"]) + sum(float(p.get("margin", 0)) + position_pnl(p, data.get(a, {}).get("price", p["entry"])) for a, p in s["positions"].items())

    if s.get("day") != today:
        s["day"] = today
        s["day_start_equity"] = equity()

    def daily_loss():
        base = float(s.get("day_start_equity") or START)
        return max(0, (base - equity()) / base) if base else 0

    events = []
    for a, p in list(s["positions"].items()):
        price, side = data[a]["price"], p.get("side", "LONG")
        reason = exit_reason(p, price, data[a]["candle"] != s.get("last_candles", {}).get(a), data[a])
        if reason:
            raw_pnl = position_pnl(p, price)
            exit_fee = p["qty"] * price * FEE
            entry_fee = float(p.get("entry_fee", 0))
            s["cash"] += float(p.get("margin", 0)) + raw_pnl - exit_fee
            net_pnl = raw_pnl - exit_fee - entry_fee
            s["trades"].insert(0, {"time": int(time.time()*1000), "asset": a, "side": "EXIT_" + side, "price": price, "qty": p["qty"], "pnl": net_pnl, "fee": exit_fee, "reason": reason, "leverage": p.get("leverage", LEVERAGE)})
            del s["positions"][a]
            events.append(f"{a} zamknięcie {side}: {reason}")

    # Daily loss circuit breaker: flatten every simulated position at current marks.
    if daily_loss() >= DAILY_LIMIT and s["positions"]:
        for a, p in list(s["positions"].items()):
            price = data[a]["price"]
            raw_pnl = position_pnl(p, price)
            exit_fee = p["qty"] * price * FEE
            s["cash"] += float(p.get("margin", 0)) + raw_pnl - exit_fee
            net_pnl = raw_pnl - exit_fee - float(p.get("entry_fee", 0))
            s["trades"].insert(0, {"time": int(time.time()*1000), "asset": a, "side": "EXIT_" + p.get("side", "LONG"), "price": price, "qty": p["qty"], "pnl": net_pnl, "fee": exit_fee, "reason": "Dzienny limit straty 5% - awaryjne zamknięcie", "leverage": p.get("leverage", LEVERAGE)})
            del s["positions"][a]
            events.append(f"{a} awaryjne zamknięcie - limit dzienny 5%")

    # Evaluate both LONG and SHORT on each newly closed 15-minute candle.
    for a, m in data.items():
        if m["candle"] == s.get("last_candles", {}).get(a):
            continue
        s.setdefault("last_candles", {})[a] = m["candle"]
        if not s.get("enabled", True) or a in s["positions"] or len(s["positions"]) >= MAX_POS or daily_loss() >= DAILY_LIMIT:
            continue
        side = None
        if m["ema20"] > m["ema50"] and 45 <= m["rsi"] <= 72:
            side = "LONG"
        elif m["ema20"] < m["ema50"] and 28 <= m["rsi"] <= 55:
            side = "SHORT"
        if side is None:
            continue
        eq = equity()
        risk_cash = eq * RISK
        unit_risk = m["price"] * STOP + m["price"] * FEE * 2
        risk_qty = risk_cash / unit_risk
        max_margin = eq * MARGIN_PER_POSITION
        margin_qty = max_margin * LEVERAGE / m["price"]
        cash_qty = float(s["cash"]) / (m["price"] / LEVERAGE + m["price"] * FEE)
        qty = min(risk_qty, margin_qty, cash_qty)
        notional = qty * m["price"]
        margin, entry_fee = notional / LEVERAGE, notional * FEE
        if qty <= 0 or notional < 100 or margin + entry_fee > float(s["cash"]):
            continue
        stop_price = m["price"] * (1 - STOP if side == "LONG" else 1 + STOP)
        take_price = m["price"] * (1 + TAKE if side == "LONG" else 1 - TAKE)
        s["cash"] -= margin + entry_fee
        s["positions"][a] = {"side": side, "qty": qty, "entry": m["price"], "opened_at": int(time.time()*1000), "leverage": LEVERAGE, "margin": margin, "entry_fee": entry_fee, "stop_price": stop_price, "take_price": take_price}
        s["trades"].insert(0, {"time": int(time.time()*1000), "asset": a, "side": side, "price": m["price"], "qty": qty, "pnl": None, "fee": entry_fee, "reason": f"EMA20/50 + RSI · {side}", "leverage": LEVERAGE})
        events.append(f"{a} otwarcie {side} x{LEVERAGE}")

    s["trades"] = s.get("trades", [])[:500]
    s["prices"] = {a: m["price"] for a, m in data.items()}
    s["indicators"] = {a: {"ema20": m["ema20"], "ema50": m["ema50"], "rsi": m["rsi"]} for a, m in data.items()}
    s["last_run"] = now.isoformat()
    s["last_events"] = events
    s["equity"] = equity()
    s["daily_loss_pct"] = daily_loss() * 100
    s["config"] = {"profile": "active", "initial_capital": START, "max_positions": MAX_POS, "short_enabled": True, "max_leverage": LEVERAGE, "stop_loss_pct": STOP*100, "take_profit_pct": TAKE*100, "risk_per_trade_pct": RISK*100, "daily_loss_limit_pct": DAILY_LIMIT*100, "candle_interval_minutes": 15, "paper_trading_only": True}
    history = s.get("history", [])
    sample = {"time": int(now.timestamp()*1000), "equity": round(s["equity"], 2)}
    sample.update({a: round(m["price"], 2) for a, m in data.items()})
    history.append(sample)
    s["history"] = history[-2016:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    print(json.dumps({"last_run": s["last_run"], "equity": s["equity"], "cash": s["cash"], "positions": len(s["positions"]), "trades": len(s["trades"]), "events": events, "daily_loss_pct": s["daily_loss_pct"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
