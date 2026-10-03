"""Screen GTJA Alpha1 (report table 6, PDF page 11) and window variants."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from screen_wq101_gm import panel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'gtja_alpha1_gm'


def run():
    bars = panel().sort_values(['symbol', 'date']).reset_index(drop=True)
    group = bars.groupby('symbol', sort=False)
    bars['volume_delta'] = np.log(bars.volume.where(bars.volume > 0)) - np.log(
        group.volume.shift().where(group.volume.shift() > 0))
    bars['volume_delta'] = bars.volume_delta.where(
        bars.day_number - group.day_number.shift() == 1)
    bars['intraday_return'] = (bars.close - bars.open) / bars.open
    bars['rank_volume_delta'] = bars.groupby('date').volume_delta.rank(pct=True)
    bars['rank_intraday'] = bars.groupby('date').intraday_return.rank(pct=True)
    rows = []
    for window in (4, 6, 10):
        corr = bars.groupby('symbol', sort=False).apply(
            lambda x: x.rank_volume_delta.rolling(window, min_periods=window).corr(
                x.rank_intraday), include_groups=False).reset_index(level=0, drop=True)
        contiguous = bars.day_number - group.day_number.shift(window - 1) == window - 1
        bars['factor'] = -corr.where(contiguous)
        bars[['date', 'symbol', 'day_number', 'factor', 'return_1', 'return_5']].to_parquet(
            ROOT / 'data' / f'gtja_alpha1_{window}_signals.parquet', index=False)
        for horizon in (1, 5):
            for date, day in bars.groupby('date', sort=True):
                clean = day[['factor', f'return_{horizon}']].dropna()
                if len(clean) < 100 or clean.factor.nunique() < 10:
                    continue
                rows.append({'date': date, 'window': window, 'horizon': horizon,
                             'names': len(clean), 'rank_ic': clean.factor.corr(
                                 clean[f'return_{horizon}'], method='spearman')})
    daily = pd.DataFrame(rows)
    daily['period'] = pd.cut(daily.date.dt.year, [2019, 2023, 2025, 2026],
                             labels=['discovery_2020_23', 'review_2024_25', 'seen_2026'])
    summary = pd.concat([daily, daily.assign(period='all')]).groupby(
        ['window', 'horizon', 'period'], observed=True).agg(
        days=('rank_ic', 'size'), mean_ic=('rank_ic', 'mean'),
        positive_fraction=('rank_ic', lambda s: (s > 0).mean()),
        mean_names=('names', 'mean')).reset_index()
    OUT.mkdir(exist_ok=True)
    daily.to_csv(OUT / 'daily_ic.csv', index=False)
    summary.to_csv(OUT / 'summary.csv', index=False)
    (OUT / 'manifest.json').write_text(json.dumps({
        'source': 'GTJA 2017-06-15, table 6, PDF page 11, Alpha1',
        'formula': '-CORR(RANK(DELTA(LOG(VOLUME),1)),RANK((CLOSE-OPEN)/OPEN),6)',
        'windows': [4, 6, 10], 'original_window': 6,
        'rank': 'daily HS300 cross-sectional percentile',
        'signal': 'after close t', 'entry': 'open t+1',
        'label': 'adjusted open t+1 to t+2 or t+6',
        'scope': 'exploratory IC only; no execution or cost claim',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    run()
