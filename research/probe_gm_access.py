"""Small, read-only GM coverage check. Never prints or saves GM_TOKEN."""

import json
import os

from gm.api import (ADJUST_NONE, history, get_history_instruments, set_token,
                    stk_get_fundamentals_balance_pt, stk_get_index_constituents)


def main():
    token = os.environ.get('GM_TOKEN')
    if not token:
        raise RuntimeError('GM_TOKEN is not set in this process')
    set_token(token)

    bars = history(symbol='SHSE.600000', frequency='1d',
                   start_time='2025-01-02', end_time='2025-01-10',
                   fields='symbol,eob,open,high,low,close,volume,amount',
                   adjust=ADJUST_NONE, df=True)
    members = stk_get_index_constituents(index='SHSE.000300',
                                         trade_date='2025-01-02')
    instruments = get_history_instruments(symbols='SHSE.600000',
                                          start_date='2025-01-02',
                                          end_date='2025-01-03', df=True)
    balance = stk_get_fundamentals_balance_pt(symbols='SHSE.600000',
                                               fields='ttl_ast,ttl_liab',
                                               date='2025-05-02', df=True)
    print(json.dumps({
        'daily_bar_rows': len(bars), 'daily_bar_fields': list(bars.columns),
        'hs300_rows': len(members), 'hs300_fields': list(members.columns),
        'instrument_rows': len(instruments),
        'instrument_fields': list(instruments.columns),
        'balance_rows': len(balance), 'balance_fields': list(balance.columns),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
