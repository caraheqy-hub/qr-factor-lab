"""Small exploratory screen of published daily-bar formulas."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .research import prepare, rank_ic


FACTOR_IDS = (
    "F01", "F08", "F09", "F10", "F11", "F12", "F14", "F15", "F17", "F18", "F19"
)


def build_factors(raw: pd.DataFrame) -> pd.DataFrame:
    data = prepare(raw)
    group = data.groupby("symbol", sort=False)
    close, volume = data["close"], data["volume"]
    lag_close = group["close"].shift(1)
    change = close / lag_close - 1
    weighted_move = change.abs() * volume

    def rolling(series: pd.Series, method: str) -> pd.Series:
        return series.groupby(data["symbol"]).transform(
            lambda values: getattr(values.rolling(20, min_periods=20), method)()
        )

    data["F01"] = -rolling(volume, "mean")
    data["F08"] = (close - data["open"]) / data["open"]
    data["F09"] = group["close"].shift(20) / close
    data["F10"] = rolling(close, "mean") / close
    data["F11"] = rolling(close, "std") / close
    data["F12"] = close.groupby(data["symbol"]).transform(
        lambda values: values.rolling(20, min_periods=20).corr(
            np.log1p(volume.loc[values.index])
        )
    )
    up = (close > lag_close).astype(float).where(lag_close.notna())
    down = (close < lag_close).astype(float).where(lag_close.notna())
    data["F14"] = rolling(up, "mean")
    data["F15"] = data["F14"] - rolling(down, "mean")
    data["F17"] = rolling(volume, "mean") / volume.replace(0, np.nan)
    data["F18"] = rolling(volume, "std") / volume.replace(0, np.nan)
    data["F19"] = rolling(weighted_move, "std") / rolling(weighted_move, "mean").replace(0, np.nan)
    data.loc[volume == 0, FACTOR_IDS] = np.nan
    return data.replace([np.inf, -np.inf], np.nan)


def screen(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = build_factors(raw)
    daily_ic = pd.DataFrame({factor: rank_ic(data, factor) for factor in FACTOR_IDS})
    common = daily_ic.dropna()
    if common.empty:
        raise ValueError("No common dates with at least ten valid names for every factor")
    rows = []
    for factor in FACTOR_IDS:
        aligned = data[data["date"].isin(common.index)]
        valid = aligned[[factor, "next_open_return"]].dropna()
        rows.append({
            "factor_id": factor,
            "common_dates": len(common),
            "mean_rank_ic": common[factor].mean(),
            "median_rank_ic": common[factor].median(),
            "positive_day_fraction": (common[factor] > 0).mean(),
            "coverage": len(valid) / len(aligned),
        })
    return pd.DataFrame(rows).sort_values("mean_rank_ic", ascending=False), common


def main() -> None:
    parser = argparse.ArgumentParser(description="Exploratory screen on a fixed daily-bar snapshot")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = pd.read_csv(args.input)
    summary, daily_ic = screen(raw)
    args.output.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output / "screen_summary.csv", index=False)
    daily_ic.to_csv(args.output / "daily_rank_ic.csv", index_label="date")
    (args.output / "manifest.json").write_text(json.dumps({
        "input": str(args.input),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "symbols": int(raw["symbol"].nunique()),
        "candidate_ids": list(FACTOR_IDS),
        "common_dates": len(daily_ic),
        "first_signal_date": daily_ic.index.min().strftime("%Y-%m-%d"),
        "last_signal_date": daily_ic.index.max().strftime("%Y-%m-%d"),
        "signal_time": "after close t",
        "label": "open t+1 to open t+2",
        "scope": "exploratory Rank IC screen; no execution or cost model",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
