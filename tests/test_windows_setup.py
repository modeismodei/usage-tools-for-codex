# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Windows onboarding in temporary homes; dependency downloads and user PATH are mocked."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_limit_tools.quota import resolve_executable, MonitorError

ROOT = pathlib.Path(__file__).resolve().parents[1]


class PosixResolution(unittest.TestCase):
    def test_posix_never_reads_windows_configuration(self):
        with patch('codex_limit_tools.quota.os.name', 'posix'), patch('pathlib.Path.home', side_effect=AssertionError('Windows lookup')):
            self.assertEqual(resolve_executable('codex'), 'codex')
            self.assertEqual(resolve_executable('/synthetic/codex'), '/synthetic/codex')


@unittest.skipUnless(os.name == 'nt', 'Native Windows onboarding')
class WindowsSetup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)/'home spaces \u00e8'
        self.root.mkdir()
        self.shell = pathlib.Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        self.config = self.root/'.local/share/usage-tools-for-codex/windows.json'
        self.fake = self.root/'GUI bundle/codex.exe'
        self.fake.parent.mkdir()
        self.fake.write_bytes(b'not an executable: must never run')
        self.env = {**os.environ, 'USERPROFILE':str(self.root), 'HOME':str(self.root),
                    'LOCALAPPDATA':str(self.root/'local'), 'XDG_STATE_HOME':str(self.root/'state'),
                    'XDG_CONFIG_HOME':str(self.root/'config'), 'CODEX_HOME':str(self.root/'codex'),
                    'PSModulePath':str(self.shell.parent/'Modules'), 'SETUP_ROOT':str(ROOT),
                    'SETUP_PYTHON':sys.executable, 'SETUP_CODEX':str(self.fake)}

    def ps(self, command=None, file=None, args=(), answers=None):
        options = ['-Command', command] if command else ['-File', str(ROOT/file), *args]
        result = subprocess.run([str(self.shell), '-NoProfile', '-ExecutionPolicy', 'RemoteSigned', *options],
                                input=answers, env=self.env, capture_output=True, encoding='utf-8', errors='replace', timeout=60)
        return result

    def save(self, codex=None, **extra):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(json.dumps(dict(version=1, python_path=sys.executable,
                                              codex_path=str(codex or self.fake), **extra)), encoding='utf-8')

    def test_missing_python_stops_without_prompt_install_or_deeper_search(self):
        result = self.ps(r"""
. (Join-Path $env:SETUP_ROOT 'configure.ps1')
function Find-DoctorPython { return $null }
function Read-Host { throw 'Unexpected prompt' }
function Invoke-SetupPython { throw 'Unexpected install' }
exit (Invoke-WindowsConfigure)
""")
        self.assertEqual(result.returncode, 1, result.stdout+result.stderr)
        self.assertIn('https://www.python.org/downloads/windows/', result.stdout)
        self.assertIn('SetEnvironmentVariable', result.stdout)
        self.assertNotIn('Unexpected', result.stdout+result.stderr)
        self.assertFalse(self.config.exists())

    def test_configure_declines_do_not_create_venv_change_path_or_run_codex(self):
        result = self.ps(r"""
. (Join-Path $env:SETUP_ROOT 'configure.ps1')
function Confirm-WindowsSetup { param($Message); return ($Message -like 'Python is outside*') }
function Invoke-SetupPython { throw 'Unapproved dependency command' }
function Set-SetupUserPath { throw 'Unapproved PATH write' }
exit (Invoke-WindowsConfigure -PythonPath $env:SETUP_PYTHON -CodexPath $env:SETUP_CODEX)
""")
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        data = json.loads(self.config.read_text())
        self.assertEqual(data['python_path'].lower(), sys.executable.lower())
        self.assertIsNone(data['codex_path'])
        self.assertFalse((self.config.parent/'venv').exists())
        self.assertFalse((self.root/'.local/bin').exists())
        self.assertIn('doctor-windows.ps1', result.stdout)

    def test_configure_dependency_consent_uses_venv_and_binary_only_installs(self):
        result = self.ps(r"""
. (Join-Path $env:SETUP_ROOT 'configure.ps1')
$script:ready = $false
function Confirm-WindowsSetup { param($Message); return ($Message -notlike 'Create *user PATH') }
function Find-DoctorPython {
    param($RequestedPath)
    [pscustomobject]@{Path=$RequestedPath;Info=[pscustomobject]@{version='3.14';supported=$true;bits=64;
        modules=[pscustomobject]@{sqlite3=$true;ctypes=$true;msvcrt=$true;venv=$true;pip=$script:ready;curses=$script:ready}}}
}
function Invoke-SetupPython {
    param($Executable, $Arguments)
    if ($Arguments -contains 'venv') {
        if ($Arguments[-1] -ne (Join-Path $env:USERPROFILE '.local\share\usage-tools-for-codex\venv')) { throw 'Wrong venv path' }
    } else {
        if ($Executable -ne (Join-Path $env:USERPROFILE '.local\share\usage-tools-for-codex\venv\Scripts\python.exe')) { throw 'Wrong interpreter' }
    }
    if ($Arguments -contains 'pip') {
        if ($Arguments -notcontains '--only-binary=:all:' -or $Arguments -notcontains '--isolated') { throw 'Source build possible' }
        $script:ready = $true
    }
    Write-Host ('SIMULATED ' + ($Arguments -join ' '))
}
function Set-SetupUserPath { throw 'Unexpected PATH write' }
exit (Invoke-WindowsConfigure -PythonPath $env:SETUP_PYTHON -CodexPath $env:SETUP_CODEX)
""")
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('ensurepip', result.stdout)
        self.assertIn('--only-binary=:all:', result.stdout)
        data = json.loads(self.config.read_text())
        self.assertEqual(pathlib.Path(data['python_path']), self.config.parent/'venv/Scripts/python.exe')
        self.assertEqual(pathlib.Path(data['codex_path']), self.fake)

    def test_unavailable_wheel_stops_setup_without_fallback_or_config_overwrite(self):
        self.save()
        before = self.config.read_bytes()
        result = self.ps(r"""
. (Join-Path $env:SETUP_ROOT 'configure.ps1')
function Confirm-WindowsSetup { param($Message); return ($Message -notlike 'Create or reuse*') }
function Invoke-DoctorPythonProbe {
    [pscustomobject]@{version='3.14';supported=$true;bits=64;
        modules=[pscustomobject]@{sqlite3=$true;ctypes=$true;msvcrt=$true;venv=$true;pip=$true;curses=$false}}
}
function Invoke-SetupPython { throw 'Synthetic wheel unavailable' }
function Set-SetupUserPath { throw 'Unexpected PATH write' }
exit (Invoke-WindowsConfigure -PythonPath $env:SETUP_PYTHON)
""")
        self.assertEqual(result.returncode, 1, result.stdout+result.stderr)
        self.assertIn('Synthetic wheel unavailable', result.stdout)
        self.assertEqual(self.config.read_bytes(), before)

    def test_user_path_append_is_idempotent_preserves_entries_and_requires_consent(self):
        result = self.ps(r"""
. (Join-Path $env:SETUP_ROOT 'configure.ps1')
$script:stored = 'C:\synthetic\keep;%SYNTHETIC_VARIABLE%'
$script:writes = 0
function Get-SetupUserPath { $script:stored }
function Set-SetupUserPath { param($Value); $script:stored=$Value; $script:writes++ }
function Confirm-WindowsSetup { return $true }
Add-SetupUserBin
Add-SetupUserBin
if ($script:writes -ne 1 -or $script:stored -ne ('C:\synthetic\keep;%SYNTHETIC_VARIABLE%;' + (Join-Path $env:USERPROFILE '.local\bin'))) { exit 1 }
function Confirm-WindowsSetup { return $false }
Add-SetupUserBin
if ($script:writes -ne 1) { exit 2 }
""")
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue((self.root/'.local/bin').is_dir())

    def test_saved_paths_drive_doctor_without_discovery_and_stale_path_does_not_fallback(self):
        self.save()
        result = self.ps(r"""
. (Join-Path $env:SETUP_ROOT 'doctor-windows.ps1')
function Get-DoctorPythonCandidates {
    param($RequestedPath)
    if (-not $RequestedPath) { throw 'Unexpected discovery' }
    $RequestedPath
}
exit (Invoke-WindowsDoctor -NoColor)
""")
        self.assertIn(result.returncode, (0, 2), result.stdout+result.stderr)
        self.assertIn('Saved path is shared', result.stdout)
        self.assertIn(r'Next: powershell.exe -File .\install.ps1', result.stdout)
        self.save(codex=self.root/'missing.exe')
        with patch.dict(os.environ, self.env), patch('codex_limit_tools.quota.shutil.which', side_effect=AssertionError('Unexpected discovery')):
            with self.assertRaisesRegex(MonitorError, 'rerun configure.ps1'):
                resolve_executable('codex')

    def test_resolution_precedence_validation_and_absent_config_fallback(self):
        self.save()
        with patch.dict(os.environ, self.env):
            with patch('codex_limit_tools.quota.shutil.which', side_effect=AssertionError('Unexpected discovery')):
                self.assertEqual(resolve_executable('codex'), str(self.fake))
            self.assertEqual(resolve_executable(sys.executable), sys.executable)
            for value in ('{', '[]', '{"version":2}', '{"version":1,"codex_path":"relative.exe"}'):
                self.config.write_text(value)
                with self.assertRaisesRegex(MonitorError, 'configure.ps1'):
                    resolve_executable('codex')
                self.assertEqual(resolve_executable(sys.executable), sys.executable)
            self.config.unlink()
            with patch('codex_limit_tools.quota.shutil.which', return_value=str(self.fake)):
                self.assertEqual(resolve_executable('codex'), str(self.fake))

    def test_wrapper_installs_in_temp_home_and_prompts_for_upgrade(self):
        self.save()
        result = self.ps(file='install.ps1')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        dest = self.root/'.local/lib/codex-limit-tools'
        for name in ('configure.ps1', 'doctor-windows.ps1', 'install.ps1', 'docs/INSTALL.md'):
            self.assertEqual((dest/name).read_bytes(), (ROOT/name).read_bytes())
        marker = dest/'synthetic-marker'
        marker.write_text('preserve this')
        result = self.ps(file='install.ps1', answers='n\n')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('cancelled', result.stdout)
        self.assertEqual(marker.read_text(), 'preserve this')
        result = self.ps(file='install.ps1', answers='y\n')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(next(dest.parent.glob('codex-limit-tools.backup-*/synthetic-marker')).read_text(), 'preserve this')
        command = self.root/'.local/bin/codex-usage.cmd'
        version = subprocess.run([str(command), '--version'], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(version.returncode, 0, version.stdout+version.stderr)
        self.assertIn('codex-usage', version.stdout)

    def test_wrapper_decline_and_child_failure_leave_installation_unchanged(self):
        self.save()
        dest = self.root/'.local/lib/codex-limit-tools'
        dest.mkdir(parents=True)
        result = self.ps(r"""
. (Join-Path $env:SETUP_ROOT 'install.ps1')
function Confirm-WindowsSetup { return $true }
function Invoke-SetupPython {
    param($Executable, $Arguments)
    if ($Arguments -notcontains '--upgrade' -or $Arguments -notcontains '--data-dir') { throw 'Missing upgrade/state flags' }
    throw 'Synthetic installer failure'
}
exit (Invoke-WindowsInstall -DataDir @('synthetic-a','synthetic-b'))
""")
        self.assertEqual(result.returncode, 1, result.stdout+result.stderr)
        self.assertIn('Synthetic installer failure', result.stdout)
        self.assertEqual(list(dest.iterdir()), [])

    def test_real_venv_creation_without_downloading_or_system_changes(self):
        result = self.ps(r"""
. (Join-Path $env:SETUP_ROOT 'configure.ps1')
function Confirm-WindowsSetup {
    param($Message)
    return ($Message -like 'Python is outside*' -or $Message -like 'Create or reuse*' -or $Message -like 'Locate the native*')
}
function Set-SetupUserPath { throw 'Unexpected PATH write' }
exit (Invoke-WindowsConfigure -PythonPath $env:SETUP_PYTHON -CodexPath $env:SETUP_CODEX)
""")
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        data = json.loads(self.config.read_text())
        selected = pathlib.Path(data['python_path'])
        self.assertTrue(selected.is_file())
        result = subprocess.run([str(selected), '-E', '-X', 'utf8', '-B', '-c', 'import sys, pip; print(sys.prefix)'],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(pathlib.Path(result.stdout.strip()), self.config.parent/'venv')

    def test_entrypoints_preserve_explicit_parameters_and_help(self):
        for file in ('configure.ps1', 'install.ps1'):
            result = self.ps(file=file, args=('-Help',))
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn('Usage:', result.stdout)
            result = self.ps(file=file, args=('-PythonPath', str(self.root/'missing.exe')))
            self.assertEqual(result.returncode, 1, result.stdout+result.stderr)
        self.assertFalse(self.config.exists())

    def test_shallow_python_paths_and_atomic_configuration_refresh(self):
        self.save()
        result = self.ps(r"""
. (Join-Path $env:SETUP_ROOT 'configure.ps1')
$script:searched = New-Object 'System.Collections.Generic.List[string]'
function Get-Command { }
function Get-ChildItem { param($Path, $LiteralPath, [switch]$File); if ($Path) { $script:searched.Add($Path) } }
$env:ProgramFiles = Join-Path $env:USERPROFILE 'programs'
${env:ProgramFiles(x86)} = Join-Path $env:USERPROFILE 'programs-x86'
$null = @(Get-DoctorPythonCandidates)
$expected = Join-Path ($env:SystemDrive + '\') 'Python*\python.exe'
if ($script:searched.Count -ne 5 -or $script:searched[-1] -ne $expected) { throw ('Incorrect shallow paths: ' + ($script:searched -join ', ')) }
$config = Read-WindowsSetup
$config.codex_path = $env:SETUP_PYTHON
Save-WindowsSetup $config
if ((Read-WindowsSetup).codex_path -ne $env:SETUP_PYTHON) { throw 'Configuration refresh failed' }
""")
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(json.loads(self.config.read_text())['codex_path'], sys.executable)
        self.assertEqual(list(self.config.parent.glob('*.tmp')), [])
