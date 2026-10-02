import unittest

import pandas as pd

from qr_factor_lab.factor_screen import build_factors


class ScreenTimingTests(unittest.TestCase):
    def test_future_bar_does_not_change_earlier_factor(self):
        dates = pd.bdate_range("2025-01-01", periods=24)
        rows = [
            {"date": date, "symbol": "SHSE.600000", "open": 10 + day / 10,
             "close": 10 + day / 10 + day / 100, "volume": 1000 + day * 20}
            for day, date in enumerate(dates)
        ]
        original = build_factors(pd.DataFrame(rows))
        altered = pd.DataFrame(rows)
        altered.loc[altered.index[-1], ["open", "close", "volume"]] = [99, 100, 90000]
        changed = build_factors(altered)
        for factor in ("F01", "F08", "F09", "F10", "F12", "F17", "F19"):
            self.assertEqual(original.loc[21, factor], changed.loc[21, factor])


if __name__ == "__main__":
    unittest.main()
