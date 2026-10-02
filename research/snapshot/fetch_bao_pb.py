import csv
import socket
from pathlib import Path

import baostock as bs
import pandas as pd

root = Path(__file__).resolve().parents[2] / 'data'
socket.setdefaulttimeout(25)
members = pd.read_csv(root / 'bao_hs300_monthly_members.csv')
symbols = sorted(members['symbol'].unique())
target = root / 'bao_hs300_pb_2019_2026.csv'
done = set(pd.read_csv(target, usecols=['symbol'])['symbol']) if target.exists() else set()
login = bs.login()
if login.error_code != '0':
    raise RuntimeError(login.error_msg)
try:
    with target.open('a', newline='', encoding='utf-8') as out:
        writer = csv.writer(out)
        if out.tell() == 0:
            writer.writerow(['date', 'symbol', 'pbMRQ', 'peTTM', 'turn'])
        for i, symbol in enumerate(symbols, 1):
            if symbol in done:
                continue
            result = bs.query_history_k_data_plus(symbol, 'date,code,pbMRQ,peTTM,turn',
                                                  start_date='2019-01-01', end_date='2026-09-30',
                                                  frequency='d', adjustflag='3')
            if result.error_code != '0':
                raise RuntimeError(result.error_msg)
            n = 0
            while result.next():
                row = result.get_row_data()
                writer.writerow(row)
                n += 1
            if result.error_code != '0':
                raise RuntimeError(result.error_msg)
            out.flush()
            print(i, len(symbols), symbol, n, flush=True)
finally:
    bs.logout()
