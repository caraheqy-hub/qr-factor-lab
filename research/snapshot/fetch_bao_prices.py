import csv
import json
import socket
from pathlib import Path

import baostock as bs
import pandas as pd

socket.setdefaulttimeout(25)
root = Path(__file__).resolve().parents[2] / 'data'
root.mkdir(exist_ok=True)
members_file = root / 'bao_hs300_monthly_members.csv'
bars_file = root / 'bao_hs300_2019_2026.csv'


def rows(result):
    if result.error_code != '0':
        raise RuntimeError(result.error_msg)
    result_rows = []
    while result.next():
        result_rows.append(result.get_row_data())
    if result.error_code != '0':
        raise RuntimeError(result.error_msg)
    return result.fields, result_rows


login = bs.login()
if login.error_code != '0':
    raise RuntimeError(login.error_msg)
try:
    if not members_file.exists():
        with members_file.open('w', newline='', encoding='utf-8') as out:
            writer = csv.writer(out)
            writer.writerow(['snapshot_date', 'effective_date', 'symbol'])
            for date in pd.date_range('2019-12-31', '2026-09-30', freq='ME'):
                d = date.strftime('%Y-%m-%d')
                fields, data = rows(bs.query_hs300_stocks(d))
                for entry in data:
                    row = dict(zip(fields, entry))
                    writer.writerow([d, row['updateDate'], row['code']])
                out.flush()
                print('members', d, len(data), flush=True)

    members = pd.read_csv(members_file)
    symbols = sorted(members['symbol'].unique())
    completed = set()
    if bars_file.exists():
        completed = set(pd.read_csv(bars_file, usecols=['symbol'])['symbol'].unique())
    with bars_file.open('a', newline='', encoding='utf-8') as out:
        writer = csv.writer(out)
        if out.tell() == 0:
            writer.writerow(['date', 'symbol', 'open', 'close', 'volume', 'amount', 'tradestatus', 'isST'])
        for i, symbol in enumerate(symbols, 1):
            if symbol in completed:
                continue
            fields, data = rows(bs.query_history_k_data_plus(
                symbol, 'date,code,open,close,volume,amount,tradestatus,isST',
                start_date='2019-01-01', end_date='2026-09-30', frequency='d', adjustflag='2'))
            for entry in data:
                row = dict(zip(fields, entry))
                writer.writerow([row['date'], row['code'], row['open'], row['close'], row['volume'],
                                 row['amount'], row['tradestatus'], row['isST']])
            out.flush()
            print('bars', i, len(symbols), symbol, len(data), flush=True)
    (root / 'bao_source.json').write_text(json.dumps({
        'provider': 'BaoStock', 'query': 'query_hs300_stocks monthly; query_history_k_data_plus daily',
        'period': ['2019-01-01', '2026-09-30'], 'adjustflag': '2 (retrospective forward adjusted)',
        'members_file': members_file.name, 'bars_file': bars_file.name,
        'limitations': ['Monthly constituent snapshots', 'Retrospective price adjustment',
                        'No order book or price limit execution data']
    }, ensure_ascii=False, indent=2), encoding='utf-8')
finally:
    bs.logout()
