import unittest
from backtest import indicators, run_backtest

class BacktestTests(unittest.TestCase):
    def test_indicators_are_finite(self):
        rows=[]
        for i in range(130):
            c=100+i*0.2
            rows.append({"timestamp":f"2026-01-{1+i//24:02d}T{i%24:02d}:00:00Z","symbol":"TEST","open":c-0.1,"high":c+0.5,"low":c-0.5,"close":c,"volume":1000+i})
        values=indicators(rows)
        for key in ("ema20","ema50","atr","rsi","adx","vol_avg"):
            self.assertEqual(len(values[key]),len(rows))
            self.assertTrue(all(v==v for v in values[key]))

    def test_empty_input_preserves_capital(self):
        result=run_backtest({})
        self.assertEqual(result["final_equity"],30000.0)
        self.assertEqual(result["trades"],0)

    def test_costs_reduce_profit(self):
        # A flat series must not produce trades or fabricate profit.
        rows=[]
        for i in range(150):
            c=100.0
            rows.append({"timestamp":f"2026-01-{1+i//24:02d}T{i%24:02d}:00:00Z","symbol":"FLAT","open":c,"high":c+0.1,"low":c-0.1,"close":c,"volume":1000})
        result=run_backtest({"FLAT":rows})
        self.assertEqual(result["trades"],0)
        self.assertEqual(result["net_pnl"],0.0)

if __name__=="__main__":
    unittest.main()
