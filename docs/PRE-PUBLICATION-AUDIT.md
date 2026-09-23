# Pre-publication side-effect audit

Audited code: **`0d862fbd54c09d77692653110537b043805c5482`**.
Starting revision: `283333dd0a358572a12c34cf33eb3d73fbf46f1a`.
Audit date: 2026-09-23. Environment: Linux, Python 3.14.4.

The [command-by-command boundaries](SIDE-EFFECTS.md) document allowed reads,
writes, subprocesses, network activity and database changes for installation,
every CLI action and the daemon. File mutations, process creation, RPC send
paths and both legacy migration paths were reviewed.

Observed effects were confined to temporary package/config/state/output paths,
SQLite coordination files and terminal/output devices. Indexing updated local
token metadata; tracking wrote observations/status and used a fake stdio RPC
child. Installation created package files, command links and retained backups;
upgrades preserved history and external prices. Offline reports did not change
database rows. No authenticated account or permanent installation was used.

Verified fixes in the audited commit:

- Atomic exports and price imports preserve linked targets and previous outputs
  on failure; installer price creation is exclusive and atomic.
- Mutable database/sidecar/lock/log aliases and symlinked installer subdirectories
  are refused. New private state, backups and outputs use owner-only permissions.
- Invalid starts and unconfigured resumes are rejected before database changes;
  entry points no longer create package bytecode.
- Offline indexing holds the daemon lock; active-index reads, checkpoint inspection
  and noninteractive display use read-only connections. RPC transport also enforces
  the four-method quota allowlist.

## Reproducible verification

Run from the repository root; `--trace` requires `strace` and permission to trace
child processes. The runner creates temporary HOME/XDG/Codex directories, strips
inherited credentials, disables real Codex and Python networking, and retains
summaries/raw logs/traces only under ignored `.runtime/audit/`.

```bash
python3 -B tests/run_audit.py --trace
python3 -B tests/run_audit.py --pattern test_side_effects.py
python3 -B tests/run_audit.py --pattern test_rpc.py
```

- **76 tests passed**, exit 0; includes 16 added side-effect/protocol regressions.
- Covered synthetic tracking, pause/resume/shutdown, checkpoints, terminal controls,
  offline commands/exports, fresh installation, upgrades, failure rollback, schema
  0/1 migrations, newer-schema refusal and frozen-price/history preservation.
- Sentinel content, permissions and modification times remained unchanged,
  including synthetic authentication, input logs and unrelated files.
- Syscall audit: **0 internet calls, 0 unexpected write-capable file operations
  outside the temporary workspace, 0 unresolved trace entries**. Terminal/null
  devices are allowed. The 26 local Unix-socket attempts were failed OS name-service
  cache lookups. No Python network denial was triggered.

The index and local Git history were inspected for credentials/private data,
including metadata, filenames, UTF-8 content and PNG pixels/metadata. At the
audited revision the inventory covered 12 commits, 138 blobs and 54 trees;
reflogs and two unreachable objects were included. No credential or unexpected
private-data findings remained within this scope. No remote history was fetched
or inspected. The final documentation is reviewed separately before its commit.

## Remaining risks and manual review

Live-account compatibility and the external Codex executable's own authentication,
cache/log writes and provider traffic remain **unverified**. SQLite read-only
reports may still create/update WAL coordination files. Filesystem checks assume
trusted directories; they do not eliminate concurrent path replacement races.
Abrupt termination/power loss during installation requires manual recovery from
retained backups; handled switch failures were tested.

Before upgrading, review the executable and configured paths, existing state
permissions, linked log targets and every custom tracking directory. Keep runtime
data/exports and audit artifacts private. Use the [upgrade sequence](UPGRADING.md):
shut down collectors, run `bash install.sh --upgrade` with all required state paths,
then migrate, compare history and resume. The real installation/database were
unchanged; nothing was pushed or published.
