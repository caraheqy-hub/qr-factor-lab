"""Predeclared Alpha5 turnover-reduction grid; optimistic diagnostic only."""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUT = ROOT / 'results' / 'gtja_alpha5_gm'
GRID = [(smooth, hold, breadth) for smooth in (1, 5, 10)
        for hold in (5, 10) for breadth in (0.2, 0.4)]


def months(suffix):
    return pd.concat((pd.read_parquet(path) for path in sorted(
        DATA.glob(f'gm_hs300_*_{suffix}.parquet'))), ignore_index=True)


def prepare():
    signals = pd.read_parquet(DATA / 'gtja_alpha5_5_5_3_signals.parquet')
    signals = signals.sort_values(['symbol', 'date']).reset_index(drop=True)
    members = months('members')
    calendar = sorted(pd.to_datetime(members.trade_date).dt.normalize().unique())
    group = signals.groupby('symbol', sort=False)
    for smooth in (1, 5, 10):
        value = group.factor.transform(lambda s: s.rolling(
            smooth, min_periods=smooth).mean())
        if smooth > 1:
            contiguous = signals.day_number - group.day_number.shift(smooth - 1) == smooth - 1
            value = value.where(contiguous)
        signals[f'smooth_{smooth}'] = value

    bars = months('bars').drop_duplicates(['date', 'symbol'])
    inst = months('instruments')
    bars['date'] = pd.to_datetime(bars.date).dt.normalize()
    inst['date'] = pd.to_datetime(inst.date).dt.normalize()
    prices = bars[['date', 'symbol', 'open']].merge(
        inst[['date', 'symbol', 'adj_factor', 'upper_limit', 'lower_limit',
              'is_suspended', 'sec_name']], on=['date', 'symbol'], validate='one_to_one')
    prices['adj_open'] = prices.open * prices.adj_factor
    for hold in (5, 10):
        for side, offset in (('entry', 1), ('exit', hold + 1)):
            index = signals.day_number + offset
            signals[f'{side}_{hold}_date'] = pd.to_datetime(
                [calendar[i] if i < len(calendar) else pd.NaT for i in index])
            renamed = prices.rename(columns={
                'date': f'{side}_{hold}_date', 'open': f'{side}_{hold}_raw_open',
                'adj_open': f'{side}_{hold}_adj_open',
                'upper_limit': f'{side}_{hold}_upper',
                'lower_limit': f'{side}_{hold}_lower',
                'is_suspended': f'{side}_{hold}_suspended',
                'sec_name': f'{side}_{hold}_name'})
            cols = [f'{side}_{hold}_date', 'symbol', f'{side}_{hold}_raw_open',
                    f'{side}_{hold}_adj_open', f'{side}_{hold}_upper',
                    f'{side}_{hold}_lower', f'{side}_{hold}_suspended',
                    f'{side}_{hold}_name']
            signals = signals.merge(renamed[cols], on=[f'{side}_{hold}_date', 'symbol'],
                                    how='left', validate='many_to_one')
        signals[f'return_{hold}'] = (signals[f'exit_{hold}_adj_open'] /
                                      signals[f'entry_{hold}_adj_open'] - 1)
    return signals


def trial(data, smooth, hold, breadth):
    data = data[data.day_number.mod(hold).eq(0)]
    factor, label = f'smooth_{smooth}', f'return_{hold}'
    rows = []
    previous = {}
    for date, day in data.groupby('date', sort=True):
        ranked = day.dropna(subset=[factor]).sort_values(
            [factor, 'symbol'], ascending=[False, True])
        if len(ranked) < 200:
            continue
        selected = ranked.head(int(len(ranked) * breadth))
        missing = int(selected[label].isna().sum())
        if missing:
            rows.append({'date': date, 'usable': False, 'missing_selected': missing})
            previous = {}
            continue
        target = dict.fromkeys(selected.symbol, 1 / len(selected))
        turnover = sum(abs(target.get(symbol, 0) - previous.get(symbol, 0))
                       for symbol in target.keys() | previous.keys())
        returns = dict(zip(selected.symbol, selected[label]))
        gross = selected[label].mean()
        previous = {symbol: weight * (1 + returns[symbol]) / (1 + gross)
                    for symbol, weight in target.items()}
        buy_blocked = ((selected[f'entry_{hold}_suspended'] == 1) |
                       (selected[f'entry_{hold}_raw_open'] >=
                        selected[f'entry_{hold}_upper'] - 1e-6)).sum()
        sell_blocked = ((selected[f'exit_{hold}_suspended'] == 1) |
                        (selected[f'exit_{hold}_raw_open'] <=
                         selected[f'exit_{hold}_lower'] + 1e-6)).sum()
        rows.append({'date': date, 'usable': True, 'selected': len(selected),
                     'gross_excess': gross - ranked[label].dropna().mean(),
                     'turnover': turnover, 'buy_blocked': int(buy_blocked),
                     'sell_blocked': int(sell_blocked),
                     'st_name': int(selected[f'entry_{hold}_name'].astype(str).str.contains(
                         'ST', case=False).sum())})
    return pd.DataFrame(rows).assign(smooth=smooth, hold=hold, breadth=breadth)


def run():
    data = prepare()
    trials = pd.concat((trial(data, *parameters) for parameters in GRID),
                       ignore_index=True)
    good = trials[trials.usable].copy()
    good['year'] = good.date.dt.year
    summary = good.groupby(['smooth', 'hold', 'breadth', 'year']).agg(
        periods=('gross_excess', 'size'),
        gross_excess_bps=('gross_excess', lambda s: 10000 * s.mean()),
        mean_turnover=('turnover', 'mean'),
        buy_blocked=('buy_blocked', 'sum'),
        sell_blocked=('sell_blocked', 'sum'),
        st_name=('st_name', 'sum')).reset_index()
    skipped = trials[~trials.usable].assign(year=lambda x: x.date.dt.year).groupby(
        ['smooth', 'hold', 'breadth', 'year']).size().rename('skipped_periods').reset_index()
    summary = summary.merge(skipped, on=['smooth', 'hold', 'breadth', 'year'], how='left')
    summary['skipped_periods'] = summary.skipped_periods.fillna(0).astype(int)
    for bps in (5, 10, 15, 25):
        summary[f'net_excess_{bps}bps'] = (
            summary.gross_excess_bps - bps * summary.mean_turnover)
    OUT.mkdir(exist_ok=True)
    trials.to_csv(OUT / 'tuning_periods.csv', index=False)
    summary.to_csv(OUT / 'tuning_yearly.csv', index=False)
    discovery = summary[summary.year.between(2020, 2023)].groupby(
        ['smooth', 'hold', 'breadth']).agg(
        years=('year', 'size'), weakest_year=('net_excess_15bps', 'min'),
        mean_net=('net_excess_15bps', 'mean')).reset_index()
    discovery.to_csv(OUT / 'tuning_discovery.csv', index=False)
    (OUT / 'tuning_manifest.json').write_text(json.dumps({
        'source_factor': 'GTJA Alpha5 / WorldQuant Alpha26, original 5/5/3',
        'grid': {'smoothing_days': [1, 5, 10], 'holding_days': [5, 10],
                 'top_fraction': [0.2, 0.4]},
        'selection_period': '2020-2023, already seen in this project',
        'review_period': '2024-2025, already seen',
        'seen_2026': '2026 through September; incomplete forward labels',
        'cost_bps_per_traded_notional': [5, 10, 15, 25],
        'turnover': 'target weights versus prior holdings drifted by realised return',
        'limit_handling': 'counted only; returns still assume fills',
        'missing_selected_return': 'skip entire period and reset holdings',
        'scope': 'optimistic diagnostic; no executable backtest claim',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(discovery.sort_values('mean_net', ascending=False).to_string(index=False))


if __name__ == '__main__':
    run()
