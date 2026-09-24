# Windows port handoff

- W-01–W-05 implemented in `4ab5f5e`; W-06 offline and native console evidence
  recorded in docs/porting/WINDOWS-PORT.md, with remaining acceptance gates below.
- Standalone doctor followed in `8859f26`. Current follow-up extends W-02/W-05:
  configure.ps1, doctor-windows.ps1, install.ps1, docs/INSTALL.md, and a saved
  Windows-only Codex default shared by quota and the estimator.
- Configuration prompts for the venv, dependency installation, Codex discovery
  and user PATH. Python/Codex are never installed automatically. Only prebuilt
  windows-curses wheels are allowed; package installation is confined to setup.
- install.ps1 wraps install.py and prompts before --upgrade; the Python installer
  changed only its distribution manifest. Runtime schemas/prices are unchanged.
- Windows paths are stored under the dedicated share directory in windows.json.
  Explicit executable paths override the default; stale saved paths fail clearly.
  Restart an existing collector after upgrading to load the new resolver.
- Environment: native Windows build 26200 AMD64, CPython 3.14.7 x64 in the
  development venv, prebuilt windows-curses 2.4.2; PowerShell 7.6.5 host and
  Windows PowerShell 5.1.26100.9444 for onboarding tests.
- Full offline command: `.runtime/windows-venv/Scripts/python.exe -B tests/run_audit.py`.
  Result before final shallow-discovery/config-replacement fixes: 106 tests,
  exit 0, ten existing symlink skips (three methods and seven subcases),
  synthetic sentinels unchanged, no Python network-guard denials.
- Final affected-group command adds `--pattern 'test_[dw]*.py'`: 19 tests;
  one newly added test exposed PowerShell 5.1's null-to-empty-string conversion
  in File.Replace. Corrected with NullString; the single failing case passed:
  `.runtime/windows-venv/Scripts/python.exe -B -c 'import sys,unittest; sys.path.insert(0,"tests"); suite=unittest.defaultTestLoader.loadTestsFromName("test_windows_setup.WindowsSetup.test_shallow_python_paths_and_atomic_configuration_refresh"); result=unittest.TextTestRunner().run(suite); sys.exit(not result.wasSuccessful())'`.
  Other valid results were reused. Detailed logs remain ignored under .runtime.
- Tested: real temporary venv creation, install/decline/upgrade, saved paths,
  missing Python/wheel handling, consent, PATH idempotence, and fake RPC through
  the saved default. Dependency downloads and persistent user PATH writes were
  mocked; no user installation/configuration/history was modified.
- Original combined native console evidence remains valid for unchanged TUI
  and lifecycle code: colors/views/keys/resize, detach, surviving collector,
  second-console shutdown and lock release, using synthetic state/fake RPC.
- Next action: run `python3 -B tests/run_audit.py` on native Linux at this
  candidate (identify the exact revision with `git rev-parse HEAD`). Linux gate
  is PENDING; the Windows-only resolver branch has a POSIX bypass unit test.
- User reports GUI quota success with an explicit executable; no live account
  check was performed by the agent. This follow-up's saved-path integration was
  verified offline only. Symlink-specific native acceptance still needs privilege.
- Non-ASCII Python executable paths still require an ASCII short-path alias.
  No new TUI session, remote OS access, CI or macOS implementation was added.
- README/tasks unchanged. Commits remain local; no unrelated work included.
