"""Point-in-time annual asset-growth screen on historical HS300 members."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'asset_growth_gm'


def main():
    files = sorted((ROOT / 'data').glob('gm_hs300_*_financial_annual_balance.parquet'))
    if len(files) != 81:
        raise RuntimeError(f'Expected 81 annual balance snapshots, got {len(files)}')
    balance = pd.concat((pd.read_parquet(p) for p in files), ignore_index=True)
    for column in ('signal_date', 'query_date', 'pub_date', 'rpt_date'):
        balance[column] = pd.to_datetime(balance[column]).dt.normalize()
    if ((balance.pub_date > balance.query_date).any() or
            not balance.rpt_type.eq(12).all() or
            not balance.data_type.eq(101).all()):
        raise RuntimeError('Annual PIT balance integrity failure')
    balance = balance.sort_values(['symbol', 'rpt_date', 'query_date'])
    earliest = balance.drop_duplicates(['symbol', 'rpt_date'])[
        ['symbol', 'rpt_date', 'ttl_ast', 'query_date']].rename(columns={
            'rpt_date': 'prior_rpt_date', 'ttl_ast': 'prior_assets',
            'query_date': 'prior_first_observed'})
    balance['prior_rpt_date'] = balance.rpt_date - pd.DateOffset(years=1)
    balance = balance.merge(earliest, on=['symbol', 'prior_rpt_date'],
                            how='left', validate='many_to_one')
    valid = ((balance.ttl_ast > 0) & (balance.prior_assets > 0) &
             (balance.prior_first_observed <= balance.query_date) &
             (balance.signal_date - balance.rpt_date).dt.days.between(0, 548))
    balance['low_asset_growth'] = -(balance.ttl_ast / balance.prior_assets - 1).where(valid)

    labels = pd.read_parquet(ROOT / 'data' / 'fangzheng_cashflow_assets_annual_signals.parquet')
    labels['date'] = pd.to_datetime(labels.date).dt.normalize()
    screen = labels[['date', 'symbol', 'next_month_return', 'log_cap']].merge(
        balance[['signal_date', 'symbol', 'low_asset_growth']].rename(
            columns={'signal_date': 'date'}), on=['date', 'symbol'],
        how='left', validate='one_to_one')
    screen['low_asset_growth'] = screen.low_asset_growth.replace([np.inf, -np.inf], np.nan)
    rows = []
    for date, month in screen.groupby('date', sort=True):
        clean = month.dropna(subset=['low_asset_growth', 'next_month_return'])
        if len(clean) < 100:
            continue
        rows.append({'date': date, 'members': len(month), 'names': len(clean),
                     'rank_ic': clean.low_asset_growth.corr(clean.next_month_return,
                                                            method='spearman'),
                     'size_rank_corr': clean.low_asset_growth.corr(clean.log_cap,
                                                                   method='spearman')})
    monthly = pd.DataFrame(rows)
    monthly['period'] = pd.cut(monthly.date.dt.year, [2019, 2023, 2025, 2026],
                               labels=['discovery_2020_23', 'review_2024_25', 'seen_2026'])
    summary = monthly.groupby('period', observed=True).agg(
        months=('rank_ic', 'size'), mean_ic=('rank_ic', 'mean'),
        positive_fraction=('rank_ic', lambda s: (s > 0).mean()),
        mean_names=('names', 'mean'), min_names=('names', 'min'),
        mean_size_rank_corr=('size_rank_corr', 'mean')).reset_index()
    yearly = monthly.groupby(monthly.date.dt.year).agg(
        months=('rank_ic', 'size'), mean_ic=('rank_ic', 'mean'),
        positive_fraction=('rank_ic', lambda s: (s > 0).mean()),
        mean_names=('names', 'mean')).reset_index(names='year')
    OUT.mkdir(exist_ok=True)
    monthly.to_csv(OUT / 'monthly.csv', index=False)
    summary.to_csv(OUT / 'summary.csv', index=False)
    yearly.to_csv(OUT / 'yearly.csv', index=False)
    (OUT / 'manifest.json').write_text(json.dumps({
        'source': 'Cooper, Gulen, Schill (2008), asset growth effect',
        'formula': '-(current annual total assets / prior annual total assets - 1)',
        'current': 'GM original consolidated annual PIT snapshot as of previous trading day',
        'prior': 'first observed historical snapshot of immediately prior annual report',
        'universe': 'historical HS300 members',
        'label': 'next month first open to following month first open',
        'scope': 'exploratory rank IC; no trading claim',
    }, indent=2), encoding='utf-8')
    print(summary.to_string(index=False))
    print(yearly.to_string(index=False))


if __name__ == '__main__':
    main()
