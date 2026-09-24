# User guide

For setup and updates, see the [installation guide](INSTALL.md).
For all commands, options and keyboard shortcuts, see the
[command reference](COMMANDS.md).

## Windows

Report local token usage, check account quota, or start tracking:

```powershell
codex-usage.cmd
codex-quota.cmd
codex-limit-estimator.cmd start tracking
```

Manage an existing tracker:

```powershell
codex-limit-estimator.cmd          # Reopen the dashboard
codex-limit-estimator.cmd status   # Check tracker status
codex-limit-estimator.cmd stop     # Pause collection
codex-limit-estimator.cmd resume   # Resume, or restart after shutdown
codex-limit-estimator.cmd shutdown # Stop the background process
```

Use the `.cmd` extension for these three programs, including when following
examples in the command reference.

## Linux/UNIX-like systems

```bash
codex-usage
codex-quota
codex-limit-estimator start tracking
```

Manage an existing tracker:

```bash
codex-limit-estimator          # Reopen the dashboard
codex-limit-estimator status   # Check tracker status
codex-limit-estimator stop     # Pause collection
codex-limit-estimator resume   # Resume, or restart after shutdown
codex-limit-estimator shutdown # Stop the background process
```

## Using the dashboard

Tracking runs in the background and samples every five minutes by default.
Press `q` to close the dashboard **without stopping tracking**, `s` to pause,
`r` to resume, and `v` to change views. Use `shutdown` to end the background
process; saved history is retained. After shutdown or reboot, use `resume`.

Estimates appear once new local usage and account quota consumption have been
observed. They describe the observed workload, not an invoice or an official
token allowance. Small samples, unpriced models and activity on other devices
can affect the results. Cached input and reasoning output are already included
in their respective totals.

## Saved history and prices

Use `report`, `runs`, `segments`, `analyze` and `export` to inspect saved history
without starting collection. A run keeps its configuration and reference prices;
resuming preserves it. Changing the external price list does not reprice old
runs. See the [command reference](COMMANDS.md) for options and examples, and
[analysis and exports](ANALYSIS.md) for interpreting detailed results.

Keep history and exports private: they can contain local paths and usage
metadata. See [data and side effects](SIDE-EFFECTS.md) for storage details.
