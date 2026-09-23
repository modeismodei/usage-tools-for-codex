# Command reference

For installation, see the [README](../README.md). For an explanation of runs,
segments, prices, and estimates, see the [user guide](USAGE.md).

All commands accept `--help`, `--version`, and `--license`. JSON output keeps
stdout machine-readable, without progress messages or startup notices.
History and control commands accept `--data-dir DIR`; use the same directory
consistently when managing a tracker.

## Usage and quota reports

| Command | Description |
| --- | --- |
| `codex-usage [--json] [--prices FILE]` | Report local tokens and reference cost. Refresh the index when the collector is offline; otherwise read the latest saved index. |
| `codex-quota [--json]` | Retrieve account quota through the authenticated Codex CLI. |

## Tracking and history

The commands below follow `codex-limit-estimator`. Running it with no subcommand
opens the terminal interface; it does not start a collector.

| Subcommand | Description |
| --- | --- |
| `ui` | Open the terminal interface. |
| `start tracking [--background]` | Start tracking, or attach to an existing tracker without replacing its configuration. |
| `start tracking --new-run --label TEXT [--prices FILE]` | Create a separate run with its own ID and frozen prices, after shutting down the collector. |
| `stop` | Pause collection; leave the background process available. |
| `resume` | Resume a paused tracker, or restart a configured tracker after shutdown or reboot. |
| `shutdown` | End the background process without deleting history. |
| `status` | Show saved tracker status and whether the daemon is running. |
| `report [--json]` | Show saved segment and daily summaries. |
| `runs [--json] [--label TEXT]` | List configured runs, including a legacy/unknown entry where applicable. |
| `segments [FILTERS] [--json]` | List segment IDs, run IDs, and recorded quota/snapshot endpoints. |
| `analyze [FILTERS] [--group-by run\|day\|overall] [--json]` | Aggregate compatible observations and report their coverage. |
| `checkpoint [--wait] [--timeout SECONDS] [--json]` | Ask an existing, unpaused daemon for one immediate sample. |
| `checkpoint --request-id ID [--wait] [--json]` | Inspect a checkpoint request without requesting another sample. |
| `migrate` | Back up and migrate history while the collector is shut down. |
| `export --output FILE.csv\|FILE.json` | Export daily CSV or segment/daily JSON. |
| `export --view segments\|snapshots\|analysis [FILTERS] --output FILE.csv\|FILE.json` | Export raw history or analyzed observations. |
| `prices path` | Locate the editable price file. |
| `prices validate [FILE]` | Validate the selected price JSON. |
| `prices import FILE` | Validate and import an external price file without repricing saved runs. |

`status`, `report`, `runs`, `segments`, `analyze`, and `export` work offline on
existing history. They do not start collection, request quota, or migrate the
database. Export replaces the explicitly named output file; choose its path
accordingly. See [data and side effects](SIDE-EFFECTS.md) for filesystem details.

A checkpoint needs a running, unpaused collector. Its timeout defaults to
90 seconds and can be set to a positive value up to 300 seconds. It does not
eliminate provider reporting lag or guarantee final accounting.

## Terminal controls

| Key | Action |
| --- | --- |
| `q` / Escape | Close the interface; leave tracking running. |
| `s` | Pause collection. |
| `r` | Resume a paused live daemon with a fresh baseline. |
| `v` | Cycle segment, current-run aggregate, and daily views. |
| `h` | Toggle daily history. |
| `[` / `]` | Select compatibility groups in the run view. |

Navigation renders saved observations without requesting quota or changing the
sampling interval. To restart an offline daemon, use the CLI `resume` command.

## Filters and grouping

History selections accept `--run UUID` (repeatable), `--segments 12,13,14`
(repeatable), `--label TEXT`, `--from TIME`, and `--to TIME`. Filters intersect;
repeated IDs count once. Unknown IDs and invalid combinations return an error.

Timestamps require an explicit timezone. A date-only start means UTC midnight;
a date-only end includes that whole UTC date, ending at the following midnight.
Time selection uses `[start, end)`. Results report the actual observed endpoints
and any uncovered edges rather than interpolating observations.

Analysis also accepts either paired `--snapshot-from ID --snapshot-to ID`
(inclusive), or `--remaining-from PERCENT --remaining-to PERCENT` with optional
`--allow-partial`. These options, along with grouping, also work with
`export --view analysis`.

Use `--across-runs` with `--group-by overall` or `day` to combine compatible runs
explicitly. Prices, labels, and account meters still partition the result.
A common workload label does not establish a comparable model or cache mix.

## Examples

Replace `RUN_ID`, `SEGMENT_ID`, and snapshot IDs with values returned by the tools.

```bash
# Find runs and their segments.
codex-limit-estimator runs
codex-limit-estimator segments --run RUN_ID

# Analyze one segment, an entire run, or selected segments.
codex-limit-estimator analyze --segments SEGMENT_ID
codex-limit-estimator analyze --run RUN_ID
codex-limit-estimator analyze --segments 12,13,14 --group-by overall

# Compare UTC days or report the selected period as a compatible run total.
codex-limit-estimator analyze --run RUN_ID --from 2026-09-23 --to 2026-09-30 --group-by day --json
codex-limit-estimator analyze --run RUN_ID --from 2026-09-23 --to 2026-09-30 --group-by overall

# Select an observed quota range.
codex-limit-estimator analyze --run RUN_ID --remaining-from 73 --remaining-to 40
codex-limit-estimator analyze --segments SEGMENT_ID --remaining-from 73 --remaining-to 40 --allow-partial

# Combine compatible runs with the same workload label.
codex-limit-estimator analyze --label "single-model comparison" --group-by overall --across-runs

# Read legacy history without migrating it.
codex-limit-estimator analyze --data-dir /path/to/archived-state --run legacy

# Export raw records or analyzed results.
codex-limit-estimator export --view segments --output segments.csv
codex-limit-estimator export --view snapshots --output snapshots.csv
codex-limit-estimator export --view analysis --run RUN_ID --output analysis.json
```

A change from 73% to 40% remaining is 33 consumed quota points. With $132 and
3,300 input tokens matched to those endpoints, the equivalents are $400 and
10,000 input tokens per 100 points. Aggregates use summed usage divided by summed
quota consumption: 1 point/$10 plus 9 points/$18 gives $280, not an unweighted
average of $600. Cached input and reasoning output remain subsets of their totals.

Quota thresholds select actual observations: a step from 41% to 39% ends at 39%,
not an invented 40%. Candidates from different cycles stay separate. An unfinished
range can be reported with `--allow-partial`, but an unrecorded start cannot be
recovered. See [manual checkpoints](ANALYSIS.md#manual-checkpoints) for recording
baseline and final snapshot IDs around a workload, and [ANALYSIS.md](ANALYSIS.md)
for complete selection and export rules.

## Older history

Offline analysis can read the original schema without migration. Original
segments, snapshots, reference costs, and daily export columns remain usable.
Unknown run membership is shown as `legacy/unknown`; those segments stay separate
unless aggregation across runs is explicit. Missing observations across old
midnight boundaries, pauses, resets, or errors cannot be recovered.

Run IDs and checkpoint records apply to observations collected with versions that
support them. Migration preserves old segment IDs and data; it does not invent
run membership or snapshots. Follow the [upgrade guide](UPGRADING.md) before
restarting collection with an updated installation.
