"""Formula-level HS300 transfer of Fangzheng's 2022 team/coin factor."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUT = ROOT / 'results' / 'fangzheng_team_coin_gm'
LEGS = ('interday', 'intraday', 'overnight')


def load():
    def months(suffix):
        return pd.concat((pd.read_parquet(p) for p in sorted(DATA.glob(
            f'gm_hs300_*_{suffix}.parquet'))), ignore_index=True)

    if len(list(DATA.glob('gm_hs300_*_turnover.parquet'))) != len(list(DATA.glob('gm_hs300_*_members.parquet'))):
        raise RuntimeError('Turnover download is incomplete')

    bars = months('bars').drop_duplicates(['date', 'symbol'])
    members = months('members')
    inst = months('instruments')
    turnover = months('turnover')
    bars['date'] = pd.to_datetime(bars.date)
    members['date'] = pd.to_datetime(members.trade_date).dt.normalize()
    inst['date'] = pd.to_datetime(inst.date)
    turnover['date'] = pd.to_datetime(turnover.date)
    bars = bars.merge(inst[['date', 'symbol', 'adj_factor']], on=['date', 'symbol'],
                      validate='one_to_one')
    bars = bars.merge(turnover[['date', 'symbol', 'turnrate']], on=['date', 'symbol'],
                      how='left', validate='one_to_one')
    bars = bars.merge(members[['date', 'symbol']].assign(member=True),
                      on=['date', 'symbol'], how='left', validate='one_to_one')
    bars = bars.sort_values(['symbol', 'date']).reset_index(drop=True)
    calendar = sorted(members.date.unique())
    bars['day_number'] = bars.date.map({d: i for i, d in enumerate(calendar)})
    group = bars.groupby('symbol', sort=False)
    contiguous = bars.day_number - group.day_number.shift() == 1
    bars['adj_open'] = bars.open * bars.adj_factor
    bars['adj_close'] = bars.close * bars.adj_factor
    bars['interday'] = (bars.adj_close / group.adj_close.shift() - 1).where(contiguous)
    bars['intraday'] = bars.close / bars.open - 1
    overnight_return = (bars.adj_open / group.adj_close.shift() - 1).where(contiguous)
    mean_overnight = overnight_return.where(bars.member == True).groupby(bars.date).transform('mean')
    bars['overnight'] = (overnight_return - mean_overnight).abs()
    bars['turn_change'] = (bars.turnrate - group.turnrate.shift()).where(contiguous)
    mean_turn = bars.turn_change.where(bars.member == True).groupby(bars.date).transform('mean')
    bars['turn_distance'] = (bars.turn_change - mean_turn).abs()
    bars['prior_turn_distance'] = group.turn_distance.shift().where(contiguous)
    mean_prior_distance = bars.prior_turn_distance.where(bars.member == True).groupby(bars.date).transform('mean')
    bars['turn_low'] = bars.turn_change < mean_turn
    bars['prior_turn_low'] = bars.prior_turn_distance < mean_prior_distance
    return bars, members, calendar


def zscore_by_date(frame, column):
    grouped = frame.groupby('date')[column]
    return (frame[column] - grouped.transform('mean')) / grouped.transform('std').replace(0, np.nan)


def run():
    bars, members, calendar = load()
    pos = {d: i for i, d in enumerate(calendar)}
    signal_dates = members.groupby(members.date.dt.to_period('M')).date.max().tolist()
    signals = members[members.date.isin(signal_dates)][['date', 'symbol']]
    prices = bars[['date', 'symbol', 'adj_open']]
    trials = []
    for window in (10, 20, 40):
        group = bars.groupby('symbol', sort=False)
        frame = bars[['date', 'symbol']].copy()
        contiguous = bars.day_number - group.day_number.shift(window) == window
        for leg in LEGS:
            base = bars[leg]
            mean = base.groupby(bars.symbol).transform(
                lambda s: s.rolling(window, min_periods=window).mean()).where(contiguous)
            vol = base.groupby(bars.symbol).transform(
                lambda s: s.rolling(window, min_periods=window).std()).where(contiguous)
            frame[f'{leg}_mean'] = mean
            frame[f'{leg}_vol'] = vol
            low = bars.prior_turn_low if leg == 'overnight' else bars.turn_low
            turn_available = (bars.prior_turn_distance.notna() if leg == 'overnight'
                              else bars.turn_change.notna())
            flipped = base.where(~low, -base).where(turn_available)
            frame[f'{leg}_turn'] = flipped.groupby(bars.symbol).transform(
                lambda s: s.rolling(window, min_periods=window).mean()).where(contiguous)
        frame = signals.merge(frame, on=['date', 'symbol'], validate='one_to_one')
        for leg in LEGS:
            mean_vol = frame.groupby('date')[f'{leg}_vol'].transform('mean')
            frame[f'{leg}_volflip'] = frame[f'{leg}_mean'].where(
                frame[f'{leg}_vol'] >= mean_vol, -frame[f'{leg}_mean'])
            frame[f'{leg}_revised'] = (zscore_by_date(frame, f'{leg}_volflip') +
                                      zscore_by_date(frame, f'{leg}_turn')) / 2
        frame['team_coin'] = sum(zscore_by_date(frame, f'{leg}_revised') for leg in LEGS) / 3
        frame['entry_date'] = frame.date.map({d: calendar[pos[d] + 1] for d in signal_dates
                                               if pos[d] + 1 < len(calendar)})
        frame['exit_date'] = frame.date.map({d: calendar[pos[signal_dates[i + 1]] + 1]
                                              for i, d in enumerate(signal_dates[:-1])
                                              if pos[signal_dates[i + 1]] + 1 < len(calendar)})
        for side in ('entry', 'exit'):
            frame = frame.merge(prices.rename(columns={'date': f'{side}_date',
                                                       'adj_open': f'{side}_open'}),
                                on=[f'{side}_date', 'symbol'], how='left', validate='many_to_one')
        frame['next_month_return'] = frame.exit_open / frame.entry_open - 1
        if window == 20:
            frame.to_parquet(DATA / 'fangzheng_team_coin_20_signals.parquet', index=False)
        factors = ['team_coin'] + [f'{leg}_{kind}' for leg in LEGS
                                   for kind in ('volflip', 'turn', 'revised')]
        for factor in factors:
            for date, day in frame.groupby('date', sort=True):
                clean = day[[factor, 'next_month_return']].dropna()
                if len(clean) < 100 or clean[factor].nunique() < 10:
                    continue
                trials.append({'date': date, 'window': window, 'factor': factor,
                               'names': len(clean), 'rank_ic': clean[factor].corr(
                                   clean.next_month_return, method='spearman')})
    monthly = pd.DataFrame(trials)
    monthly['period'] = pd.cut(monthly.date.dt.year, [2019, 2023, 2025, 2026],
                               labels=['discovery_2020_23', 'review_2024_25', 'seen_2026'])
    summary = pd.concat([monthly, monthly.assign(period='all')]).groupby(
        ['window', 'factor', 'period'], observed=True).agg(
        months=('rank_ic', 'size'), mean_ic=('rank_ic', 'mean'),
        negative_fraction=('rank_ic', lambda s: (s < 0).mean()),
        mean_names=('names', 'mean')).reset_index()
    OUT.mkdir(exist_ok=True)
    monthly.to_csv(OUT / 'monthly_ic.csv', index=False)
    summary.to_csv(OUT / 'summary.csv', index=False)
    (OUT / 'manifest.json').write_text(json.dumps({
        'source': 'Fangzheng Securities 2022-06-11, sections 2.4-2.14',
        'formula': 'three monthly revised reversal legs, each combining volatility and turnover flips',
        'windows': [10, 20, 40], 'original_window': 20,
        'implementation_choice': 'cross-sectional zscore before each equal-weight combination',
        'universe_change': 'daily HS300 rather than all A shares',
        'neutralization': 'no industry or size regression',
        'scope': 'exploratory IC; no executable portfolio claim',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(summary[(summary.factor == 'team_coin')].to_string(index=False))


if __name__ == '__main__':
    run()
