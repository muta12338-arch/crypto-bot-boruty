import json, os, time, urllib.request
from datetime import datetime, timezone, date

STATE_FILE = "portfolio-state.json"
START, FEE, STOP, TAKE, RISK, MAX_POS, DAILY_LIMIT = 1000.0, 0.001, 0.025, 0.05, 0.01, 2, 0.03
ASSETS = {"BTC":"BTCUSDT", "ETH":"ETHUSDT"}

def get_json(url):
    req=urllib.request.Request(url, headers={"User-Agent":"CryptoBOT-boruty-paper/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def ema(values, period):
    k=2/(period+1); out=values[0]
    for x in values[1:]: out += (x-out)*k
    return out

def indicators(closes):
    e20=ema(closes[-80:],20); e50=ema(closes[-120:],50)
    gains=[]; losses=[]
    for a,b in zip(closes[-15:-1],closes[-14:]):
        d=b-a; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains)/14; al=sum(losses)/14
    rsi=100 if al==0 else 100-100/(1+ag/al)
    return e20,e50,rsi

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f: s=json.load(f)
        return s
    return {"cash":START,"positions":{},"trades":[],"last_candles":{},"day":None,"day_start_equity":START,"enabled":True,"last_run":None,"prices":{}}

def main():
    s=load_state()
    now=datetime.now(timezone.utc); today=now.date().isoformat()
    fx=get_json("https://api.nbp.pl/api/exchangerates/rates/a/usd/?format=json")["rates"][0]["mid"]
    data={}
    for asset,symbol in ASSETS.items():
        candles=get_json(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=120")
        closed=candles[:-1]
        closes=[float(c[4]) for c in closed]
        ticker=float(get_json(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}")["price"])
        e20,e50,rsi=indicators(closes)
        data[asset]={"price":ticker*fx,"candle":int(closed[-1][0]),"ema20":e20,"ema50":e50,"rsi":rsi}
    def equity():
        return float(s["cash"])+sum(data.get(a,{}).get("price",p["entry"])*p["qty"] for a,p in s["positions"].items())
    if s.get("day") != today:
        s["day"]=today; s["day_start_equity"]=equity()
    def daily_loss():
        base=float(s.get("day_start_equity") or START)
        return max(0,(base-equity())/base) if base else 0
    events=[]
    # Risk exits are checked on every scheduled run, not only at candle close.
    for a,p in list(s["positions"].items()):
        price=data[a]["price"]
        if price <= p["entry"]*(1-STOP):
            reason="Stop loss -2.5%"
        elif price >= p["entry"]*(1+TAKE):
            reason="Take profit +5%"
        elif data[a]["candle"] != s.get("last_candles",{}).get(a) and (data[a]["ema20"] < data[a]["ema50"] or data[a]["rsi"] >= 75):
            reason="Wyjście techniczne EMA/RSI"
        else:
            reason=None
        if reason:
            gross=p["qty"]*price; fee=gross*FEE; pnl=gross-fee-p["qty"]*p["entry"]
            s["cash"] += gross-fee
            s["trades"].insert(0,{"time":int(time.time()*1000),"asset":a,"side":"SELL","price":price,"qty":p["qty"],"pnl":pnl,"fee":fee,"reason":reason})
            del s["positions"][a]; events.append(f"{a} sprzedaż")
    for a,m in data.items():
        fresh=m["candle"] != s.get("last_candles",{}).get(a)
        if fresh:
            s.setdefault("last_candles",{})[a]=m["candle"]
            if s.get("enabled",True) and a not in s["positions"] and len(s["positions"])<MAX_POS and daily_loss()<DAILY_LIMIT and m["ema20"]>m["ema50"] and 50<=m["rsi"]<=68:
                eq=equity(); risk_cash=eq*RISK
                unit=m["price"]*STOP+m["price"]*FEE+m["price"]*(1-STOP)*FEE
                qty=min(risk_cash/unit,eq*.35/m["price"],float(s["cash"])/(m["price"]*(1+FEE)))
                if qty>0 and qty*m["price"]>=20:
                    gross=qty*m["price"]; fee=gross*FEE
                    s["cash"]-=gross+fee
                    s["positions"][a]={"qty":qty,"entry":m["price"],"opened_at":int(time.time()*1000)}
                    s["trades"].insert(0,{"time":int(time.time()*1000),"asset":a,"side":"BUY","price":m["price"],"qty":qty,"pnl":None,"fee":fee,"reason":"EMA20>EMA50, RSI 50-68"})
                    events.append(f"{a} kupno")
    s["trades"]=s.get("trades",[])[:500]
    s["prices"]={a:m["price"] for a,m in data.items()}
    s["indicators"]={a:{"ema20":m["ema20"],"ema50":m["ema50"],"rsi":m["rsi"]} for a,m in data.items()}
    s["last_run"]=now.isoformat()
    s["last_events"]=events
    s["equity"]=equity()
    s["daily_loss_pct"]=daily_loss()*100
    with open(STATE_FILE,"w",encoding="utf-8") as f: json.dump(s,f,ensure_ascii=False,indent=2)
    print(json.dumps({"last_run":s["last_run"],"equity":s["equity"],"cash":s["cash"],"positions":len(s["positions"]),"trades":len(s["trades"]),"events":events},ensure_ascii=False))

if __name__=="__main__": main()
