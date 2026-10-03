"""Audit local PIT financial snapshots without publishing statement values."""

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data'
OUT = ROOT / 'results' / 'gm_financial_audit.json'
FIELDS = {'balance': ('ttl_ast', 'ttl_liab'),
          'income': ('net_prof_pcom',), 'cashflow': ('net_cf_oper',),
          'annual_balance': ('ttl_ast', 'ttl_liab'),
          'annual_income': ('net_prof_pcom',),
          'annual_cashflow': ('net_cf_oper',)}


def audit():
    months = []
    for member_file in sorted(DATA.glob('gm_hs300_*_members.parquet')):
        record = {'month': member_file.name[9:16].replace('_', '-')}
        frames = {}
        for name, fields in FIELDS.items():
            file = member_file.with_name(member_file.name.replace(
                '_members', f'_financial_{name}'))
            if not file.exists():
                record[f'{name}_missing_file'] = True
                continue
            frame = pd.read_parquet(file)
            frames[name] = frame
            record[f'{name}_rows'] = len(frame)
            record[f'{name}_latest_pub'] = str(frame.pub_date.max())
            record[f'{name}_published_after_query'] = int((
                pd.to_datetime(frame.pub_date) > pd.to_datetime(frame.query_date)).sum())
            record[f'{name}_nonmissing'] = {
                field: int(frame[field].notna().sum()) for field in fields}
            record[f'{name}_sha256'] = hashlib.sha256(file.read_bytes()).hexdigest()
        if all(name in frames for name in ('balance', 'income', 'cashflow')):
            shared = frames['balance'][['symbol', 'rpt_date']].merge(
                frames['income'][['symbol', 'rpt_date']], on='symbol',
                suffixes=('_balance', '_income')).merge(
                frames['cashflow'][['symbol', 'rpt_date']].rename(
                    columns={'rpt_date': 'rpt_date_cashflow'}), on='symbol')
            record['shared_symbols'] = len(shared)
            record['aligned_report_dates'] = int((
                shared.rpt_date_balance.eq(shared.rpt_date_income) &
                shared.rpt_date_balance.eq(shared.rpt_date_cashflow)).sum())
        if all(name in frames for name in ('annual_balance', 'annual_income',
                                           'annual_cashflow')):
            annual = frames['annual_balance'][['symbol', 'rpt_date']].merge(
                frames['annual_income'][['symbol', 'rpt_date']], on='symbol',
                suffixes=('_balance', '_income')).merge(
                frames['annual_cashflow'][['symbol', 'rpt_date']].rename(
                    columns={'rpt_date': 'rpt_date_cashflow'}), on='symbol')
            record['annual_shared_symbols'] = len(annual)
            record['annual_aligned_report_dates'] = int((
                annual.rpt_date_balance.eq(annual.rpt_date_income) &
                annual.rpt_date_balance.eq(annual.rpt_date_cashflow)).sum())
        months.append(record)
    summary = {
        'source': 'GM original consolidated statements (data_type=101)',
        'query_rule': 'previous trading day before monthly signal close',
        'months': months,
        'complete_months': sum(all(f'{name}_rows' in m for name in FIELDS)
                               for m in months),
        'published_after_query': sum(m.get(f'{name}_published_after_query', 0)
                                     for m in months for name in FIELDS),
        'limitations': ['Historical revisions and announcement intraday times not independently verified',
                        'Values are locally cached and omitted from Git'],
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'months': len(months),
                      'complete_months': summary['complete_months'],
                      'published_after_query': summary['published_after_query'],
                      'aligned_report_dates': sum(m.get('aligned_report_dates', 0) for m in months),
                      'shared_symbols': sum(m.get('shared_symbols', 0) for m in months),
                      'annual_aligned_report_dates': sum(m.get('annual_aligned_report_dates', 0)
                                                         for m in months)}))


if __name__ == '__main__':
    audit()
