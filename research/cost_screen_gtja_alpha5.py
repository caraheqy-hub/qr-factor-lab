"""Optimistic 5-day long-only screen for preregistered GTJA Alpha5 windows."""

from pathlib import Path

import pandas as pd

from cost_screen_gtja_alpha1 import trial

OUT = Path(__file__).resolve().parents[1] / 'results' / 'gtja_alpha5_gm'


if __name__ == '__main__':
    grids = ('3_3_3', '5_5_3', '10_10_5')
    trials = [trial(grid, horizon, family='gtja_alpha5')
              for grid in grids for horizon in (1, 5)]
    OUT.mkdir(exist_ok=True)
    pd.concat((x[0] for x in trials)).to_csv(OUT / 'cost_daily.csv', index=False)
    pd.concat((x[1] for x in trials), ignore_index=True).to_csv(
        OUT / 'cost_summary.csv', index=False)
