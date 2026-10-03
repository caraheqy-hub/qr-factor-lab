"""Fetch point-in-time instrument status for one saved HS300 month."""

import argparse
import json
import os
from pathlib import Path

import pandas as pd
from gm.api import get_history_instruments, set_token

DATA = Path(__file__).resolve().parents[2] / 'data'
FIELDS = ('symbol,trade_date,pre_close,upper_limit,lower_limit,'
          'adj_factor,is_suspended,sec_name')


def fetch(month):
    token = os.environ.get('GM_TOKEN')
    if not token:
        raise RuntimeError('GM_TOKEN is not set')
    set_token(token)
    stem = f'gm_hs300_{month.replace("-", "_")}'
    output = DATA / f'{stem}_instruments.parquet'
    if output.exists():
        print(json.dumps({'month': month, 'status': 'already_complete'}))
        return
    members = pd.read_parquet(DATA / f'{stem}_members.parquet')
    symbols = sorted(members.symbol.unique())
    dates = pd.to_datetime(members.trade_date).dt.date
    frames = []
    for offset in range(0, len(symbols), 80):
        frame = get_history_instruments(
            symbols=symbols[offset:offset + 80],
            start_date=str(dates.min()), end_date=str(dates.max()),
            fields=FIELDS, df=True)
        frames.append(frame)
    panel = pd.concat(frames, ignore_index=True)
    panel['date'] = pd.to_datetime(panel.trade_date).dt.date.astype(str)
    if panel.duplicated(['date', 'symbol']).any():
        raise RuntimeError('Duplicate instrument dates')
    panel.to_parquet(output, index=False)
    print(json.dumps({'month': month, 'instrument_rows': len(panel),
                      'symbols': panel.symbol.nunique(),
                      'suspended_rows': int((panel.is_suspended == 1).sum())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('month', help='YYYY-MM')
    fetch(parser.parse_args().month)
