# User guide

For installation and a first run, start with the [README](../README.md).
The [command reference](COMMANDS.md) covers individual commands and options.

## The three tools

| Command | Purpose |
| --- | --- |
| `codex-usage` | Read local Codex session logs and report token usage and reference cost. |
| `codex-quota` | Retrieve the authenticated account's current quota. |
| `codex-limit-estimator` | Track both over time, display estimates, and analyze or export saved observations. |

The usage and quota reports can be used independently. When the collector is
running, `codex-usage` reads its latest index and may lag by one sampling interval.
When the collector is offline, it updates the index itself.

## Tracking and saved history

```bash
codex-limit-estimator start tracking
```

This starts a detached background collector and opens the terminal interface.
Add `--background` to start without opening the interface. Sampling defaults to
300 seconds; the display refreshes stored data more often without requesting
quota again. Starting an already-running tracker attaches to it without replacing
its configuration. A paused tracker stays paused until resumed.

The first successful sample establishes a baseline. Old session history helps
build the local index, but only matched changes after that baseline contribute
to the live estimate. An estimate needs observed quota consumption; a lifetime
token total and today's remaining quota are not a valid pair for this calculation.

### Pause, detach, and shut down

Closing the interface with `q` or Escape leaves collection running. `stop` pauses
collection but leaves the background process available; `resume` continues it.
`shutdown` ends the background process without deleting history. `resume` can
also restart a configured tracker after shutdown or reboot. There is no automatic
startup service.

A pause or shutdown may wait for an in-progress scan or quota request to finish.
These commands do not stop other Codex processes or enforce a spending limit.

### Runs and segments

A **run** is a saved tracking configuration with a stable ID, workload label, and
frozen reference prices. Resuming keeps the same run. A **segment** is an
uninterrupted series of observations within a run.

A new segment begins after a pause, restart, reset or quota replenishment,
reset-deadline change, account or plan change, collection gap, log error, or
changed historical model attribution. Quota movement without newly indexed
local tokens also ends continuity. An apparent reset may be a reporting
correction; the tool records the observation without claiming its cause.

Intervals crossing these boundaries are excluded. The next successful sample
starts a fresh baseline; consumption during an unobserved gap is not reconstructed.
Tracking continues after resets rather than stopping at the end of a quota cycle.

Use `runs`, `segments`, `analyze`, or `export` to work with saved history without
starting collection or contacting Codex. These commands do not refresh or migrate
history. See [analysis and exports](ANALYSIS.md) for filters and coverage rules.

## Reading the dashboard

The main estimate extrapolates observed token usage and API-equivalent cost to
100 quota percentage points:

```text
equivalent per 100% = 100 × matched usage / consumed quota points
```

For example, $40 of reference-priced local usage matched to 10 consumed quota
points gives an estimate of $400 per 100%. This describes the observed workload;
it is neither an invoice nor a measurement of a hidden server-side token allowance.

The dashboard also shows the supporting quota points and duration, token
breakdown, model mix, cache share, price coverage, and rounding bounds.

### Token accounting and incomplete prices

Cached input is part of total input; reasoning is part of total output. Cache
writes, when reported, are part of non-cached input and are priced separately.
Do not add these subsets to their totals a second time.

Tokens from models without known prices are retained and marked **unpriced**,
not discarded or treated as free. Their missing cost makes the monetary subtotal
incomplete. **Priced-token coverage** describes how much usage has a known price;
it is not statistical confidence. Token estimates do not depend on reference
prices.

### Small samples and rounding

Estimates below five consumed quota points are marked provisional by default.
The display says `Confidence: not quantified`: the available observations do not
justify a statistical confidence percentage.

The default assumed quota resolution is one percentage point. With up to half
a point of rounding error at each endpoint, a measured change of `d` points can
have up to one point of error. For a positive reference cost `C`, the conditional
rounding envelope is:

```text
lower = 100 × C / (d + 1)
upper = 100 × C / (d - 1)
```

The upper bound is unbounded when `d <= 1`. The `--resolution` option changes
the assumed quota resolution. These bounds cover rounding only, not reporting
lag, external activity, missing logs, incorrect prices, workload variation, or
changes in subscription charging. They are not statistical confidence intervals.

### Daily and combined estimates

Combined estimates use the ratio of summed usage to summed quota consumption,
not an average of individual estimates. For example, 1 point/$10 plus 9 points/$18
gives $280 per 100%, not $600.

Groups keep different price lists, workload labels, and account meters separate.
Runs also remain separate unless aggregation across runs is requested explicitly.
A matching label does not establish a matching workload.

Collection continues across UTC midnight. Each interval belongs to the UTC day
of its ending observation, without an invented midnight sample. Zero-quota-change
intervals retain their usage in larger aggregates; a daily result with no consumed
points has no estimate rather than a zero estimate. Legacy gaps remain excluded.
Rounding calculations cancel shared endpoints; separated segments can therefore
have wider bounds than a continuous interval. See [ANALYSIS.md](ANALYSIS.md) for
the exact rules.

## Comparing results over time

Keep the reference price list fixed and compare sufficiently large samples,
preferably tens of quota points rather than a single point. Keep the model,
reasoning effort, service mode, context lengths, and cache mix as similar as
practical. The tool reports model and cache information, but does not control
these conditions or infer the full reasoning-effort and service-tier mix.

**Account quota can change because of work this machine cannot observe.**
Activity on another device or in a browser can reduce quota without adding local
tokens, making the measured ratio lower. The absence of a segment warning does
not rule out outside activity, particularly when local and external work overlap.
Pause before using other devices and resume after that work and its reporting
have settled. Use a separate state directory when changing Codex home, account,
or machine; do not merge databases from different devices as though their
observations were synchronized.

Review missing prices, log errors, and excluded intervals before drawing a
conclusion. Similar API prices do not imply identical subscription quota weights.
A repeated change under comparable conditions describes a change in the effective
usage-to-quota ratio for that workload; it does not by itself establish why the
ratio changed or prove an official allowance cut.

## Reference prices

```bash
codex-limit-estimator prices path
codex-limit-estimator prices validate
codex-limit-estimator prices import /path/to/revised-prices.json
```

`prices path` locates the editable file. Imports validate JSON before replacing
it. The file defines model rates, aliases, and long-context settings, so changing
them does not require editing Python code.

Rates are per million tokens, with separate `input`, `cached`, `cache_write`, and
`output` fields. For entries marked `long_context`, the bundled default rule
applies above 272,000 input tokens **per response**: input and cache prices are
doubled, and output prices are multiplied by 1.5. The threshold and multipliers
are settings in the price file, not assumptions to apply to every model.

The bundled [prices.json](../prices.json) records rate values, dates, and
provenance. Some entries were carried over from an earlier `codex-usage`
implementation and have not all been reverified. Reference prices exclude taxes,
regional adjustments, tool charges, Batch/Flex, and Fast-mode adjustments. They
provide a comparison convention, not a reproduction of subscription charging.
Differences from older usage reports may also reflect accounting corrections
rather than quota changes.

### Changing prices for a new run

Each run stores a copy and hash of its price list. Editing or importing external
prices does not reprice an active run or rewrite historical estimates.

To begin a separate run with updated prices or a different workload label:

```bash
codex-limit-estimator shutdown
codex-limit-estimator status
```

Wait for `Daemon: offline`, then start the new run:

```bash
codex-limit-estimator start tracking --new-run \
  --label "single-model comparison" --prices /path/to/prices.json
```

Old segments remain available, and different price hashes stay separate in
comparisons. The standalone `codex-usage --prices /path/to/prices.json` report
uses the selected prices instead of a run's frozen snapshot.

## Data, privacy, and compatibility

The default installation uses these locations:

| Content | Default location |
| --- | --- |
| Commands | `~/.local/bin` |
| Shared package | `~/.local/lib/codex-limit-tools` |
| Editable prices | `~/.config/codex-limit-tools/prices.json` |
| History and tracker state | `~/.local/state/codex-limit-estimator/` |

Configuration and state respect `XDG_CONFIG_HOME` and `XDG_STATE_HOME`.
`--data-dir` selects a different tracking directory. State includes
`tracking.sqlite3`, its SQLite sidecars, `daemon.lock`, and `daemon.log`.
It is stored outside the project being worked on. Use SQLite's backup API, or
shut down collection before making a database backup; a copy of only the main
file from a live WAL database can miss committed data.

The index reads response-level usage and model metadata from `sessions` and
`archived_sessions` under the selected Codex home. It deduplicates responses and
reads appended data incrementally after the initial scan. Cached and reasoning
tokens are accounted for as subsets, not added twice. Repeated legacy
`token_count` events are diagnostic only, not a substitute for supported
`token_usage_record` records. If the supported format is missing, the tool reports
an error rather than claiming zero usage.

Responses without timestamps contribute to the standalone lifetime report, but
not timed estimates. Incomplete trailing log lines are retried on a later scan;
truncated or replaced files are rescanned with deduplication. Deleting or
archiving a log does not subtract already recorded usage. Arbitrary in-place
edits that leave file metadata unchanged are outside the incremental indexing
assumptions. Missing records, imported history, and delayed telemetry can still
affect results.

The tracking database stores usage metadata, not prompts, source code, tool
output, or credential tokens. History, errors, and exports can still contain
paths, workload labels, identifiers, timestamps, model metadata, and
account-derived hashes. **Treat them as private.**

Quota retrieval uses the authenticated Codex CLI's app-server protocol, limited
to `initialize`, `initialized`, `account/read`, and `account/rateLimits/read`.
The tools do not submit prompts or start model workloads, and do not send
analytics to an additional service. The external Codex executable may read its
own credentials, update its own logs or cache, and contact provider services.
Compatibility depends on that executable and the available log format; use
`codex-quota` and `codex-usage` to check both data sources. Collection errors are
shown in status/the interface and retried with bounded backoff.

A separate `watch-codex-quota` installation is neither required nor modified,
and its state file is not used. Running both tools results in independent quota
requests. See [data and side effects](SIDE-EFFECTS.md) for the full command-by-command
reference, including installation and export writes.

## Technical references

The account queries use the [Codex app-server protocol](https://learn.chatgpt.com/docs/app-server).
For published rates and model-specific pricing rules, consult
[OpenAI API pricing](https://developers.openai.com/api/docs/pricing) and the
provenance recorded in [prices.json](../prices.json).
