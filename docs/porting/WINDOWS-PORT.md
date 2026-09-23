# Windows port: implementation pipeline

## Target and limits

Implement the existing three tools on **native Windows**, with an installed CPython interpreter, an ordinary user account and local storage. WSL/Git Bash do not count as native verification. Start with the available Windows x64 development machine and record its OS, Python, architecture and terminal; do not imply all architectures/builds were tested.

Read the [source report](PORTABILITY-REPORT.md) first. Findings `F01`–`F15` refer to that report. The macOS pipeline is **not** a prerequisite. Preserve unrelated work and any already-landed port fixes.

No application executable build, compiler, service, scheduled task, GUI rewrite, packaging framework, new quota endpoint, data migration, or feature work. Keep Python 3.10+ compatibility unless a concrete blocker requires a separately approved change. Existing `tasks/` documents and the README remain unchanged. Record essential Windows operation notes here or in the final handoff, not in a new user manual.

The one proposed runtime addition is **`windows-curses` for interactive use only**. Use a prebuilt wheel in the selected development interpreter:

```powershell
py -3 -m pip install --only-binary=:all: windows-curses
```

`py -3` is illustrative: an explicit installed `python.exe` is equally valid, and is preferable when multiple environments exist. Use that same interpreter for installation, tests and generated launchers. Do not install dependencies from inside the application or installer. If the matching wheel is absent, report the Python/architecture limitation; do not compile it or silently replace the TUI.

## Order and verification budget

`W-01 → W-02 → W-03 → W-04 → W-05 → W-06`

Tasks describe acceptance, not a demand to run the entire suite at every step. Update a test fixture when the corresponding task needs it. Batch focused verification after W-03 and W-05; run the full native offline suite once in W-06. Repeat only failed/invalidated checks. A task whose acceptance has not yet been verified is implemented, not verified.

### W-01 — Make shared file and lock operations native

**Findings:** F01, F04–F07, F11.
**Files:** `codex_limit_tools/common.py`, `tracker.py`, `installer.py`; a small internal platform helper if useful; relevant cases in `test_history.py`, `test_checkpoints.py`, `test_side_effects.py`.

**Implementation**

- Guard Unix imports. Keep the POSIX implementation and lock filenames/locations unchanged. Route the installer lock, daemon/migration lock and `running()` probe through a single Windows lock implementation.
- Use nonblocking fixed-range locking (`msvcrt.locking` first candidate; `LockFileEx` only if necessary). Seek explicitly, distinguish contention from other errors, release on every exit and prevent inheritance. An empty lock file must work without a pre-lock write. The status probe must not create/change state or claim a permission error means “running.”
- Implement the Windows equivalent of `private_open`: append/exclusive and binary modes preserved; final-file reparse/symlink/hard-link checks before writes; opened-handle validation; no silent removal of no-follow protection. Keep the helper internal rather than adding a filesystem abstraction framework.
- Preserve private creation through Windows ACLs for state, SQLite sidecars, logs, backups and export temporaries. Restrict newly created private artifacts before content is written; do not recursively change pre-existing user ACLs. Cover both default and explicitly selected state/export locations. Use the report's narrowly scoped native-handle/ACL candidate; no `pywin32` requirement.
- Preserve atomic replacement and exclusive publication. Release owned handles before replacing/deleting files. Failed writes must retain the prior complete destination and not write through aliases.
- Add any new runtime module to the explicit installer manifest immediately.

**Acceptance**

All three commands import and provide help/version/license on Windows. The same exclusion rule covers a second collector, migration, installation and the status probe, including separate handles in one process and competing processes. Releasing or exiting the owner permits reacquisition. Existing data/price snapshots and schema versions are unchanged. Alias sentinels are unchanged after rejected operations; Windows ACL assertions test access-control semantics rather than POSIX mode bits. Unix mode/lock tests remain intact.

**Verification:** collect this evidence in focused batch A after W-03; tiny import checks while implementing are sufficient until then. Do not skip the entire side-effect suite because a Windows symlink fixture needs privileges.

### W-02 — Port quota transport and executable resolution

**Depends on:** W-01. **Findings:** F02, F03, F14.
**Files:** `codex_limit_tools/quota.py`; fake-server setup in `tests/test_rpc.py`, `tests/test_tools.py`.

**Implementation**

Retain `QuotaSource` and its allowlisted initialize/account/rate-limit sequence. Keep bucket selection, weekly-window validation, account hashing and returned fields unchanged. On Windows replace only the pipe wait mechanism with one bounded reader thread/queue per process; use the existing framing/parser, request IDs, deadlines, 2 MiB guard and redacted errors. Preserve Unix `select()`.

Handle a path to a native executable, paths containing spaces, and discovery of an installed Codex command. Prefer direct native-process ownership. Resolve a recognized npm shim only from its actual nearby installed package layout; otherwise explain how to use existing `--codex-bin` with the native payload. Do not use `shell=True` as a universal fix or change PowerShell execution policy. Cleanup must include the owned app-server and reader after success, timeout, EOF, oversized output or protocol error; a full queue must not hang shutdown.

Use a native fake server without compiling an executable. The report describes the `sys.executable` plus isolated `app-server` Python fixture approach. Preserve fake-server method auditing and negative cases; no production test-only CLI option.

**Acceptance**

Fake quota results and validation errors match the existing contract. A partial line times out; closed and oversized streams fail clearly; notifications/unmatched IDs do not become quota results; server requests receive rejection. Only the four allowed methods are sent. Repeated open/read/close operations do not accumulate owned processes or reader threads. Unsupported shims fail explicitly, not by falling through to some other installed Codex.

**Verification:** existing RPC cases plus only missing framing/cleanup cases, in batch A. No live account required.

### W-03 — Preserve background collector lifecycle

**Depends on:** W-02. **Findings:** F08, F14.
**Files:** `codex_limit_tools/cli.py`, `tracker.py`, Windows launch helper if introduced; `tests/test_tools.py`, `test_checkpoints.py`.

**Implementation**

Use Windows background creation flags with redirected stdin/logs; keep `start_new_session=True` on Unix. Keep the existing SQLite control/checkpoint mechanism. Do not add PID-file control, services, process-name killing or a second control protocol. Ensure the quota subprocess remains owned and is cleaned up by normal collector shutdown/error handling.

Adapt the portable integration fixture to native execution. In `test_tools.py`, isolate only the Unix PTY block; do not disable the surrounding fake-RPC, daemon or checkpoint tests on Windows.

**Acceptance**

Starting twice does not create two collectors. Pause stops observations, resume preserves run identity and starts a fresh baseline, checkpoint acknowledgement/error/paused behavior is unchanged, and shutdown reaches offline and releases the lock. A detached collector survives exit of its launching shell and TUI `q`, without popup windows or inherited terminal dependencies. No unrelated Codex process is stopped. Use synthetic state and fake quota throughout.

**Verification — batch A:** run focused existing persistence, RPC, lifecycle and checkpoint tests. Only a real terminal close/detach observation may be deferred to the single native console session in W-06. This batch is needed because the changed process/lock boundaries can corrupt or strand tracking even when pure calculation tests pass.

### W-04 — Keep the same TUI using a Windows curses wheel

**Depends on:** W-03. **Finding:** F09.
**Files:** `codex_limit_tools/tui.py`, UI-entry paths in `cli.py`; `tests/test_tui.py`, `test_licensing.py`, relevant CLI tests.

**Implementation**

Make curses loading lazy so pure rendering and headless commands work without it. Before an interactive UI is requested, check that the dependency is available; for interactive `start tracking`, do this before creating run/state or starting the collector. Match the existing TTY/`--background` decision, rather than requiring curses for redirected/headless use.

Use `windows-curses` with the existing `lines_for()` and curses renderer. Change only demonstrated PDCurses differences (for example resize/color handling), with conditional code where needed. Preserve content, views, keyboard controls, narrow-screen behavior and terminal restoration. Do not introduce a second ANSI renderer, Textual/Rich or new UI features.

**Acceptance**

Without the wheel, help/reports/exports/background tracking remain available; an interactive request fails with an actionable dependency message and no newly started collector. With the wheel, segment/run/history views, `q`, `s`, `r`, `v`, `h`, `[` and `]` preserve their current behavior. Rendering remains recognizable at equal dimensions and tolerates a narrow terminal and resize.

**Verification:** pure rendering and missing-dependency/preflight assertions join batch B. Actual display/input is checked once in W-06, not through a new ConPTY automation project.

### W-05 — Add native installation and command launchers

**Depends on:** W-04. **Findings:** F07, F10–F12, F14.
**Files:** new `install.py`; `codex_limit_tools/installer.py`, `usage.py` (UTF-8 reads); `licensing.py` only as needed; installation/licensing/side-effect fixtures.

**Implementation**

- Add a minimal Python entry calling the existing installer engine with the correct source directory. Keep Unix `install.sh` and command symlinks. The snapshot's installer module does not automatically call `main` under `python -m`; do not document that invocation without implementing it.
- On Windows install three `.cmd` launchers instead of symlinks. Invoke the selected interpreter and installed scripts, preserve arguments and return codes, and quote interpreter/install paths. Do not rely on `.py` file associations or a different Python on PATH.
- Include new modules/entry point in `PAYLOAD`. Update collision checks, command backups, atomic switching and rollback for the actual `.cmd` filenames. Retain the explicit manifest and GPL/license payload.
- Preserve `--prefix`, `--upgrade`/`--update`, repeated `--data-dir`, external prices and database backups. No automatic migration, tracking, PATH/registry editing or dependency installation.
- Make UTF-8 contract reads explicit where needed, especially price loading/copying. Do not change accounting or globally reconfigure the terminal encoding.

**Acceptance**

Temporary installation works from PowerShell without Bash, admin rights or symlink privileges. All installed commands support help/version/license and pass representative offline operations. A path containing spaces and non-ASCII characters works with that interpreter. Upgrade retains state/configuration/frozen prices, refuses an active collector and backs up each supplied state directory. An injected switch failure restores the previous package and all command launchers. Installed code includes every helper, not merely checkout code.

**Verification — batch B:** run adapted installer/licensing tests plus TUI preflight/rendering cases. This catches distribution failures distinct from batch A. Do not test by upgrading the user's active installation.

### W-06 — Complete native evidence and hand off the Linux gate

**Depends on:** W-05. **Findings:** F13–F15; integration acceptance for all previous tasks.
**Files:** `tests/run_audit.py`, existing test fixtures, only product files needed for a reproduced defect; short `docs/NEXT-RUN.md` handoff.

**Implementation / verification**

1. Finish the minimal Windows audit-harness adaptation: necessary system variables preserved; synthetic `USERPROFILE`/AppData/temp paths; explicit fake executable paths; no live-account/PATH fallback; correctly decoded test output. Keep `--trace` Linux-only.
2. Reuse indexing fixtures and add only missing coverage for a Unicode/space-containing path, CRLF/partial appended records, and equivalent `CODEX_HOME` spelling where reproducible. Do not rewrite file identity or add a new log schema speculatively.
3. Run **one full native offline suite** via the selected interpreter:

   ```powershell
   py -3 -B tests/run_audit.py
   ```

   Record passed/failed/skipped counts and the candidate revision. Meaningful OS-specific skips must be named; do not label skipped checks as passing. Fix failures with focused reruns, then repeat the full suite only when the final tested tree changed.

4. In **one short native console session**, use synthetic history/fake quota to check: the same rows/color roles at roughly 110 columns; narrow resize around 30 columns; segment/run/history and grouping keys; pause/resume; `q` with normal terminal restoration; collection surviving launcher-terminal closure; shutdown from a second terminal and clean owned-process exit. Combine observations in one session. No long-running workload or benchmark.
5. Only with separate explicit permission, make one real native Codex quota read and verify cleanup; inspect an authorized existing log sample only if permitted. Report live integration as unverified otherwise.
6. Give the maintainer the exact candidate revision and `python3 -B tests/run_audit.py` for Linux. Reuse a valid Linux result for identical relevant code; otherwise this single native Linux run is a release gate, not a reason to build remote access or CI. Shared POSIX changes require corresponding native evidence before the no-regression claim.

**Completion record**

Report only: changed behavior/files, completed task IDs, environment, test commands/counts/revision, console result, live-check status, Linux-gate status, and concrete limitations. Keep detailed logs local and ignored. Mark the implementation ready for the remaining gate rather than “fully supported” when native-console, live-integration or Linux evidence is still missing. Do not revise the README in this pipeline.
