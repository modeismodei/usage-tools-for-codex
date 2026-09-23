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
