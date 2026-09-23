# Usage Tools for Codex

Terminal tools for monitoring local Codex token usage and account quota, with a
live dashboard, saved history, and CSV/JSON exports. The estimator compares usage
with quota consumption to estimate the token volume and API-equivalent cost per
100% of weekly quota.

**In development. Linux is the currently supported platform.**

An independent community project, not affiliated with or endorsed by OpenAI.

![Codex Limit Estimator showing token usage, model mix, and a quota-based estimate](codex-limit-estimator.png)

## Installation

Requires **Python 3.10+** (including SQLite and curses), **Bash**, and an installed,
authenticated **Codex CLI** on your `PATH`. No additional Python packages or API
key are needed.

Clone or download this repository, then run from its root directory:

```bash
bash install.sh
```

Commands are installed in `~/.local/bin`; make sure it is on your `PATH`.
Check local usage and account quota:

```bash
codex-usage
codex-quota
```

The first usage scan may take a while if you have a large session history.

## Usage

Start tracking and open the terminal interface:

```bash
codex-limit-estimator start tracking
```

The tracker runs in the background and samples every five minutes by default.
Estimates become available after new usage and quota consumption are observed.
Press `q` to close the interface **without stopping tracking**, `s` to pause, or
`r` to resume. Press `v` to switch between segment, run, and daily views.

```bash
codex-limit-estimator           # Reopen the interface
codex-limit-estimator status    # Check tracker status
codex-limit-estimator shutdown  # Stop the background process
```

History is kept locally. To restart tracking after a shutdown or reboot, use
`codex-limit-estimator resume`. No automatic startup service is installed.

## Updating

These steps use default paths. For custom paths or multiple trackers, follow
the [upgrade guide](docs/UPGRADING.md).

Stop the collector before updating:

```bash
codex-limit-estimator shutdown
codex-limit-estimator status
```

Wait until status shows `Daemon: offline`. Update your checkout or download a
fresh source archive, then run from its root directory:

```bash
bash install.sh --upgrade
```

Open a new terminal, then migrate and inspect your saved history:

```bash
codex-limit-estimator migrate
codex-limit-estimator runs
codex-limit-estimator report
```

After checking the history, restart tracking with `codex-limit-estimator resume`.
The upgrade guide also covers backups and rollback.

## Understanding the estimates

Results compare **local usage and account quota consumed over the same period**.
They are estimates, not an API bill or an official subscription allowance.
Small samples, rounded quota readings, missing prices, and activity on other
devices can affect the result. Keep prices and workloads comparable when
comparing runs.

The tools read local session logs and query quota through Codex; they do not
submit prompts or run model workloads. See the [user guide](docs/USAGE.md) for
pricing, data storage, and interpretation.

## Documentation

- [User guide](docs/USAGE.md): tracking, prices, and interpreting results.
- [Command reference](docs/COMMANDS.md): controls, history, analysis, and exports.
- [Analysis and exports](docs/ANALYSIS.md): calculations, selection rules, and data formats.
- [Data and side effects](docs/SIDE-EFFECTS.md): files, processes, network access, and privacy.

## License

[GNU GPL v3.0 only](LICENSE) (`GPL-3.0-only`). Free software, provided without
warranty. See [NOTICE](NOTICE), or run any command with `--license` for the full
terms.
