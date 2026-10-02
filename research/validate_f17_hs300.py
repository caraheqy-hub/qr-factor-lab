"""Offline replication check of F17 on historical CSI 300 membership snapshots.

This is an exploratory screen: adjusted prices are retrospective and no fill model is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_panel(bars_path: Path, members_path: Path) -> pd.DataFrame:
    bars = pd.read_csv(bars_path, parse_dates=["date"])
    members = pd.read_csv(members_path, parse_dates=["snapshot_date"])
    for column in ("open", "close", "volume", "amount"):
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    if bars.duplicated(["date", "symbol"]).any():
        raise ValueError("Duplicate bar keys")
    if members.duplicated(["snapshot_date", "symbol"]).any():
        raise ValueError("Duplicate membership keys")
    bars = bars.sort_values(["symbol", "date"]).reset_index(drop=True)
    grouped = bars.groupby("symbol", sort=False)
    calendar = pd.Index(sorted(bars["date"].unique()))
    date_number = bars["date"].map({date: i for i, date in enumerate(calendar)})
    bars["f17"] = grouped["volume"].transform(
        lambda s: s.rolling(20, min_periods=20).mean()
    ) / bars["volume"].replace(0, np.nan)
    bars["f01"] = -grouped["volume"].transform(
        lambda s: s.rolling(20, min_periods=20).mean()
    )
    bars["f09"] = grouped["close"].shift(20) / bars["close"]
    bars["f08"] = (bars["close"] - bars["open"]) / bars["open"]
    bars["mean_amount"] = grouped["amount"].transform(
        lambda s: s.rolling(20, min_periods=20).mean()
    )
    for horizon in (1, 5):
        entry = grouped["open"].shift(-1)
        exit_price = grouped["open"].shift(-(horizon + 1))
        exit_date = grouped["date"].shift(-(horizon + 1))
        returns = exit_price / entry - 1
        valid = exit_date.map({date: i for i, date in enumerate(calendar)}) == date_number + horizon + 1
        bars[f"return_{horizon}"] = returns.where(valid)
    bars.loc[(bars["tradestatus"] != 1) | (bars["isST"] != 0),
             ["f17", "f01", "f09", "f08"]] = np.nan
    snapshots = pd.DataFrame({"date": calendar})
    snapshots = pd.merge_asof(snapshots, members[["snapshot_date"]].drop_duplicates().sort_values("snapshot_date"),
                              left_on="date", right_on="snapshot_date", direction="backward")
    bars = bars.merge(snapshots, on="date", how="left")
    bars = bars.merge(members[["snapshot_date", "symbol"]].assign(member=True),
                      on=["snapshot_date", "symbol"], how="left")
    bars = bars[bars["member"].fillna(False)].copy()
    numeric = ["f17", "f01", "f09", "f08", "mean_amount", "return_1", "return_5"]
    bars[numeric] = bars[numeric].replace([np.inf, -np.inf], np.nan)
    return bars


def daily_ic(panel: pd.DataFrame, factor: str, horizon: int) -> pd.DataFrame:
    label = f"return_{horizon}"
    rows = []
    for date, day in panel.groupby("date", sort=True):
        valid = day[[factor, label]].dropna()
        if len(valid) < 100 or valid[factor].nunique() < 10:
            continue
        rows.append({"date": date, "factor": factor, "horizon": horizon,
                     "ic": valid[factor].corr(valid[label], method="spearman"),
                     "coverage": len(valid) / len(day), "names": len(valid)})
    return pd.DataFrame(rows)


def summarize(ics: pd.DataFrame) -> pd.DataFrame:
    ics = ics.copy()
    ics["period"] = ics["date"].dt.year.astype(str)
    all_periods = ics.assign(period="all")
    return pd.concat([ics, all_periods]).groupby(["factor", "horizon", "period"]).agg(
        days=("ic", "size"), mean_ic=("ic", "mean"), median_ic=("ic", "median"),
        positive_fraction=("ic", lambda x: (x > 0).mean()),
        mean_coverage=("coverage", "mean"), min_names=("names", "min"),
    ).reset_index()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--members", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    panel = load_panel(args.bars, args.members)
    ics = pd.concat([daily_ic(panel, factor, horizon)
                     for factor in ("f17", "f01", "f09", "f08")
                     for horizon in (1, 5)], ignore_index=True)
    args.output.mkdir(parents=True, exist_ok=True)
    summarize(ics).to_csv(args.output / "ic_summary.csv", index=False)
    ics.to_csv(args.output / "daily_ic.csv", index=False)
    metadata = {"bars_sha256": hashlib.sha256(args.bars.read_bytes()).hexdigest(),
                "members_sha256": hashlib.sha256(args.members.read_bytes()).hexdigest(),
                "bars": len(panel), "symbols": panel["symbol"].nunique(),
                "first_date": str(panel["date"].min().date()),
                "last_date": str(panel["date"].max().date()),
                "signal": "after close t", "entry": "open t+1",
                "returns": "open t+1 to open t+2 or t+6",
                "membership": "latest available monthly HS300 snapshot at or before signal date",
                "price_adjustment": "BaoStock adjustflag=2, retrospectively adjusted",
                "scope": "exploratory Rank IC, no order fills or transaction costs"}
    (args.output / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
    print(summarize(ics).to_string(index=False))


if __name__ == "__main__":
    main()
