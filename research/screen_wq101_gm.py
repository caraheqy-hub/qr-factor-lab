"""Exploratory WorldQuant Alpha 101 screen on daily historical GM members."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'wq101_gm'


def panel():
    files = sorted((ROOT / 'data').glob('gm_hs300_*_bars.parquet'))
    bars = pd.concat((pd.read_parquet(path) for path in files), ignore_index=True)
    members = pd.concat((pd.read_parquet(path) for path in
                         sorted((ROOT / 'data').glob('gm_hs300_*_members.parquet'))),
                        ignore_index=True)
    instruments = pd.concat((pd.read_parquet(path) for path in
                             sorted((ROOT / 'data').glob('gm_hs300_*_instruments.parquet'))),
                            ignore_index=True)
    bars['date'] = pd.to_datetime(bars['date'])
    members['date'] = pd.to_datetime(members['trade_date']).dt.normalize()
    instruments['date'] = pd.to_datetime(instruments['date'])
    bars = bars.drop_duplicates(['date', 'symbol']).sort_values(['symbol', 'date'])
    bars = bars.merge(instruments[['date', 'symbol', 'adj_factor']],
                      on=['date', 'symbol'], how='left', validate='one_to_one')
    if bars.adj_factor.isna().any():
        raise RuntimeError('Some bars lack same-day adjustment factors')
    bars['adjusted_open'] = bars.open * bars.adj_factor
    calendar = sorted(members.date.unique())
    bars['day_number'] = bars.date.map({date: i for i, date in enumerate(calendar)})
    group = bars.groupby('symbol', sort=False)
    bars['original'] = (bars.close - bars.open) / (bars.high - bars.low + 0.001)
    bars.loc[(bars.high < bars.low) | (bars.open <= 0), 'original'] = np.nan
    for window in (1, 5, 10):
        value = group['original'].transform(
            lambda x: x.rolling(window, min_periods=window).mean())
        if window > 1:
            contiguous = bars.day_number - group.day_number.shift(window - 1) == window - 1
            value = value.where(contiguous)
        bars[f'alpha_{window}'] = value
    for horizon in (1, 5):
        entry = group.adjusted_open.shift(-1)
        exit_price = group.adjusted_open.shift(-(horizon + 1))
        valid = (group.day_number.shift(-1) == bars.day_number + 1) & (
            group.day_number.shift(-(horizon + 1)) == bars.day_number + horizon + 1)
        bars[f'return_{horizon}'] = (exit_price / entry - 1).where(valid)
    bars = bars.merge(members[['date', 'symbol']], on=['date', 'symbol'], how='inner',
                      validate='one_to_one')
    return bars.replace([np.inf, -np.inf], np.nan)


def screen(bars):
    rows = []
    for window in (1, 5, 10):
        for horizon in (1, 5):
            for date, day in bars.groupby('date', sort=True):
                clean = day[[f'alpha_{window}', f'return_{horizon}']].dropna()
                if len(clean) < 100 or clean.iloc[:, 0].nunique() < 10:
                    continue
                rows.append({'date': date, 'window': window, 'horizon': horizon,
                             'names': len(clean), 'coverage': len(clean) / len(day),
                             'rank_ic': clean.iloc[:, 0].corr(clean.iloc[:, 1], method='spearman')})
    daily = pd.DataFrame(rows)
    daily['period'] = pd.cut(daily.date.dt.year, [2019, 2023, 2025, 2026],
                             labels=['discovery_2020_23', 'review_2024_25', 'seen_2026'])
    summary = pd.concat([daily, daily.assign(period='all')]).groupby(
        ['window', 'horizon', 'period'], observed=True).agg(
        days=('rank_ic', 'size'), mean_ic=('rank_ic', 'mean'),
        positive_fraction=('rank_ic', lambda x: (x > 0).mean()),
        coverage=('coverage', 'mean'), min_names=('names', 'min')).reset_index()
    return daily, summary


if __name__ == '__main__':
    data = panel()
    daily, summary = screen(data)
    OUT.mkdir(exist_ok=True)
    daily.to_csv(OUT / 'daily_ic.csv', index=False)
    summary.to_csv(OUT / 'summary.csv', index=False)
    (OUT / 'manifest.json').write_text(json.dumps({
        'source': 'WorldQuant 101 Formulaic Alphas, alpha 101',
        'formula': '(close-open)/(high-low+0.001)',
        'windows': [1, 5, 10], 'windows_other_than_1': 'adaptations',
        'horizons': [1, 5], 'signal': 'after close t',
        'return': 'open t+1 to open t+2 or t+6',
        'prices': 'GM raw OHLC for signal; entry/exit open multiplied by same-day adj_factor',
        'scope': 'exploratory IC only; no cost or execution claim',
        'bar_rows': len(data), 'first_date': str(data.date.min().date()),
        'last_date': str(data.date.max().date()),
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(summary.to_string(index=False))
