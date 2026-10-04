"""Check historical all-A universe metadata without downloading quotes."""

import json
import os

import pandas as pd
from gm.api import get_instrumentinfos, set_token


def main():
    token = os.environ.get('GM_TOKEN')
    if not token:
        raise RuntimeError('GM_TOKEN is not set')
    set_token(token)
    instruments = get_instrumentinfos(exchanges=['SHSE', 'SZSE'], sec_types=1, df=True)
    print(json.dumps({'rows': len(instruments),
                      'columns': list(instruments.columns)}, ensure_ascii=False))
    if {'listed_date', 'delisted_date'}.issubset(instruments.columns):
        for date in ('2020-01-23', '2025-12-31', '2026-09-30'):
            listed = pd.to_datetime(instruments.listed_date, errors='coerce')
            delisted = pd.to_datetime(instruments.delisted_date, errors='coerce')
            as_of = pd.Timestamp(date)
            active = listed.le(as_of) & (delisted.isna() | delisted.gt(as_of))
            print(json.dumps({'date': date, 'active_symbols': int(active.sum()),
                              'missing_listing_dates': int(listed.isna().sum())}))


if __name__ == '__main__':
    main()
