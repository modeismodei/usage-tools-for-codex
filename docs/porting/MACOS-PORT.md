# macOS port: implementation pipeline

## Approach

**Validate the existing Unix implementation first; patch only observed incompatibilities.** The [source inspection](PORTABILITY-REPORT.md) found no unconditional macOS runtime blocker. In particular, `fcntl`, pipe `select`, POSIX file modes, session detachment, Bash and curses are not Linux-exclusive.

This pipeline does not depend on the Windows port. Use a native Mac with an installed Python 3.10+ that provides curses/SQLite and an actual terminal. Record macOS version, CPU architecture, Python distribution/version, terminal and, if authorized, Codex version/install method. Verification on one architecture must not be described as testing both Intel and Apple Silicon.

Keep existing paths, installer, command names, TUI and quota protocol. Do not add Homebrew packaging, a launchd agent, app bundle, universal executable, new dependencies, an alternate quota backend or a path migration. Existing `tasks/` files and the README are frozen for this phase.

## Order and verification budget

`M-01 → M-02 (only if needed) → M-03`

The Windows task list is not a second backlog to implement here. If its changes already exist, reuse them and preserve their Windows branch. Do not replace a proven POSIX path just for cross-platform symmetry.

One native full offline baseline is justified because there is no prior native macOS result. If it passes and relevant code/tests stay unchanged, reuse it as the final suite result. If a repair is required, use focused failing tests while editing, then one final full offline run. Add one short native terminal/lifecycle session. Live account checks are separately opt-in.

### M-01 — Establish the native baseline

**Findings:** F01–F15, with macOS status as classified in the report.
**Inspect:** `quota.py`, `common.py`, `tracker.py`, `tui.py`, `installer.py`, `install.sh`, `tests/run_audit.py`, OS-sensitive integration fixtures.

**Work**

Confirm that the checkout matches the inspected functions; account for intervening commits without restarting a repository-wide audit. Check interpreter imports and terminal availability. A Python build missing curses is an environment prerequisite failure, not evidence that a new renderer is needed.

Before running the existing harness, check that its isolated home/Codex/temp setup stays isolated on this Mac. Run the existing full offline suite without syscall tracing:

```bash
python3 -B tests/run_audit.py
```

Do not run `--trace`: that mode depends on Linux `strace`. Do not install tracing tools or implement DTrace support. If forced `C.UTF-8` or `/var` versus `/private/var` path spelling causes a concrete fixture failure, record it as a harness issue rather than changing runtime semantics blindly.

The baseline should exercise the existing fake-RPC and Unix PTY fixtures, locks, SQLite history/migration, installer/rollback, alias protections, licenses, calculations and exports. Installer tests must continue to operate only in temporary directories.

**Acceptance**

A recorded native result identifies any failing cases, OS-specific skips and environment blockers. The normal installer/commands need no GNU-only substitutions unless a failure demonstrates one. No live account call or real-state migration occurred. Existing Linux evidence is not relabeled as macOS evidence.

**Next action**

If the baseline passes, M-02 may be a documented no-op; proceed to the terminal/native-integration session. Do not manufacture code changes to “complete the port.”

### M-02 — Repair only demonstrated macOS issues

**Depends on:** M-01. **Findings:** only those reproduced on this Mac.
**Files:** only the failed boundary and its existing tests; likely `quota.py`, `tui.py`, `usage.py`, installer or verification fixtures, but none is a mandatory edit.

**Candidate repairs, conditional on evidence**

| Observed failure | Bounded candidate | Do not do |
|---|---|---|
| Codex not found or wrapper child survives cleanup | Honor the actual `--codex-bin`; resolve a recognized installed wrapper's native target only if needed. Keep the same stdio protocol and ownership checks. | Parse a UI, scrape credentials or introduce a new quota source. |
| Partial/closed server response mishandled | Fix the specific framed-I/O or cleanup defect while preserving request deadlines and allowlist. | Replace functioning Unix pipe `select` with the Windows thread path without necessity. |
| Curses color/default background/resize or restoration failure | Guard only the unsupported operation, reusing current rendering and keybindings. | Re-theme, rewrite the UI or add a GUI. |
| Equivalent `CODEX_HOME` path incorrectly rejected | Reproduce with an isolated fixture and use filesystem identity/equivalence where appropriate. Preserve Linux case-sensitive distinctions. | Lowercase all paths, rewrite history keys or change schemas. |
| UTF-8 asset decoding fails | Specify UTF-8 for the affected text contract. | Reconfigure the user's global locale or normalize every file. |
| Installer failure under the existing system Bash | Correct only the nonportable operation; preserve stages, command links, backups, no-clobber prices and rollback. | Require GNU Bash/coreutils as a speculative dependency. |
| Harness locale/temp-path mismatch | Select an available encoding/normalize fixture paths, keeping synthetic homes and explicit fake executables. | Disable isolation, copy real credentials or skip whole suites. |

Do not treat availability of a different upstream log event schema as authorization to add new ingestion features. Verify whether it is genuinely required by the installed native Codex, then report a scoped blocker if it exceeds this port.

**Acceptance**

Each source change corresponds to an observed failure and an existing or minimal regression assertion. No accounting/export/schema/price behavior changes. Linux's original branches and Windows changes, if present, remain intact. Run focused failed/affected cases rather than the full suite after every edit.

A no-op task is acceptable when the baseline and subsequent native checks show no need for a patch.

### M-03 — Verify terminal behavior, native integration and Linux preservation

**Depends on:** M-01 and any needed M-02 fixes.
**Files:** no mandatory runtime edits; a short `docs/NEXT-RUN.md` verification/handoff entry if needed.

**Native session**

Use synthetic tracking history and the existing fake app-server in one short actual-terminal session. Verify the following together:

- Familiar content/order/color roles at comparable dimensions (roughly 110 columns); narrow view around 30 columns and resize recovery; segment/run/history and grouping controls; readable special characters.
- Pause/resume and checkpoint behavior; `q` detaches without stopping the collector and restores the terminal. Close the launching terminal, check the fake collector from another terminal, then shut it down and confirm the owned fake app-server/lock are gone.
- The normal `bash install.sh` path and installed command resolution are covered by the temporary installer fixture. Add a manual temporary-install check only if that fixture did not cover an observed shell/PATH problem.

The terminal session is needed because passing text and PTY tests does not establish real terminal/font/color behavior. No screenshot baseline service, repeated interactive sessions, long quota sampling or generated workload is required.

**Optional real integration**

Default authorization is **no live account access**. With explicit permission, perform one `codex-quota` read using the native installed Codex and normal authenticated environment, then confirm cleanup. Do not start a collector or send any model request. An authorized existing log sample may confirm `token_usage_record` and normal `CODEX_HOME` discovery; do not copy logs, identifiers or payloads into tracked evidence.

If unavailable, distinguish offline/fake verification from “live integration unverified.” A successful fake test alone does not validate an upstream executable or account response.

**Final automated result**

Reuse M-01's full result if relevant code/tests did not change. Otherwise, after fixes, run once:

```bash
python3 -B tests/run_audit.py
```

Do not additionally run `run_checks.py` over the unchanged tree just to duplicate full discovery. Record real counts, skips and revision; retain detailed logs only locally.

**Linux gate**

Any changed shared runtime/test code requires a Linux regression result for the candidate tree. Hand the maintainer its revision and the same full offline command. No remote Mac/Linux access or new CI setup is required. With no relevant changes, reuse already valid Linux evidence; with missing evidence, mark the gate pending. If a shared change affects a previously completed Windows port, request only the affected native Windows recheck and do not claim that old result verifies new code.

**Acceptance and handoff**

The final record names the environment, whether runtime patches were necessary, passed/failed/skipped tests, terminal result, real-Codex verification status and Linux gate. No unsupported architecture claim, README rewrite or unrelated improvement is included. Remaining environment/live checks are explicit rather than counted as passed.
