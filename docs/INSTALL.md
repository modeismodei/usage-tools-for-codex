# Installation

## Windows

Use native Windows with PowerShell 5.1 or newer and **CPython 3.10+** including
SQLite, `ctypes`, `msvcrt`, `venv` and `ensurepip` (included in normal CPython
installations). An installed and authenticated Codex is needed for quota and
tracking. The desktop app's bundled native `codex.exe` can be used; a separate
Codex CLI installation is not required when that executable is available.
Offline usage reports do not require the Codex executable.

Download Python, if needed, from the official
[Python for Windows page](https://www.python.org/downloads/windows/).
Setup never installs Python or Codex. It searches PATH, Python registry entries,
the dedicated venv, and shallow known Python installation directories, including
user-local and Program Files locations. Store aliases and recognized Python
install-manager launchers are not executed. There is no recursive disk search.

From the root of a downloaded/existing checkout, run these in order:

```powershell
powershell.exe -File .\configure.ps1
powershell.exe -File .\doctor-windows.ps1
powershell.exe -File .\install.ps1
```

`-File` makes the script invocation explicit. If the local execution policy
blocks scripts, use the following process-scoped form for each command instead:

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\configure.ps1
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\doctor-windows.ps1
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\install.ps1
```

This does not change persistent execution policy or override Group Policy.
For a reviewed download marked as coming from the Internet, Windows may also
require unblocking the downloaded archive/scripts in Properties before use.

### What configuration does

Accept the `[Y/n]` prompts (Enter means yes) to prepare the complete setup:

1. Use the discovered Python, with confirmation if it is outside PATH.
2. Create or reuse the dedicated venv at
   `%USERPROFILE%\.local\share\usage-tools-for-codex\venv`.
3. Install missing Python dependencies into that interpreter: bundled pip via
   `ensurepip` if needed, then **a prebuilt `windows-curses` wheel only** for the
   existing terminal interface. Package installation needs Internet access, or
   access to the configured package source. No compiler or source build is used.
4. Locate native Codex on PATH or in the desktop app's versioned bundle directory
   under `%LOCALAPPDATA%\OpenAI\Codex\bin`, and save its full path. When several
   bundles exist, the most recently modified executable is selected and shown.
   If discovery fails, enter an explicit path or skip this step.
5. Create `%USERPROFILE%\.local\bin` if needed and add it to the **user** PATH,
   preserving existing entries and avoiding duplicate additions.

The script then asks you to run the doctor before installation. Declining a
step leaves the corresponding feature unprepared; warnings explain what remains.
If venv creation is declined, dependency installation targets the selected
interpreter, and still requires separate consent. Accept venv creation to keep
these packages isolated from your other Python projects.

With a complete supported Python and an available matching wheel, **all extra
Python dependencies can be installed by configuration**: no separate pip command
is necessary. A missing standard-library component, broken Python installation,
unavailable wheel or failed download stops the relevant setup with an error;
the script never builds from source or silently substitutes another interface.
The application never installs dependencies at runtime.

### Saved paths and executable selection

Configuration writes a small UTF-8 JSON file:

```text
%USERPROFILE%\.local\share\usage-tools-for-codex\windows.json
```

It contains `version`, `python_path` and `codex_path`, without credentials.
Doctor and installer use the saved Python. The installed `.cmd` launchers bind
to that interpreter. Keep the venv after installation; if you change Python,
rerun configuration, doctor and installer to update those launchers.

On **Windows only**, quota and the estimator resolve their default `codex`
through the saved Codex path, including a tracker whose existing configuration
contains that default. They do not search GUI bundles at runtime. An explicit
`--codex-bin` path overrides the saved default. Without a saved Codex path,
the existing native executable lookup on PATH remains available.
Linux executable selection is unchanged.

After a desktop app update removes/moves the saved executable, shut down the
collector and rerun configuration and doctor to record its new location, then
resume. A stale configured path produces an actionable error, not a silent
fallback. Setup and doctor check Codex's presence only; neither runs Codex,
reads your account nor starts tracking.

For an installation outside known locations:

```powershell
powershell.exe -File .\configure.ps1 -PythonPath 'C:\path\to\Python\python.exe' -CodexPath 'C:\path\to\Codex\codex.exe'
```

An explicit unusable Python path does not silently fall back. Python does not
need to be on PATH for these scripts. If you want to add it yourself, substitute
the actual interpreter directory in this example:

```powershell
$pythonDirectory = 'C:\path\to\Python'
[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $pythonDirectory, 'User')
$env:Path = $pythonDirectory + ';' + $env:Path
```

### Doctor, installation and first use

The doctor starts with PowerShell alone. When Python is available it checks
Python modules with that interpreter, and prints green successes, yellow
warnings and red missing dependencies. Use `-NoColor` for plain output.
Exit codes: **0** dependencies found, **1** required dependency/configuration
unavailable, **2** optional or feature-specific dependencies need attention.
At the end it shows the installation command. Resolve relevant warnings first;
doctor success does not establish authentication or live integration.

`install.ps1` wraps the existing `install.py` installer using the selected
interpreter. It installs the three commands in `%USERPROFILE%\.local\bin` and
the package in `%USERPROFILE%\.local\lib\codex-limit-tools`. It does not install
dependencies, start collectors or migrate history. Spaces and Unicode in the
installation directory are supported. A non-ASCII Python executable path needs
an available ASCII Windows short-path alias; if unavailable, installation fails
explicitly rather than creating an unusable launcher.

After setup, open a new terminal application to pick up the saved user PATH.
A child `powershell.exe` cannot modify the shell that launched it. For immediate
use in that existing PowerShell session, this optional refresh is sufficient:

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;" + $env:Path
```

First, check the installation without accessing your account:

```powershell
codex-usage.cmd --version
codex-quota.cmd --help
codex-limit-estimator.cmd --help
```

Then use the tools normally (quota and tracking read the authenticated account):

```powershell
codex-usage.cmd
codex-quota.cmd
codex-limit-estimator.cmd start tracking
```

No `--codex-bin` is needed after successful configuration. The manual override,
when wanted, is `codex-limit-estimator.cmd start tracking --codex-bin 'C:\path\to\codex.exe'`
for a new tracker/run. An existing run retains its explicit executable setting;
changing the saved default does not rewrite that run. See the
[command reference](COMMANDS.md) for `--new-run` and history behavior.

### Updating an existing Windows installation

Before installing over an existing copy, stop its collector:

```powershell
codex-limit-estimator.cmd shutdown
codex-limit-estimator.cmd status
```

Wait for `Daemon: offline`. From the updated source checkout, run the same three
setup commands. `install.ps1` detects the existing package and prompts
`Repeat installation / upgrade ... [Y/n]`; yes invokes `install.py --upgrade`,
and no leaves the installation unchanged. Existing installer locking, backups,
external prices and history preservation still apply. A running collector blocks
the upgrade; the wrapper does not stop it implicitly.

Follow [the upgrade guide](UPGRADING.md) to migrate and inspect history before
resuming. After an upgrade fixing the old default Codex lookup error, restarting
the collector with the updated package is necessary; an already running process
keeps its old code. Configuration alone cannot replace that process.

Advanced paths are forwarded to the Python installer:

```powershell
.\install.ps1 -Prefix 'C:\tools\usage-tools' -DataDir 'C:\tracking-one','C:\tracking-two'
```

List every custom tracking directory for upgrade locking and backups. A custom
prefix's `bin` directory is not the default user PATH entry added by configuration.

## Linux

Refer to [README.md](../README.md#installation).

## macOS

Refer to [README.md](../README.md#installation).
