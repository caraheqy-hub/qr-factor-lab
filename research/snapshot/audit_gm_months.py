"""Audit saved GM monthly panels without publishing licensed raw data."""

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data'
OUT = ROOT / 'results' / 'gm_snapshot_audit.json'


def audit():
    months = []
    for member_file in sorted(DATA.glob('gm_hs300_*_members.parquet')):
        bar_file = member_file.with_name(member_file.name.replace('_members', '_bars'))
        if not bar_file.exists():
            continue
        members = pd.read_parquet(member_file)
        bars = pd.read_parquet(bar_file)
        keys = members[['symbol', 'trade_date']].rename(columns={'trade_date': 'date'})
        keys['date'] = pd.to_datetime(keys['date']).dt.date.astype(str)
        joined = keys.merge(bars[['symbol', 'date']], on=['symbol', 'date'],
                            how='left', indicator=True, validate='one_to_one')
        record = {
            'month': member_file.name[9:16].replace('_', '-'),
            'trade_dates': int(keys.date.nunique()),
            'member_rows': int(len(keys)),
            'matched_member_bars': int((joined['_merge'] == 'both').sum()),
            'missing_member_bars': int((joined['_merge'] == 'left_only').sum()),
            'raw_bar_rows': int(len(bars)),
            'member_sha256': hashlib.sha256(member_file.read_bytes()).hexdigest(),
            'bar_sha256': hashlib.sha256(bar_file.read_bytes()).hexdigest(),
        }
        instrument_file = member_file.with_name(member_file.name.replace('_members', '_instruments'))
        if instrument_file.exists():
            instruments = pd.read_parquet(instrument_file)
            missing = joined.loc[joined['_merge'] == 'left_only', ['symbol', 'date']]
            checked = missing.merge(instruments[['symbol', 'date', 'is_suspended']],
                                    on=['symbol', 'date'], how='left', validate='one_to_one')
            record['instrument_rows'] = int(len(instruments))
            record['missing_bars_suspended'] = int((checked.is_suspended == 1).sum())
            record['missing_bars_unexplained'] = int((checked.is_suspended != 1).sum())
            record['instrument_sha256'] = hashlib.sha256(instrument_file.read_bytes()).hexdigest()
        turnover_file = member_file.with_name(member_file.name.replace('_members', '_turnover'))
        if turnover_file.exists():
            turnover = pd.read_parquet(turnover_file)
            record['turnover_rows'] = int(len(turnover))
            record['turnover_nonmissing'] = int(turnover.turnrate.notna().sum())
            record['turnover_sha256'] = hashlib.sha256(turnover_file.read_bytes()).hexdigest()
        months.append(record)
    summary = {'source': 'GM/MyQuant', 'adjustment': 'ADJUST_NONE',
               'months': months,
               'total_member_rows': sum(x['member_rows'] for x in months),
               'total_missing_member_bars': sum(x['missing_member_bars'] for x in months),
               'limitations': ['ST status and point-in-time revisions not yet independently verified',
                               'Fundamental publication history not yet bulk captured']}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'months': len(months),
                      'total_member_rows': summary['total_member_rows'],
                      'total_missing_member_bars': summary['total_missing_member_bars'],
                      'missing_bars_unexplained': sum(x.get('missing_bars_unexplained', 0) for x in months)}))


if __name__ == '__main__':
    audit()
