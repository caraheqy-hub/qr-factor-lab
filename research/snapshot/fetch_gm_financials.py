"""Save monthly GM original financial statements using prior-day PIT queries."""

import os
import time
from pathlib import Path

import pandas as pd

from gm.api import (set_token, stk_get_fundamentals_balance_pt,
                    stk_get_fundamentals_cashflow_pt,
                    stk_get_fundamentals_income_pt)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data'
TABLES = {
    'balance': (stk_get_fundamentals_balance_pt, 'ttl_ast,ttl_liab', 0),
    'income': (stk_get_fundamentals_income_pt, 'net_prof_pcom', 0),
    'cashflow': (stk_get_fundamentals_cashflow_pt, 'net_cf_oper', 0),
    'annual_balance': (stk_get_fundamentals_balance_pt, 'ttl_ast,ttl_liab', 12),
    'annual_income': (stk_get_fundamentals_income_pt, 'net_prof_pcom', 12),
    'annual_cashflow': (stk_get_fundamentals_cashflow_pt, 'net_cf_oper', 12),
}


def fetch():
    token = os.environ.get('GM_TOKEN')
    if not token:
        raise RuntimeError('GM_TOKEN is not set')
    set_token(token)
    files = sorted(DATA.glob('gm_hs300_*_members.parquet'))
    if len(files) != 81:
        raise RuntimeError(f'Expected 81 member snapshots; got {len(files)}')
    for file in files:
        members = pd.read_parquet(file)
        dates = sorted(pd.to_datetime(members.trade_date).dt.normalize().unique())
        signal_date, query_date = dates[-1], dates[-2]
        symbols = sorted(members.loc[
            pd.to_datetime(members.trade_date).dt.normalize().eq(signal_date),
            'symbol'].unique())
        for name, (function, fields, rpt_type) in TABLES.items():
            path = file.with_name(file.name.replace('_members', f'_financial_{name}'))
            if path.exists():
                continue
            for attempt in range(3):
                try:
                    frame = function(symbols=','.join(symbols), fields=fields,
                                     date=str(query_date.date()), data_type=101,
                                     rpt_type=rpt_type, df=True)
                    if frame.empty:
                        raise RuntimeError('Empty financial response')
                    if frame.symbol.duplicated().any() or not set(frame.symbol).issubset(symbols):
                        raise RuntimeError('Invalid symbols or duplicates')
                    if pd.to_datetime(frame.pub_date).max() > query_date:
                        raise RuntimeError('Publication date after PIT query date')
                    frame['signal_date'] = signal_date
                    frame['query_date'] = query_date
                    frame.to_parquet(path, index=False)
                    print(file.name[9:16], name, len(frame), '/', len(symbols), flush=True)
                    break
                except Exception as exc:
                    if attempt == 2:
                        raise RuntimeError(f'{file.name} {name}: {exc}') from exc
                    time.sleep(2 ** attempt)


if __name__ == '__main__':
    fetch()
