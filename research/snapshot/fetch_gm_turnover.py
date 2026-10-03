"""Fetch daily turnover for the saved HS300 universe in one month."""

import argparse
import json
import os
from pathlib import Path

import pandas as pd
from gm.api import set_token, stk_get_daily_basic_pt

DATA = Path(__file__).resolve().parents[2] / 'data'


def fetch(month):
    token = os.environ.get('GM_TOKEN')
    if not token:
        raise RuntimeError('GM_TOKEN is not set')
    set_token(token)
    stem = f'gm_hs300_{month.replace("-", "_")}'
    output = DATA / f'{stem}_turnover.parquet'
    if output.exists():
        print(json.dumps({'month': month, 'status': 'already_complete'}))
        return
    members = pd.read_parquet(DATA / f'{stem}_members.parquet')
    frames = []
    for day, rows in members.groupby('trade_date', sort=True):
        frame = stk_get_daily_basic_pt(symbols=rows.symbol.tolist(),
                                       fields='turnrate', trade_date=str(day), df=True)
        frames.append(frame)
    panel = pd.concat(frames, ignore_index=True)
    panel['date'] = pd.to_datetime(panel.trade_date).dt.date.astype(str)
    if panel.duplicated(['date', 'symbol']).any():
        raise RuntimeError('Duplicate turnover keys')
    panel.to_parquet(output, index=False)
    print(json.dumps({'month': month, 'rows': len(panel),
                      'nonmissing_turnrate': int(panel.turnrate.notna().sum())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('month', help='YYYY-MM')
    fetch(parser.parse_args().month)
