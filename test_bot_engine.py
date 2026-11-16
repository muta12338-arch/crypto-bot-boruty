import unittest
import bot_engine as bot

class StrategySafetyTests(unittest.TestCase):
    def test_active_configuration_limits(self):
        self.assertEqual(bot.START, 30000.0)
        self.assertEqual(bot.MAX_POS, 10)
        self.assertEqual(bot.LEVERAGE, 3)
        self.assertEqual(bot.STOP, 0.025)
        self.assertEqual(bot.TAKE, 0.04)
        self.assertEqual(bot.DAILY_LIMIT, 0.05)
        self.assertEqual(bot.RISK, 0.01)

    def test_long_and_short_pnl(self):
        p = {'side': 'LONG', 'entry': 100.0, 'qty': 2.0}
        self.assertEqual(bot.position_pnl(p, 110.0), 20.0)
        p = {'side': 'SHORT', 'entry': 100.0, 'qty': 2.0}
        self.assertEqual(bot.position_pnl(p, 90.0), 20.0)
        self.assertEqual(bot.position_pnl(p, 110.0), -20.0)

    def test_stop_and_take_for_both_directions(self):
        long = {'side': 'LONG', 'entry': 100.0, 'qty': 1, 'leverage': 3}
        short = {'side': 'SHORT', 'entry': 100.0, 'qty': 1, 'leverage': 3}
        market = {'ema20': 101, 'ema50': 100, 'rsi': 55}
        self.assertEqual(bot.exit_reason(long, 97.4, False, market), 'Stop Loss')
        self.assertEqual(bot.exit_reason(long, 104.1, False, market), 'Take Profit')
        self.assertEqual(bot.exit_reason(short, 102.6, False, market), 'Stop Loss')
        self.assertEqual(bot.exit_reason(short, 95.9, False, market), 'Take Profit')

    def test_daily_loss_limit_value(self):
        self.assertAlmostEqual(bot.START * bot.DAILY_LIMIT, 1500.0)

    def test_flat_market_rsi_is_neutral(self):
        self.assertEqual(bot.indicators([100.0] * 130)[2], 50)

if __name__ == '__main__':
    unittest.main()
