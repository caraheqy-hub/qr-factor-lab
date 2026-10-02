"""Daily cross-sectional factor checks using next-session execution."""

from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED = {"date", "symbol", "open", "close", "volume"}


def prepare(
    raw: pd.DataFrame, *, momentum_window: int = 20, momentum_skip: int = 5,
    volatility_window: int = 20,
) -> pd.DataFrame:
    if momentum_window <= momentum_skip or momentum_skip < 1 or volatility_window < 2:
        raise ValueError("Require momentum_window > momentum_skip >= 1 and volatility_window >= 2")
    missing = REQUIRED - set(raw.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    data = raw.copy()
    data["date"] = pd.to_datetime(data["date"]).dt.normalize()
    if data.duplicated(["date", "symbol"]).any():
        raise ValueError("Duplicate date/symbol rows")
    if (data[["open", "close"]] <= 0).any().any() or (data["volume"] < 0).any():
        raise ValueError("Prices must be positive and volume must be nonnegative")
    data = data.sort_values(["symbol", "date"]).reset_index(drop=True)
    grouped = data.groupby("symbol", sort=False)
    # Signal is known after close t. Trade at open t+1, exit at open t+2.
    data["entry_date"] = grouped["date"].shift(-1)
    data["exit_date"] = grouped["date"].shift(-2)
    data["next_open_return"] = grouped["open"].shift(-2) / grouped["open"].shift(-1) - 1
    sessions = sorted(data["date"].unique())
    expected_entry = dict(zip(sessions, sessions[1:]))
    expected_exit = dict(zip(sessions, sessions[2:]))
    misaligned = (data["entry_date"] != data["date"].map(expected_entry)) | (
        data["exit_date"] != data["date"].map(expected_exit)
    )
    data.loc[misaligned, "next_open_return"] = np.nan
    data["momentum"] = (
        grouped["close"].shift(momentum_skip) / grouped["close"].shift(momentum_window) - 1
    )
    daily_return = grouped["close"].pct_change(fill_method=None)
    data["low_vol"] = -daily_return.groupby(data["symbol"]).transform(
        lambda s: s.rolling(volatility_window, min_periods=volatility_window).std()
    )
    # Current-day volume is known by close and prevents ranking a halted name.
    data.loc[data["volume"] == 0, ["momentum", "low_vol"]] = np.nan
    return data


def rank_ic(data: pd.DataFrame, factor: str, min_names: int = 10) -> pd.Series:
    def one_day(group: pd.DataFrame) -> float:
        valid = group[[factor, "next_open_return"]].dropna()
        if len(valid) < min_names or valid[factor].nunique() < 2:
            return np.nan
        return float(valid[factor].corr(valid["next_open_return"], method="spearman"))

    return pd.Series(
        {date: one_day(day) for date, day in data.groupby("date", sort=True)},
        name="rank_ic", dtype=float,
    )


def add_volume_mean_factor(data: pd.DataFrame, window: int) -> pd.DataFrame:
    """Report factor: low 20-day mean volume ranks high for long-only testing."""
    if window < 2:
        raise ValueError("Volume window must be at least 2")
    result = data.copy()
    result["low_volume_mean"] = -result.groupby("symbol")["volume"].transform(
        lambda values: values.rolling(window, min_periods=window).mean()
    )
    result.loc[result["volume"] == 0, "low_volume_mean"] = np.nan
    return result


def top_quantile_backtest(
    data: pd.DataFrame, factor: str, *, top_fraction: float = 0.2, cost_bps: float = 15.0
) -> pd.DataFrame:
    """Long-only equal weights, daily rebalance at next open; cost per traded notional."""
    if not 0 < top_fraction <= 1 or cost_bps < 0:
        raise ValueError("Invalid top_fraction or cost_bps")
    rows = []
    previous_weights: dict[str, float] = {}
    terminal_dates = {pd.Timestamp(value) for value in sorted(data["date"].unique())[-2:]}
    for date, day in data.groupby("date", sort=True):
        candidates = day.dropna(subset=[factor])
        if len(candidates) < 10:
            continue
        if candidates["next_open_return"].isna().any():
            if date in terminal_dates:
                continue
            raise ValueError(f"Missing next-session execution prices on {date}")
        n = max(1, int(len(candidates) * top_fraction))
        selected = candidates.nlargest(n, factor)
        if selected["entry_date"].nunique() != 1 or selected["exit_date"].nunique() != 1:
            raise ValueError(f"Execution dates differ across selected symbols on {date}")
        weights = dict.fromkeys(selected["symbol"], 1.0 / n)
        turnover = sum(
            abs(weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
            for symbol in weights.keys() | previous_weights.keys()
        )
        gross = float(selected["next_open_return"].mean())
        baseline = float(day["next_open_return"].mean())
        rows.append(
            {"date": date, "entry_date": selected["entry_date"].iloc[0],
             "exit_date": selected["exit_date"].iloc[0],
             "gross_return": gross, "net_return": gross - turnover * cost_bps / 10000,
             "baseline_return": baseline, "turnover": turnover, "holdings": ",".join(sorted(weights))}
        )
        # Positions drift during the holding day; rebalance from those weights.
        previous_weights = {
            symbol: weight * (1 + ret) / (1 + gross)
            for symbol, weight, ret in zip(selected["symbol"], weights.values(),
                                           selected["next_open_return"])
        }
    return pd.DataFrame(rows)


def summarize(daily: pd.DataFrame, ic: pd.Series) -> dict:
    if daily.empty:
        raise ValueError("No valid backtest days; check date range and data coverage")
    values = daily["net_return"]
    equity = (1 + values).cumprod()
    drawdown = equity.to_numpy() / np.maximum.accumulate(
        np.r_[1.0, equity.to_numpy()]
    )[1:] - 1
    valid_ic = ic.dropna()
    return {
        "days": int(len(daily)),
        "mean_rank_ic": float(valid_ic.mean()) if len(valid_ic) else None,
        "ic_positive_fraction": float((valid_ic > 0).mean()) if len(valid_ic) else None,
        "annual_return": float(equity.iloc[-1] ** (252 / len(equity)) - 1),
        "annual_volatility": float(values.std(ddof=1) * np.sqrt(252)),
        "sharpe": float(values.mean() / values.std(ddof=1) * np.sqrt(252))
        if len(values) > 1 and values.std(ddof=1) > 0 else None,
        "max_drawdown": float(drawdown.min()),
        "mean_daily_turnover": float(daily["turnover"].mean()),
        "baseline_total_return": float((1 + daily["baseline_return"]).prod() - 1),
    }
