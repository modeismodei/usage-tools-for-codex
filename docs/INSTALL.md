# Installation

## Windows

### Configure and install

Install [Python 3.10+](https://www.python.org/downloads/windows/) and sign in to
Codex (desktop app or CLI) first. Configuration does not install Python or Codex;
it looks for Python in known installation directories.

Download this repository, open PowerShell in its root directory, and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\configure.ps1
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\doctor-windows.ps1
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\install.ps1
```

Accept the recommended `[Y/n]` options with Enter. Configuration creates an
isolated Python environment, installs the additional dependencies (including
`windows-curses`), locates Codex, and adds the commands to your user PATH.
Check the doctor's results and resolve any reported problems before installing.

Keep the environment at `%USERPROFILE%\.local\share\usage-tools-for-codex\venv`
after installation. Open a new terminal so the commands are available.

### Update

Stop tracking and check its status:

```powershell
codex-limit-estimator.cmd shutdown
codex-limit-estimator.cmd status
```

Wait for `Daemon: offline`. Update your checkout or download a fresh copy, then
run from its root directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\install.ps1
```

Accept the upgrade prompt. See the [upgrade guide](UPGRADING.md) for checking
saved history before resuming, or for custom installation paths.

### Launch

```powershell
codex-usage.cmd
codex-quota.cmd
codex-limit-estimator.cmd start tracking
```

The first usage scan may take a while. See the [user guide](USAGE.md) for everyday
controls. Windows commands use the `.cmd` extension.

### Troubleshooting

- **Python not found:** install it from the link above, or select an existing
  installation with `-PythonPath 'C:\path\to\Python\python.exe'` when running
  `configure.ps1`.
- **Codex not found, including after an app update:** stop tracking, rerun
  configuration and doctor, then resume. Configuration lets you enter the path
  to `codex.exe` if needed.
- **Missing dependencies or terminal interface:** rerun configuration and check
  the doctor. Setup needs a compatible prebuilt `windows-curses` package; follow
  the reported error if it cannot be installed.
- **Command not found:** open a new terminal. To update the current PowerShell
  session instead, run:

  ```powershell
  $env:Path = "$env:USERPROFILE\.local\bin;" + $env:Path
  ```

- **Downloaded scripts blocked:** use the PowerShell commands shown above. If
  Windows still blocks a trusted download, unblock it in file Properties.

## Linux

Requires Python 3.10+ with SQLite and curses, Bash, and an authenticated Codex CLI
on your `PATH`. From the downloaded repository root, optionally check dependencies,
then install:

```bash
bash doctor.sh  # optional
bash install.sh
```

Make sure `~/.local/bin` is on your `PATH`.

## macOS

Refer to [README.md](../README.md#linuxmacos).
