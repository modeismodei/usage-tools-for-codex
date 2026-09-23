# Command reference and examples

All commands accept `--help`. History/control commands accept `--data-dir DIR`;
use it consistently when you maintain more than one tracker. Examples use
placeholder IDs from `runs`, `segments` and checkpoint output. JSON output is
machine-readable; descriptions and progress are omitted from JSON stdout.
All three commands and `install.sh` also accept `--license` to show GPLv3 terms
without side effects and `--version` to show the version and license. Human
startup notices go to stderr; JSON mode suppresses them. The TUI shows the notice.

| Command | Behavior |
| --- | --- |
| `codex-usage [--json] [--prices FILE]` | Independent local token report; refreshes the log index when the collector is offline |
| `codex-quota [--json]` | Independent read-only account request; requires authenticated Codex |
| `codex-limit-estimator` or `ui` | Attach the terminal interface; `q` detaches |
| `start tracking [--background]` | Start the observer, or attach to an existing one |
| `start tracking --new-run --label TEXT [--prices FILE]` | Create a separate UUID and frozen prices after shutdown |
| `stop`, `resume`, `shutdown` | Pause, resume/restart, or shut down the observer |
| `status`, `report [--json]` | Existing offline status and segment/daily summaries |
| `prices path`, `prices validate [FILE]`, `prices import FILE` | Locate, validate or import external prices |
| `runs [--json] [--label TEXT]` **new** | Inventory configured runs plus a legacy/unknown entry |
| `segments [FILTERS] [--json]` **new** | Segment IDs, run IDs and actual quota/snapshot endpoints |
| `analyze [FILTERS] [--group-by run\|day\|overall] [--json]` **new** | Compatible interval aggregates and coverage |
| `checkpoint [--wait] [--timeout SECONDS] [--json]` **new** | One immediate sample by the existing daemon, with acknowledgement |
| `checkpoint --request-id ID [--wait] [--json]` **new** | Inspect an existing request without sampling again |
| `migrate` **new** | Back up and migrate history while collection is shut down |
| `export --output FILE.csv\|FILE.json` | Existing default daily CSV or segment/daily JSON export |
| `export --view segments\|snapshots\|analysis [FILTERS] --output FILE.csv\|FILE.json` **new** | Raw or analyzed history exports |

Filters are `--run UUID` (repeatable), `--segments 12,13,14` (repeatable),
`--label TEXT`, `--from TIME`, and `--to TIME`. All intersect; repeated IDs count
once. A timestamp requires an explicit timezone. A date-only start selects from
UTC midnight; a date-only end includes that UTC date, ending at the following
midnight. Observations obey `[start, end)`; effective endpoints and uncovered
edges are reported. Unknown IDs and invalid combinations exit nonzero.

Analysis additionally accepts paired `--snapshot-from ID --snapshot-to ID`
(inclusive), or `--remaining-from PERCENT --remaining-to PERCENT` with optional
`--allow-partial`. Grouping/range/snapshot options also work with
`export --view analysis`. Use `--across-runs` with `--group-by overall` or `day`
to explicitly combine compatible runs; labels, prices and account meters still
partition the result. A workload label alone does not establish comparable mix.

## Worked selections

```bash
# Find a run and the current/latest segment ID without starting a collector.
codex-limit-estimator runs
codex-limit-estimator segments --run RUN_ID

# Current segment, full run, and selected segments.
codex-limit-estimator analyze --segments SEGMENT_ID
codex-limit-estimator analyze --run RUN_ID
codex-limit-estimator analyze --segments 12,13,14 --group-by overall

# Multiple UTC days, reported as daily groups or as a compatible run total.
codex-limit-estimator analyze --run RUN_ID --from 2026-09-23 --to 2026-09-30 --group-by day --json
codex-limit-estimator analyze --run RUN_ID --from 2026-09-23 --to 2026-09-30 --group-by overall

# Observed quota range; multiple cycles return separate candidates.
codex-limit-estimator analyze --run RUN_ID --remaining-from 73 --remaining-to 40
codex-limit-estimator analyze --segments SEGMENT_ID --remaining-from 73 --remaining-to 40 --allow-partial

# Explicit across-run comparison still separates prices, labels and meters.
codex-limit-estimator analyze --label "Astra Ultra / VM only" --group-by overall --across-runs

# Offline legacy history; original run boundaries cannot be reconstructed.
codex-limit-estimator analyze --data-dir /path/to/archived-state --run legacy

# Reproducible exports.
codex-limit-estimator export --view segments --output segments.csv
codex-limit-estimator export --view snapshots --output snapshots.csv
codex-limit-estimator export --view analysis --run RUN_ID --output analysis.json
```

For 73% to 40% remaining, consumption is 33 percentage points. With $132 and
3,300 input tokens matched to those endpoints, the equivalent is $400 and 10,000
input tokens per 100 points. For two compatible segments of 1 point/$10 and
9 points/$18, the combined equivalent is $280, not the unweighted $600 average.
Cached input and reasoning output remain subsets of their totals.

Thresholds select actual observations: a step from 41% to 39% ends at 39%.
Missing starts and unfinished ranges have explicit statuses. Partial selection
cannot invent a missing start. Use [manual checkpoints](ANALYSIS.md#manual-checkpoints)
to record precise baseline/final snapshot IDs around your independently run work.
Checkpoint timeout defaults to 90 seconds and accepts up to 300 seconds. A
checkpoint cannot eliminate provider reporting lag or guarantee final accounting.

## Existing history and new observations

All offline analysis commands can read the original schema without migration.
Old segments, snapshots, reference costs and daily export columns remain usable.
Unknown original runs are labeled `legacy/unknown`; they are separated by segment
unless across-run aggregation is explicit. Missing observations across old
midnight boundaries, resets, pauses and errors cannot be recovered.

Persistent run UUIDs, uninterrupted midnight collection and checkpoints apply to
new observations made by the updated collector. Migration preserves original
segment IDs and data rather than fabricating membership or new snapshots. Run
the [upgrade procedure](UPGRADING.md) before restarting collection.

The TUI cycles segment/run/daily views with `v`. `h` toggles daily history; `[` and
`]` select run compatibility groups. `q`, `s` and `r` retain detach/pause/resume.
All views render saved observations; navigation causes no account requests.
