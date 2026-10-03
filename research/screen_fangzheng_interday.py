"""Monthly screen of Fangzheng's interday volatility-flip reversal subfactor."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'fangzheng_interday_gm'


def load():
    data = ROOT / 'data'
    bars = pd.concat((pd.read_parquet(p) for p in sorted(data.glob('gm_hs300_*_bars.parquet'))),
                     ignore_index=True).drop_duplicates(['date', 'symbol'])
    inst = pd.concat((pd.read_parquet(p) for p in sorted(data.glob('gm_hs300_*_instruments.parquet'))),
                     ignore_index=True)
    members = pd.concat((pd.read_parquet(p) for p in sorted(data.glob('gm_hs300_*_members.parquet'))),
                        ignore_index=True)
    bars['date'] = pd.to_datetime(bars.date)
    inst['date'] = pd.to_datetime(inst.date)
    members['date'] = pd.to_datetime(members.trade_date).dt.normalize()
    bars = bars.merge(inst[['date', 'symbol', 'adj_factor']], on=['date', 'symbol'],
                      validate='one_to_one').sort_values(['symbol', 'date'])
    bars['adj_close'] = bars.close * bars.adj_factor
    bars['adj_open'] = bars.open * bars.adj_factor
    return bars, members


def run():
    bars, members = load()
    calendar = sorted(members.date.unique())
    pos = {date: i for i, date in enumerate(calendar)}
    bars['day_number'] = bars.date.map(pos)
    group = bars.groupby('symbol', sort=False)
    bars['daily_return'] = (bars.adj_close / group.adj_close.shift() - 1).where(
        bars.day_number - group.day_number.shift() == 1)
    signal_dates = members.groupby(members.date.dt.to_period('M')).date.max().tolist()
    chosen = members[members.date.isin(signal_dates)][['date', 'symbol']]
    prices = bars[['date', 'symbol', 'adj_open']]
    rows = []
    for window in (10, 20, 40):
        mean = group.daily_return.transform(lambda x: x.rolling(window, min_periods=window).mean())
        vol = group.daily_return.transform(lambda x: x.rolling(window, min_periods=window).std())
        valid = bars.day_number - group.day_number.shift(window) == window
        frame = bars[['date', 'symbol']].copy()
        frame['mean'] = mean.where(valid)
        frame['vol'] = vol.where(valid)
        frame = chosen.merge(frame, on=['date', 'symbol'], validate='one_to_one')
        frame['cross_mean_vol'] = frame.groupby('date').vol.transform('mean')
        frame['vol_flip'] = frame['mean'].where(frame.vol >= frame.cross_mean_vol, -frame['mean'])
        frame['baseline'] = frame['mean']
        frame['entry_date'] = frame.date.map({d: calendar[pos[d] + 1] for d in signal_dates
                                               if pos[d] + 1 < len(calendar)})
        frame['exit_date'] = frame.date.map({d: calendar[pos[signal_dates[i + 1]] + 1]
                                              for i, d in enumerate(signal_dates[:-1])
                                              if pos[signal_dates[i + 1]] + 1 < len(calendar)})
        for side in ('entry', 'exit'):
            frame = frame.merge(prices.rename(columns={'date': f'{side}_date',
                                                       'adj_open': f'{side}_open'}),
                                on=[f'{side}_date', 'symbol'], how='left',
                                validate='many_to_one')
        frame['next_month_return'] = frame.exit_open / frame.entry_open - 1
        frame.to_parquet(ROOT / 'data' / f'fangzheng_interday_{window}_signals.parquet', index=False)
        for factor in ('baseline', 'vol_flip'):
            for date, day in frame.groupby('date', sort=True):
                clean = day[[factor, 'next_month_return']].dropna()
                if len(clean) < 100 or clean[factor].nunique() < 10:
                    continue
                rows.append({'date': date, 'window': window, 'factor': factor,
                             'names': len(clean), 'rank_ic': clean[factor].corr(
                                 clean.next_month_return, method='spearman')})
    daily = pd.DataFrame(rows)
    daily['period'] = pd.cut(daily.date.dt.year, [2019, 2023, 2025, 2026],
                             labels=['discovery_2020_23', 'review_2024_25', 'seen_2026'])
    summary = pd.concat([daily, daily.assign(period='all')]).groupby(
        ['window', 'factor', 'period'], observed=True).agg(
        months=('rank_ic', 'size'), mean_ic=('rank_ic', 'mean'),
        negative_fraction=('rank_ic', lambda x: (x < 0).mean()),
        mean_names=('names', 'mean')).reset_index()
    OUT.mkdir(exist_ok=True)
    daily.to_csv(OUT / 'monthly_ic.csv', index=False)
    summary.to_csv(OUT / 'summary.csv', index=False)
    (OUT / 'manifest.json').write_text(json.dumps({
        'source': 'Fangzheng Securities, 2022-06-11, section 2.4',
        'formula': 'flip 20-day mean close-to-close return if its 20-day volatility is below cross-sectional mean',
        'windows': [10, 20, 40], 'original_window': 20,
        'universe_change': 'HS300 instead of all A shares',
        'neutralization': 'none; report uses size and industry neutralization',
        'signal': 'month-end after close', 'entry': 'next trading day open',
        'exit': 'open after next month-end',
        'returns': 'raw open times same-day GM adj_factor',
        'scope': 'exploratory IC; missing entry/exit excluded; no fill or cost claim',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    run()
