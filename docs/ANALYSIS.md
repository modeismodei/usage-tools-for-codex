# Analysis and export contract

Export schema `schema_version: 2` adds analysis to the original `segments` and
`daily` report fields. The default daily CSV retains its original columns.
Schema versions for SQLite and JSON exports are independent.

An analysis interval is a pair of adjacent, actually recorded snapshots in one
continuous segment. It contains `interval_id`, `source_segment_id`, nullable
`source_run_id` (null means legacy/unknown), `start` and `end` objects with
`snapshot_id`, Unix UTC `ts`, `used` and `remaining` quota percentages,
`points`, `duration` in seconds, `delta`, `compatibility`, `resolution`,
`min_points`, `included` and nullable `exclusion_reason`.
Compatibility includes `price_hash`, `meter_hash` and `label`.

Analysis results contain `selection`, `groups`, `intervals`,
`excluded_intervals`, `range_candidates` and `quality_notes`. Each group carries
raw `delta` metrics and nullable `estimate` metrics per 100 quota points,
source run/segment IDs, observed `points`, interval/segment counts, duration,
actual endpoints, priced coverage, partial-pricing status and conditional
rounding bounds. A null estimate states its reason; it never means zero capacity.
These keys are additive to the original report and export contract.

Metrics retain the existing names: `input`, `noncached`, `cached`, `writes`,
`output`, `reasoning`, `cost`, cost components, coverage counts and response
counts. Cached input is inside input; reasoning is inside output; cache writes
are inside non-cached input. Do not sum subset fields as independent tokens.

For included intervals, use `100 * sum(delta) / sum(points)`, including intervals
with zero quota movement. Do not average segment ratios. Synthetic fixtures in
`tests/analysis_fixtures.py` state independent expected totals, including
33 points/$132 => $400 and 1 point/$10 + 9 points/$18 => $280 per 100 points.

## Persistent history

SQLite schema 1 adds configured-run UUIDs. New segments reference their run;
legacy segments keep a null run ID because their original membership is unknown.
Resuming a saved configuration retains its UUID and prices. A new configuration
created with `--new-run` gets a new UUID. Registering a resumed legacy
configuration affects future segments only.

`codex-limit-estimator migrate` upgrades history without contacting Codex.
Migration uses the collector lock, SQLite's backup API and a transaction. Existing
databases get a uniquely named `tracking.sqlite3.backup-v...` file before changes;
failures roll back and retain that backup. Newer unsupported schemas are refused.
Shutdown still works against the original schema. Stop the collector and confirm
it is offline before migration; no old observations are repriced or bridged.

## Selection, grouping and uncertainty

The pure `analyze_history` function accepts persisted segments and snapshots.
Run, segment, label and time filters intersect; repeated IDs are deduplicated.
Timestamps require a timezone. A date-only start means UTC midnight; a date-only
end means the following UTC midnight. Snapshot selection is half-open
`start <= observed_time < end`. Only adjacent recorded snapshots inside the
selection contribute. Effective snapshot IDs/times and uncovered edge durations
are returned; no counters or quota observations are interpolated.

Groups always partition price hash, meter hash and label. Runs stay separate
unless across-run aggregation is explicit. Unknown legacy run IDs stay separate
by segment by default. Compatibility does not imply equal model/effort/cache mix;
model deltas and cache share are diagnostics, not proof of controlled conditions.

New segments continue across UTC midnight. Each adjacent interval belongs to its
ending UTC day, including intervals whose quota delta is zero. Such a daily row
can have a null estimate while still contributing tokens/cost to a longer
selection. Original segment boundaries, including legacy midnight gaps, remain
excluded with recorded reasons. Pauses, resets, errors and other gaps are never
bridged. Coverage durations describe observations, not an entire weekly cycle.

For each distinct snapshot endpoint, add its signed coefficient across included
intervals. The conditional quota error is the sum of absolute coefficients times
half that endpoint's assumed resolution. Shared interior endpoints cancel; two
disjoint segments usually retain twice the one-segment error. Bounds divide the
metric delta by upper/lower consumption bounds. A non-positive lower consumption
bound yields a null upper estimate, meaning unbounded. These bounds do not cover
reporting lag, other-device activity, missing logs or workload variation.

Priced coverage is null when the counters cannot establish it; monetary subtotals
then remain partial. Unpriced tokens are retained. Observed quota points, priced
coverage and rounding bounds are distinct from statistical confidence and from
an official allowance. More than 100 observed points are an aggregate equivalent
across replenishments, not one complete weekly cycle.

## Offline commands and quota ranges

`runs`, `segments`, `analyze`, `report`, `status` and `export` open existing history
read-only and use a consistent SQLite read transaction. They work without a
daemon, a Codex executable or login. They do not migrate or refresh history.
Use `migrate` separately, or let controlled tracking startup migrate. Original
schema history is readable with `--run legacy` even before migration.

`--run` and `--segments` may be repeated; comma-separated segment IDs are also
accepted. All filters intersect, and unknown IDs are errors. `--group-by run`
is the default. Day and overall views also separate runs unless `--across-runs`
is supplied. Groups order by UTC day, run and compatibility keys; observations
order by time then segment/snapshot ID. `runs` orders by start and UUID, with the
legacy/unknown inventory entry last. JSON stdout contains no progress messages.

`--remaining-from 73 --remaining-to 40` finds the first recorded start crossing
and subsequent end crossing inside each continuous selected segment. An initial
observation exactly at the start threshold is a usable observed endpoint. An
initial observation below it cannot establish the missing start. A 41% to 39%
step uses 39%, never an invented 40%. If one sample skips both thresholds, there
is no matched interval for that range. Candidates from different segments stay
separate; use `--segments` to disambiguate. `--allow-partial` explicitly uses the
last observation of an unfinished range and labels the result partial; it cannot
recover an unrecorded start. Time filters apply before threshold selection.

`export --view segments|snapshots|analysis --output FILE.csv|FILE.json` adds raw
history and analysis exports. Analysis contains raw and normalized metrics,
provenance, endpoint IDs and quality fields. New CSV views include schema version
and encode nested fields as JSON cells. Snapshot exports retain cumulative
metrics and segment compatibility/configuration so calculations are reproducible.
A non-estimable analysis CSV contains a status row. Default daily CSV keeps its
original header; default JSON keeps `segments`, `daily` and status fields.
