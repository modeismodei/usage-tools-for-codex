import json
import pathlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from codex_limit_tools import common
from codex_limit_tools.common import connect, daemon_lock, ensure_run, get, put, read_snapshot
from codex_limit_tools.estimate import report
from analysis_fixtures import LARGE


def legacy_database(path):
    """Original schema, deliberately independent of the migration implementation."""
    path.mkdir()
    db = sqlite3.connect(path / 'tracking.sqlite3')
    db.row_factory = sqlite3.Row
    db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE files(path TEXT PRIMARY KEY,identity TEXT,offset INTEGER,thread TEXT,mtime INTEGER);
        CREATE TABLE turns(thread TEXT,turn TEXT,model TEXT,PRIMARY KEY(thread,turn,model));
        CREATE TABLE responses(id TEXT PRIMARY KEY,thread TEXT,turn TEXT,ts REAL,inp INTEGER,cached INTEGER,writes INTEGER,out INTEGER,reason INTEGER,direct_model TEXT);
        CREATE INDEX response_ts ON responses(ts);
        CREATE TABLE segments(id INTEGER PRIMARY KEY,started REAL,reason TEXT,label TEXT,price_hash TEXT,config TEXT);
        CREATE TABLE snapshots(id INTEGER PRIMARY KEY,segment INTEGER,ts REAL,used REAL,reset_at REAL,metrics TEXT);
        CREATE TABLE events(id INTEGER PRIMARY KEY,ts REAL,kind TEXT,detail TEXT);
        INSERT INTO files VALUES ('synthetic.log','synthetic',10,'synthetic',1);
        INSERT INTO turns VALUES ('synthetic','turn','synthetic');
        INSERT INTO responses VALUES ('response','synthetic','turn',100,100,0,0,10,0,'synthetic');
        INSERT INTO events VALUES (1,100,'baseline','synthetic');
    ''')
    config = dict(prices={'name': 'frozen', 'models': {}}, started_at=10, label='synthetic')
    put(db, 'config', config)
    db.execute('INSERT INTO segments VALUES (7,100,?,?,?,?)',
               ('legacy', 'synthetic', 'price-a', json.dumps({'resolution': 1})))
    for s in LARGE:
        db.execute('INSERT INTO snapshots VALUES (?,7,?,?,?,?)',
                   (s['id'], s['ts'], s['used'], s['reset_at'], json.dumps(s['metrics'])))
    db.commit()
    return db


class History(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name) / 'state'

    def test_legacy_backup_and_repeatable_migration(self):
        old = legacy_database(self.path)
        self.addCleanup(old.close)
        expected = report(old, {})
        saved = {t: [tuple(r) for r in old.execute('SELECT * FROM '+t)]
                 for t in ('kv', 'files', 'turns', 'responses', 'snapshots', 'events')}
        db = connect(self.path)
        self.addCleanup(db.close)
        self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], common.SCHEMA_VERSION)
        self.assertEqual(report(db, {}), expected)
        self.assertIsNone(db.execute('SELECT run_id FROM segments').fetchone()[0])
        for table, rows in saved.items():
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM '+table)], rows)
        backups = list(self.path.glob('*.backup-*'))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as backup:
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 0)
            self.assertEqual(backup.execute('SELECT count(*) FROM snapshots').fetchone()[0], 2)
        c = ensure_run(db, get(db, 'config'))
        db.commit()
        again = connect(self.path)
        self.addCleanup(again.close)
        self.assertEqual(ensure_run(again, get(again, 'config'))['run_id'], c['run_id'])
        self.assertEqual(again.execute('SELECT count(*) FROM runs').fetchone()[0], 1)
        self.assertEqual(len(list(self.path.glob('*.backup-*'))), 1)
        fresh = dict(c)
        fresh.pop('run_id')
        self.assertNotEqual(ensure_run(again, fresh)['run_id'], c['run_id'])
        self.assertIsNone(again.execute('SELECT run_id FROM segments').fetchone()[0])

    def test_failure_rolls_back_schema_and_leaves_backup(self):
        legacy_database(self.path).close()
        migration = common._migration_v1
        def fail(db):
            migration(db)
            raise RuntimeError('synthetic migration failure')
        with patch.object(common, '_migration_v1', fail):
            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                connect(self.path)
        with closing(sqlite3.connect(self.path / 'tracking.sqlite3')) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
            self.assertNotIn('run_id', [r[1] for r in db.execute('PRAGMA table_info(segments)')])
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 2)
        self.assertEqual(len(list(self.path.glob('*.backup-*'))), 1)
        connect(self.path).close()

    def test_active_legacy_collector_blocks_migration_but_allows_shutdown(self):
        legacy_database(self.path).close()
        with daemon_lock(self.path):
            with self.assertRaisesRegex(ValueError, 'shutdown'):
                connect(self.path)
            db = connect(self.path, migrate=False)
            put(db, 'control', {'shutdown': True})
            db.commit()
            db.close()
        self.assertFalse(list(self.path.glob('*.backup-*')))

    def test_newer_schema_rejected_without_backup(self):
        db = connect(self.path)
        db.execute('PRAGMA user_version=999')
        db.close()
        for readonly in (False, True):
            with self.assertRaisesRegex(ValueError, 'newer database'):
                connect(self.path, readonly=readonly)
        self.assertFalse(list(self.path.glob('*.backup-*')))

    def test_consistent_read_during_writer_commit(self):
        writer = connect(self.path)
        self.addCleanup(writer.close)
        put(writer, 'value', 1)
        writer.commit()
        reader = connect(self.path, readonly=True)
        self.addCleanup(reader.close)
        with read_snapshot(reader):
            self.assertEqual(get(reader, 'value'), 1)
            put(writer, 'value', 2)
            writer.commit()
            self.assertEqual(get(reader, 'value'), 1)
            with self.assertRaises(sqlite3.OperationalError):
                put(reader, 'value', 3)
        self.assertEqual(get(reader, 'value'), 2)
