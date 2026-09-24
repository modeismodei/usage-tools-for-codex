# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
<#
.SYNOPSIS
Offline dependency doctor for native Windows. Requires only PowerShell 5.1+.
.DESCRIPTION
Runs even without Python. When Python exists, runs a bounded import probe in
that interpreter. Never runs Codex, reads account data, installs software,
changes PATH/execution policy, or starts tracking. No external modules required.
.PARAMETER PythonPath
Exact python.exe to check. No fallback when an explicit path is unusable.
.PARAMETER CodexPath
Optional native codex.exe path, checked for presence only, never executed.
.PARAMETER NoColor
Print plain status labels without colors.
.EXAMPLE
.\doctor-windows.ps1 -PythonPath 'C:\tools\venv\Scripts\python.exe'
.NOTES
Exit 0: dependencies found; 1: required dependency unavailable;
2: optional/TUI/quota dependency or installer prerequisite needs attention.
Presence of Codex does not verify authentication or live integration.
#>
[CmdletBinding()]
param([string]$PythonPath, [string]$CodexPath, [switch]$NoColor, [switch]$Help)

function Write-DoctorStatus {
    param([string]$State, [string]$Label, [string]$Detail, [switch]$Plain)
    $colors = @{ OK = 'Green'; MISSING = 'Red'; WARN = 'Yellow'; INFO = 'Cyan'; FOUND = 'Green' }
    $line = '  [{0,-7}] {1}' -f $State, $Label
    if ($Plain) { Write-Host $line } else { Write-Host $line -ForegroundColor $colors[$State] }
    if ($Detail) { Write-Host ('              ' + $Detail) }
}

function Get-DoctorPythonCandidates {
    param([string]$RequestedPath)
    if ($RequestedPath) { $RequestedPath; return }
    if ($env:VIRTUAL_ENV) { Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe' }
    if ($env:USERPROFILE) {
        Join-Path $env:USERPROFILE '.local\share\usage-tools-for-codex\venv\Scripts\python.exe'
    }
    Get-Command python.exe, python3.exe -CommandType Application -All -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Source }
    # Includes Python Install Manager registrations; never invoke py (it can install runtimes).
    foreach ($key in @('HKCU:\Software\Python\PythonCore', 'HKLM:\Software\Python\PythonCore',
                       'HKLM:\Software\WOW6432Node\Python\PythonCore')) {
        Get-ChildItem -LiteralPath $key -ErrorAction SilentlyContinue | Sort-Object PSChildName -Descending |
            ForEach-Object {
                $install = Get-ItemProperty -LiteralPath ($_.PSPath + '\InstallPath') -ErrorAction SilentlyContinue
                if ($install -and $install.ExecutablePath) { $install.ExecutablePath }
                elseif ($install -and $install.'(default)') { Join-Path $install.'(default)' 'python.exe' }
            }
    }
    if ($env:LOCALAPPDATA) {
        foreach ($pattern in @('Python\pythoncore-*\python.exe', 'Programs\Python\Python*\python.exe')) {
            Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA $pattern) -File -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
        }
    }
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, ($env:SystemDrive + '\'))) {
        if ($base) {
            Get-ChildItem -Path (Join-Path $base 'Python*\python.exe') -File -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
        }
    }
}

function Get-WindowsSetupPath {
    Join-Path $env:USERPROFILE '.local\share\usage-tools-for-codex\windows.json'
}

function Read-WindowsSetup {
    $path = Get-WindowsSetupPath
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try {
        $config = Get-Content -LiteralPath $path -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if ($config.version -ne 1) { throw 'Unsupported version' }
        foreach ($key in @('python_path', 'codex_path')) {
            $value = $config.$key
            if ($null -ne $value -and ($value -isnot [string] -or -not [IO.Path]::IsPathRooted($value) -or
                $value -notmatch '^(?:[A-Za-z]:[\\/]|\\\\)' -or [IO.Path]::GetExtension($value) -ne '.exe')) {
                throw ('Invalid ' + $key)
            }
        }
        return $config
    }
    catch { throw "Cannot read Windows configuration at $path. Repair it or move it aside, then run configure.ps1. $($_.Exception.Message)" }
}

function Find-DoctorPython {
    param([string]$RequestedPath)
    $seen = @{}
    $unsupported = $null
    foreach ($candidate in @(Get-DoctorPythonCandidates $RequestedPath)) {
        if (-not $candidate -or $seen.ContainsKey($candidate)) { continue }
        $seen[$candidate] = $true
        if ($candidate -match '\\Microsoft\\WindowsApps\\' -or
            [IO.Path]::GetExtension($candidate) -ne '.exe' -or
            -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $item = Get-Item -LiteralPath $candidate
        # Do not execute install managers: they can download a missing runtime.
        if ($item.VersionInfo.ProductName -match '(?i)manage|python launcher') { continue }
        $info = Invoke-DoctorPythonProbe $item.FullName
        if ($info) {
            $result = [pscustomobject]@{ Path = $item.FullName; Info = $info }
            if ($RequestedPath -or $info.supported) { return $result }
            if (-not $unsupported) { $unsupported = $result }
        }
    }
    return $unsupported
}

function Invoke-DoctorPythonProbe {
    param([string]$Executable)
    # No companion .py file, pip subprocess, package bytecode or disk database.
    $probe = @'
import importlib, importlib.util, json, struct, sys
result = {'version': sys.version.split()[0], 'supported': sys.version_info >= (3, 10),
          'bits': struct.calcsize('P') * 8, 'modules': {}}
for name in ('sqlite3', 'ctypes', 'msvcrt', 'curses', 'pip', 'venv'):
    try:
        if name == 'pip':
            if importlib.util.find_spec(name) is None: raise ImportError()
        else:
            module = importlib.import_module(name)
            if name == 'sqlite3':
                db = module.connect(':memory:')
                db.execute('SELECT 1').fetchone()
                db.close()
        result['modules'][name] = True
    except Exception:
        result['modules'][name] = False
print(json.dumps(result))
'@
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $Executable
    # Probe contains no double quotes; pass it as one Windows command-line argument.
    $start.Arguments = '-E -B -c "' + $probe + '"'
    $start.WorkingDirectory = $env:SystemRoot
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { return $null }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(8000)) {
            $process.Kill()
            $null = $process.WaitForExit(1000)
            return $null
        }
        if ($process.ExitCode -ne 0 -or -not $stdout.Wait(1000)) { return $null }
        return ($stdout.Result | ConvertFrom-Json -ErrorAction Stop)
    }
    catch { return $null }
    finally { $process.Dispose() }
}

function Find-DoctorCodex {
    param([string]$RequestedPath)
    if ($RequestedPath) {
        if ([IO.Path]::GetExtension($RequestedPath) -eq '.exe' -and
            (Test-Path -LiteralPath $RequestedPath -PathType Leaf)) { return $RequestedPath }
        return $null
    }
    $command = Get-Command codex.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    if ($env:LOCALAPPDATA) {
        $bundled = @(Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin\*\codex.exe') -File -ErrorAction SilentlyContinue |
                     Sort-Object LastWriteTimeUtc -Descending)
        if ($bundled.Count) { return $bundled[0].FullName }
    }
    return $null
}

function Invoke-WindowsDoctor {
    param([string]$PythonPath, [string]$CodexPath, [switch]$NoColor)
    Write-Host ''
    Write-Host '  Usage Tools for Codex | Windows doctor'
    Write-Host '  -------------------------------------'
    Write-Host '  Offline checks - no installation or account access.'
    Write-Host ''
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $PSVersionTable.PSVersion -lt [version]'5.1') {
        Write-DoctorStatus MISSING 'Native Windows / PowerShell 5.1+' 'This doctor is for Windows only.' -Plain:$NoColor
        return 1
    }
    Write-DoctorStatus OK 'Windows / PowerShell' ('PowerShell ' + $PSVersionTable.PSVersion) -Plain:$NoColor
    $missing = 0
    $warnings = 0
    try {
        $config = Read-WindowsSetup
        if ($config) {
            Write-DoctorStatus INFO 'Saved Windows configuration' (Get-WindowsSetupPath) -Plain:$NoColor
            if (-not $PythonPath) { $PythonPath = $config.python_path }
            if (-not $CodexPath) { $CodexPath = $config.codex_path }
        }
    }
    catch { Write-DoctorStatus MISSING 'Windows configuration' $_.Exception.Message -Plain:$NoColor; return 1 }
    $python = Find-DoctorPython $PythonPath
    $selected = if ($python) { $python.Path } else { $null }
    $info = if ($python) { $python.Info } else { $null }
    if (-not $selected) {
        Write-DoctorStatus MISSING 'Python 3.10+' 'No usable interpreter found. Install CPython, or pass -PythonPath with its python.exe.' -Plain:$NoColor
        Write-DoctorStatus INFO 'Python modules' 'SQLite, native modules, pip and curses cannot be checked until Python works.' -Plain:$NoColor
        $missing++
    }
    else {
        $pythonState = if ($info.supported) { 'OK' } else { 'MISSING' }
        Write-DoctorStatus $pythonState ('Python ' + $info.version + ' / ' + $info.bits + '-bit') $selected -Plain:$NoColor
        if (-not $info.supported) {
            Write-Host '              Requires Python 3.10 or newer; select a newer interpreter with -PythonPath.'
            $missing++
        }
        foreach ($module in @('sqlite3', 'ctypes', 'msvcrt')) {
            if ($info.modules.$module) { Write-DoctorStatus OK $module 'Included with the selected Python.' -Plain:$NoColor }
            else {
                Write-DoctorStatus MISSING $module 'Repair/reinstall CPython; this is a standard-library component, not a pip package.' -Plain:$NoColor
                $missing++
            }
        }
        if ($info.modules.curses) { Write-DoctorStatus OK 'curses / interactive TUI' 'Import succeeds in the selected interpreter.' -Plain:$NoColor }
        else {
            Write-DoctorStatus WARN 'windows-curses / interactive TUI' 'Missing or broken. Headless reports and background mode do not require it.' -Plain:$NoColor
            Write-Host ('              & ''' + $selected.Replace("'", "''") + ''' -m pip install --only-binary=:all: windows-curses')
            $warnings++
        }
        foreach ($module in @('pip', 'venv')) {
            if ($info.modules.$module) { Write-DoctorStatus OK $module 'Available for dependency/environment setup; not required at application runtime.' -Plain:$NoColor }
            else {
                Write-DoctorStatus WARN $module 'Unavailable. Repair Python setup if you need to install dependencies or create a venv.' -Plain:$NoColor
                $warnings++
            }
        }
    }
    $codex = Find-DoctorCodex $CodexPath
    if ($codex) {
        Write-DoctorStatus FOUND 'Native Codex executable (presence only)' $codex -Plain:$NoColor
        $detail = if ($config -and $config.codex_path -eq $codex) {
            'Not executed or authenticated. Saved path is shared by quota and the estimator on Windows.'
        } else { 'Not executed or authenticated. Run configure.ps1 to save this path for all Windows commands.' }
        Write-DoctorStatus INFO 'Quota / tracking integration' $detail -Plain:$NoColor
    }
    else {
        Write-DoctorStatus WARN 'Native Codex executable' 'Needed for quota/tracking, not offline reports. Use -CodexPath to check a GUI-bundled codex.exe; a separate CLI install is not necessarily needed.' -Plain:$NoColor
        $warnings++
    }
    Write-Host ''
    Write-Host '  Next: powershell.exe -File .\install.ps1'
    Write-Host '  Resolve missing dependencies first; configure.ps1 can prepare the dedicated venv.'
    if ($missing) {
        Write-DoctorStatus MISSING 'Required dependencies need attention' ('Blocking checks: ' + $missing + '; other checks needing attention: ' + $warnings) -Plain:$NoColor
        return 1
    }
    if ($warnings) {
        Write-DoctorStatus WARN 'Core Python dependencies are ready' ('Optional or feature-specific checks needing attention: ' + $warnings) -Plain:$NoColor
        return 2
    }
    Write-DoctorStatus OK 'Dependencies found' 'Live integration and terminal rendering were not tested by this doctor.' -Plain:$NoColor
    return 0
}

if ($Help) {
    Write-Host 'Usage: .\doctor-windows.ps1 [-PythonPath PATH] [-CodexPath PATH] [-NoColor]'
    Write-Host 'Read-only, offline; no installations. Runs even when Python is absent.'
    Write-Host 'Exit codes: 0 found; 1 required dependency unavailable; 2 optional/feature dependency needs attention.'
}
elseif ($MyInvocation.InvocationName -ne '.') {
    exit (Invoke-WindowsDoctor -PythonPath $PythonPath -CodexPath $CodexPath -NoColor:$NoColor)
}
