# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
<#
.SYNOPSIS
Install/update on Windows using the Python selected by configure.ps1.
#>
[CmdletBinding()]
param([Alias('PythonPath')][string]$InstallPythonPath, [string]$Prefix, [string[]]$DataDir,
      [Alias('Help')][switch]$InstallHelp)

. (Join-Path $PSScriptRoot 'configure.ps1')

function Invoke-WindowsInstall {
    param([string]$PythonPath, [string]$Prefix, [string[]]$DataDir)
    $ErrorActionPreference = 'Stop'
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { Write-Host 'This installer is for native Windows.'; return 1 }
    try {
        if (-not $PythonPath) {
            $config = Read-WindowsSetup
            if ($config) { $PythonPath = $config.python_path }
            if (-not $PythonPath) { throw 'Run configure.ps1 and doctor-windows.ps1 first, or specify -PythonPath explicitly.' }
        }
        $python = Find-DoctorPython $PythonPath
        if (-not $python -or -not $python.Info.supported) { throw 'Configured Python is unavailable. Rerun configure.ps1 -PythonPath PATH.' }
        foreach ($module in @('sqlite3', 'ctypes', 'msvcrt')) {
            if (-not $python.Info.modules.$module) { throw "Python is missing $module. Run doctor-windows.ps1." }
        }
        if (-not $Prefix) { $Prefix = Join-Path $env:USERPROFILE '.local' }
        $arguments = @('-E', '-B', (Join-Path $PSScriptRoot 'install.py'), '--prefix', $Prefix)
        foreach ($directory in $DataDir) { $arguments += @('--data-dir', $directory) }
        $upgrade = Test-Path -LiteralPath (Join-Path $Prefix 'lib\codex-limit-tools')
        if ($upgrade) {
            Write-Host '  Existing installation found. Shut down its collector first (codex-limit-estimator.cmd shutdown).'
            if (-not (Confirm-WindowsSetup 'Repeat installation / upgrade, preserving existing backups and history')) {
                Write-Host '  Installation cancelled. Existing installation unchanged.'
                return 0
            }
            $arguments += '--upgrade'
        }
        Invoke-SetupPython $python.Path $arguments
        Write-DoctorStatus OK 'Installation complete' (Join-Path $Prefix 'bin')
        Write-Host '  Open a new terminal application to pick up the user PATH saved during configuration.'
        Write-Host '  Offline check: codex-usage.cmd --version'
        if ($upgrade) { Write-Host '  Before resuming, follow docs/UPGRADING.md: migrate and inspect your saved history.' }
        return 0
    }
    catch { Write-DoctorStatus MISSING 'Installation stopped' $_.Exception.Message; return 1 }
}

if ($InstallHelp) {
    Write-Host 'Usage: powershell.exe -File .\install.ps1 [-PythonPath PATH] [-Prefix PATH] [-DataDir PATH,PATH]'
    Write-Host 'Uses install.py; prompts before --upgrade. Never installs dependencies or starts tracking.'
}
elseif ($MyInvocation.InvocationName -ne '.') {
    exit (Invoke-WindowsInstall -PythonPath $InstallPythonPath -Prefix $Prefix -DataDir $DataDir)
}
