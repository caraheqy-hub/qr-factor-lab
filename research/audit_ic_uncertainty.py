"""Descriptive HAC intervals for already-seen monthly IC series."""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'method_audit'


def hac_mean(series: pd.Series, lags: int = 3) -> tuple[float, float, float]:
    values = series.dropna().to_numpy(dtype=float)
    n = len(values)
    if n <= lags + 1:
        raise ValueError('Too few months for the chosen HAC lag')
    centered = values - values.mean()
    long_run = np.dot(centered, centered) / n
    for lag in range(1, lags + 1):
        covariance = np.dot(centered[lag:], centered[:-lag]) / n
        long_run += 2 * (1 - lag / (lags + 1)) * covariance
    se = np.sqrt(max(long_run, 0) / n)
    return float(values.mean()), float(values.mean() - 1.96 * se), float(values.mean() + 1.96 * se)


def main():
    specs = [
        ('low_asset_growth', ROOT / 'results' / 'asset_growth_gm' / 'monthly.csv', None),
        ('team_coin_20', ROOT / 'results' / 'fangzheng_team_coin_gm' / 'monthly_ic.csv',
         {'window': 20, 'factor': 'team_coin'}),
        ('cashflow_assets', ROOT / 'results' / 'fangzheng_cashflow_assets_gm' / 'monthly_ic.csv',
         {'factor': 'cashflow_assets'}),
    ]
    rows = []
    for factor, path, filters in specs:
        frame = pd.read_csv(path, parse_dates=['date'])
        for column, value in (filters or {}).items():
            frame = frame[frame[column].eq(value)]
        for name, years in (('discovery_2020_23', (2020, 2023)),
                            ('review_2024_25', (2024, 2025)),
                            ('seen_2026', (2026, 2026))):
            selected = frame[frame.date.dt.year.between(*years)].sort_values('date')
            if len(selected) < 6:
                continue
            mean, lower, upper = hac_mean(selected.rank_ic)
            rows.append({'factor': factor, 'period': name, 'months': len(selected),
                         'mean_ic': mean, 'hac_lag': 3,
                         'normal_95_lower': lower, 'normal_95_upper': upper,
                         'positive_month_fraction': float((selected.rank_ic > 0).mean()),
                         'scope': 'post-hoc descriptive; no multiple-test correction'})
    OUT.mkdir(exist_ok=True)
    result = pd.DataFrame(rows)
    result.to_csv(OUT / 'ic_uncertainty.csv', index=False)
    print(result.to_string(index=False))


if __name__ == '__main__':
    main()
