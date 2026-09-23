# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from codex_limit_tools.tui import lines_for

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Licensing(unittest.TestCase):
    def test_license_and_version_are_offline_without_state_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            env = {**os.environ, 'XDG_STATE_HOME':str(root/'state'), 'XDG_CONFIG_HOME':str(root/'config')}
            commands = [[sys.executable,str(ROOT/name)] for name in ('codex-limit-estimator','codex-usage','codex-quota')]
            commands.append(['bash',str(ROOT/'install.sh')])
            for command in commands:
                license_result = subprocess.run(command+['--license'],env=env,capture_output=True,text=True,timeout=5)
                self.assertEqual(license_result.returncode,0,license_result.stderr)
                self.assertEqual(license_result.stdout,(ROOT/'LICENSE').read_text())
                version = subprocess.run(command+['--version'],env=env,capture_output=True,text=True,timeout=5)
                self.assertEqual(version.returncode,0,version.stderr)
                self.assertIn('GPLv3',version.stdout)
            self.assertFalse((root/'state').exists())
            self.assertFalse((root/'config').exists())

    def test_human_startup_and_tui_notice_leave_json_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            command = [sys.executable,str(ROOT/'codex-usage'),'--data-dir',str(root/'state'),
                       '--codex-home',str(root/'codex'),'--prices',str(ROOT/'prices.json')]
            human = subprocess.run(command,capture_output=True,text=True,timeout=5)
            self.assertEqual(human.returncode,0,human.stderr)
            self.assertIn('GPLv3',human.stderr)
            self.assertIn('no warranty',human.stderr)
            machine = subprocess.run(command+['--json'],capture_output=True,text=True,timeout=5)
            self.assertEqual(machine.returncode,0,machine.stderr)
            self.assertEqual(machine.stderr,'')
            self.assertEqual(json.loads(machine.stdout)['totals']['input'],0)
        rows = lines_for({},None,[],{})
        self.assertIn('GPLv3','\n'.join(r[0] for r in rows))
