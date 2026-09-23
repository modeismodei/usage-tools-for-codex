# Upgrading

An upgrade replaces the installed tools; migration updates the saved-history
format. These are separate steps. Stop every collector using the installation
before either step, and check the saved history before resuming.

## Upgrade an existing installation

### 1. Record the current state and stop collection

Keep a copy of your current report for comparison after the upgrade. Reports and
exports can contain private metadata, so store them outside the repository.

If your installed version supports checkpoints and collection is active, you can
record a final observation first:

```bash
codex-limit-estimator checkpoint --wait
```

Keep the returned snapshot ID. Skip this step for an older version without
checkpoints, or when the collector is paused or offline.

Shut down the collector and check its status:

```bash
codex-limit-estimator shutdown
codex-limit-estimator status
```

Wait for `Daemon: offline`; an in-progress scan or quota request may take time
to finish. For custom tracking directories, add `--data-dir /path/to/state` to
both commands. Repeat for every collector that uses this installation.

### 2. Install the updated source

Update your checkout or extract a fresh source archive, then run from its root:

```bash
bash install.sh --upgrade
```

`--update` is an alias for `--upgrade`. For a custom installation prefix or state
directory, supply the same paths used before. Repeat `--data-dir` for every
tracking directory using this package:

```bash
bash install.sh --upgrade --prefix /path/to/prefix \
  --data-dir /path/to/state --data-dir /path/to/another-state
```

The installer cannot discover arbitrary custom state directories. Supplying all
of them allows it to check their locks and back up their databases. It does not
shut down or start collectors, migrate history, or make account requests.

### 3. Migrate and inspect the history

Open a new terminal, or refresh your shell's command cache with `rehash` in Zsh
or `hash -r` in Bash. Then run:

```bash
codex-limit-estimator migrate
codex-limit-estimator runs
codex-limit-estimator report --json
```

Add the same `--data-dir` to each command for custom tracking directories, and
repeat for each directory. Compare segment IDs, counts, and estimates with the
pre-upgrade report before continuing.

### 4. Resume collection

```bash
codex-limit-estimator resume
codex-limit-estimator status
```

Use the matching `--data-dir` where needed. The next successful sample starts
a fresh segment in the same configured run, preserving its frozen prices.
The shutdown gap is not included in the estimate.

## What is backed up and preserved

The installer stages the package from an explicit distribution manifest and
validates the three entry points and bundled prices before switching. It uses
the collector's daemon lock; an active collector blocks the upgrade. A plain
installation refuses an existing package unless `--upgrade` or `--update` is
supplied.

The previous package is retained as `codex-limit-tools.backup-...`, alongside
backups of existing command files or links. On a handled command-switch failure,
the installer restores the previous package and commands, retaining the failed
package for inspection. Command-link backups preserve their original targets;
use the preserved package directory itself to inspect the old version.

Each supplied existing database receives a SQLite backup named
`tracking.sqlite3.backup-upgrade-...`, including committed WAL data. Installation
does not change the database schema. Migration makes its own
`tracking.sqlite3.backup-v...` backup, then updates the schema in a transaction.
Schema versions 0 and 1 can migrate to the current version, 2; unsupported newer
schemas are refused. Migration failures roll back and retain the backup.

Existing external `prices.json` files are preserved byte for byte. Frozen run
prices and historical observations remain intact. The separate quota watcher
and its state are not modified. Old installations, backups, and failed staging
directories are not cleaned up automatically.

## Rolling back

Shut down collection first. Preserve the current installation and database, then
restore the matching old package and pre-migration database backup **as a pair**.
Do not run an older collector against a newer schema, or copy only the main file
of a live WAL database. Keep backup generations until the chosen version and
its history have been checked.

Automatic rollback covers handled command-switch failures, not every possible
interruption. An abrupt termination or power loss during installation may
require manual recovery from the retained backups.

## Trying an installation separately

Use a temporary prefix **and** temporary configuration and state locations.
Changing `--prefix` alone does not isolate the external price file or history.

```bash
trial_dir=$(mktemp -d)
XDG_CONFIG_HOME="$trial_dir/config" XDG_STATE_HOME="$trial_dir/state" \
  bash install.sh --prefix "$trial_dir/prefix"
XDG_CONFIG_HOME="$trial_dir/config" XDG_STATE_HOME="$trial_dir/state" \
  bash install.sh --upgrade --prefix "$trial_dir/prefix"
```

These commands install and upgrade the tools without contacting an account or
starting collection. Keep the same isolated environment if you later run the
trial installation.
