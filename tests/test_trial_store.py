"""Regression checks for the unified research ledger."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import trial_store


class TrialStoreTest(unittest.TestCase):
    def test_refresh_is_deterministic_and_preserves_all_parameter_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / 'results' / 'alpha'
            study.mkdir(parents=True)
            (study / 'summary.csv').write_text(
                'window,period,mean_ic,months\n10,discovery,0.04,12\n'
                '20,discovery,-0.01,12\n', encoding='utf-8')
            with (patch.object(trial_store, 'ROOT', root),
                  patch.object(trial_store, 'RESULTS', root / 'results'),
                  patch.object(trial_store, 'STORE', root / 'results' / 'trial_store')):
                self.assertEqual(trial_store.refresh(), (2, 1))
                output = (root / 'results' / 'trial_store' / 'records.jsonl').read_bytes()
                self.assertEqual(trial_store.refresh(), (2, 1))
                self.assertEqual(output, (root / 'results' / 'trial_store' /
                                          'records.jsonl').read_bytes())
                rows = [json.loads(line) for line in output.splitlines()]
                self.assertEqual({r['parameters']['window'] for r in rows}, {10, 20})
                self.assertEqual({r['evidence_level'] for r in rows}, {'signal_screen'})
                self.assertTrue(all(r['historical_execution_verified'] is False
                                    for r in rows))

    def test_run_records_changed_artifact_and_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / 'results' / 'alpha'
            study.mkdir(parents=True)
            (study / 'summary.csv').write_text('window,mean_ic\n10,0.01\n', encoding='utf-8')
            (root / 'trial.py').write_text(
                "from pathlib import Path\n"
                "Path('results/alpha/summary.csv').write_text("
                "'window,mean_ic\\n10,0.02\\n', encoding='utf-8')\n",
                encoding='utf-8')
            with (patch.object(trial_store, 'ROOT', root),
                  patch.object(trial_store, 'RESULTS', root / 'results'),
                  patch.object(trial_store, 'STORE', root / 'results' / 'trial_store')):
                self.assertEqual(trial_store.run('trial.py', []), 0)
                self.assertEqual(trial_store.run('trial.py', []), 0)
                history = [json.loads(line) for line in
                           (root / 'results' / 'trial_store' / 'run_history.jsonl')
                           .read_text(encoding='utf-8').splitlines()]
                self.assertEqual(len(history), 2)
                self.assertEqual(len(history[0]['changed_artifacts']), 1)
                self.assertEqual(history[1]['changed_artifacts'], [])
                snapshot = next((root / 'results' / 'trial_store' /
                                 'artifact_snapshots').glob('*.csv'))
                self.assertIn('0.02', snapshot.read_text(encoding='utf-8'))

    def test_failed_script_is_kept_in_run_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'results').mkdir()
            (root / 'broken.py').write_text('raise SystemExit(7)\n', encoding='utf-8')
            with (patch.object(trial_store, 'ROOT', root),
                  patch.object(trial_store, 'RESULTS', root / 'results'),
                  patch.object(trial_store, 'STORE', root / 'results' / 'trial_store')):
                self.assertEqual(trial_store.run('broken.py', []), 7)
                event = json.loads((root / 'results' / 'trial_store' /
                                    'run_history.jsonl').read_text(encoding='utf-8'))
                self.assertEqual(event['exit_code'], 7)
                self.assertEqual(event['indexed_records'], 0)


if __name__ == '__main__':
    unittest.main()
