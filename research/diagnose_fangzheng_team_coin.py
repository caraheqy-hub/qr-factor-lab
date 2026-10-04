"""Audit the already-seen 20-day HS300 team/coin signal; no parameter fitting."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'fangzheng_team_coin_gm'


def main():
    signal = pd.read_parquet(ROOT / 'data' / 'fangzheng_team_coin_20_signals.parquet')
    bars = pd.concat((pd.read_parquet(p) for p in sorted((ROOT / 'data').glob(
        'gm_hs300_*_bars.parquet'))), ignore_index=True)
    inst = pd.concat((pd.read_parquet(p) for p in sorted((ROOT / 'data').glob(
        'gm_hs300_*_instruments.parquet'))), ignore_index=True)
    bars['date'] = pd.to_datetime(bars.date)
    inst['date'] = pd.to_datetime(inst.date)
    bars = bars.merge(inst[['date', 'symbol', 'adj_factor']], on=['date', 'symbol'],
                      validate='one_to_one').sort_values(['symbol', 'date'])
    bars['adjusted_close'] = bars.close * bars.adj_factor
    bars['prior_20d_return'] = bars.adjusted_close / bars.groupby('symbol').adjusted_close.shift(20) - 1
    signal = signal.merge(bars[['date', 'symbol', 'prior_20d_return']],
                          on=['date', 'symbol'], how='left', validate='one_to_one')

    rows = []
    for date, month in signal.groupby('date', sort=True):
        clean = month[['team_coin', 'next_month_return', 'prior_20d_return']].dropna()
        if len(clean) < 100:
            continue
        factor = clean.team_coin.rank(pct=True)
        future = clean.next_month_return.rank(pct=True)
        prior = clean.prior_20d_return.rank(pct=True)
        # Residual rank correlation is a descriptive momentum control, not a fitted strategy.
        beta_factor = factor.cov(prior) / prior.var()
        beta_future = future.cov(prior) / prior.var()
        partial = (factor - beta_factor * prior).corr(future - beta_future * prior)
        rows.append({
            'date': date, 'members': len(month),
            'factor_available': int(month.team_coin.notna().sum()),
            'future_return_available': int(month.next_month_return.notna().sum()),
            'joint_with_prior': len(clean),
            'rank_ic': factor.corr(future),
            'prior_return_ic': prior.corr(future),
            'factor_prior_return_corr': factor.corr(prior),
            'partial_rank_corr_after_prior_return': partial,
        })
    audit = pd.DataFrame(rows)
    audit.to_csv(OUT / 'team_coin_20_monthly_diagnosis.csv', index=False)
    print(audit.groupby(audit.date.dt.year).agg(
        months=('rank_ic', 'size'), mean_ic=('rank_ic', 'mean'),
        median_ic=('rank_ic', 'median'), negative_months=('rank_ic', lambda x: int((x < 0).sum())),
        mean_names=('joint_with_prior', 'mean')).to_string())
    print(audit[audit.date.dt.year.ge(2025)][[
        'date', 'rank_ic', 'prior_return_ic', 'factor_prior_return_corr',
        'partial_rank_corr_after_prior_return', 'members', 'factor_available',
        'future_return_available']].to_string(index=False))


if __name__ == '__main__':
    main()
