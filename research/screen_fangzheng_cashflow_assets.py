"""Monthly PIT transfer of Fangzheng's operating cash flow to assets signal."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUT = ROOT / 'results' / 'fangzheng_cashflow_assets_gm'
FACTORS = ('cashflow_assets', 'profit_assets', 'negative_leverage')


def load_months(suffix):
    files = sorted(DATA.glob(f'gm_hs300_*_{suffix}.parquet'))
    if len(files) != 81:
        raise RuntimeError(f'Expected 81 {suffix} snapshots; got {len(files)}')
    return pd.concat((pd.read_parquet(file) for file in files), ignore_index=True)


def run():
    members = load_months('members')
    members['date'] = pd.to_datetime(members.trade_date).dt.normalize()
    calendar = sorted(members.date.unique())
    signal_dates = members.groupby(members.date.dt.to_period('M')).date.max().tolist()
    positions = {date: i for i, date in enumerate(calendar)}
    signals = members.loc[members.date.isin(signal_dates),
                          ['date', 'symbol', 'market_value_total']].copy()
    signals['log_cap'] = np.log(signals.market_value_total.where(
        signals.market_value_total > 0))

    frames = {}
    for name, field in (('balance', 'ttl_ast'), ('income', 'net_prof_pcom'),
                        ('cashflow', 'net_cf_oper')):
        frame = load_months(f'financial_annual_{name}')
        frame['date'] = pd.to_datetime(frame.signal_date).dt.normalize()
        frame['query_date'] = pd.to_datetime(frame.query_date).dt.normalize()
        frame['pub_date'] = pd.to_datetime(frame.pub_date).dt.normalize()
        frame['rpt_date'] = pd.to_datetime(frame.rpt_date).dt.normalize()
        if (frame.pub_date > frame.query_date).any() or not frame.rpt_type.eq(12).all():
            raise RuntimeError(f'PIT or annual report violation in {name}')
        values = ['ttl_ast', 'ttl_liab'] if name == 'balance' else [field]
        frames[name] = frame[['date', 'symbol', 'rpt_date', *values]].rename(
            columns={'rpt_date': f'rpt_{name}'})
    for name in frames:
        signals = signals.merge(frames[name], on=['date', 'symbol'], how='left',
                                validate='one_to_one')
    aligned = signals.rpt_balance.eq(signals.rpt_income) & signals.rpt_balance.eq(
        signals.rpt_cashflow)
    age = (signals.date - signals.rpt_balance).dt.days
    valid = aligned & age.between(0, 548) & (signals.ttl_ast > 0)
    signals['cashflow_assets'] = (signals.net_cf_oper / signals.ttl_ast).where(valid)
    signals['profit_assets'] = (signals.net_prof_pcom / signals.ttl_ast).where(valid)
    signals['negative_leverage'] = (-signals.ttl_liab / signals.ttl_ast).where(valid)

    bars = load_months('bars').drop_duplicates(['date', 'symbol'])
    inst = load_months('instruments')
    bars['date'] = pd.to_datetime(bars.date).dt.normalize()
    inst['date'] = pd.to_datetime(inst.date).dt.normalize()
    prices = bars.merge(inst[['date', 'symbol', 'adj_factor']],
                        on=['date', 'symbol'], validate='one_to_one')
    prices['adj_open'] = prices.open * prices.adj_factor
    signals['entry_date'] = signals.date.map({
        date: calendar[positions[date] + 1] for date in signal_dates
        if positions[date] + 1 < len(calendar)})
    signals['exit_date'] = signals.date.map({
        date: calendar[positions[signal_dates[i + 1]] + 1]
        for i, date in enumerate(signal_dates[:-1])
        if positions[signal_dates[i + 1]] + 1 < len(calendar)})
    for side in ('entry', 'exit'):
        signals = signals.merge(prices[['date', 'symbol', 'adj_open']].rename(
            columns={'date': f'{side}_date', 'adj_open': f'{side}_open'}),
            on=[f'{side}_date', 'symbol'], how='left', validate='many_to_one')
    signals['next_month_return'] = signals.exit_open / signals.entry_open - 1
    signals['sort_cashflow'] = -signals.cashflow_assets
    signals.to_parquet(DATA / 'fangzheng_cashflow_assets_annual_signals.parquet', index=False)

    rows = []
    for date, day in signals.groupby('date', sort=True):
        clean = day[[*FACTORS, 'next_month_return', 'log_cap']].replace(
            [np.inf, -np.inf], np.nan).dropna()
        if len(clean) < 100:
            continue
        for factor in FACTORS:
            if clean[factor].nunique() < 10:
                continue
            rows.append({'date': date, 'factor': factor, 'names': len(clean),
                         'rank_ic': clean[factor].corr(clean.next_month_return,
                                                       method='spearman'),
                         'size_rank_corr': clean[factor].corr(clean.log_cap,
                                                               method='spearman')})
    monthly = pd.DataFrame(rows)
    monthly['period'] = pd.cut(monthly.date.dt.year, [2019, 2023, 2025, 2026],
                               labels=['discovery_2020_23', 'review_2024_25',
                                       'seen_2026'])
    summary = pd.concat([monthly, monthly.assign(period='all')]).groupby(
        ['factor', 'period'], observed=True).agg(
        months=('rank_ic', 'size'), mean_ic=('rank_ic', 'mean'),
        positive_fraction=('rank_ic', lambda s: (s > 0).mean()),
        mean_names=('names', 'mean'), mean_size_rank_corr=('size_rank_corr', 'mean'),
    ).reset_index()
    OUT.mkdir(exist_ok=True)
    monthly.to_csv(OUT / 'monthly_ic.csv', index=False)
    summary.to_csv(OUT / 'summary.csv', index=False)
    (OUT / 'manifest.json').write_text(json.dumps({
        'source': 'Fangzheng 2023-07-07 convertible bond factor, transferred to HS300 equities',
        'definition': 'last publicly available original annual net_cf_oper / ttl_ast',
        'baselines': ['net_prof_pcom / ttl_ast', '-ttl_liab / ttl_ast'],
        'pit': 'data_type=101, rpt_type=12, previous trading day monthly query',
        'same_report_date_required': True, 'max_report_age_days': 548,
        'signal': 'month-end close', 'label': 'next month open to following month open',
        'scope': 'exploratory IC; not an execution backtest',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    run()
