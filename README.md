# Codex limit tools

A project-independent, non-agentic bundle for measuring local token activity per
percentage point of account quota. Bash is needed only for installation; runtime
uses Python 3.10+ standard libraries, SQLite, curses, and your authenticated Codex
CLI. No pip dependencies, API key, extra model session, prompt injection, or
quota heartbeat messages are used.

## Install and start

Extract the ZIP and run from its extracted directory:

```bash
bash install.sh
```

The installer creates commands under `~/.local/bin`, backs up existing commands
with matching names, and installs the shared package under
`~/.local/lib/codex-limit-tools`. It installs an editable price file under
`${XDG_CONFIG_HOME:-~/.config}/codex-limit-tools/prices.json` if none exists.
It NEVER replaces or modifies `watch-codex-quota` or an existing quota state file.
Make sure `~/.local/bin` is on PATH. If your shell cached the old command, open a
new terminal or run `rehash` in Zsh / `hash -r` in Bash.

First verify the two independent inputs, without an agent:

```bash
codex-usage
codex-quota
```

The first log scan can take time for a large history; later scans are incremental.
Then start collection and enter the TUI:

```bash
codex-limit-estimator start tracking
```

A detached background process starts automatically. You do NOT need a separate
terminal, the v2 watcher, a manually created JSON state, or an agent to start it.
Collection defaults to every 300 seconds (five minutes). The TUI refreshes local
state more often without making account requests. Existing history provides
index context; only matched differences after the first new baseline contribute
to the live estimate. An estimate requires actual quota consumption.

| Key | Action |
| --- | --- |
| `q` / Escape | Exit TUI; leave tracking running |
| `s` | Stop/pause collecting; leave the background process available |
| `r` | Resume a paused live daemon with a fresh baseline |
| `h` | Toggle daily history |

Reattach at any time:

```bash
codex-limit-estimator
```

Other commands:

```bash
codex-limit-estimator start tracking --background
codex-limit-estimator status
codex-limit-estimator report
codex-limit-estimator stop
codex-limit-estimator resume
codex-limit-estimator shutdown
codex-limit-estimator export --output estimates.csv
codex-limit-estimator export --output estimates.json
```

`shutdown` ends the background process. Disk history remains. `resume` can restart
it after shutdown/reboot; its first sample is a new baseline. Pauses and shutdowns
may wait for an in-progress log scan/account request to finish; they do not kill
other Codex processes. Reboot startup is not automatically installed.
Starting an already-running tracker attaches without replacing its configuration.
If it is paused, press `r` or run `resume`.

## Editable prices, including GPT-6 Sol

```bash
codex-limit-estimator prices path
codex-limit-estimator prices validate
codex-limit-estimator prices import /path/to/revised-prices.json
codex-usage --prices /path/to/revised-prices.json
```

`prices path` prints the actual file to edit in your editor. JSON is validated
before import. No Python code changes are needed to add a model, update a rate,
add an alias, or change the long-context rule. The bundled GPT-6 entries use
Standard reference prices verified against the official pages on 2026-09-23:

| Model | Input / 1M | Cached read / 1M | Cache write / 1M | Output / 1M |
| --- | ---: | ---: | ---: | ---: |
| GPT-6 Astra | $10.00 | $1.00 | $12.50 | $50.00 |
| GPT-6 Sol | $2.00 | $0.20 | $2.50 | $10.00 |
| GPT-6 Luna | $0.10 | $0.01 | $0.125 | $0.50 |

The remaining entries are retained from the supplied 2026-09-11 script, with that
provenance stated in the JSON. They have not all been reverified as current.
The reference excludes taxes, regional uplifts, tool charges, Batch/Flex and
Fast-mode adjustments. It is deliberately a fixed comparison convention, not
an attempt to reproduce an invoice or subscription charging weights.

Example model entry:

```json
"gpt-6-sol": {
  "input": 2.0,
  "cached": 0.2,
  "output": 10.0,
  "cache_write": 2.5,
  "long_context": true
}
```

For models marked `long_context`, the default rule applies above 272,000 input
tokens PER RESPONSE: input/cache prices x2, output x1.5. The threshold and
multipliers are JSON settings. Token estimates do not depend on prices.

A tracking run embeds a copy and hash of its price list. Editing the external
JSON does not rewrite old estimates or silently reprice an active run. To begin
a separate run with updated prices or a new workload label:

```bash
codex-limit-estimator shutdown
codex-limit-estimator status
# Wait until Daemon: offline, then:
codex-limit-estimator start tracking --new-run --label "Astra Ultra / VM only" --prices /path/to/prices.json
```

Historical segments remain available. Comparisons using different price hashes
are kept separate. For a controlled month-long comparison, keep the SAME price
file even if market prices change. `codex-usage` is a standalone retrospective
report and does use the currently selected JSON; an active estimator uses its
frozen snapshot instead.

## What the estimate means

Let x be consumed weekly quota in percentage POINTS (100 minus percentage left),
and y be local token use or its API-equivalent reference cost. Within an
uninterrupted segment:

`equivalent per 100% = 100 * (y1 - y0) / (x1 - x0)`

Example: $40 of matched local usage and 10 percentage points consumed gives
$400 per 100%. If a comparable later interval gives $20 for 10 points, the
observed equivalent is $200. This is a legitimate descriptive measurement.
It does not establish why the ratio changed or prove an official allowance cut.

A lifetime API-equivalent total and current quota remaining are not a matched
pair of deltas and must not be divided to estimate weekly capacity. Tracking
starts with new synchronized observations.

The TUI shows:

- API-equivalent cost extrapolated to 100% of quota.
- Non-cached input, cached input, output, and reasoning token equivalents.
- Actual quota points and duration supporting the estimate.
- A rounding envelope and a provisional/partial-pricing label.
- Cache share, model mix, and priced-token coverage.
- Daily history and reference-price/workload labels.

Cached tokens are part of input. Reasoning tokens are part of output. Neither is
added twice. Cache-write tokens, when reported, belong to non-cached input and
are priced separately. Unknown models retain their tokens and are reported as
unpriced, not discarded or presented as free usage. Their missing cost means
the displayed priced-dollar subtotal is incomplete.

## Confidence and uncertainty

The display intentionally says `Confidence: not quantified`. A percentage such
as "95% confident the weekly cap shrank" would not be justified by these data.
`priced-token coverage` is a coverage percentage, NOT statistical confidence.

Default quota resolution is one percentage point. If each endpoint has rounding
error bounded by half a point, a measured change d has rounding uncertainty of
up to +/-1 point. For a positive cost change C, the conditional envelope is:

`[100*C/(d+1), 100*C/(d-1)]`

The upper end is unbounded when d <= 1. Configure another assumed resolution
using `--resolution`. This is a deterministic rounding envelope only; it does
not cover reporting lag, external activity, missing logs, incorrect prices,
model mix, service tier, reasoning settings, or changes in subscription charging.
The envelope therefore must not be called a 95% confidence interval.
Estimates below five consumed points are marked provisional by default.

## Segments, resets, and daily comparisons

The estimator continues tracking across resets; it does NOT stop an agent or
apply a spending threshold. It starts a new segment on any quota replenishment,
reset-deadline change, account/plan change, pause/resume, restart, collection gap,
log read/parse problem, changed historical model attribution, or UTC date change.
It excludes the interval crossing such a boundary rather than assigning its
mixed consumption to one side. The first sample on each side is a baseline.
A correction can look like a reset; the event is labeled descriptively.
Quota movement without newly indexed local tokens also splits the segment.

Within a day and price/workload/account-meter group, daily results use the ratio of summed
cost differences to summed quota-point differences, not an average of ratios.
Exports also include daily input, non-cached, cached, output and reasoning
equivalents per 100%. Account/plan/bucket identities remain separate.
Intervals with no measurable quota consumption are not estimated. When grouping
multiple segments, the daily report does not fabricate a confidence interval.
Cross-midnight boundary intervals are omitted; day labels use UTC, not local time.

For the question "did it fall from $400 to $200 in a month?":

1. Keep prices fixed and use enough consumed quota per comparison (prefer tens
   of points rather than one point).
2. Use only this machine for all activity consuming the selected account bucket.
   Browser Work or another device can reduce quota without appearing in local
   logs, biasing the estimate downward. Pause BEFORE using other devices, resume
   AFTER that activity and reporting have settled.
3. Keep model, effort, service mode, context-length regime, and cache mix as
   comparable as practical. The tool reports models/cache and accepts a workload
   label; it does NOT automatically infer or control reasoning-effort/service-tier
   mix from logs. A single-model workload gives a clearer comparison.
4. Review unpriced coverage, errors and omitted boundaries. Similar API dollar
   prices do not imply similar subscription quota weights across models.
5. Compare repeated daily/segment results. A repeated drop under comparable
   conditions is evidence of a changed effective conversion for that workload,
   not a direct measurement of hidden server-side token allowances.

## Architecture and compatibility

Three commands share the same package:

- `codex-usage`: incremental log index and token/cost report, with `--json` support.
- `codex-quota`: one read-only account quota request, optionally `--json`.
- `codex-limit-estimator`: detached collector, persistent statistics, controls,
  exports and TUI.

`watch-codex-quota` remains separately useful as an agent stop-policy monitor.
This estimator reuses its read-only RPC approach through a shared module rather
than calling/parsing its terminal output. It deliberately does not depend on
its state file, because that watcher exits after a latched reset while this
tracker needs to continue into the next interval. Running both makes independent
account-status requests but creates no model turns.

Only these app-server methods are used: `initialize`, `initialized`,
`account/read`, `account/rateLimits/read`. No turn/thread creation, queueing,
reset-credit consumption, or prompt submission is implemented. The official
protocol is documented, but compatibility with your authenticated CLI must be
verified locally using `codex-quota`. Errors appear in the TUI/status and are
retried by ordinary background code with bounded backoff, without model calls.

The index reads `token_usage_record` response records and per-turn model metadata
from local `sessions` and `archived_sessions` rollout JSONL files. It deduplicates
by response ID AFTER rejecting foreign-thread copies. It does not derive usage
by summing repeated `token_count` events. Those legacy events are counted only
as diagnostics. If no supported records are found, tracking reports a format
error instead of claiming zero usage. Untimestamped responses count in the
standalone lifetime report but are excluded from timed estimates. Missing local
records, imported history and delayed telemetry can still bias intervals.

Initial indexing scans the files once. Subsequent runs read appended bytes,
retain incomplete trailing lines for the next pass, and deduplicate rescans
following truncation/replacement. Arbitrary same-inode in-place log edits with
unchanged metadata are outside the append-only indexing contract. Deleted or
archived files do not subtract previously observed responses from the ledger.
No prompts, source code, tool output or credential tokens are stored in the
index; it retains response/thread IDs, model metadata and token counts.

While the collector runs, `codex-usage` reads its latest index instead of competing
as a second writer; its output indicates that it may lag up to the sample
interval. Without the daemon it refreshes the index itself. Use a separate
`--data-dir` when changing CODEX_HOME/account/machine. Do not merge state databases
from multiple devices and treat the result as a synchronized account measurement.

Default state location:
`${XDG_STATE_HOME:-~/.local/state}/codex-limit-estimator/tracking.sqlite3`.
The state directory is outside any project or repository. Back it up with SQLite's
backup API or while the daemon is shut down; WAL sidecars matter for live copies.
The bundle does not install a boot service or send analytics elsewhere.

## Tests and validation limits

```bash
python3 -m unittest discover -s tests
```

Fifteen offline tests cover deduplication/foreign copies, incremental and partial
JSONL reads, token accounting, long context and Sol prices, unpriced models,
invalid records, source isolation, ratio/rounding behavior, segmentation,
price validation, read-only fake RPC, actual detached daemon lifecycle,
stop/resume/shutdown and curses attachment/detachment through a pseudoterminal.
The fake RPC rejects non-allowlisted methods. These tests do not access a real
account, spend subscription quota, or establish live CLI compatibility.

The preview image uses explicitly synthetic data to illustrate layout; it is
not a measured result from the user's account.

## Sources

- [Official Codex app-server protocol](https://learn.chatgpt.com/docs/app-server).
- [Official API pricing](https://developers.openai.com/api/docs/pricing).
- [GPT-6 Sol model pricing and long-context rules](https://developers.openai.com/api/docs/models/gpt-6-sol).
- The user's supplied `codex-usage` script, including its legacy price snapshot
  and response-level accounting approach. This bundle corrects identified
  accounting/visibility issues; exact totals can therefore differ from the old
  script independently of any quota change.
