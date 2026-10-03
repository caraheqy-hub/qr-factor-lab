"""Optimistic monthly cost/fill screen; not an execution backtest."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def run(window=20, cost_bps=15, factor='vol_flip', family='fangzheng_interday'):
    output = ROOT / 'results' / f'{family}_gm'
    signals = pd.read_parquet(ROOT / 'data' / f'{family}_{window}_signals.parquet')
    inst = pd.concat((pd.read_parquet(p) for p in sorted(
        (ROOT / 'data').glob('gm_hs300_*_instruments.parquet'))), ignore_index=True)
    inst['date'] = pd.to_datetime(inst.date)
    fields = ['date', 'symbol', 'upper_limit', 'lower_limit', 'adj_factor', 'is_suspended']
    for side in ('entry', 'exit'):
        rename = {'date': f'{side}_date', 'upper_limit': f'{side}_upper',
                  'lower_limit': f'{side}_lower', 'adj_factor': f'{side}_factor',
                  'is_suspended': f'{side}_suspended'}
        signals = signals.merge(inst[fields].rename(columns=rename),
                                on=[f'{side}_date', 'symbol'], how='left',
                                validate='many_to_one')
        signals[f'{side}_raw_open'] = signals[f'{side}_open'] / signals[f'{side}_factor']

    rows = []
    previous = {}
    for date, day in signals.groupby('date', sort=True):
        ranked = day.dropna(subset=[factor]).sort_values([factor, 'symbol'])
        if len(ranked) < 200:
            continue
        selected = ranked.head(len(ranked) // 5)
        if selected.next_month_return.isna().any():
            rows.append({'date': date, 'usable': False,
                         'missing_selected': int(selected.next_month_return.isna().sum())})
            previous = {}
            continue
        benchmark = ranked.next_month_return.dropna().mean()
        target = dict.fromkeys(selected.symbol, 1 / len(selected))
        turnover = sum(abs(target.get(s, 0) - previous.get(s, 0))
                       for s in target.keys() | previous.keys())
        previous = target
        gross = selected.next_month_return.mean()
        buy_blocked = ((selected.entry_suspended == 1) |
                       (selected.entry_raw_open >= selected.entry_upper - 1e-6)).sum()
        sell_blocked = ((selected.exit_suspended == 1) |
                        (selected.exit_raw_open <= selected.exit_lower + 1e-6)).sum()
        rows.append({'date': date, 'usable': True, 'selected': len(selected),
                     'gross': gross, 'benchmark': benchmark, 'turnover': turnover,
                     'net': gross - cost_bps / 10000 * turnover,
                     'buy_blocked': int(buy_blocked), 'sell_blocked': int(sell_blocked)})
    monthly = pd.DataFrame(rows)
    output.mkdir(exist_ok=True)
    monthly.to_csv(output / f'monthly_cost_screen_{window}.csv', index=False)
    good = monthly[monthly.usable].copy()
    good['year'] = good.date.dt.year
    summary = good.groupby('year').agg(
        months=('net', 'size'), gross_monthly=('gross', 'mean'),
        net_monthly=('net', 'mean'), benchmark_monthly=('benchmark', 'mean'),
        turnover=('turnover', 'mean'), buy_blocked=('buy_blocked', 'sum'),
        sell_blocked=('sell_blocked', 'sum'))
    summary['net_excess_bps_month'] = 10000 * (summary.net_monthly - summary.benchmark_monthly)
    summary['skipped_months'] = monthly[~monthly.usable].groupby(monthly.date.dt.year).size()
    summary['skipped_months'] = summary.skipped_months.fillna(0).astype(int)
    summary.to_csv(output / f'cost_screen_summary_{window}.csv')
    print('window=', window)
    print(summary.to_string())


if __name__ == '__main__':
    for window in (10, 20, 40):
        run(window)
