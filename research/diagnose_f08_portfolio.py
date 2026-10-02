"""Cost and coverage diagnostic for the reverse intraday-return candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from validate_f17_hs300 import load_panel


def diagnose(panel: pd.DataFrame, cost_bps: float = 15.0) -> pd.DataFrame:
    rows = []
    previous: dict[str, float] = {}
    for date, day in panel.groupby("date", sort=True):
        if date.year < 2020:
            continue
        ranked = day.dropna(subset=["f08"]).sort_values(["f08", "symbol"])
        if len(ranked) < 200:
            continue
        selected = ranked.head(len(ranked) // 5)
        missing = int(selected["return_1"].isna().sum())
        if missing:
            rows.append({"date": date, "usable": False, "missing_selected": missing,
                         "selected": len(selected)})
            previous = {}
            continue
        benchmark = ranked["return_1"].dropna().mean()
        gross = selected["return_1"].mean()
        target = dict.fromkeys(selected["symbol"], 1 / len(selected))
        turnover = sum(abs(target.get(s, 0) - previous.get(s, 0))
                       for s in target.keys() | previous.keys())
        # Approximation: next rebalance begins at the previous exit open.
        previous = {s: target[s] * (1 + ret) / (1 + gross)
                    for s, ret in zip(selected["symbol"], selected["return_1"])}
        rows.append({"date": date, "usable": True, "missing_selected": 0,
                     "selected": len(selected), "gross": gross, "benchmark": benchmark,
                     "turnover": turnover, "net": gross - cost_bps / 10000 * turnover})
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--members", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    daily = diagnose(load_panel(args.bars, args.members))
    args.output.mkdir(parents=True, exist_ok=True)
    daily.to_csv(args.output / "f08_daily_diagnostic.csv", index=False)
    valid = daily[daily["usable"]].copy()
    valid["year"] = valid["date"].dt.year
    summary = valid.groupby("year").agg(
        days=("net", "size"), gross_daily=("gross", "mean"),
        benchmark_daily=("benchmark", "mean"), net_daily=("net", "mean"),
        turnover=("turnover", "mean"))
    summary["gross_excess_bps"] = 10000 * (summary["gross_daily"] - summary["benchmark_daily"])
    summary["net_excess_bps"] = 10000 * (summary["net_daily"] - summary["benchmark_daily"])
    summary["skipped_days"] = daily[~daily["usable"]].groupby(daily["date"].dt.year).size()
    summary["skipped_days"] = summary["skipped_days"].fillna(0).astype(int)
    summary.to_csv(args.output / "f08_portfolio_summary.csv")
    print(summary.to_string())


if __name__ == "__main__":
    main()
