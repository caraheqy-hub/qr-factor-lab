"""Exploratory monthly low-volatility portfolio on historical CSI 300 members."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def evaluate(bars_path: Path, members_path: Path, window: int, cost_bps: float = 15) -> pd.DataFrame:
    bars = pd.read_csv(bars_path, parse_dates=["date"])
    members = pd.read_csv(members_path, parse_dates=["snapshot_date"])
    bars = bars.sort_values(["symbol", "date"])
    group = bars.groupby("symbol", sort=False)
    close_return = group["close"].pct_change(fill_method=None)
    bars["vol"] = close_return.groupby(bars["symbol"]).transform(
        lambda s: s.rolling(window, min_periods=window).std())
    calendar = pd.DatetimeIndex(sorted(bars["date"].unique()))
    month_ends = pd.Series(calendar).groupby(calendar.to_period("M")).max()
    snapshots = sorted(members["snapshot_date"].unique())
    indexed = bars.set_index(["date", "symbol"])
    previous: dict[str, float] = {}
    rows = []
    for date in month_ends:
        future = calendar[calendar > date]
        if len(future) == 0:
            continue
        entry_date = future[0]
        next_month = future[future.to_period("M") != entry_date.to_period("M")]
        if len(next_month) == 0:
            continue
        exit_date = next_month[0]
        prior_snapshots = [d for d in snapshots if d <= date]
        if not prior_snapshots:
            continue
        snapshot = prior_snapshots[-1]
        universe = set(members.loc[members["snapshot_date"] == snapshot, "symbol"])
        signal = indexed.loc[date].copy()
        signal = signal[signal.index.isin(universe)]
        signal = signal[(signal["tradestatus"] == 1) & (signal["isST"] == 0)]
        signal = signal.dropna(subset=["vol"])
        if len(signal) < 200:
            continue
        selected = signal.nsmallest(len(signal) // 5, "vol")
        entry = indexed.loc[entry_date, "open"]
        exit_price = indexed.loc[exit_date, "open"]
        returns = exit_price / entry - 1
        selected_returns = returns.reindex(selected.index)
        missing = int(selected_returns.isna().sum())
        if missing:
            rows.append({"date": date, "entry_date": entry_date, "exit_date": exit_date,
                         "window": window, "usable": False,
                         "missing_selected": missing})
            previous = {}
            continue
        gross = float(selected_returns.mean())
        benchmark = float(returns.reindex(signal.index).mean())
        target = dict.fromkeys(selected.index, 1 / len(selected))
        turnover = sum(abs(target.get(s, 0) - previous.get(s, 0))
                       for s in target.keys() | previous.keys())
        previous = {s: target[s] * (1 + ret) / (1 + gross)
                    for s, ret in selected_returns.items()}
        rows.append({"date": date, "entry_date": entry_date, "exit_date": exit_date,
                     "window": window, "usable": True,
                     "missing_selected": 0, "names": len(signal),
                     "gross": gross, "benchmark": benchmark,
                     "turnover": turnover, "net": gross - turnover * cost_bps / 10000})
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--members", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = pd.concat([evaluate(args.bars, args.members, window)
                      for window in (60, 252)], ignore_index=True)
    args.output.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.output / "monthly_lowvol_daily.csv", index=False)
    valid = data[data["usable"]].copy()
    valid["year"] = valid["entry_date"].dt.year
    summary = valid.groupby(["window", "year"]).agg(
        months=("net", "size"), gross_mean=("gross", "mean"),
        benchmark_mean=("benchmark", "mean"), net_mean=("net", "mean"),
        mean_turnover=("turnover", "mean"))
    summary["gross_excess_bps"] = (summary["gross_mean"] - summary["benchmark_mean"]) * 10000
    summary["net_excess_bps"] = (summary["net_mean"] - summary["benchmark_mean"]) * 10000
    summary.to_csv(args.output / "monthly_lowvol_summary.csv")
    print(summary.to_string())


if __name__ == "__main__":
    main()
