# Data and side effects

The tools read local usage logs and retrieve account quota through Codex. They
do not submit prompts or start model workloads. This reference describes the
files, database changes, processes, and network access associated with each
command. It assumes trusted source code and user-controlled directories.

For a shorter overview, see [data, privacy, and compatibility](USAGE.md#data-privacy-and-compatibility)
in the user guide.

## Files and directories

Paths below mean their resolved locations, including explicitly selected parent
directory links:

- **Package**: source bundle or `PREFIX/lib/codex-limit-tools`.
- **Config**: `XDG_CONFIG_HOME/codex-limit-tools`, defaulting to
  `~/.config/codex-limit-tools`; the external price file is `prices.json`.
- **State**: `--data-dir`, defaulting to
  `XDG_STATE_HOME/codex-limit-estimator` or `~/.local/state/codex-limit-estimator`.
- **History**: state `tracking.sqlite3`, including SQLite WAL, shared-memory and
  journal sidecars. State also contains `daemon.lock` and `daemon.log`.
- **Logs**: `rollout-*.jsonl` below `CODEX_HOME`/`--codex-home` `sessions` and
  `archived_sessions`. Log file links are followed; their targets must be trusted.

All commands read their Python package and normal interpreter/OS resources
(libraries, locale, terminal descriptions and local name-service configuration).
They write normal output/errors to the caller's streams. Entry points suppress
package bytecode creation. No command downloads dependencies or installs a service.

## Command reference

| Operation | Additional allowed reads | Allowed writes and database changes | Subprocesses / network |
| --- | --- | --- | --- |
| `install.sh` | Explicit package manifest, existing commands/config, supplied history | Prefix `lib`/`bin` directories, install lock, staged package, three command links, retained command backups; create external prices only if absent; state directories/locks and SQLite backups of existing histories. No schema migration. | Bash starts Python; Python runs three staged commands with `--help`. No account RPC or internet. |
| `install.sh --upgrade` / `--update` | Same as installation | Same; retain old package, switch package/links, restore previous package/links on handled switch failure. Failed stages/backups may remain. All supplied state locks must be available. | Same as installation; never starts/stops a collector. |
| All `--help`, `--version`, `--license` | Package; bundled license for `--license` | Output only; no config/history creation | None beyond entry-point interpreter. |
| `codex-usage` while offline | Logs, selected external/bundled `--prices`, history | Lock state; create/migrate history as needed; update file offsets, identities, token responses, model mappings and index diagnostics. No quota snapshots or run repricing. | None; no internet. |
| `codex-usage` while state lock is held | Existing history and prices | Logical read-only view of the stored index; no indexing or migration | None; no internet. |
| `codex-quota` | Responses from selected Codex executable | Output only in this package; no tracking DB | One owned `codex app-server` child, closed on exit/error. External Codex caveat below. |
| Estimator `prices path` | Price-file existence | Output only | None. |
| `prices validate [FILE]` | Selected price JSON | Output only | None. |
| `prices import FILE` | Supplied price JSON | Create config directory; atomically replace external price file. Preserve frozen run prices/history. | None. |
| `start tracking` / `--new-run` | History/config and prices for a new run | Validate command/prices first; initialize/migrate DB; register run with frozen prices when needed; set control/status; append daemon log. Existing run configuration is reused unless `--new-run`. | Starts detached Python `_daemon` if offline; optional interactive UI. Daemon effects below. |
| `stop` | Existing history | Request pause in control row; an already running sample can finish. Daemon acknowledges pause and creates an observation boundary. | No new process; daemon closes its RPC child on pause. |
| `resume` | Existing configured run | Validate configuration first; migrate if needed; clear pause/shutdown controls; preserve run and frozen prices | Starts `_daemon` only if offline. |
| `shutdown` | Existing history | Set shutdown control; daemon finishes cleanup and marks status offline, rejects unfinished checkpoints | No new process; daemon terminates its owned RPC child. |
| `status`, `report`, `runs`, `segments`, `analyze` | Existing history; lock status where applicable | Logical read-only snapshot; no migration | None; no RPC or internet. |
| `export` (all views) | Existing history | Logical read-only history; atomic replacement of the explicitly named `.json`/`.csv` output | None; no RPC or internet. |
| `checkpoint` / `--wait` | Existing history and daemon lock | Insert bounded checkpoint request; expire stale requests. Daemon acknowledges/error-marks it and can collect one additional sample. Waiting only polls. | No child started by this command; existing daemon performs allowed quota reads. |
| `checkpoint --request-id` | Existing checkpoint/history and lock if waiting | Logical read-only; never requests another sample | None. |
| `ui` / default command | Existing history and terminal | Navigation/detach only render. Interactive `s`/`r` write pause/resume controls for a running daemon. Noninteractive display is logical read-only. | No collector started; local terminal mode/screen changes restored on exit. |
| `migrate` | Existing history/schema | Acquire daemon lock; back up existing DB; transactional schema upgrade and WAL initialization; may initialize an empty state directory | None. |
| `_daemon` (internal collector) | Saved run configuration, logs, history, quota responses | Hold state lock; incremental index writes; append segments/snapshots/events; update status, daemon metadata and checkpoints; append errors to daemon log. Pause/errors/reset/gaps end continuity. | Owns one read-only stdio RPC child at a time; closes/reopens on failure/resume and terminates it on shutdown. |

## Database reads and migrations

“Logical read-only” does not mean zero filesystem activity: SQLite can create or
update `-wal`/`-shm` coordination files while reading WAL history. Readers use
`mode=ro` and `query_only`, retaining committed WAL data rather than opening an
unsafe immutable view. Reading may also update filesystem access times.

Migration paths are **0 → 1 → 2** and **1 → 2**. Schema 1 adds runs and nullable
segment membership; old segments remain legacy/unknown. Schema 2 adds checkpoint
requests. Existing rows and frozen prices are retained. `user_version` and DDL
commit together; failures roll back and retain the pre-migration SQLite backup.
Newer unsupported schemas are refused. No migration or installer deletes history.

## Permissions and filesystem limits

New state files/backups/logs and atomic exports/prices use owner-only permissions.
Existing permissions are not silently changed. Mutable DB/sidecar/lock/log files
must be regular files with one link; aliased state is refused. Atomic output
replacement replaces a destination symlink/hard link without modifying its target.
Installation refuses symlinked internal `lib`/`bin` directories. These checks are
not a security sandbox against another process changing directory entries mid-operation.

## Codex requests and external effects

The only outgoing RPC methods are `initialize`, `initialized`, `account/read`
with `refreshToken: false`, and `account/rateLimits/read`. Server-initiated requests
receive an error response, never approval or model work. The selected external
Codex executable inherits its environment, can read authentication/configuration,
write its own logs/cache/state, and contact provider services. Those external
side effects depend on that executable and were **not verified with a live account**.

## Private data

Runtime history, daemon errors and exports can contain paths, labels, response
identifiers, timestamps, model metadata and account-derived hashes. Treat them as
private. Prompt/transcript text is not stored in the tracking database. No watcher,
shell profile, login configuration, boot service, Git remote or user authentication
file is intentionally modified by this package.
