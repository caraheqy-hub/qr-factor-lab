import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from monthly_value import evaluate  # noqa: E402


class MonthlyTimingTest(unittest.TestCase):
    def test_december_signal_enters_in_january_and_exits_in_february(self):
        dates = pd.to_datetime(["2019-12-30", "2019-12-31", "2020-01-02",
                                "2020-01-31", "2020-02-03"])
        symbols = [f"S{i:03}" for i in range(200)]
        bars = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"]).to_frame(index=False)
        bars["open"] = 10.0
        bars["close"] = 10.0
        bars["tradestatus"] = 1
        bars["isST"] = 0
        valuation = bars[["date", "symbol"]].copy()
        valuation["pbMRQ"] = 1.0
        members = pd.DataFrame({"snapshot_date": [pd.Timestamp("2019-12-31")] * 200,
                                "symbol": symbols})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bars.to_csv(root / "bars.csv", index=False)
            valuation.to_csv(root / "pb.csv", index=False)
            members.to_csv(root / "members.csv", index=False)
            result = evaluate(root / "bars.csv", root / "pb.csv", root / "members.csv")
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["date"], pd.Timestamp("2019-12-31"))
        self.assertEqual(result.iloc[0]["entry_date"], pd.Timestamp("2020-01-02"))
        self.assertEqual(result.iloc[0]["exit_date"], pd.Timestamp("2020-02-03"))


if __name__ == "__main__":
    unittest.main()
