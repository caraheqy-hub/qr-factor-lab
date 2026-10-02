import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qr_factor_lab.research import (add_volume_mean_factor, prepare, summarize,
                                    top_quantile_backtest)  # noqa: E402


class ResearchTimingTests(unittest.TestCase):
    def test_signal_uses_only_prior_closes_and_next_two_opens_for_return(self):
        dates = pd.date_range("2025-01-01", periods=30)
        bars = pd.DataFrame({"date": dates, "symbol": "SHSE.600000",
                             "open": range(1, 31), "close": range(2, 32), "volume": 100})
        panel = prepare(bars)
        row = panel.iloc[20]
        self.assertAlmostEqual(row["momentum"], bars.iloc[15]["close"] / bars.iloc[0]["close"] - 1)
        self.assertAlmostEqual(row["next_open_return"], bars.iloc[22]["open"] / bars.iloc[21]["open"] - 1)

    def test_missing_execution_price_is_rejected(self):
        dates = pd.date_range("2025-01-01", periods=32)
        bars = pd.concat([
            pd.DataFrame({"date": dates, "symbol": f"S{i}", "open": 10 + i,
                          "close": 10 + i, "volume": 100}) for i in range(10)
        ], ignore_index=True)
        bars.loc[(bars["symbol"] == "S0") & (bars["date"] == dates[23]), "open"] = float("nan")
        panel = prepare(bars)
        with self.assertRaisesRegex(ValueError, "Missing next-session"):
            top_quantile_backtest(panel, "momentum")

    def test_report_volume_factor_uses_volume_known_at_signal_close(self):
        dates = pd.date_range("2026-03-01", periods=25)
        bars = pd.DataFrame({"date": dates, "symbol": "S0", "open": 10,
                             "close": 10, "volume": range(1, 26)})
        panel = add_volume_mean_factor(prepare(bars), 20)
        self.assertAlmostEqual(panel.iloc[19]["low_volume_mean"], -10.5)
        self.assertAlmostEqual(panel.iloc[20]["low_volume_mean"], -11.5)

    def test_missing_session_cannot_be_skipped_in_next_open_return(self):
        dates = pd.date_range("2026-04-27", periods=5)
        bars = pd.concat([
            pd.DataFrame({"date": dates, "symbol": "complete", "open": 10,
                          "close": 10, "volume": 100}),
            pd.DataFrame({"date": dates.delete(3), "symbol": "gap", "open": 10,
                          "close": 10, "volume": 100}),
        ], ignore_index=True)
        panel = prepare(bars)
        row = panel[(panel["symbol"] == "gap") & (panel["date"] == dates[1])].iloc[0]
        self.assertTrue(pd.isna(row["next_open_return"]))

    def test_first_day_loss_counts_as_drawdown(self):
        daily = pd.DataFrame({"net_return": [-0.1, 0.02], "turnover": [0, 0],
                              "baseline_return": [0, 0]})
        self.assertAlmostEqual(summarize(daily, pd.Series(dtype=float))["max_drawdown"], -0.1)


if __name__ == "__main__":
    unittest.main()
