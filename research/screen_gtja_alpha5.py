"""Screen the reported GTJA Alpha5 and two preregistered window variants."""

import json
from pathlib import Path

import pandas as pd

from screen_wq101_gm import panel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'gtja_alpha5_gm'
GRID = ((3, 3, 3), (5, 5, 3), (10, 10, 5))


def run():
    bars = panel().sort_values(['symbol', 'date']).reset_index(drop=True)
    group = bars.groupby('symbol', sort=False)
    rows = []
    for rank_days, corr_days, max_days in GRID:
        volume_rank = group.volume.transform(
            lambda s: s.rolling(rank_days, min_periods=rank_days).rank(pct=True))
        high_rank = group.high.transform(
            lambda s: s.rolling(rank_days, min_periods=rank_days).rank(pct=True))
        bars['volume_rank'] = volume_rank
        bars['high_rank'] = high_rank
        corr = bars.groupby('symbol', sort=False).apply(
            lambda x: x.volume_rank.rolling(corr_days, min_periods=corr_days).corr(
                x.high_rank), include_groups=False).reset_index(level=0, drop=True)
        bars['corr'] = corr
        factor = -bars.groupby('symbol', sort=False)['corr'].transform(
            lambda s: s.rolling(max_days, min_periods=max_days).max())
        span = rank_days + corr_days + max_days - 2
        contiguous = bars.day_number - group.day_number.shift(span - 1) == span - 1
        bars['factor'] = factor.where(contiguous)
        bars[['date', 'symbol', 'day_number', 'factor', 'return_1', 'return_5']].to_parquet(
            ROOT / 'data' / f'gtja_alpha5_{rank_days}_{corr_days}_{max_days}_signals.parquet',
            index=False)
        for horizon in (1, 5):
            for date, day in bars.groupby('date', sort=True):
                clean = day[['factor', f'return_{horizon}']].dropna()
                if len(clean) < 100 or clean.factor.nunique() < 10:
                    continue
                rows.append({'date': date, 'rank_days': rank_days,
                             'corr_days': corr_days, 'max_days': max_days,
                             'horizon': horizon, 'names': len(clean),
                             'rank_ic': clean.factor.corr(clean[f'return_{horizon}'],
                                                          method='spearman')})
    daily = pd.DataFrame(rows)
    daily['period'] = pd.cut(daily.date.dt.year, [2019, 2023, 2025, 2026],
                             labels=['discovery_2020_23', 'review_2024_25', 'seen_2026'])
    summary = pd.concat([daily, daily.assign(period='all')]).groupby(
        ['rank_days', 'corr_days', 'max_days', 'horizon', 'period'],
        observed=True).agg(days=('rank_ic', 'size'), mean_ic=('rank_ic', 'mean'),
                           positive_fraction=('rank_ic', lambda s: (s > 0).mean()),
                           mean_names=('names', 'mean')).reset_index()
    OUT.mkdir(exist_ok=True)
    daily.to_csv(OUT / 'daily_ic.csv', index=False)
    summary.to_csv(OUT / 'summary.csv', index=False)
    (OUT / 'manifest.json').write_text(json.dumps({
        'source': 'GTJA 2017-06-15, table 6, PDF page 11, Alpha5',
        'formula': '-TSMAX(CORR(TSRANK(VOLUME,5),TSRANK(HIGH,5),5),3)',
        'grid': GRID, 'original': (5, 5, 3),
        'tsrank': 'rolling percentile rank including signal date',
        'signal': 'after close t', 'entry': 'open t+1',
        'label': 'adjusted open t+1 to t+2 or t+6',
        'scope': 'exploratory IC; no cost or execution claim',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    run()
