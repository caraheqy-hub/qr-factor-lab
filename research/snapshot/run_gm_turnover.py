"""Resume monthly GM turnover downloads with a per-process timeout."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).with_name('fetch_gm_turnover.py')


def main():
    months = [f'{year}-{month:02d}' for year in range(2020, 2027)
              for month in range(1, 13) if (year, month) <= (2026, 9)]
    failures = []
    for month in months:
        output = ROOT / 'data' / f'gm_hs300_{month.replace("-", "_")}_turnover.parquet'
        if output.exists():
            continue
        for attempt in range(1, 4):
            try:
                result = subprocess.run([sys.executable, str(SCRIPT), month],
                                        capture_output=True, text=True, timeout=45,
                                        check=False)
                if result.returncode == 0 and output.exists():
                    print(result.stdout.strip().splitlines()[-1], flush=True)
                    break
                print(f'{month} attempt {attempt} failed: exit {result.returncode}', flush=True)
            except subprocess.TimeoutExpired:
                print(f'{month} attempt {attempt} timed out', flush=True)
        else:
            failures.append(month)
    print(json.dumps({'failed_months': failures}, ensure_ascii=False))


if __name__ == '__main__':
    main()
