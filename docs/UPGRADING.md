# Safe installation upgrades

Run these commands yourself when ready. Development and verification use only
temporary installations; they do not upgrade your permanent installation.

1. If your installed version supports checkpoints and tracking is active, run
   `codex-limit-estimator checkpoint --wait` and retain its snapshot ID. Skip
   this step for the original version or a paused/offline collector.
2. Run `codex-limit-estimator shutdown`, then `codex-limit-estimator status`.
   Wait until it says `Daemon: offline`. A sample already in progress may take
   time to finish. Repeat this for every collector using this installation.
3. From the updated source bundle, run:

   ```bash
   bash install.sh --upgrade
   # --update is an alias for --upgrade.
   ```

   For a custom installation or state directory, specify the same paths used
   before. Repeat `--data-dir` for every tracking directory using the package:

   ```bash
   bash install.sh --upgrade --prefix /path/to/prefix \
     --data-dir /path/to/state --data-dir /path/to/another-state
   ```

4. Refresh the shell command cache (`rehash` in Zsh or `hash -r` in Bash), then
   migrate the history explicitly and verify it before restarting:

   ```bash
   codex-limit-estimator migrate
   codex-limit-estimator runs
   codex-limit-estimator report --json
   codex-limit-estimator resume
   codex-limit-estimator status
   ```

   Add the same `--data-dir` to each command for custom tracking directories.
   Repeat migration and verification for each such directory. Compare historical
   segment IDs, counts and estimates with your pre-upgrade report. After resume,
   the next successful sample establishes a fresh segment baseline in the same
   configured run; it does not bridge the shutdown gap.

The upgrade script stages an explicit distribution manifest and validates all
three entry points and the bundled prices before switching. It takes the same
daemon lock used by the original collector, so an active collector blocks the
upgrade. The script cannot discover arbitrary custom state directories: supply
all of them with `--data-dir`. It never shuts down or starts a collector itself.

For every supplied existing database it makes a SQLite backup, including
committed WAL data, named `tracking.sqlite3.backup-upgrade-...`. The database
schema remains unchanged during installation. The subsequent migration creates
its own `tracking.sqlite3.backup-v...` backup and changes the schema in a
transaction. Unsupported newer schemas are refused. Original schema 0 and
intermediate schema 1 are supported; the current schema is 2.

The previous package is retained beside the new one as
`codex-limit-tools.backup-...`; existing command files/links are also backed up.
On a command-switch failure, the installer restores the previous package and
commands, retaining the failed package for inspection. Command-link backups
preserve their original targets; use the preserved package directory itself to
inspect the previous version. A plain install still refuses an existing package
unless `--upgrade`/`--update` was supplied.

External `prices.json` is preserved byte for byte when it exists. Frozen run
prices and all history remain intact. The independent quota watcher and its
state are untouched. Old installations, backups and failed staging directories
are never cleaned up automatically.

If you need to return to the old version, first shut down collection. Preserve
the current installation and database, then restore the matching old package
and pre-migration database backup as a pair. Do not run an older collector
against a newer schema or copy just the main file of a live WAL database. Keep
all backup generations until you have verified your chosen version and history.

For an isolated trial, use a temporary prefix **and** a temporary config/state
location; changing `--prefix` alone does not isolate external prices or history:

```bash
trial_dir=$(mktemp -d)
XDG_CONFIG_HOME="$trial_dir/config" XDG_STATE_HOME="$trial_dir/state" \
  bash install.sh --prefix "$trial_dir/prefix"
XDG_CONFIG_HOME="$trial_dir/config" XDG_STATE_HOME="$trial_dir/state" \
  bash install.sh --upgrade --prefix "$trial_dir/prefix"
```

These install commands perform no account requests. The automated tests exercise
fresh installation, upgrades from synthetic original history, price preservation,
lock refusal, invalid payloads, command-switch rollback and migration, entirely
under temporary directories.
