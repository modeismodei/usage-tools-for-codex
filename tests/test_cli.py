import csv
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from codex_limit_tools.common import connect, ensure_run
from analysis_fixtures import LARGE
from test_history import legacy_database

ROOT = pathlib.Path(__file__).resolve().parents[1]


class AnalysisCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.path = self.root / 'state'
        self.db = connect(self.path)
        self.addCleanup(self.db.close)
        self.run = ensure_run(self.db, dict(prices={'name':'synthetic','models':{}}, started_at=100, label='synthetic'))['run_id']
        self.db.execute('INSERT INTO segments VALUES (1,100,?,?,?, ?,?)',
                        ('baseline','synthetic','price-a',json.dumps({'resolution':1,'meter_hash':'meter-a'}),self.run))
        for s in LARGE:
            self.db.execute('INSERT INTO snapshots VALUES (?,1,?,?,?,?)',
                            (s['id'],s['ts'],s['used'],s['reset_at'],json.dumps(s['metrics'])))
        self.db.commit()

    def command(self, *args, ok=True, path=None):
        result = subprocess.run([sys.executable,str(ROOT/'codex-limit-estimator'),*args,
                                 '--data-dir',str(path or self.path),'--codex-bin','unused-synthetic-command'],
                                text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout+result.stderr)
        return result

    def test_offline_commands_and_json_do_not_change_state(self):
        before = list(self.db.iterdump())
        runs = json.loads(self.command('runs','--json').stdout)
        self.assertEqual(runs['runs'][0]['id'],self.run)
        segments = json.loads(self.command('segments','--run',self.run,'--json').stdout)
        self.assertEqual(segments['segments'][0]['remaining_start'],73)
        for args in (['--run',self.run], ['--segments','1,1'], ['--from','1970-01-01','--to','1970-01-01'],
                     ['--label','synthetic','--group-by','overall'], ['--run',self.run,'--group-by','day'],
                     ['--snapshot-from','1','--snapshot-to','2'],
                     ['--run',self.run,'--remaining-from','73','--remaining-to','40']):
            result = json.loads(self.command('analyze',*args,'--json').stdout)
            self.assertEqual(result['schema_version'],2)
            self.assertEqual(result['groups'][0]['estimate']['cost'],400)
        text = self.command('analyze','--run',self.run).stdout
        self.assertIn('73% -> 40%',text)
        self.assertIn('snapshots 1 -> 2',text)
        self.assertIn('33.00 quota pp',text)
        self.assertIn(self.run,text)
        report = json.loads(self.command('report','--json').stdout)
        self.assertFalse(report['daemon_running'])
        self.assertEqual(report['daily'][0]['api_equivalent_per_100'],400)
        self.assertEqual(list(self.db.iterdump()),before)

    def test_exports_keep_default_csv_and_reproducible_history(self):
        from codex_limit_tools.render import DAILY_CSV_FIELDS
        for view in ('daily','segments','snapshots','analysis'):
            for suffix in ('csv','json'):
                output = self.root / (view+'.'+suffix)
                args = ['export','--output',str(output)]
                if view != 'daily':args += ['--view',view]
                if view == 'analysis':args += ['--run',self.run]
                self.command(*args)
                if suffix == 'json':
                    data = json.loads(output.read_text())
                    self.assertEqual(data['schema_version'],2)
                    if view == 'analysis':self.assertEqual(data['groups'][0]['delta']['cost'],132)
                    elif view == 'snapshots':self.assertEqual([r['id'] for r in data['snapshots']],[1,2])
                    else:self.assertTrue(data[view])
                else:
                    with output.open() as stream:
                        reader = csv.DictReader(stream)
                        rows = list(reader)
                    self.assertTrue(rows)
                    if view == 'daily':self.assertEqual(reader.fieldnames,DAILY_CSV_FIELDS)
                    if view == 'analysis':
                        self.assertEqual(float(rows[0]['cost_per_100']),400)
                        self.assertEqual(json.loads(rows[0]['source_run_ids']),[self.run])

    def test_invalid_selectors_are_errors_and_do_not_mutate(self):
        before = list(self.db.iterdump())
        cases = [('analyze','--run','missing'),('analyze','--segments','999'),
                 ('analyze','--segments','1,,2'),('analyze','--remaining-from','40','--remaining-to','73'),
                 ('analyze','--from','1970-01-01T00:00:00'),('analyze','--across-runs'),
                 ('report','--segments','1'),('export','--view','analysis'),('runs','unexpected')]
        for args in cases:
            self.command(*args,ok=False)
        self.assertEqual(list(self.db.iterdump()),before)
        missing = self.root/'missing'
        self.command('analyze','--run','missing',path=missing,ok=False)
        self.assertFalse(missing.exists())

    def test_legacy_history_reads_without_migration(self):
        path = self.root/'legacy'
        db = legacy_database(path)
        self.addCleanup(db.close)
        before = list(db.iterdump())
        data = json.loads(self.command('analyze','--run','legacy','--json',path=path).stdout)
        self.assertEqual(data['groups'][0]['estimate']['cost'],400)
        self.command('status',path=path)
        self.assertEqual(list(db.iterdump()),before)
        self.assertFalse(list(path.glob('*.backup-*')))
