"""Fetch a bounded GM snapshot and run a reproducible factor experiment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .research import add_volume_mean_factor, prepare, rank_ic, summarize, top_quantile_backtest


FACTORS = ("momentum", "low_vol")


def demo_data(args: argparse.Namespace) -> None:
    """Make a deterministic synthetic panel for trying the public workflow."""
    rng = np.random.default_rng(20261002)
    dates = pd.bdate_range("2025-01-02", periods=130)
    frames = []
    for number in range(12):
        close = 10 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, len(dates))))
        opening = close * (1 + rng.normal(0, 0.003, len(dates)))
        frames.append(pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"), "symbol": f"DEMO.{number:03d}",
            "open": opening, "close": close,
            "volume": rng.integers(100_000, 1_000_000, len(dates)),
        }))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(args.output, index=False)
    print(f"Saved synthetic demo bars to {args.output}; not market data")


def fetch_gm(args: argparse.Namespace) -> None:
    token = os.environ.get("GM_TOKEN")
    if not token:
        raise SystemExit("Set GM_TOKEN for this PowerShell session; do not put it in source files")
    from gm.api import ADJUST_PREV, history, set_token

    symbols = [line.strip() for line in args.symbols.read_text(encoding="utf-8").splitlines()]
    symbols = [symbol for symbol in symbols if symbol and not symbol.startswith("#")]
    if len(symbols) < 10 or len(symbols) != len(set(symbols)):
        raise SystemExit("Use at least 10 unique symbols")
    set_token(token)
    frames = []
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    if end < start:
        raise SystemExit("end must be on or after start")
    months = pd.date_range(start.replace(day=1), end, freq="MS")
    for month in months:
        chunk_start = max(start, month)
        chunk_end = min(end, month + pd.offsets.MonthEnd(1))
        frame = history(
            symbol=",".join(symbols), frequency="1d",
            start_time=chunk_start.strftime("%Y-%m-%d"),
            end_time=chunk_end.strftime("%Y-%m-%d"),
            fields="symbol,eob,open,close,volume", adjust=ADJUST_PREV, df=True,
        )
        if frame.empty:
            raise RuntimeError(f"No GM bars for {month.strftime('%Y-%m')}")
        frames.append(frame.rename(columns={"eob": "date"}))
    bars = pd.concat(frames, ignore_index=True)
    missing_symbols = set(symbols) - set(bars["symbol"])
    if missing_symbols:
        raise RuntimeError(f"No bars for symbols: {', '.join(sorted(missing_symbols))}")
    bars["date"] = pd.to_datetime(bars["date"]).dt.strftime("%Y-%m-%d")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bars[["date", "symbol", "open", "close", "volume"]].to_csv(args.output, index=False)
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(".source.json").write_text(
        json.dumps({"provider": "GM gm.api", "adjustment": "ADJUST_PREV",
                    "adjust_end_time": "SDK default (fetch time)", "symbols": symbols,
                    "start": args.start, "end": args.end,
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(), "rows": len(bars),
                    "gm_version": importlib.metadata.version("gm"), "sha256": digest},
                   ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"Saved {len(bars)} real daily bars to {args.output}")


def analyze(args: argparse.Namespace) -> None:
    raw = pd.read_csv(args.input)
    data = prepare(raw, momentum_window=args.momentum_window,
                   momentum_skip=args.momentum_skip,
                   volatility_window=args.volatility_window)
    args.output.mkdir(parents=True, exist_ok=True)
    results = {}
    for factor in FACTORS:
        discovery_panel = data[data["exit_date"] < args.split_date]
        holdout_panel = data[data["date"] >= args.split_date]
        if discovery_panel.empty or holdout_panel.empty:
            raise ValueError("Split date must leave valid discovery and holdout periods")
        discovery = top_quantile_backtest(discovery_panel, factor, cost_bps=args.cost_bps)
        holdout = top_quantile_backtest(holdout_panel, factor, cost_bps=args.cost_bps)
        discovery["period"] = "discovery"
        holdout["period"] = "holdout"
        daily = pd.concat([discovery, holdout], ignore_index=True)
        discovery_ic = rank_ic(discovery_panel, factor)
        holdout_ic = rank_ic(holdout_panel, factor)
        results[factor] = {
            "discovery": summarize(discovery, discovery_ic),
            "holdout": summarize(holdout, holdout_ic),
        }
        daily.to_csv(args.output / f"{factor}_daily.csv", index=False)
        pd.concat([discovery_ic, holdout_ic]).to_csv(args.output / f"{factor}_ic.csv")
    report = {"input": str(args.input), "split_date": args.split_date,
              "factor_parameters": {"momentum_window": args.momentum_window,
                                    "momentum_skip": args.momentum_skip,
                                    "volatility_window": args.volatility_window},
              "cost_bps_per_traded_notional": args.cost_bps, "factors": results,
              "limits": ["Static user-supplied universe may have survivorship bias",
                         "GM adjusted data is retrospective; results are research examples",
                         "No live trading or broker order execution"]}
    (args.output / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


def sweep(args: argparse.Namespace) -> None:
    """Select momentum parameters by discovery IC, then open the holdout once."""
    raw = pd.read_csv(args.input)
    args.output.mkdir(parents=True, exist_ok=True)
    windows = [int(value) for value in args.windows.split(",")]
    skips = [int(value) for value in args.skips.split(",")]
    trials = []
    for window in windows:
        for skip in skips:
            if window <= skip:
                continue
            panel = prepare(raw, momentum_window=window, momentum_skip=skip)
            discovery_panel = panel[panel["exit_date"] < args.split_date]
            ic = rank_ic(discovery_panel, "momentum")
            daily = top_quantile_backtest(discovery_panel, "momentum", cost_bps=args.cost_bps)
            stats = summarize(daily, ic)
            trials.append({"window": window, "skip": skip, **stats})
    if not trials:
        raise ValueError("No valid momentum parameter pairs")
    trial_table = pd.DataFrame(trials).sort_values("mean_rank_ic", ascending=False)
    trial_table.to_csv(args.output / "discovery_trials.csv", index=False)
    winner = trial_table.iloc[0]
    panel = prepare(raw, momentum_window=int(winner["window"]),
                    momentum_skip=int(winner["skip"]))
    holdout_panel = panel[panel["date"] >= args.split_date]
    holdout_ic = rank_ic(holdout_panel, "momentum")
    holdout_daily = top_quantile_backtest(holdout_panel, "momentum", cost_bps=args.cost_bps)
    holdout_daily.to_csv(args.output / "selected_holdout_daily.csv", index=False)
    result = {"selection_rule": "highest discovery mean Rank IC", "split_date": args.split_date,
              "selected": {"momentum_window": int(winner["window"]),
                           "momentum_skip": int(winner["skip"])},
              "discovery": {key: (None if pd.isna(value) else float(value))
                            for key, value in winner.items() if key not in ("window", "skip")},
              "holdout": summarize(holdout_daily, holdout_ic)}
    (args.output / "selection.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def report_volume(args: argparse.Namespace) -> None:
    """Recreate one published formula, tune after publication, then test later data."""
    if args.split_date <= "2026-03-10":
        raise ValueError("Split date must be after the report publication date")
    windows = [int(value) for value in args.windows.split(",")]
    if len(windows) != len(set(windows)) or any(window < 2 for window in windows):
        raise ValueError("Use unique volume windows of at least 2 days")
    raw = pd.read_csv(args.input)
    complete = raw.groupby("symbol")["date"].nunique() == raw["date"].nunique()
    excluded = complete.index[~complete].tolist()
    panel = prepare(raw[raw["symbol"].isin(complete.index[complete])])
    sessions = sorted(panel["date"].unique())
    if len(sessions) < max(windows) + 3:
        raise ValueError("Not enough sessions for the longest volume window")
    common_start = sessions[max(windows) - 1]
    args.output.mkdir(parents=True, exist_ok=True)
    trials = []
    for window in windows:
        factor_data = add_volume_mean_factor(panel, window)
        discovery = factor_data[(factor_data["date"] > "2026-03-10") &
                                (factor_data["date"] >= common_start) &
                                (factor_data["exit_date"] < args.split_date)]
        stats = summarize(top_quantile_backtest(discovery, "low_volume_mean",
                                                cost_bps=args.cost_bps),
                          rank_ic(discovery, "low_volume_mean"))
        trials.append({"window": window, **stats})
    table = pd.DataFrame(trials).sort_values("mean_rank_ic", ascending=False)
    table.to_csv(args.output / "discovery_trials.csv", index=False)
    selected_window = int(table.iloc[0]["window"])
    selected = add_volume_mean_factor(panel, selected_window)
    holdout = selected[selected["date"] >= args.split_date]
    daily = top_quantile_backtest(holdout, "low_volume_mean", cost_bps=args.cost_bps)
    daily.to_csv(args.output / "selected_holdout_daily.csv", index=False)
    result = {
        "report": "Huafu Securities, 2026-03-10, mean daily volume over 20 days",
        "report_url": "https://www.scribd.com/document/1023858597/",
        "publication_date": "2026-03-10", "split_date": args.split_date,
        "common_discovery_start": pd.Timestamp(common_start).strftime("%Y-%m-%d"),
        "input": str(args.input),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "symbols": int(panel["symbol"].nunique()), "bars": int(len(panel)),
        "excluded_incomplete_symbols": excluded,
        "published_window": 20, "tested_windows": windows,
        "cost_bps_per_traded_notional": args.cost_bps,
        "selection_rule": "highest post-publication discovery mean Rank IC",
        "selected_window": selected_window,
        "holdout": summarize(daily, rank_ic(holdout, "low_volume_mean")),
        "interpretation": "Formula-level transfer to a fixed tech sample, not the report's full portfolio",
    }
    published = add_volume_mean_factor(panel, 20)
    published_holdout = published[published["date"] >= args.split_date]
    published_daily = top_quantile_backtest(published_holdout, "low_volume_mean",
                                            cost_bps=args.cost_bps)
    published_daily.to_csv(args.output / "published_20_holdout_daily.csv", index=False)
    result["published_20_holdout"] = summarize(
        published_daily, rank_ic(published_holdout, "low_volume_mean")
    )
    (args.output / "selection.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Small A-share factor research lab")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo-data", help="create synthetic bars for a first run")
    demo.add_argument("--output", type=Path, required=True)
    fetch = commands.add_parser("fetch-gm", help="save GM daily bars; requires GM_TOKEN")
    fetch.add_argument("--symbols", type=Path, required=True)
    fetch.add_argument("--start", required=True)
    fetch.add_argument("--end", required=True)
    fetch.add_argument("--output", type=Path, required=True)
    study = commands.add_parser("analyze", help="evaluate two baseline factors from a CSV")
    study.add_argument("--input", type=Path, required=True)
    study.add_argument("--output", type=Path, required=True)
    study.add_argument("--split-date", required=True)
    study.add_argument("--cost-bps", type=float, default=15.0)
    study.add_argument("--momentum-window", type=int, default=20)
    study.add_argument("--momentum-skip", type=int, default=5)
    study.add_argument("--volatility-window", type=int, default=20)
    tune = commands.add_parser("sweep", help="tune momentum on discovery period only")
    tune.add_argument("--input", type=Path, required=True)
    tune.add_argument("--output", type=Path, required=True)
    tune.add_argument("--split-date", required=True)
    tune.add_argument("--windows", default="20,40,60")
    tune.add_argument("--skips", default="5,10")
    tune.add_argument("--cost-bps", type=float, default=15.0)
    volume = commands.add_parser("report-volume", help="test Huafu's 20-day volume factor")
    volume.add_argument("--input", type=Path, required=True)
    volume.add_argument("--output", type=Path, required=True)
    volume.add_argument("--split-date", default="2026-07-01")
    volume.add_argument("--windows", default="20,10,40")
    volume.add_argument("--cost-bps", type=float, default=15.0)
    args = parser.parse_args()
    {"demo-data": demo_data, "fetch-gm": fetch_gm, "analyze": analyze, "sweep": sweep,
     "report-volume": report_volume}[args.command](args)


if __name__ == "__main__":
    main()
