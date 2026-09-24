# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Native PowerShell doctor checks; no Pester or live Codex required."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCTOR = ROOT/'doctor-windows.ps1'


@unittest.skipUnless(os.name == 'nt', 'Native Windows PowerShell doctor')
class WindowsDoctor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.shell = pathlib.Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        self.env = {**os.environ, 'PSModulePath':str(self.shell.parent/'Modules'),
                    'USERPROFILE':str(self.root), 'LOCALAPPDATA':str(self.root/'local'),
                    'DOCTOR_SOURCE':str(DOCTOR), 'DOCTOR_PYTHON':sys.executable}
        # An invalid .exe proves presence checks never try to execute Codex.
        self.fake = self.root/'GUI bundle spaces'/ 'codex.exe'
        self.fake.parent.mkdir()
        self.fake.write_bytes(b'synthetic sentinel, not an executable')

    def run_doctor(self, *args, command=None):
        options = ['-Command', command] if command else ['-File', str(DOCTOR), *args]
        # Local reviewed script; policy is process-scoped, never persisted.
        return subprocess.run([str(self.shell), '-NoProfile', '-NonInteractive',
                               '-ExecutionPolicy', 'RemoteSigned', *options],
                              env=self.env, capture_output=True, text=True, timeout=25)

    def test_runs_without_python_and_does_not_fallback_for_explicit_path(self):
        result = self.run_doctor('-PythonPath', str(self.root/'missing.exe'),
                                 '-CodexPath', str(self.fake), '-NoColor')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('[MISSING]', result.stdout)
        self.assertIn('No usable interpreter found', result.stdout)
        self.assertIn('cannot be checked until Python works', result.stdout)
        self.assertIn('[FOUND', result.stdout)
        self.assertEqual(self.fake.read_bytes(), b'synthetic sentinel, not an executable')

    def test_real_interpreter_probe_on_builtin_powershell(self):
        result = self.run_doctor('-PythonPath', sys.executable, '-CodexPath', str(self.fake), '-NoColor')
        self.assertIn(result.returncode, (0, 2), result.stderr)
        self.assertIn('[OK     ] sqlite3', result.stdout)
        self.assertIn('[OK     ] ctypes', result.stdout)
        self.assertIn('[OK     ] msvcrt', result.stdout)
        self.assertIn('Not executed or authenticated', result.stdout)
        self.assertNotIn('\x1b', result.stdout)
        self.assertFalse(list(self.root.rglob('*.sqlite3')))

    def test_install_manager_launcher_is_not_executed(self):
        command = """
. $env:DOCTOR_SOURCE
function Get-Item {
    [pscustomobject]@{FullName=$env:DOCTOR_PYTHON;VersionInfo=[pscustomobject]@{ProductName='manage'}}
}
function Invoke-DoctorPythonProbe { throw 'Manager must not be executed' }
exit (Invoke-WindowsDoctor -PythonPath $env:DOCTOR_PYTHON -CodexPath 'missing.exe' -NoColor)
"""
        result = self.run_doctor(command=command)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('No usable interpreter found', result.stdout)
        self.assertNotIn('Manager must not be executed', result.stderr)

    def test_missing_optional_modules_offer_binary_only_install(self):
        # Replace only the probe result; exercise actual status/exit/remediation logic.
        command = """
. $env:DOCTOR_SOURCE
function Invoke-DoctorPythonProbe {
    [pscustomobject]@{version='3.14.0';supported=$true;bits=64;
        modules=[pscustomobject]@{sqlite3=$true;ctypes=$true;msvcrt=$true;curses=$false;pip=$true;venv=$true}}
}
exit (Invoke-WindowsDoctor -PythonPath $env:DOCTOR_PYTHON -CodexPath 'missing.exe' -NoColor)
"""
        result = self.run_doctor(command=command)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('Headless reports and background mode do not require it', result.stdout)
        self.assertIn('--only-binary=:all: windows-curses', result.stdout)
        self.assertIn('separate CLI install is not necessarily needed', result.stdout)

    def test_missing_required_module_and_unsupported_python_are_blocking(self):
        command = """
. $env:DOCTOR_SOURCE
function Invoke-DoctorPythonProbe {
    [pscustomobject]@{version='3.9.0';supported=$false;bits=64;
        modules=[pscustomobject]@{sqlite3=$false;ctypes=$true;msvcrt=$true;curses=$true;pip=$true;venv=$true}}
}
exit (Invoke-WindowsDoctor -PythonPath $env:DOCTOR_PYTHON -CodexPath 'missing.exe' -NoColor)
"""
        result = self.run_doctor(command=command)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('[MISSING] sqlite3', result.stdout)
        self.assertIn('Requires Python 3.10 or newer', result.stdout)
        self.assertIn('not a pip package', result.stdout)

    def test_gui_binary_is_discovered_without_cli_and_help_needs_no_python(self):
        target = self.root/'local/OpenAI/Codex/bin/synthetic/codex.exe'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'synthetic GUI executable sentinel')
        command = """
. $env:DOCTOR_SOURCE
$env:PATH = ''
$found = Find-DoctorCodex
if ($found -ne (Join-Path $env:LOCALAPPDATA 'OpenAI\\Codex\\bin\\synthetic\\codex.exe')) { exit 1 }
"""
        result = self.run_doctor(command=command)
        self.assertEqual(result.returncode, 0, result.stderr)
        help_result = self.run_doctor('-Help')
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('Runs even when Python is absent', help_result.stdout)
