# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
<#
.SYNOPSIS
Interactive native Windows setup. Python and Codex must already be installed.
.DESCRIPTION
Uses shallow Python discovery, creates an optional dedicated venv, installs only
prebuilt Python dependencies with consent, saves executable paths, and optionally
adds the default command directory to the user PATH. Never runs Codex.
#>
[CmdletBinding()]
param([Alias('PythonPath')][string]$SetupPythonPath, [Alias('CodexPath')][string]$SetupCodexPath,
      [Alias('Help')][switch]$SetupHelp)

. (Join-Path $PSScriptRoot 'doctor-windows.ps1')

function Confirm-WindowsSetup {
    param([string]$Message)
    while ($true) {
        $answer = Read-Host ($Message + ' [Y/n]')
        if ([string]::IsNullOrWhiteSpace($answer) -or $answer -match '^(?i)y(es)?$') { return $true }
        if ($answer -match '^(?i)n(o)?$') { return $false }
        Write-Host 'Please enter Y or n.'
    }
}

function Invoke-SetupPython {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Python command failed (exit $LASTEXITCODE). Setup stopped; no source builds will be attempted." }
}

function Show-SetupPythonPathHint {
    param([string]$Directory = 'C:\path\to\Python')
    Write-Host '  Python need not be on PATH for this setup. To add its directory yourself:'
    Write-Host ('    $pythonDirectory = ''' + $Directory.Replace("'", "''") + '''')
    Write-Host '    [Environment]::SetEnvironmentVariable(''Path'', [Environment]::GetEnvironmentVariable(''Path'', ''User'') + '';'' + $pythonDirectory, ''User'')'
    Write-Host '    $env:Path = $pythonDirectory + '';'' + $env:Path'
}

function Save-WindowsSetup {
    param($Config)
    $path = Get-WindowsSetupPath
    $directory = Split-Path -Parent $path
    $null = [IO.Directory]::CreateDirectory($directory)
    $temporary = Join-Path $directory ('windows-' + [guid]::NewGuid().ToString('N') + '.tmp')
    # Atomic replacement avoids partially written configuration; no executable code.
    [IO.File]::WriteAllText($temporary, ($Config | ConvertTo-Json) + "`n", (New-Object Text.UTF8Encoding($false)))
    # PowerShell 5.1 converts ordinary $null to an empty string for this overload.
    if ([IO.File]::Exists($path)) { [IO.File]::Replace($temporary, $path, [NullString]::Value) }
    else { [IO.File]::Move($temporary, $path) }
}

function Get-SetupUserPath { [Environment]::GetEnvironmentVariable('Path', 'User') }
function Set-SetupUserPath { param([string]$Value); [Environment]::SetEnvironmentVariable('Path', $Value, 'User') }

function Add-SetupUserBin {
    $bin = Join-Path $env:USERPROFILE '.local\bin'
    $old = Get-SetupUserPath
    $present = @($old -split ';' | Where-Object {
        [Environment]::ExpandEnvironmentVariables($_).Trim().Trim('"').TrimEnd('\', '/') -ieq $bin.TrimEnd('\', '/')
    }).Count -gt 0
    if (Confirm-WindowsSetup "Create $bin if needed and add it to your user PATH") {
        $null = [IO.Directory]::CreateDirectory($bin)
        if (-not $present) {
            $new = if ([string]::IsNullOrEmpty($old)) { $bin } else { $old.TrimEnd(';') + ';' + $bin }
            Set-SetupUserPath $new
        }
        Write-DoctorStatus OK 'User PATH' $bin
        Write-Host '  Open a new terminal application after setup. A child PowerShell cannot update its parent shell.'
        Write-Host '  To use commands immediately in the current PowerShell session, run:'
        Write-Host '    $env:Path = "$env:USERPROFILE\.local\bin;" + $env:Path'
    }
}

function Invoke-WindowsConfigure {
    param([string]$PythonPath, [string]$CodexPath)
    $ErrorActionPreference = 'Stop'
    Write-Host "`n  Usage Tools for Codex | Windows configuration`n"
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $PSVersionTable.PSVersion -lt [version]'5.1') {
        Write-DoctorStatus MISSING 'Native Windows / PowerShell 5.1+' 'Use the platform installation instructions.'
        return 1
    }
    try {
        $saved = Read-WindowsSetup
        if (-not $PythonPath -and $saved.python_path) { $PythonPath = $saved.python_path }
        $python = Find-DoctorPython $PythonPath
        if (-not $python -or -not $python.Info.supported) {
            Write-DoctorStatus MISSING 'Python 3.10+' 'No usable supported interpreter found in PATH, registry or known shallow locations.'
            Write-Host '  Download and configure Python from https://www.python.org/downloads/windows/'
            Write-Host '  If installed elsewhere, rerun configure.ps1 -PythonPath ''C:\path\to\Python\python.exe''.'
            Show-SetupPythonPathHint
            return 1
        }
        $selected = $python.Path
        Write-DoctorStatus FOUND ('Python ' + $python.Info.version + ' / ' + $python.Info.bits + '-bit') $selected
        $onPath = @(Get-Command python.exe, python3.exe -CommandType Application -All -ErrorAction SilentlyContinue |
                    Where-Object { $_.Source -ieq $selected }).Count -gt 0
        if (-not $onPath) {
            Show-SetupPythonPathHint (Split-Path -Parent $selected)
            if (-not (Confirm-WindowsSetup "Python is outside PATH. Use $selected")) { return 2 }
        }
        foreach ($module in @('sqlite3', 'ctypes', 'msvcrt', 'venv')) {
            if (-not $python.Info.modules.$module) { throw "Python is missing $module. Repair the CPython installation; this component is not a pip package." }
        }
        $venv = Join-Path $env:USERPROFILE '.local\share\usage-tools-for-codex\venv'
        $venvPython = Join-Path $venv 'Scripts\python.exe'
        if (Confirm-WindowsSetup "Create or reuse the dedicated Python venv at $venv") {
            if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
                if (Test-Path -LiteralPath $venv) { throw "The venv directory exists but is incomplete: $venv. Repair it or move it aside before retrying." }
                Invoke-SetupPython $selected @('-E', '-B', '-m', 'venv', $venv)
            }
            $python = Find-DoctorPython $venvPython
            if (-not $python -or -not $python.Info.supported) { throw 'The dedicated venv is not usable. Repair it or move it aside before retrying.' }
            $selected = $python.Path
        }
        if (-not $python.Info.modules.curses -or -not $python.Info.modules.pip) {
            if (Confirm-WindowsSetup "Install missing Python dependencies into $selected (bundled pip and prebuilt windows-curses only)") {
                if (-not $python.Info.modules.pip) { Invoke-SetupPython $selected @('-E', '-B', '-m', 'ensurepip', '--upgrade') }
                if (-not $python.Info.modules.curses) {
                    Invoke-SetupPython $selected @('-E', '-B', '-m', 'pip', '--isolated', 'install', '--only-binary=:all:', 'windows-curses')
                }
                $python = Find-DoctorPython $selected
                if (-not $python -or -not $python.Info.modules.curses -or -not $python.Info.modules.pip) { throw 'Dependency verification failed. Run doctor-windows.ps1 for details.' }
            }
        }
        $codex = if ($saved) { $saved.codex_path } else { $null }
        if (Confirm-WindowsSetup 'Locate the native Codex executable and save its path for quota and the estimator') {
            $codex = Find-DoctorCodex $CodexPath
            if (-not $codex) {
                $manual = Read-Host 'Codex was not found. Enter the full codex.exe path, or leave blank to skip'
                if ($manual) { $codex = Find-DoctorCodex $manual.Trim('"') }
            }
            if ($codex) { $codex = (Get-Item -LiteralPath $codex).FullName; Write-DoctorStatus FOUND 'Codex (not executed)' $codex }
            else { Write-DoctorStatus WARN 'Codex path not configured' 'Quota/tracking need a native codex.exe. Rerun with -CodexPath PATH.' }
        }
        Save-WindowsSetup ([ordered]@{version=1; python_path=$selected; codex_path=$codex})
        Write-DoctorStatus OK 'Saved Windows paths' (Get-WindowsSetupPath)
        Add-SetupUserBin
        Write-Host "`n  Next: powershell.exe -File .\doctor-windows.ps1"
        Write-Host '  Check its results before running powershell.exe -File .\install.ps1.'
        if (-not $python.Info.modules.curses -or -not $python.Info.modules.pip -or -not $codex -or -not (Find-DoctorCodex $codex)) { return 2 }
        return 0
    }
    catch { Write-DoctorStatus MISSING 'Configuration stopped' $_.Exception.Message; return 1 }
}

if ($SetupHelp) {
    Write-Host 'Usage: powershell.exe -File .\configure.ps1 [-PythonPath PATH] [-CodexPath PATH]'
    Write-Host 'Interactive Windows setup; never installs Python or Codex, and never executes Codex.'
}
elseif ($MyInvocation.InvocationName -ne '.') {
    exit (Invoke-WindowsConfigure -PythonPath $SetupPythonPath -CodexPath $SetupCodexPath)
}
