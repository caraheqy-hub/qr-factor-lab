"""Fetch one month of HS300 daily membership and raw bars from GM."""

import argparse
import json
import os
from pathlib import Path

import pandas as pd
from gm.api import ADJUST_NONE, history, set_token, stk_get_index_constituents

DATA = Path(__file__).resolve().parents[2] / 'data'
INDEX = 'SHSE.000300'
FIELDS = 'symbol,eob,open,high,low,close,volume,amount'


def fetch(month):
    token = os.environ.get('GM_TOKEN')
    if not token:
        raise RuntimeError('GM_TOKEN is not set')
    set_token(token)
    first = pd.Timestamp(month + '-01')
    end = first + pd.offsets.MonthEnd()
    stem = DATA / f'gm_hs300_{first:%Y_%m}'
    member_file = stem.with_name(stem.name + '_members.parquet')
    bar_file = stem.with_name(stem.name + '_bars.parquet')
    if member_file.exists() and bar_file.exists():
        print(json.dumps({'month': month, 'status': 'already_complete'}))
        return
    DATA.mkdir(exist_ok=True)

    calendar = history(symbol=INDEX, frequency='1d',
                       start_time=str(first.date()), end_time=str(end.date()),
                       fields='eob', adjust=ADJUST_NONE, df=True)
    dates = sorted({pd.Timestamp(x).date() for x in calendar['eob']
                    if first.date() <= pd.Timestamp(x).date() <= end.date()})
    if not dates:
        raise RuntimeError(f'No trading dates found for {month}')
    members = pd.concat([stk_get_index_constituents(
        index=INDEX, trade_date=str(date)) for date in dates], ignore_index=True)
    if (members.groupby('trade_date')['symbol'].nunique() != 300).any():
        raise RuntimeError('HS300 daily membership is not 300 unique symbols')
    members.to_parquet(member_file, index=False)

    symbols = sorted(members['symbol'].unique())
    bars = []
    for offset in range(0, len(symbols), 80):
        batch = symbols[offset:offset + 80]
        frame = history(symbol=','.join(batch), frequency='1d',
                        start_time=str(first.date()), end_time=str(end.date()),
                        fields=FIELDS, adjust=ADJUST_NONE, df=True)
        bars.append(frame)
        print(f'bars {min(offset + 80, len(symbols))}/{len(symbols)}', flush=True)
    panel = pd.concat(bars, ignore_index=True)
    panel['date'] = pd.to_datetime(panel['eob']).dt.date.astype(str)
    panel = panel[panel['date'].isin({str(x) for x in dates})]
    panel = panel.drop_duplicates(['date', 'symbol'])
    if panel.empty:
        raise RuntimeError('No member bars returned')
    panel.to_parquet(bar_file, index=False)
    print(json.dumps({'month': month, 'trade_dates': len(dates),
                      'member_rows': len(members), 'symbols': len(symbols),
                      'bar_rows': len(panel), 'bar_symbols': panel.symbol.nunique()},
                     ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('month', help='YYYY-MM')
    fetch(parser.parse_args().month)
