# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Sentinel regressions for command boundaries, using only synthetic state."""
from contextlib import closing
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_limit_tools import cli, installer
from codex_limit_tools.common import connect, daemon_lock, put
from codex_limit_tools.quota import RPC, MonitorError
from test_history import legacy_database

ROOT = pathlib.Path(__file__).resolve().parents[1]


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mode, path.stat().st_mtime_ns


class SideEffects(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.state = self.root/'state'
        self.outside = self.root/'outside'
        self.outside.mkdir()
        self.sentinel = self.outside/'sentinel'
        self.sentinel.write_text('synthetic sentinel\n')
        self.before = fingerprint(self.sentinel)
        self.addCleanup(lambda: self.assertEqual(fingerprint(self.sentinel), self.before))
        self.env = {**os.environ, 'HOME':str(self.root/'home'), 'CODEX_HOME':str(self.root/'codex'),
                    'XDG_STATE_HOME':str(self.root/'states'), 'XDG_CONFIG_HOME':str(self.root/'config')}

    def command(self, name, *args, ok=True, env=None):
        result = subprocess.run([sys.executable, str(ROOT/name), *args], env=env or self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout+result.stderr)
        return result

    def test_export_replaces_links_without_touching_their_targets(self):
        for suffix in ('.json', '.csv'):
            for kind in ('symlink', 'hardlink'):
                dest = self.root/(kind+suffix)
                if kind == 'symlink':
                    dest.symlink_to(self.sentinel)
                else:
                    os.link(self.sentinel, dest)
                cli.export_file(dest, {'daily':[]}, 'daily')
                self.assertEqual(fingerprint(self.sentinel), self.before)
                self.assertFalse(dest.is_symlink())
                self.assertEqual(dest.stat().st_mode & 0o777, 0o600)

    def test_failed_export_preserves_existing_destination(self):
        dest = self.root/'export.json'
        dest.write_text('previous complete export')
        with self.assertRaises(ValueError):
            cli.export_file(dest, {'invalid':float('nan')}, 'daily')
        self.assertEqual(dest.read_text(), 'previous complete export')
        with patch('codex_limit_tools.common.os.replace', side_effect=OSError('synthetic disk error')):
            with self.assertRaises(OSError):
                cli.export_file(dest, {'daily':[]}, 'daily')
        self.assertEqual(dest.read_text(), 'previous complete export')

    def test_prices_import_replaces_link_and_preserves_frozen_run(self):
        dest = self.root/'config/codex-limit-tools/prices.json'
        dest.parent.mkdir(parents=True)
        dest.symlink_to(self.sentinel)
        with closing(connect(self.state)) as db:
            put(db, 'config', {'prices':{'name':'synthetic frozen prices'}})
            db.commit()
            before = list(db.iterdump())
            self.command('codex-limit-estimator', 'prices', 'import', str(ROOT/'prices.json'),
                         '--data-dir', str(self.state))
            self.assertEqual(list(db.iterdump()), before)
        self.assertFalse(dest.is_symlink())
        self.assertEqual(fingerprint(self.sentinel), self.before)

    def test_invalid_start_does_not_create_or_migrate_database(self):
        self.command('codex-limit-estimator', 'start', 'invalid', '--data-dir', str(self.state), ok=False)
        self.assertFalse(self.state.exists())
        old = legacy_database(self.state)
        self.addCleanup(old.close)
        before = list(old.iterdump())
        self.command('codex-limit-estimator', 'start', '--data-dir', str(self.state), ok=False)
        self.assertEqual(list(old.iterdump()), before)
        self.assertEqual(old.execute('PRAGMA user_version').fetchone()[0], 0)
        self.assertFalse(list(self.state.glob('*.backup-*')))

    def test_resume_without_config_preserves_controls_and_schema(self):
        with closing(legacy_database(self.state)) as db:
            db.execute("DELETE FROM kv WHERE key='config'")
            put(db, 'control', {'paused':True, 'shutdown':True})
            db.commit()
            before = list(db.iterdump())
            self.command('codex-limit-estimator', 'resume', '--data-dir', str(self.state), ok=False)
            self.assertEqual(list(db.iterdump()), before)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
        self.assertFalse(list(self.state.glob('*.backup-*')))

    def test_mutable_state_aliases_are_rejected(self):
        with closing(connect(self.outside/'database')) as db:
            put(db, 'sentinel', 'synthetic original')
            db.commit()
        database = self.outside/'database/tracking.sqlite3'
        original = fingerprint(database)
        for kind in ('symlink', 'hardlink'):
            state = self.root/kind
            state.mkdir()
            alias = state/'tracking.sqlite3'
            if kind == 'symlink':alias.symlink_to(database)
            else:os.link(database, alias)
            with self.assertRaises(ValueError):
                with closing(connect(state)) as db:put(db, 'sentinel', 'changed'); db.commit()
            alias.unlink()
            self.assertEqual(fingerprint(database), original)
        for name in ('tracking.sqlite3-wal', 'tracking.sqlite3-shm', 'tracking.sqlite3-journal', 'daemon.lock'):
            state = self.root/name
            state.mkdir()
            (state/name).symlink_to(self.sentinel)
            with self.assertRaises((ValueError, OSError)):
                if name == 'daemon.lock':
                    with daemon_lock(state):pass
                else:
                    with closing(connect(state)):pass

    def test_new_private_state_backups_and_daemon_logs_are_owner_only(self):
        previous = os.umask(0o022)
        self.addCleanup(os.umask, previous)
        self.state.mkdir(mode=0o755)
        with closing(connect(self.state)):pass
        legacy = self.root/'legacy'
        legacy_database(legacy).close()
        with closing(connect(legacy)):pass
        with patch('codex_limit_tools.cli.subprocess.Popen'):
            cli.start_process(self.state)
        backup = installer.backup_database(legacy, 'synthetic')
        files = [self.state/'tracking.sqlite3', self.state/'daemon.lock', self.state/'daemon.log',
                 backup, *legacy.glob('*.backup-v0-*')]
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in files))

    def test_daemon_log_alias_does_not_spawn_process(self):
        self.state.mkdir()
        (self.state/'daemon.log').symlink_to(self.sentinel)
        with patch('codex_limit_tools.cli.subprocess.Popen') as process:
            with self.assertRaises((ValueError, OSError)):cli.start_process(self.state)
            process.assert_not_called()

    def test_installer_rejects_symlinked_internal_directories(self):
        for child in ('lib', 'bin'):
            prefix = self.root/child
            prefix.mkdir()
            (prefix/child).symlink_to(self.outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'directory'):
                installer.install(ROOT, prefix, [self.state], self.root/'config')
        self.assertEqual(list(self.outside.iterdir()), [self.sentinel])

    def test_entry_points_do_not_write_package_bytecode(self):
        bundle = self.root/'bundle'
        bundle.mkdir()
        installer.copy_payload(ROOT, bundle)
        env = dict(self.env)
        env.pop('PYTHONDONTWRITEBYTECODE', None)
        # The runner's sitecustomize is outside the bundle and is not part of this assertion.
        for name in installer.COMMANDS:
            result = subprocess.run([sys.executable, str(bundle/name), '--help'], env=env,
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0)
        result = subprocess.run(['bash', str(bundle/'install.sh'), '--help'], env=env,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(list(bundle.rglob('__pycache__')))

    def test_offline_commands_leave_history_unchanged(self):
        with closing(connect(self.state)) as db:
            put(db, 'control', {'paused':True, 'shutdown':True})
            db.execute("INSERT INTO checkpoints VALUES ('synthetic',1,2,'synthetic','error',NULL,'expired')")
            db.commit()
            before = list(db.iterdump())
            for action in ('status', 'report', 'runs', 'segments', 'analyze', 'ui'):
                self.command('codex-limit-estimator', action, '--data-dir', str(self.state), '--json')
            self.command('codex-limit-estimator', 'checkpoint', '--request-id', 'synthetic',
                         '--data-dir', str(self.state), '--json')
            for view in ('daily', 'segments', 'snapshots', 'analysis'):
                self.command('codex-limit-estimator', 'export', '--view', view, '--output',
                             str(self.root/(view+'.json')), '--data-dir', str(self.state))
            self.assertEqual(list(db.iterdump()), before)
        for target in ('path', 'validate'):
            self.command('codex-limit-estimator', 'prices', target)

    def test_usage_locks_offline_indexing_and_reads_active_legacy_history(self):
        with closing(legacy_database(self.state)) as db:
            before = list(db.iterdump())
            with daemon_lock(self.state):
                self.command('codex-usage', '--data-dir', str(self.state), '--json')
            self.assertEqual(list(db.iterdump()), before)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
        self.assertFalse(list(self.state.glob('*.backup-*')))
        def inspect_lock(db, home):
            with self.assertRaisesRegex(ValueError, 'active'):
                with daemon_lock(self.state):pass
            return {}
        with patch.dict(os.environ, self.env), patch.object(cli, 'index', side_effect=inspect_lock), \
                patch('sys.stdout', new_callable=io.StringIO):
            cli.usage(['--data-dir', str(self.state), '--json'])

    def test_rpc_transport_rejects_workload_methods(self):
        rpc = object.__new__(RPC)
        rpc.p = type('Process', (), {'stdin':io.BytesIO()})()
        for method in ('turn/start', 'thread/start', 'item/steer', 'heartbeat'):
            with self.assertRaisesRegex(MonitorError, 'not allowed'):
                rpc.send({'id':1, 'method':method})
            with self.assertRaisesRegex(MonitorError, 'not allowed'):
                rpc.call(method)
        self.assertEqual(rpc.p.stdin.getvalue(), b'')
