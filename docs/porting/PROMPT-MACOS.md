# Astra launch prompt — native macOS port

Place the five port documents under `docs/porting/`, open the repository on the Mac, and give Astra the following prompt. Do not execute the Windows backlog in the same run.

```text
Validate and, only where necessary, implement native macOS support for
Usage Tools for Codex in this checkout.

Read AGENTS.md, applicable nested instructions, and .MODEI.md if present;
keep private instructions/identity details private. Inspect git status and
preserve unrelated work. Read docs/porting/PORTABILITY-REPORT.md and
MACOS-PORT.md. This request selects M-01 through M-03 as the active backlog,
replacing the old backlog pointer for this run. Do not edit files under the
existing tasks/ directory or rewrite the README.

Work on a native Mac. Record macOS version, architecture, Python and
terminal. Check relevant functions against the inspected snapshot; avoid a
new repository-wide audit. The source inspection found no unconditional
macOS runtime blocker: prove the existing Unix path first. Do not manufacture
patches when tests and native checks pass. The Windows pipeline is not a
prerequisite or extra work for this run. Preserve any already-landed Windows
support and reuse its shared helpers where applicable.

Keep the existing stdio Codex app-server protocol, Unix select/flock/file
semantics, session detachment, Bash installer and curses renderer unless a
reproduced native failure requires a targeted change. Preserve CLI, paths,
accounting, exports, schemas, historical data and frozen prices. No new
features, alternate quota backend, GUI/theme, launchd job, app bundle,
Homebrew package, compiler dependency or speculative portability framework.

Run M-01's isolated native offline baseline once, without --trace. The
Linux strace audit is not a macOS runtime requirement. Repair only concrete
product/fixture failures through M-02 and focused affected tests. If no
relevant code/tests change, reuse that baseline as the final result;
otherwise run one final full offline suite after fixes. Combine terminal,
resize, keys, pause/resume, detach and shutdown checks in one short native
console session. No new terminal automation infrastructure or repeated
full suites without a reason. Keep detailed logs local and ignored.

Use synthetic state, logs and an explicit fake app-server. Keep the quota
method allowlist: initialize, initialized, account/read,
account/rateLimits/read. No prompts, model turns, heartbeat/session injection,
quota-consumption experiments or credential scraping. Live account access
is NOT authorized: do not invoke the real quota client or collector.
Do not upgrade the active installation, migrate real databases or change
an unrelated watcher. Temporary installation/rollback tests are authorized.

Proceed autonomously with routine reversible repairs; do not delegate to
other agents. Missing native terminal/curses/access is a specific blocker,
not a reason to pretend native checks passed. Continue other safe work and
record unavailable checks explicitly. Ask only for genuinely essential
missing information or an action requiring additional permission.

No remote OS setup or new CI pipeline is required. Any changed shared code
needs valid Linux regression evidence for the candidate revision; otherwise
hand off that revision and the existing Linux command, marking the gate
pending. Reuse identical-code evidence. If a change invalidates an earlier
Windows result, identify the affected recheck without implementing Windows
work here or claiming the old result covers new code.

Follow the repository's local commit/privacy rules; do not push, publish,
rewrite history or change global Git configuration. Update docs/NEXT-RUN.md
only at a meaningful handoff, not per edit. Finish with task IDs, actual
changes (including a legitimate no-op), environment, test counts/commands/
revision, native-console result, live-integration status, Linux gate,
commits if made, and specific remaining limitations. Do not claim testing
on another architecture or promise zero regressions.
```

A real native Codex read is a separate, explicitly authorized follow-up verification step described in M-03, not permission implied by running this prompt.
