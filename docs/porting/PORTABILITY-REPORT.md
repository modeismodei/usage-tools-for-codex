# Native Windows and macOS portability report

## Scope and evidence

This report concerns the supplied **`usage-tools-for-codex-snapshot-2026-09-23.zip`**, not a later GitHub revision. Its SHA-256 is:

```text
6a966e52d0a05e202894b8858e67327db5b69fe6da2637de1b5e328281ff0a09
```

The snapshot declares package version **1.1.0** and database schema **2**. It contains no Git metadata from which to identify a commit. File and line references below refer to this snapshot; use the named functions if lines move.

The inspection covered the three command entry points, all eleven package modules, the installer, and the test/verification infrastructure. **No project code, tests, installer, collector, or live quota request was executed for this report.** Confirmed incompatibilities are source-level findings supported by platform documentation, not results from native Windows/macOS execution. Conditional findings explicitly require reproduction.

Companion documents: [Windows tasks](WINDOWS-PORT.md), [macOS tasks](MACOS-PORT.md), [Windows launch prompt](PROMPT-WINDOWS.md), [macOS launch prompt](PROMPT-MACOS.md). Place these five files in `docs/porting/`. They do not replace existing `tasks/` documents or the README.

## Conclusions

**Windows needs a bounded native port.** Unconditional `fcntl` imports prevent every command from starting. After that, pipe polling, file opening/permissions, locking, background detachment, command installation, and curses need Windows-specific handling.

**macOS does not presently justify a separate runtime backend.** Its Unix interfaces match the implementation's principal dependencies. No unconditional macOS runtime blocker was found. Native installation, quota, collector lifecycle, and terminal checks remain necessary; passing static inspection is not a support certification. The optional `strace` audit mode is Linux-specific, not part of normal operation.

**Quota acquisition is not Linux-specific at the protocol level.** Both ports should retain the current Codex app-server stdio protocol. Windows needs a different way to wait for pipe output; macOS should first use the existing implementation unchanged.

## Findings and affected files

Status: **B** = definite blocker or incompatible semantics; **C** = conditional defect/risk; **V** = native verification required, no confirmed incompatibility; **T** = test/development tooling only.

| ID | Feature and source evidence | Native Windows | macOS | Proposed action / tasks |
|---|---|---|---|---|
| F01 | All CLI startup: `common.py:3`, `tracker.py:3`, `installer.py:6` import `fcntl`; `cli.py:5–10` imports the first two before argument handling. | **B:** all three commands fail, including help/version/license. | **V:** `fcntl` is a Unix facility. | Conditional platform imports; preserve POSIX implementation. W-01 / M-01. |
| F02 | Quota response waiting: `quota.py:14–72`, especially `RPC.call():46–49`, uses `select()` on subprocess stdout. | **B:** Windows `select()` cannot monitor these pipes. | **V:** Unix pipe polling is supported. | Windows bounded reader thread; same framing/parser and methods. W-02 / M-01, M-03. |
| F03 | Codex launch and ownership: `quota.py:14`, `RPC.close():16–25`; `cli.py` stores `--codex-bin`. | **C:** bare command resolution and npm `.cmd`/`.ps1` shims are not accounted for. Terminating a wrapper may leave its native child. | **C/V:** executable/PATH and wrapper ownership must be checked with the installed distribution; not inherently broken. | Prefer an owned native executable. Resolve only understood installed layouts or use existing `--codex-bin`; no generic shell execution. W-02 / M-01, M-03. |
| F04 | Collector, migration and installation exclusion: `common.py:71–80`, `tracker.py:195–200`, `installer.py:90–101`. | **B:** three consumers rely on `flock`. An import-only fix is insufficient. | **V:** retain same lock file and POSIX primitive. | One Windows nonblocking byte-range lock protocol shared by all consumers, including the status probe. W-01 / M-01. |
| F05 | Safe mutable file opening: `common.py:9–37`, especially `private_open():22`; database/WAL checks also feed installer backup. | **B:** `O_NOFOLLOW` is unavailable; a zero-valued substitute would silently weaken alias protection. Windows reparse points also need appropriate inspection. | **V:** no replacement required on the normal local filesystem. | Small native file-opening helper preserving final-file link/regular-file checks; preserve rejection before writing. W-01 / M-01. |
| F06 | Private state/logs/backups/exports: `common.py:19–24,41–56,71–74,127–153`; `tracker.py:139–144`; `installer.py:50–63`. | **B:** POSIX modes and `umask` do not establish equivalent Windows access control. | **V:** POSIX mode behavior remains applicable. | Windows ACL equivalent for newly created private artifacts; do not claim `chmod(0600)` provides it. W-01 / M-01. |
| F07 | Atomic exports, exclusive price creation, package switch/rollback: `common.py:41–56`; `installer.py:110–149`. | **C:** open-handle sharing and filesystem capabilities may prevent replace/link/rename. These APIs are not categorically unsupported. | **V:** existing local-filesystem operations are applicable. | Keep atomic/no-clobber behavior and close owned handles correctly. Verify rollback; no new persistence scheme. W-01, W-05 / M-01. |
| F08 | Background process and control: `cli.py:20–30`; `tracker.py:139–193`. | **B/C:** `start_new_session` supplies POSIX detachment, not Windows semantics. Windows process termination is not Unix graceful SIGTERM. | **V:** existing session detachment and signal handlers should be reusable. | Native creation flags on Windows; keep SQLite pause/resume/shutdown/checkpoint control. W-03 / M-03. |
| F09 | Interactive display: `tui.py:3,64–109`; CLI starts collection before entering UI at `cli.py:206–225`. | **B:** standard CPython lacks curses. A missing UI dependency can otherwise surface after starting collection. | **C/V:** requires a curses-enabled Python and working terminal description; rendering needs native confirmation. | Windows prebuilt `windows-curses`; lazy import and preflight before UI-start side effects. Keep renderer/keybindings. W-04 / M-01, M-03. |
| F10 | Installation and command entry: `install.sh:1–13`; root scripts `:1–15`; `installer.py:35–36,102–118,128–132`. | **B:** Bash and executable shebangs are not a native Windows installation interface; symlink creation is not an ordinary-user guarantee. | **V:** simple Bash script and Unix command links are usable candidates, without GNU-specific rewrites. | Small Python installer entry point and `.cmd` launchers on Windows; retain Unix path. W-05 / M-01. |
| F11 | Distribution integration: `installer.py:19–23,154–177`. | **B if overlooked:** added helpers will be absent from installed copies unless explicitly listed. Also, `python -m codex_limit_tools.installer` currently does not invoke `main`. | Same packaging trap if shared helpers are introduced. | Update the explicit manifest; exercise installed commands, not just checkout imports. Do not copy the whole repository. W-01, W-05 / M-01. |
| F12 | Text decoding: `usage.py:21–22`, `installer.py:136`, `licensing.py:14–15`; test logs also use implicit decoding. | **C:** locale-dependent reads can misdecode UTF-8 price/config text. Shipped ASCII license text itself is not proof of a failure. | **C/V:** normally UTF-8, but inspect only a reproduced issue. | Explicit UTF-8 for UTF-8 text assets where needed; no global console/locale redesign. W-05 / M-02. |
| F13 | Local log identity/path handling: `usage.py:47–104`; `cli.py:313–314`. | **C/V:** string comparisons of resolved `CODEX_HOME` may disagree for equivalent case-insensitive paths; native log sharing/schema must be checked. | **C/V:** case-insensitive volumes and equivalent path spellings merit a fixture; no confirmed indexing defect. | Reproduce before changing path identity. `st_dev`, `st_ino`, binary JSONL reading and `Path.as_uri()` are not inherently Linux-only. W-06 / M-01, M-02. |
| F14 | Integration fixtures: `tests/test_rpc.py:11–48`; `tests/test_tools.py:99–186`; `test_install.py:44,121–134`; `test_licensing.py:22`; `test_side_effects.py:49–60,109–177`. | **T/B:** fake executable shebangs, Bash, POSIX PTYs, mode assertions and symlink setup obstruct meaningful native tests. | **T/V:** most fixtures should run unchanged; PTY/terminal details require checking. | Adapt only OS-bound fixtures/assertions. Never skip whole lifecycle/installer suites. W-01–W-06 / M-01, M-02. |
| F15 | Verification harness: `tests/run_audit.py:83–123`, `tests/run_checks.py:20–23`. | **T/C:** synthetic environment lacks Windows home/temp/system variables and executable guard conventions. `strace` mode is unavailable. | **T/C:** `--trace` unavailable; forced `C.UTF-8` or temporary-path spelling can be environment-specific. | Port ordinary offline harness; preserve isolation. Keep `--trace` Linux-only. W-06 / M-01, M-02. |

Module names in this table are relative to `codex_limit_tools/` unless a root/test path is given.

### Features not requiring a redesign

`estimate.py`, `render.py`, token aggregation, run/segment semantics, CSV/JSON contracts, price snapshots and SQLite schemas contain no identified OS-specific algorithmic blocker. Their tests remain regression checks, not an invitation to refactor them.

The existing `~/.local`, `~/.config`, `XDG_*` overrides, `CODEX_HOME`, and explicit `--data-dir` paths can be retained. They are unconventional on Windows/macOS, not unusable. Moving them to AppData or Library would add migration work unrelated to the requested port.

Binary JSONL ingestion already handles newline-terminated bytes; Windows CRLF is not a reason to replace the parser. Availability of the expected `token_usage_record` in the installed Codex version must still be confirmed. An upstream log-schema difference is not automatically an OS port defect.

## Candidate solutions and bounded decisions

### Quota: one protocol, two pipe wait implementations

The existing sequence is `initialize`, `initialized`, `account/read` with `refreshToken: false`, then `account/rateLimits/read`. `QuotaSource.read()` selects the requested bucket and a unique 10,080-minute weekly window, checks finite percentages/reset time, and hashes account identity. Preserve it. The upstream app-server documents stdio newline-delimited JSON and these account methods [S1].

On Windows, use **one reader thread per owned app-server process**, reading bounded byte chunks into a bounded queue. `RPC.call()` waits with its existing monotonic deadline and uses the shared framing/parser. Preserve the 2 MiB receive-buffer guard, response-ID matching, notification handling, rejection of server-initiated requests, and errors that do not expose account payloads. Closing must terminate/reap the owned process, unblock the reader and allow bounded cleanup, including a full queue or partial response. Do not introduce a thread per request.

Keep Unix `select()` unless an actual native defect justifies changing it. `selectors` is not a Windows-pipe fix [S2]. Avoid a second protocol, WebSocket listener, asyncio-wide rewrite, terminal scraping, credential scraping, prompts or heartbeat messages.

Use `shutil.which`/absolute paths deliberately. Prefer direct `codex.exe` ownership on Windows. For a recognized official npm shim, a small resolver may locate the installed native payload; inspect that installation instead of hard-coding one historical layout. Upstream's wrapper currently chooses a platform package and launches a native binary [S3]. If the shim cannot be resolved safely, give an actionable instruction to use the **existing** `--codex-bin` with that native executable. Do not silently claim the unresolved shim is supported. On macOS also verify wrapper cleanup rather than assuming it propagates every exit condition.

### Locks and files: preserve existing safety, not just successful startup

Keep POSIX `flock` unchanged. A Windows `msvcrt.locking` implementation is the smallest first candidate; use a fixed byte range, nonblocking acquisition and identical offsets in every caller. Locking beyond EOF is supported, so do not add a dummy write or truncate the lock before acquiring it [S4]. Verify acquisition through the read-only status-probe path; `LockFileEx` is the fallback if required for compatible access/handle semantics [S5]. Lock contention is distinct from permission or I/O failure.

For Windows file opening, a narrowly scoped `ctypes` helper around native handles is preferable to discarding `O_NOFOLLOW`. Open without following the final reparse point, check the opened object/link count before writes, and keep handles non-inheritable. `CreateFileW` exposes both reparse handling and creation security attributes [S6]. Apply equivalent protection to the installer's internal directory-alias checks; do not invent a broader filesystem hardening project.

Private output must remain private to ordinary other users. Use an appropriate Windows DACL on newly created state directories/files, backups and export temporary files; protect the temporary file **before** writing sensitive content. A small helper using Windows security descriptors can do this without a compiler or `pywin32` [S7]. Preserve existing objects' ACLs rather than recursively rewriting the user's directories. Account for SQLite sidecars through the state directory's inheritance. Access by administrators/SYSTEM is not the same as access granted to arbitrary users.

Python's Windows `chmod` is not an ACL implementation. Python 3.13+ adds special handling of `mkdir(mode=0o700)`, but that alone does not cover existing directories or arbitrary export destinations [S8]. Do not raise the project's Python minimum just to hide this gap. Use normal local filesystems for this port; expanding network/removable/cloud-filesystem support is out of scope.

### Collector: native launch, existing control plane

Retain direct Python execution, redirected stdin/logs and the SQLite control record. Windows should use appropriate detachment flags, initially `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, while Unix retains `start_new_session=True`. Verify behavior rather than merely checking the flags. `CREATE_NO_WINDOW` is not useful in combination with `DETACHED_PROCESS` [S9].

Normal shutdown must use the current control request, not global process-name kills or a new service. Track only processes created by this tool. Closing the terminal/UI, pausing and RPC failure must not leave an unmanaged app-server or terminate unrelated Codex work.

### TUI: retain curses instead of maintaining a second UI

Use a **prebuilt `windows-curses` wheel** for the Windows TUI. It supplies the existing curses API; Linux/macOS keep their standard-library interface [S10, S11]. This is one platform-scoped dependency, not a generated application executable or a build toolchain.

Check wheel availability for the actual Python/architecture before promising support. The inspected package listing supplies x86/x64 wheels; do not assume native ARM64 availability. If no suitable wheel exists, report that specific environment blocker instead of compiling or inventing another renderer.

Make curses loading lazy and check availability before an interactive `start tracking` creates state or starts a collector. Headless commands remain usable without the wheel. Preserve `lines_for()`, content order, labels, color roles, keybindings, views and resizing. Font glyphs, dim intensity and exact shades may vary by terminal; a plain-text replacement is not equivalent TUI support.

### Installer: same engine, native entry and launchers

Add a tiny root `install.py` invoking the existing installer engine, and include it plus added helpers in the manifest. Keep `install.sh` for Unix. On Windows create three ordinary `.cmd` launchers, invoking the installing Python interpreter and installed scripts with correct quoting/argument/exit-code handling. No administrator rights, Developer Mode, Bash, PowerShell execution-policy changes, registry edits, symlink privilege or compiled launcher should be required.

The backup/switch/rollback bookkeeping must manage the actual Windows launcher filenames. Installed help/license commands, upgrades, database backups and failure rollback must work from a path containing spaces. Preserve external configuration and prices. Do not migrate state or start tracking during install.

## Minimal verification and Linux preservation

### Existing coverage to reuse

| Boundary | Existing tests / observation | Reason |
|---|---|---|
| Locks and persistence | `test_history.py`, `test_checkpoints.py`, relevant `test_side_effects.py` cases | Migration/daemon/installer must not acquire incompatible locks or weaken data protection. |
| Protocol and collector | `test_rpc.py`, portable portions of `test_tools.py` | Exercise timeout, malformed/oversized/closed streams, allowlist, pause/resume, checkpoint and shutdown without an account. |
| Installation | `test_install.py`, `test_licensing.py` | Checkout-only success misses manifest, launcher and rollback failures. |
| Display | `test_tui.py`, existing Unix PTY block; one native console session | String assertions cannot verify native curses input, colors, resizing or terminal restoration. |
| Calculations and commands | Existing full unittest discovery via `tests/run_audit.py` | Detect accidental changes to shared accounting/history/export behavior. No new benchmark suite. |

**Windows fixtures:** fake shebang scripts must not be mistaken for native executables. A minimal fixture can set the fake executable to `sys.executable` and put the Python fake server in a file named `app-server` in the isolated subprocess working directory: the existing `[executable, 'app-server']` launch then works without a new public test flag or compiled stub. Adapt the fixture's argument handling and restore any changed working directory.

`test_tools.py:99–186` combines portable daemon coverage with a Unix PTY block. Split or guard **only the PTY portion** on Windows. Keep lifecycle checks. Replace POSIX permission assertions with meaningful Windows ACL checks there; retain the original assertions on Unix. If symlink creation is unavailable, skip that individual fixture with a reason, not the entire alias/side-effect suite. Retain hard-link coverage.

Make `run_audit.py` preserve required Windows system variables while directing `USERPROFILE`, AppData and temporary directories into its sandbox. Do not copy the entire real environment or expose a live Codex executable as a fallback. Its Python socket guard is not an OS-wide network sandbox. Use explicit fake executable paths. Keep `--trace` Linux-only; no DTrace, ETW, Procmon or new tracing pipeline is required.

### Test budget

Windows: one focused batch after storage/protocol/lifecycle work, one after TUI/installer work, and one full native offline suite at completion. Add a single short native console session; a live quota read is separate and **opt-in**. Re-run only failed or invalidated checks after changes.

macOS: one native full offline baseline. Fix only concrete failures, using focused reruns. Reuse the baseline as the final suite result if relevant code/tests did not change; otherwise run one final full suite. One native console/lifecycle session and an optional authorized quota read complete the platform checks.

The final full offline command is `python -B tests/run_audit.py` on the selected Windows interpreter or `python3 -B tests/run_audit.py` on Unix, **without `--trace`**. It already discovers the full unit suite; do not also run `run_checks.py` over the same unchanged tree for an identical claim.

### Sequential execution and release gate

The pipelines have no dependency on each other. macOS-first is a low-change baseline, not a requirement. Run the second port on the latest accepted tree and reuse existing helpers; do not implement both simultaneously or create two competing abstraction layers.

Preserve POSIX lock identities, launch behavior, CLI contracts, paths, schema versions, calculation outputs and frozen prices. Do not add an OS label to historical data or migrate it merely for portability.

A Linux regression result must correspond to the candidate code being accepted. Reuse valid evidence for identical relevant code; otherwise the maintainer runs the existing full offline suite on Linux once. The native-port agent can hand off the revision and command without remote access or new CI infrastructure. Lack of a Linux machine is **pending verification**, not a passing Linux gate. If later shared changes invalidate earlier platform evidence, request only the affected rechecks; do not require both agents to run concurrently.

No finite test plan proves “no regressions of any kind.” The gate prevents declaring an untested port complete and retains the concrete protections already tested by this repository.

### Live check authorization

Default: **no real account access**. A fake server verifies the client logic, not the installed Codex binary's authentication, schema or cleanup.

After explicit authorization, perform one quota read using the actual native Codex installation, without a model turn, background monitor or quota-consumption experiment. Optionally inspect an existing, authorized local log sample to confirm the expected event format; never include its content/identifiers in tracked reports. Record only versions, platform and success/failure. If this check is unavailable, record “live integration unverified,” separately from offline results.

## References

Primary platform/upstream documentation checked on 2026-09-23. These explain external APIs; they do not replace the inspected source snapshot.

- [S1 — Codex app-server: stdio, initialization and account methods](https://developers.openai.com/codex/app-server)
- [S2 — Python `select`: Windows sockets versus Unix pipes](https://docs.python.org/3/library/select.html)
- [S3 — OpenAI's npm launcher and native binary selection](https://github.com/openai/codex/blob/main/codex-cli/bin/codex.js)
- [S4 — Python `msvcrt`: byte-range locks and descriptor conversion](https://docs.python.org/3/library/msvcrt.html)
- [S5 — Microsoft `LockFileEx`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex)
- [S6 — Microsoft `CreateFileW`: reparse points, sharing and security attributes](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
- [S7 — Microsoft security descriptor string format](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-string-format)
- [S8 — Python `os`: platform availability and permission behavior](https://docs.python.org/3/library/os.html)
- [S9 — Microsoft process creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)
- [S10 — Python curses portability notes](https://docs.python.org/3/howto/curses.html)
- [S11 — `windows-curses` package and binary distributions](https://pypi.org/project/windows-curses/)
- [S12 — Python `subprocess`: sessions, Windows launch and termination](https://docs.python.org/3/library/subprocess.html)
- [S13 — Python `fcntl`: Unix availability](https://docs.python.org/3/library/fcntl.html)
