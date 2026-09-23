# Codex Limit Estimator — Extended Analysis Tasks

## Objective

Extend the existing Usage Tools for Codex bundle to estimate the API-equivalent cost and token volumes corresponding to 100% of weekly allowance from large observed consumption intervals, such as 73% remaining to 40% remaining, and from multiple compatible segments. Reuse the existing tracker, SQLite history, response index, and frozen JSON price snapshots.

Implement these tasks in dependency order. Make routine implementation decisions autonomously, preserve unrelated work, and record material deviations. This document specifies future changes; commands marked **new** are not available in the original bundle.

## Existing implementation

- `tracker.py` records cumulative snapshots approximately every five minutes and creates segments at detected discontinuities.
- `estimate.py` already estimates each segment from its first and last snapshots. Sampling does not imply averaging five-minute estimates.
- The existing daily report uses a ratio of summed costs to summed quota consumption, grouped by UTC date, price hash, workload label, and meter hash.
- SQLite contains `segments`, `snapshots`, `responses`, and `events`; historical observations must remain usable.
- `report --json` and JSON exports contain segment and daily summaries. Existing CSV exports contain daily summaries.
- A UTC day change currently creates a segment boundary and discards the boundary interval.
- The installer currently refuses to replace an existing package installation. Provide a safe upgrade procedure rather than assuming reinstall works.

## Non-negotiable constraints

- Do not send agent messages, enqueue prompts, generate model turns, or run synthetic workloads. The user may run a workload independently; this tool only observes it.
- Keep quota access read-only and retain the existing RPC method allowlist.
- Do not modify the separate `watch-codex-quota`, project agent instructions, or another monitor's state.
- Preserve `q` as TUI detach, `s` as pause, and `r` as resume. Do not silently change their behavior.
- Retain the default five-minute sampling interval and independent `codex-usage` and `codex-quota` commands.
- Keep Python standard-library dependencies unless a concrete requirement justifies an addition.
- Never fabricate historical quota observations, exact percentage crossings, official allowance sizes, or confidence percentages.
- All CLI output, documentation, and code comments should be English.

## Calculation contract

For each included, non-overlapping observation interval i:

- `p_i = used_end - used_start`, in percentage points, not fractions.
- `m_i = cumulative_metric_end - cumulative_metric_start`.
- `equivalent_per_100(metric) = 100 * sum(m_i) / sum(p_i)`.

Example: 73% to 40% remaining consumes 33 percentage points. If the matched local API-equivalent cost is $132, the estimate is $400 per 100%.

Apply the formula to cost, non-cached input, cached input, total input, output, and reasoning output. Cached input is a subset of input; reasoning output is a subset of output. Do not add these subsets twice. Preserve the existing cache-write accounting and pricing rules.

Do not average individual per-100 estimates without weighting by their consumed quota points. Do not discard zero-change samples inside a valid continuous interval: quota rounding can hide consumption between adjacent samples.

Compatible segments may describe more than 100 percentage points of observed consumption across replenishments. Label this as an aggregate equivalent, never as a single complete weekly cycle.

## Task checklist

### T01 — Define analysis contracts and regression fixtures

**Dependencies:** none. **Primary files:** `estimate.py`, tests, documentation.

- [x] Define a normalized analysis interval containing source segment/run IDs, endpoint snapshot IDs and times, quota remaining at each endpoint, metric deltas, compatibility keys, and inclusion/exclusion status.
- [x] Define stable JSON fields for aggregate estimates, endpoint selection, compatibility groups, quality indicators, and excluded intervals.
- [x] Keep existing JSON fields and the existing default daily CSV format compatible where possible; add an explicit export schema version.
- [x] Create small deterministic fixtures for a 73% to 40% interval, uneven segment sizes, a reset, a pause, a UTC midnight crossing, and incomplete pricing.

**Acceptance:** fixtures state expected totals independently of implementation; the 33-point/$132 case gives $400, and unequal-sized segments demonstrate ratio-of-sums behavior.

### T02 — Add persistent run identity and safe schema migration

**Dependencies:** T01. **Primary files:** `common.py`, `cli.py`, `tracker.py`.

- [x] Introduce a schema version and transactional, repeatable migrations.
- [x] Assign a stable UUID to each new configured run. Associate new segments with it and retain label, frozen price snapshot/hash, start time, and relevant configuration.
- [x] Resume/restart the same configured run with its existing UUID; `--new-run` creates a new UUID.
- [x] Represent legacy segments without inventing their original run boundaries: mark their run identity as legacy/unknown while retaining their IDs and data.
- [x] Coordinate migration with the daemon lock. Refuse migration while an old collector is active; give actionable shutdown instructions.
- [x] Back up an existing database using SQLite's backup API before migration. Preserve configuration and prices. Reject unsupported newer schemas clearly.

**Acceptance:** an original-format database retains all historical rows and estimates; repeated startup does not duplicate runs or migrations; migration failure leaves recoverable data.

### T03 — Implement reusable aggregation and history filters

**Dependencies:** T01, T02. **Primary file:** `estimate.py`.

- [x] Add a pure analysis layer that selects observations and returns normalized intervals and grouped results. Reuse it in CLI, TUI, and exports.
- [x] Support filtering by run, segment IDs, workload label, and time range.
- [x] Accept ISO 8601 timestamps with timezone offsets. Interpret date-only start as UTC midnight and date-only end as the following UTC midnight; document the half-open time selection convention.
- [x] Use only observed snapshots inside the requested selection. Report effective endpoints and uncovered time at the requested edges; do not interpolate tokens or quota.
- [x] Aggregate compatible intervals by run, UTC day, or overall selection.
- [x] Always partition by price hash, meter hash, and workload label. Default to separate run results; permit explicit across-run aggregation while retaining source run IDs.
- [x] Do not claim the compatibility keys prove identical model, effort, cache, or workload mix. Show available mix diagnostics and label remaining confounders.
- [x] Prevent duplicated intervals when overlapping selectors identify the same data.
- [x] Return an explicit non-estimable result when the denominator is zero or counters are invalid.

**Acceptance:** mixed prices/accounts remain separate; repeated selectors do not double-count; sum-of-deltas results match fixtures; archived data can be analyzed without starting the collector or contacting Codex.

### T04 — Separate reporting boundaries from collection discontinuities

**Dependencies:** T01, T03. **Primary files:** `tracker.py`, `estimate.py`.

- [x] Stop treating UTC midnight as a collection discontinuity for new data. Preserve continuous endpoints across dates.
- [x] Retain genuine breaks for replenishment/correction, account/plan changes, pauses, collection failures/gaps, and attribution revisions.
- [x] Calculate daily views from adjacent observed intervals inside continuous segments. Assign a midnight-crossing interval to its ending UTC day and disclose this convention; do not interpolate an exact midnight observation.
- [x] Ensure that summing the daily interval deltas reproduces the overall continuous-selection totals, including intervals with zero quota change.
- [x] Keep daily groups with local tokens but zero observed quota change visible with a null daily estimate; their deltas still contribute to a compatible broader aggregate.
- [x] Preserve original historical segmentation. Do not silently bridge legacy midnight gaps; any future recovery must be explicitly labeled and independently validated.

**Acceptance:** new collection across midnight loses no interval; overall totals equal the sum of daily deltas; resets and pauses are never bridged as continuous consumption.

### T05 — Expose coverage, exclusions, and uncertainty honestly

**Dependencies:** T03, T04. **Primary files:** `estimate.py`, CLI/TUI formatting.

- [x] Report observed consumption in percentage points, included interval count, source segment count, covered duration, requested/effective endpoints, excluded durations and known reasons.
- [x] Distinguish observed percentage points from a percentage of statistical confidence or a percentage of an official allowance measured completely.
- [x] Report priced-token coverage and unpriced token counts. Label monetary estimates as partial whenever relevant pricing is missing.
- [x] Preserve the conditional quota-rounding envelope. For disjoint intervals, account for each distinct endpoint's uncertainty; cancel shared endpoints where algebraically appropriate.
- [x] Do not use the single-interval rounding bound for an arbitrary sum of disjoint segments. Return an unbounded upper estimate when the lower consumption bound is non-positive.
- [x] State that rounding bounds exclude quota-reporting lag, other-device consumption, incomplete local logs, and workload variation.
- [x] Do not infer a provider quota reduction solely from a change in API-equivalent estimates.

**Acceptance:** continuous and disjoint interval fixtures produce the appropriate different bounds; partial pricing and unknown coverage cannot appear as fully measured weekly capacity.

### T06 — Add analysis commands and export modes

**Dependencies:** T03, T05. **Primary file:** `cli.py`.

Implement these **new** command forms, adapting internal parser structure as needed:

```bash
codex-limit-estimator runs
codex-limit-estimator segments --run RUN_ID
codex-limit-estimator analyze --run RUN_ID
codex-limit-estimator analyze --segments 12,13,14
codex-limit-estimator analyze --from 2026-09-23 --to 2026-09-30
codex-limit-estimator analyze --label "Astra Ultra / VM only" --group-by overall
codex-limit-estimator analyze --run RUN_ID --group-by day --json
codex-limit-estimator export --view segments --output segments.csv
codex-limit-estimator export --view snapshots --output snapshots.csv
codex-limit-estimator export --view analysis --run RUN_ID --output analysis.json
```

- [x] Define filter intersection semantics, valid combinations, deterministic ordering, and useful errors for invalid/unknown IDs.
- [x] Preserve `report`, `report --json`, default daily CSV export, and normal TUI attachment.
- [x] Include both raw deltas and normalized per-100 metrics in analysis exports, plus provenance and quality fields.
- [x] Take a consistent database read snapshot while collection is active. Analysis commands must not refresh quota or mutate collection state; perform required migration separately at controlled startup.
- [x] Display source run/segment IDs and actual remaining-quota endpoints in human-readable tables.

**Acceptance:** commands work with the daemon offline; stdout JSON is parseable without progress chatter; invalid selectors exit nonzero and do not change state.

### T07 — Select observed quota ranges for stress-test analysis

**Dependencies:** T03, T06. **Primary files:** analysis layer and `cli.py`.

Implement this **new** form:

```bash
codex-limit-estimator analyze --run RUN_ID --remaining-from 73 --remaining-to 40
```

- [x] Require `100 >= remaining-from > remaining-to >= 0`.
- [x] Search only within one continuous segment at a time. Select the first observed downward crossing of the start threshold and the first subsequent observed crossing of the end threshold.
- [x] Show requested thresholds and actual observed endpoints. A jump from 41% to 39% ends at the observed 39%, not a fabricated 40%.
- [x] Return separate candidates if multiple segments qualify; allow `--segments` to disambiguate. Never silently cross a replenishment.
- [x] If the start crossing is not recorded or the end is not yet reached, report that status. Offer an explicit partial-selection option using the last available observation, clearly labeled partial.
- [x] Retain the effective snapshot IDs so the result is reproducible from exported history.

**Acceptance:** exact hits, skipped thresholds, unfinished ranges, and repeated crossings in different cycles are all handled deterministically.

### T08 — Add bounded manual checkpoints

**Dependencies:** T02, T04. **Primary files:** `cli.py`, `tracker.py`.

Implement this **new** command:

```bash
codex-limit-estimator checkpoint --wait
```

- [x] Request an immediate sample from the existing daemon through local control state. Do not spawn a second collector.
- [x] Use a request ID and acknowledgement with the resulting snapshot ID; do not overwrite pending pause/shutdown requests.
- [x] Bound the wait with a documented timeout and surface collection errors. Do not retry indefinitely.
- [x] Refuse clearly when the daemon is absent or paused; do not silently resume it.
- [x] Document a workload measurement sequence: baseline checkpoint, run the user's workload, final checkpoint, analyze the recorded endpoints.
- [x] Explain that a checkpoint cannot eliminate provider reporting lag. The user may wait for observations to settle before pausing; do not promise immediate final accounting.

**Acceptance:** one request produces one acknowledged sample, failures terminate predictably, and no model turns or agent notifications are introduced.

### T09 — Add a compact aggregate TUI view

**Dependencies:** T05, T06. **Primary file:** `tui.py`.

- [x] Add a minimal switch between current-segment, current-run aggregate, and existing daily-history views, with a visible key legend.
- [x] Show observed quota points, equivalent dollars and token volumes per 100%, partial-pricing status, and conditional rounding bounds.
- [x] Render stored analysis results without causing extra quota RPCs or model activity.
- [x] Preserve existing detach/pause/resume behavior and handle small terminals gracefully.

**Acceptance:** aggregate display matches CLI JSON for the same selection; navigating the TUI does not change tracking or sampling frequency.

### T10 — Verify, document, and provide a safe upgrade

**Dependencies:** T02–T09. **Primary files:** tests, `README.md`, installation documentation.

- [x] Run focused tests after each coherent logic change; run the complete suite once before delivery and again only if a relevant failure requires it.
- [x] Cover ratio-of-sums, zero-change intervals, filtering/deduplication, midnight continuity, reset exclusion, migration, read consistency, price partitioning, quota range selection, and checkpoint acknowledgement.
- [x] Reuse the fake read-only RPC harness. Never consume real model quota for tests.
- [x] Include CLI JSON/export smoke tests and a small pseudo-terminal test for unchanged TUI controls.
- [x] Provide an English command reference and worked examples for current segment, full run, multiple days, selected segments, 73% to 40%, and offline history analysis.
- [x] Explain which commands are new, which require new data, and what legacy observations can and cannot recover.
- [x] Document an upgrade sequence: checkpoint if appropriate, shutdown, confirm daemon exit, SQLite backup, preserve the old installation, install updated package, migrate safely, resume, verify history.
- [x] Preserve the user's external prices JSON and independent quota watcher. Do not delete old history or backups automatically.
- [x] Store detailed test logs locally; report aggregate pass/fail results and inspect failure details only when needed. Do not repeatedly read long successful test output.
- [x] If working in a Git repository, make logical intermediate commits containing only task-related changes. Do not push without explicit authorization.

**Acceptance:** existing history survives a tested upgrade; old entry points remain usable; new commands have reproducible examples; final delivery states actual tests and any remaining live-environment limitations.

## Implementation order and completion

Recommended order: T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08 → T09 → T10. Add focused tests alongside each task; do not postpone correctness checks until T10.

The implementation is complete when the user can record ordinary local work, detach the UI, inspect past runs offline, estimate 100% from an observed large interval or compatible segment collection, and export reproducible results without losing historical data or creating agent/model activity.

A user-managed stress test is simply a labeled workload observed by the tracker. Automatic quota exhaustion, multi-device merging, inferred hidden quota policies, and predictive statistical confidence models are outside this scope.
