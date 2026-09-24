# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
from contextlib import closing
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_limit_tools import installer
from codex_limit_tools.common import SCHEMA_VERSION, daemon_lock
from test_history import legacy_database

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Installation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root/'bundle spazi è'
        self.source.mkdir()
        for name in (*installer.PAYLOAD, *(n for n in installer.OPTIONAL_PAYLOAD if (ROOT/n).is_file())):
            target = self.source/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/name, target)
        (self.source/'development-only.txt').write_text('synthetic development file')
        (self.source/'.env').write_text('SYNTHETIC_TEST_ONLY=true')
        (self.source/'codex_limit_tools/extra.py').write_text('synthetic_extra = True')
        self.prefix = self.root/'prefix spazi è'
        self.state = self.root/'state'
        self.config = self.root/'config/codex-limit-tools'
        self.env = {**os.environ, 'XDG_CONFIG_HOME':str(self.root/'config'),
                    'XDG_STATE_HOME':str(self.root/'states'), 'PYTHONDONTWRITEBYTECODE':'1'}
        self.dest = self.prefix/'lib/codex-limit-tools'

    def script(self, *args, state=None, ok=True):
        entry = [sys.executable,str(self.source/'install.py')] if os.name == 'nt' else ['bash',str(self.source/'install.sh')]
        result = subprocess.run([*entry,'--prefix',str(self.prefix),
                                 '--data-dir',str(state or self.state),*args],env=self.env,
                                text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode == 0,ok,result.stdout+result.stderr)
        return result

    def command(self, name, *args):
        result = subprocess.run([str(self.prefix/'bin'/(name+'.cmd' if os.name == 'nt' else name)),*args],env=self.env,
                                text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        return result

    def test_fresh_payload_old_commands_and_standalone_entry_points(self):
        (self.prefix/'bin').mkdir(parents=True)
        previous = self.prefix/'bin'/installer.COMMAND_FILES[1]
        previous.write_text('synthetic previous standalone command')
        watcher = self.prefix/'bin/watch-codex-quota'
        watcher.write_text('synthetic independent watcher')
        self.script()
        self.assertEqual(watcher.read_text(),'synthetic independent watcher')
        self.assertEqual(next((self.prefix/'bin').glob(installer.COMMAND_FILES[1]+'.backup-*')).read_text(),
                         'synthetic previous standalone command')
        self.assertFalse((self.dest/'.env').exists())
        self.assertFalse((self.dest/'development-only.txt').exists())
        self.assertFalse((self.dest/'codex_limit_tools/extra.py').exists())
        self.assertEqual((self.dest/'LICENSE').read_bytes(),(ROOT/'LICENSE').read_bytes())
        self.assertEqual((self.dest/'NOTICE').read_bytes(),(ROOT/'NOTICE').read_bytes())
        for name in installer.COMMANDS:
            self.assertIn('usage:',self.command(name,'--help').stdout)
            self.assertIn('GPLv3',self.command(name,'--version').stdout)
            self.assertEqual(self.command(name,'--license').stdout,(ROOT/'LICENSE').read_text())
        usage = json.loads(self.command('codex-usage','--codex-home',str(self.root/'empty-codex'),
                                        '--data-dir',str(self.root/'usage-state'),'--json').stdout)
        self.assertEqual(usage['totals']['input'],0)
        self.script(ok=False)

    def test_upgrade_preserves_prices_history_and_old_package_then_migrates(self):
        self.script()
        (self.dest/'preserved.txt').write_text('synthetic original package')
        prices = json.loads((self.config/'prices.json').read_text())
        prices['name'] = 'synthetic custom external prices'
        (self.config/'prices.json').write_text(json.dumps(prices))
        frozen = (self.config/'prices.json').read_bytes()
        state = self.root/'legacy'
        old = legacy_database(state)
        self.addCleanup(old.close)
        expected = list(old.iterdump())
        self.script('--update',state=state)
        previous = next(self.dest.parent.glob('codex-limit-tools.backup-*'))
        self.assertEqual((previous/'preserved.txt').read_text(),'synthetic original package')
        self.assertEqual((self.config/'prices.json').read_bytes(),frozen)
        self.assertEqual(list(old.iterdump()),expected)
        backup = next(state.glob('*.backup-upgrade-*'))
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(list(db.iterdump()),expected)
        before = json.loads(self.command('codex-limit-estimator','report','--data-dir',str(state),'--json').stdout)
        self.command('codex-limit-estimator','migrate','--data-dir',str(state))
        after = json.loads(self.command('codex-limit-estimator','report','--data-dir',str(state),'--json').stdout)
        self.assertEqual(before,after)
        self.assertEqual(after['daily'][0]['api_equivalent_per_100'],400)
        self.assertEqual(old.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
        self.assertEqual((self.config/'prices.json').read_bytes(),frozen)
        self.assertTrue(list(state.glob('*.backup-v0-*')))

    def test_active_daemon_or_invalid_payload_leaves_installation_intact(self):
        self.script()
        original = (self.dest/'codex_limit_tools/cli.py').read_bytes()
        with daemon_lock(self.state):
            result = self.script('--upgrade',ok=False)
            self.assertIn('Collector is active',result.stderr)
        (self.source/'codex_limit_tools/cli.py').write_text('raise RuntimeError("synthetic invalid package")')
        self.script('--upgrade',ok=False)
        self.assertEqual((self.dest/'codex_limit_tools/cli.py').read_bytes(),original)
        self.assertFalse(list(self.dest.parent.glob('codex-limit-tools.backup-*')))

    def test_switch_failure_restores_previous_package_and_commands(self):
        self.script()
        (self.dest/'preserved.txt').write_text('original')
        read_command = lambda n: (self.prefix/'bin'/n).read_bytes() if os.name == 'nt' else os.readlink(self.prefix/'bin'/n)
        targets = {n:read_command(n) for n in installer.COMMAND_FILES}
        replace = os.replace
        failed_once = False
        def fail(source,dest):
            nonlocal failed_once
            if pathlib.Path(dest).name == installer.COMMAND_FILES[1] and not failed_once:
                failed_once = True
                raise OSError('synthetic switch failure')
            return replace(source,dest)
        with patch('codex_limit_tools.installer.os.replace',side_effect=fail):
            with self.assertRaisesRegex(OSError,'synthetic switch failure'):
                installer.install(self.source,self.prefix,[self.state],self.config,True)
        self.assertEqual((self.dest/'preserved.txt').read_text(),'original')
        self.assertEqual({n:read_command(n) for n in installer.COMMAND_FILES},targets)
        self.assertTrue(list(self.dest.parent.glob('codex-limit-tools.failed-*')))

    def test_all_requested_state_directories_are_locked(self):
        self.script()
        other = self.root/'other-state'
        with daemon_lock(other):
            result = self.script('--upgrade','--data-dir',str(other),ok=False)
            self.assertIn('Collector is active',result.stderr)
        self.assertFalse(list(self.dest.parent.glob('codex-limit-tools.backup-*')))

    def test_upgrade_backs_up_multiple_states_and_launcher_exit_code(self):
        self.script()
        other = self.root/'second state'
        for path in (self.state, other):
            # Install only creates a lock directory; populate synthetic legacy state.
            with closing(sqlite3.connect(path/'tracking.sqlite3')) if path.exists() else closing(legacy_database(path)) as db:
                db.execute('CREATE TABLE IF NOT EXISTS sentinel(value TEXT)')
                db.execute("INSERT INTO sentinel VALUES ('synthetic')")
                db.commit()
        self.script('--upgrade','--data-dir',str(other))
        for path in (self.state,other):
            backups=list(path.glob('*.backup-upgrade-*'))
            self.assertEqual(len(backups),1)
            with closing(sqlite3.connect(backups[0])) as db:
                self.assertEqual(db.execute('SELECT value FROM sentinel').fetchone()[0],'synthetic')
        launcher=self.prefix/'bin'/installer.COMMAND_FILES[0]
        result=subprocess.run([str(launcher),'invalid-command'],env=self.env,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,2)
