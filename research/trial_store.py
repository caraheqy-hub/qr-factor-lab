"""Build a unified, source-linked ledger and run research scripts through it."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
STORE = RESULTS / 'trial_store'
PARAMS = {'factor', 'factor_id', 'window', 'rank_days', 'corr_days', 'max_days',
          'smooth', 'hold', 'breadth', 'horizon', 'holding_days', 'skip', 'quintile'}
SAMPLE = {'date', 'year', 'period', 'entry_date', 'exit_date'}
EXCLUDED = {'daily_ic.csv', 'daily_rank_ic.csv', 'daily_rank_ic_1.csv',
            'f08_daily_diagnostic.csv'}
SAFE_MANIFEST = {'source', 'source_url', 'formula', 'definition', 'universe',
                 'label', 'scope', 'cost_bps_per_traded_notional', 'input_sha256',
                 'same_report_date_required', 'max_report_age_days'}


def canonical_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() in {'.csv', '.json', '.jsonl', '.py'}:
        data = data.replace(b'\r\n', b'\n')
    return data


def digest(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()


def clean(value: str):
    if value == '' or value.lower() in {'nan', 'none', 'null'}:
        return None
    try:
        number = float(value)
    except ValueError:
        return value
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def unit(name: str) -> str:
    if 'bps' in name:
        return 'basis_points_per_reported_period'
    if name.startswith('annual_'):
        return 'annualized_fraction_or_ratio'
    if any(x in name for x in ('fraction', 'coverage', 'turnover', 'return', 'drawdown')):
        return 'fraction_or_ratio'
    if any(x in name for x in ('rank_ic', 'mean_ic', 'corr', 'sharpe')):
        return 'unitless'
    if any(x in name for x in ('days', 'months', 'periods', 'names', 'blocked', 'skipped')):
        return 'count'
    return 'unspecified_in_source'


def kind(path: Path, keys: set[str]) -> str:
    name = path.name
    if name in {'tuning_periods.csv'} or name.startswith('monthly_cost_screen_'):
        return 'optimistic_cost_period'
    if name.startswith('cost_') or name.startswith('tuning_yearly') or name == 'tuning_discovery.csv' or name in {
            'f08_portfolio_summary.csv', 'monthly_lowvol_summary.csv',
            'monthly_value_summary.csv'}:
        return 'optimistic_cost_summary'
    if name in {'discovery_trials.csv'}:
        return 'legacy_portfolio_trial'
    if name in {'quintile_periods.csv', 'quintile_summary.csv',
                'team_coin_20_monthly_diagnosis.csv'}:
        return 'diagnostic'
    if 'ic' in keys or 'mean_ic' in keys or 'rank_ic' in keys or 'mean_rank_ic' in keys:
        return 'signal_screen'
    return 'descriptive_result'


def manifest_for(csv_path: Path) -> dict:
    names = (('tuning_manifest.json', 'manifest.json', 'data_manifest.json')
             if csv_path.name.startswith('tuning_') else
             ('manifest.json', 'data_manifest.json'))
    for name in names:
        path = csv_path.parent / name
        if path.exists():
            content = json.loads(path.read_text(encoding='utf-8'))
            return {key: content[key] for key in SAFE_MANIFEST if key in content}
    return {}


def included(path: Path) -> bool:
    name = path.name
    if STORE in path.parents or path.parent.name == 'demo':
        return False
    if name in EXCLUDED or name.startswith('daily_') or name.endswith('_daily.csv'):
        return False
    # Monthly IC detail is covered by the corresponding summary; keep the store compact.
    if name == 'monthly_ic.csv':
        return False
    return True


def collect() -> tuple[list[dict], list[dict]]:
    records, sources = [], []
    for path in sorted(RESULTS.rglob('*.csv')):
        if not included(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        sha = digest(path)
        with path.open(newline='', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            if not reader.fieldnames:
                raise ValueError(f'Missing CSV header: {rel}')
            fields = set(reader.fieldnames)
            stage = kind(path, fields)
            meta = manifest_for(path)
            count = 0
            for number, raw in enumerate(reader, 1):
                if None in raw or any(key is None for key in raw):
                    raise ValueError(f'Malformed CSV row {number}: {rel}')
                row = {key: clean(value) for key, value in raw.items()}
                params = {key: row[key] for key in sorted(PARAMS & fields)}
                # Cost-screen file names carry a parameter that is absent from the rows.
                if path.name.startswith(('cost_screen_summary_', 'monthly_cost_screen_')):
                    params['window'] = int(path.stem.rsplit('_', 1)[-1])
                cohort = {key: row[key] for key in sorted(SAMPLE & fields)}
                metrics = {key: {'value': value, 'unit': unit(key)}
                           for key, value in row.items() if key not in PARAMS | SAMPLE}
                trial_key = json.dumps([path.parent.name, stage, params], sort_keys=True)
                records.append({
                    'schema_version': 1,
                    'record_id': hashlib.sha256(f'{rel}:{sha}:{number}'.encode()).hexdigest()[:20],
                    'trial_id': hashlib.sha256(trial_key.encode()).hexdigest()[:20],
                    'study_id': path.parent.name,
                    'evidence_level': stage,
                    'parameters': params,
                    'sample': cohort,
                    'metrics': metrics,
                    'source': {'artifact': rel, 'sha256': sha, 'row': number},
                    'provenance': meta,
                    'historical_execution_verified': False,
                })
                count += 1
            sources.append({'artifact': rel, 'sha256': sha, 'records': count,
                            'evidence_level': stage})
    for path in sorted(RESULTS.glob('*/selection.json')) + sorted(
            RESULTS.glob('baseline/summary.json')):
        payload = json.loads(path.read_text(encoding='utf-8'))
        rel, sha = path.relative_to(ROOT).as_posix(), digest(path)
        cases = []
        if path.parent.name == 'baseline':
            for factor, periods in payload.get('factors', {}).items():
                for period in ('discovery', 'holdout'):
                    if period in periods:
                        cases.append((factor, period, payload.get('factor_parameters', {}),
                                      periods[period]))
        else:
            chosen = payload.get('selected', {})
            parameters = chosen if isinstance(chosen, dict) else {
                'window': payload.get('selected_window')}
            for period in ('discovery', 'holdout'):
                if isinstance(payload.get(period), dict):
                    cases.append((path.parent.name, period, parameters, payload[period]))
            if isinstance(payload.get('published_20_holdout'), dict):
                cases.append((path.parent.name, 'published_20_holdout',
                              {'window': payload.get('published_window')},
                              payload['published_20_holdout']))
        for number, (factor, period, parameters, values) in enumerate(cases, 1):
            trial_key = json.dumps([path.parent.name, factor, parameters], sort_keys=True)
            records.append({
                'schema_version': 1,
                'record_id': hashlib.sha256(f'{rel}:{sha}:{number}'.encode()).hexdigest()[:20],
                'trial_id': hashlib.sha256(trial_key.encode()).hexdigest()[:20],
                'study_id': path.parent.name, 'evidence_level': 'legacy_portfolio_trial',
                'parameters': {'factor': factor, **parameters}, 'sample': {'period': period},
                'metrics': {key: {'value': value, 'unit': unit(key)}
                            for key, value in values.items() if isinstance(value, (int, float))},
                'source': {'artifact': rel, 'sha256': sha, 'row': number},
                'provenance': {key: payload[key] for key in SAFE_MANIFEST if key in payload},
                'historical_execution_verified': False,
            })
        sources.append({'artifact': rel, 'sha256': sha, 'records': len(cases),
                        'evidence_level': 'legacy_portfolio_trial'})
    return records, sources


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def refresh() -> tuple[int, int]:
    records, sources = collect()
    if len({r['record_id'] for r in records}) != len(records):
        raise ValueError('Duplicate record ids')
    archive = STORE / 'artifact_snapshots'
    archive.mkdir(parents=True, exist_ok=True)
    for row in sources:
        snapshot = archive / f"{row['sha256']}{Path(row['artifact']).suffix}"
        if not snapshot.exists():
            snapshot.write_bytes(canonical_bytes(ROOT / row['artifact']))
        if digest(snapshot) != row['sha256']:
            raise RuntimeError(f"Archived result hash mismatch: {row['artifact']}")
    excluded = [{'artifact': path.relative_to(ROOT).as_posix(),
                 'sha256': digest(path), 'reason': 'daily_detail_or_monthly_ic_already_summarized'}
                for path in sorted(RESULTS.rglob('*.csv'))
                if STORE not in path.parents and not included(path)]
    write_jsonl(STORE / 'records.jsonl', records)
    write_jsonl(STORE / 'sources.jsonl', sources)
    write_jsonl(STORE / 'excluded.jsonl', excluded)
    return len(records), len(sources)


def run(script: str, arguments: list[str]) -> int:
    script_path = (ROOT / script).resolve()
    if not script_path.is_file() or not script_path.is_relative_to(ROOT):
        raise ValueError('Script must be a file inside the repository')
    if any(any(word in arg.lower() for word in ('token', 'secret', 'password', 'apikey'))
           for arg in arguments):
        raise ValueError('Credential-like command arguments are not allowed; use environment variables')
    _, before_sources = collect()
    before = {row['artifact']: row['sha256'] for row in before_sources}
    began = datetime.now(timezone.utc).isoformat()
    result = subprocess.run([sys.executable, str(script_path), *arguments], cwd=ROOT,
                            check=False)
    ended = datetime.now(timezone.utc).isoformat()
    count, artifacts, changed, index_error = None, None, [], None
    try:
        count, artifacts = refresh()
        _, after_sources = collect()
        changed = [row for row in after_sources
                   if before.get(row['artifact']) != row['sha256']]
        archive = STORE / 'artifact_snapshots'
        archive.mkdir(parents=True, exist_ok=True)
        for row in changed:
            source = ROOT / row['artifact']
            destination = archive / f"{row['sha256']}{source.suffix}"
            if not destination.exists():
                destination.write_bytes(canonical_bytes(source))
            if digest(destination) != row['sha256']:
                raise RuntimeError(f"Archived result hash mismatch: {row['artifact']}")
    except Exception as error:
        index_error = f'{type(error).__name__}: {error}'
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    event = {
        'schema_version': 1, 'run_id': uuid.uuid4().hex,
        'started_utc': began, 'ended_utc': ended,
        'script': script_path.relative_to(ROOT).as_posix(),
        'script_sha256': digest(script_path), 'arguments': arguments,
        'git_commit': commit.stdout.strip() if commit.returncode == 0 else None,
        'exit_code': result.returncode, 'indexed_records': count,
        'indexed_artifacts': artifacts,
        'changed_artifacts': changed,
        'index_error': index_error,
    }
    STORE.mkdir(parents=True, exist_ok=True)
    with (STORE / 'run_history.jsonl').open('a', encoding='utf-8', newline='\n') as file:
        file.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + '\n')
    if index_error:
        print(index_error, file=sys.stderr)
        return 1
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('refresh')
    runner = commands.add_parser('run')
    runner.add_argument('script')
    runner.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == 'refresh':
        count, sources = refresh()
        print(f'Indexed {count} records from {sources} result files')
    else:
        arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
        raise SystemExit(run(args.script, arguments))


if __name__ == '__main__':
    main()
