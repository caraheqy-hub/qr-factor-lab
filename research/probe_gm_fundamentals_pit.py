"""Read-only check of original versus default GM point-in-time balance data."""

import json
import os
from pathlib import Path

import pandas as pd

from gm.api import (set_token, stk_get_fundamentals_balance_pt,
                    stk_get_fundamentals_cashflow_pt,
                    stk_get_fundamentals_income_pt)


def main():
    token = os.environ.get('GM_TOKEN')
    if not token:
        raise RuntimeError('GM_TOKEN is not set')
    set_token(token)
    rows = []
    for date in ('2022-05-16', '2024-05-16', '2025-05-16'):
        for data_type in (0, 101):
            frame = stk_get_fundamentals_balance_pt(
                symbols='SHSE.600000', fields='ttl_ast,ttl_liab',
                date=date, data_type=data_type, df=True)
            first = frame.iloc[0] if len(frame) else None
            rows.append({
                'query_date': date, 'data_type': data_type, 'rows': len(frame),
                'fields': list(frame.columns),
                'rpt_date': str(first['rpt_date']) if first is not None else None,
                'pub_date': str(first['pub_date']) if first is not None else None,
            })
    for name, function, fields in (
        ('income', stk_get_fundamentals_income_pt, 'net_prof_pcom'),
        ('cashflow', stk_get_fundamentals_cashflow_pt, 'net_cf_oper'),
    ):
        frame = function(symbols='SHSE.600000', fields=fields,
                         date='2025-05-16', data_type=101, df=True)
        first = frame.iloc[0] if len(frame) else None
        rows.append({
            'table': name, 'query_date': '2025-05-16', 'data_type': 101,
            'rows': len(frame), 'fields': list(frame.columns),
            'rpt_date': str(first['rpt_date']) if first is not None else None,
            'pub_date': str(first['pub_date']) if first is not None else None,
        })
    root = Path(__file__).resolve().parents[1]
    members = pd.read_parquet(root / 'data' / 'gm_hs300_2025_05_members.parquet')
    symbols = sorted(members.loc[
        members.trade_date.eq(members.trade_date.max()), 'symbol'].unique())
    frame = stk_get_fundamentals_balance_pt(
        symbols=','.join(symbols), fields='ttl_ast,ttl_liab',
        date='2025-05-29', data_type=101, df=True)
    rows.append({'table': 'balance_batch', 'query_date': '2025-05-29',
                 'requested': len(symbols), 'returned': len(frame),
                 'max_pub_date': str(frame.pub_date.max()) if len(frame) else None})
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
