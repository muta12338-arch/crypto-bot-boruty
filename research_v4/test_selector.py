import unittest
from strategy_selector import chronological_split, passes

def make_rows(n):
    return [{"timestamp":f"2026-01-{1+i//24:02d}T{i%24:02d}:00:00Z","symbol":"TEST","open":100,"high":101,"low":99,"close":100,"volume":1000} for i in range(n)]

class SelectorTests(unittest.TestCase):
    def test_split_is_chronological_and_disjoint(self):
        grouped={"TEST":make_rows(200)}
        train, validation, holdout=chronological_split(grouped)
        self.assertEqual(len(train["TEST"]),120)
        self.assertEqual(len(validation["TEST"]),40)
        self.assertEqual(len(holdout["TEST"]),40)
        self.assertLess(train["TEST"][-1]["timestamp"],validation["TEST"][0]["timestamp"])
        self.assertLess(validation["TEST"][-1]["timestamp"],holdout["TEST"][0]["timestamp"])

    def test_rejects_negative_expectancy(self):
        report={"trades":100,"net_pnl":-1,"profit_factor":1.5,"max_drawdown_pct":5,"avg_trade":-0.01}
        self.assertFalse(passes(report,30))

    def test_rejects_insufficient_sample(self):
        report={"trades":5,"net_pnl":100,"profit_factor":2.0,"max_drawdown_pct":1,"avg_trade":20}
        self.assertFalse(passes(report,30))

    def test_rejects_excessive_drawdown(self):
        report={"trades":100,"net_pnl":100,"profit_factor":1.5,"max_drawdown_pct":11,"avg_trade":1}
        self.assertFalse(passes(report,30))

if __name__=="__main__":
    unittest.main()
