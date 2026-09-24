# Windows port handoff

- Active pipeline: W-01 through W-06; the former backlog was not modified.
- Implementation commit: `4ab5f5e170500981084bbce2ecb234986b9e0f4e`.
- W-01–W-05 implemented: native ACL/file/lock handling, bounded RPC pipe reader,
  detached collector, lazy curses preflight, Python installer and .cmd launchers.
- W-06: native offline verification and console session recorded; remaining
  acceptance gates are explicit below. See docs/porting/WINDOWS-PORT.md.
- Environment: Windows 11 build 26200 AMD64, CPython 3.14.7 x64 from the system
  installation in an isolated venv, windows-curses 2.4.2 prebuilt wheel;
  PowerShell 7.6.5 / native ConPTY console.
- Final command: `.runtime/windows-venv/Scripts/python.exe -B tests/run_audit.py`.
- Original port candidate above: 87 tests, exit 0, ten symlink skips.
- Follow-up: standalone doctor-windows.ps1, included in the install payload;
  no Python dependency to start; optional Python probes, colored results,
  no installs, manager launches, Codex execution or account access.
- Doctor verified on PowerShell 5.1 and 7.6.5. Six focused tests passed;
  full native suite for this update: 93 tests, exit 0, ten symlink skips
  (three methods and seven subcases); synthetic sentinels unchanged.
- Focused A/B commands and counts, including corrected failures, are recorded
  in the Windows plan. Detailed logs remain ignored under .runtime.
- Console: 110-column views/colors/keys, 30-column resize, pause/resume, q,
  terminal restoration, collector survival after launcher exit, second-console
  shutdown and lock release verified with synthetic logs and fake RPC only.
- Next concrete action: run `python3 -B tests/run_audit.py` on native Linux
  at the current candidate, including the doctor follow-up (identify with
  `git rev-parse HEAD`). Linux regression gate is PENDING.
- GUI-only live integration is UNVERIFIED; no account read was authorized.
  A desktop bundled native executable can be supplied with --codex-bin.
- Symlink-specific checks need an account with symlink privilege; hard-link
  and junction checks passed. Unresolved .cmd/.ps1 Codex shims are rejected.
- Non-ASCII Python executable paths need an ASCII short-path alias; selected
  interpreter and Unicode/space-containing install paths passed.
- README/tasks unchanged. User installation/configuration/history untouched.
  No Codex CLI was installed; no persistent real-account collector was started.
- Commits are local only. No unrelated or intentionally uncommitted task work.
