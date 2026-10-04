"""Locate Alpha5's IC-to-long-only return gap without parameter selection."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'gtja_alpha5_gm'


def run():
    data = pd.read_parquet(ROOT / 'data' / 'gtja_alpha5_5_5_3_signals.parquet')
    data = data[data.day_number.mod(5).eq(0)]
    rows = []
    for date, day in data.groupby('date', sort=True):
        ranked = day.dropna(subset=['factor']).sort_values(
            ['factor', 'symbol'], ascending=[False, True]).reset_index(drop=True)
        if len(ranked) < 200:
            continue
        n = len(ranked)
        if ranked.iloc[:n // 5].return_5.isna().any():
            continue
        benchmark = ranked.return_5.dropna().mean()
        for quintile in range(5):
            group = ranked.iloc[quintile * n // 5:(quintile + 1) * n // 5]
            rows.append({'date': date, 'quintile': quintile + 1,
                         'names': len(group), 'valid_returns': group.return_5.notna().sum(),
                         'gross_excess_bps': 10000 * (group.return_5.mean() - benchmark)})
    periods = pd.DataFrame(rows)
    periods['year'] = pd.to_datetime(periods.date).dt.year
    summary = periods.groupby(['year', 'quintile']).agg(
        periods=('date', 'size'), mean_names=('names', 'mean'),
        valid_fraction=('valid_returns', lambda s: s.sum() / periods.loc[s.index, 'names'].sum()),
        gross_excess_bps=('gross_excess_bps', 'mean')).reset_index()
    costs = pd.read_csv(OUT / 'cost_summary.csv')
    costs = costs[costs.window.eq('5_5_3') & costs.holding_days.eq(5)].copy()
    costs['gross_excess_bps'] = 10000 * (costs.gross - costs.benchmark)
    costs['breakeven_cost_bps'] = costs.gross_excess_bps / costs.turnover
    costs[['year', 'periods', 'gross_excess_bps', 'turnover',
           'breakeven_cost_bps', 'net_excess_bps']].to_csv(
        OUT / 'cost_threshold_5_5_3.csv', index=False)
    periods.to_csv(OUT / 'quintile_periods.csv', index=False)
    summary.to_csv(OUT / 'quintile_summary.csv', index=False)
    print(summary.pivot(index='year', columns='quintile',
                        values='gross_excess_bps').round(1).to_string())
    print(costs[['year', 'breakeven_cost_bps']].round(1).to_string(index=False))


if __name__ == '__main__':
    run()
