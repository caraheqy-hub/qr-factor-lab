"""Optimistic long-only cost screen for GTJA Alpha1 window/holding grids."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'gtja_alpha1_gm'


def trial(window, horizon, cost_bps=15):
    data = pd.read_parquet(ROOT / 'data' / f'gtja_alpha1_{window}_signals.parquet')
    data = data[data.day_number.mod(horizon).eq(0)]
    label = f'return_{horizon}'
    previous = {}
    rows = []
    for date, day in data.groupby('date', sort=True):
        ranked = day.dropna(subset=['factor']).sort_values(['factor', 'symbol'], ascending=[False, True])
        if len(ranked) < 200:
            continue
        selected = ranked.head(len(ranked) // 5)
        missing = int(selected[label].isna().sum())
        if missing:
            rows.append({'date': date, 'usable': False, 'missing_selected': missing})
            previous = {}
            continue
        benchmark = ranked[label].dropna().mean()
        target = dict.fromkeys(selected.symbol, 1 / len(selected))
        turnover = sum(abs(target.get(s, 0) - previous.get(s, 0))
                       for s in target.keys() | previous.keys())
        previous = target
        gross = selected[label].mean()
        rows.append({'date': date, 'usable': True, 'gross': gross,
                     'benchmark': benchmark, 'turnover': turnover,
                     'net': gross - cost_bps / 10000 * turnover})
    daily = pd.DataFrame(rows)
    good = daily[daily.usable].copy()
    good['year'] = good.date.dt.year
    summary = good.groupby('year').agg(
        periods=('net', 'size'), gross=('gross', 'mean'),
        benchmark=('benchmark', 'mean'), net=('net', 'mean'),
        turnover=('turnover', 'mean'))
    summary['net_excess_bps'] = 10000 * (summary.net - summary.benchmark)
    summary['skipped_periods'] = daily[~daily.usable].groupby(daily.date.dt.year).size()
    summary['skipped_periods'] = summary.skipped_periods.fillna(0).astype(int)
    summary['window'] = window
    summary['holding_days'] = horizon
    return daily.assign(window=window, holding_days=horizon), summary.reset_index()


if __name__ == '__main__':
    trials = [trial(window, horizon) for window in (4, 6, 10) for horizon in (1, 5)]
    OUT.mkdir(exist_ok=True)
    pd.concat((x[0] for x in trials)).to_csv(OUT / 'cost_daily.csv', index=False)
    summary = pd.concat((x[1] for x in trials), ignore_index=True)
    summary.to_csv(OUT / 'cost_summary.csv', index=False)
    print(summary[summary.window.eq(6)].to_string(index=False))
