# Astra launch prompt — native Windows port

Place the five port documents under `docs/porting/`, open the repository on the Windows development machine, and give Astra the following prompt. The prompt authorizes implementation, not access to a real Codex account or the active installation.

```text
Implement the native Windows port of Usage Tools for Codex in this checkout.

Read AGENTS.md, applicable nested instructions, and .MODEI.md if present;
keep private instructions/identity details private. Inspect git status and
preserve unrelated work. Read docs/porting/PORTABILITY-REPORT.md and
WINDOWS-PORT.md. This request explicitly selects W-01 through W-06 as the
active backlog, replacing the old backlog pointer for this run. Do not edit
anything under the existing tasks/ directory. Do not rewrite the README.

Work on native Windows, not WSL/Git Bash as a substitute. Record the actual
OS, Python interpreter/architecture and terminal. Reconcile inspected
functions with the current checkout; do not repeat the whole source audit
unless material differences require it. The macOS pipeline is not a
prerequisite and is not authorized as extra work in this run. Reuse any
already implemented platform helper rather than creating a competing one.

Implement the tasks in order, autonomously making routine reversible
choices. Keep existing CLI/data/export/accounting contracts, frozen prices,
paths and schemas. Preserve Linux POSIX behavior. Add only the small native
file/lock/process/pipe and installer handling required by the plan. No new
features, tracing systems, services, packaging framework, GUI rewrite,
compiled application executable or compiler dependency.

For the TUI, use the existing curses renderer with a matching prebuilt
windows-curses wheel in the selected development environment. Never build
from source or install dependencies automatically at application runtime.
If a wheel or native environment is unavailable, report that blocker;
do not silently replace the TUI or claim native verification.

Keep quota RPC strictly read-only: initialize, initialized, account/read,
account/rateLimits/read. No model turns, prompts, heartbeats, session
injection, live quota-consumption experiments or credential scraping.
Use synthetic logs/history and an explicit fake app-server for tests.
Live account access is NOT authorized by this prompt. Do not invoke real
codex-quota or a real collector. Do not touch the user's active installation,
configuration, tracking database or unrelated watcher. Temporary-directory
installation/upgrade tests are authorized.

Use the verification schedule in WINDOWS-PORT.md: focused batch A after
W-03, batch B after W-05, one final native offline suite, and one combined
native console/lifecycle session. Adapt only OS-bound fixtures; do not skip
whole installer, lifecycle or safety suites. Run additional checks only for
concrete failures or invalidated evidence, briefly stating why. Reuse valid
results and keep verbose logs ignored/local. Do not delegate to other agents.

No remote OS access or new CI infrastructure is required. If Linux is not
available, hand off the exact candidate revision and existing Linux test
command. Mark Linux regression verification pending, not passed. A missing
interactive terminal or unauthorized live check must likewise remain an
explicit verification gap; continue other safe tasks.

Follow repository commit/privacy rules for coherent local commits; do not
push, publish, rewrite history or change global Git configuration. Update
docs/NEXT-RUN.md only at a meaningful handoff, briefly. Do not create a
report after every edit or mark unverified acceptance as complete.

Finish with changed files/behavior, task IDs, environment, actual test
commands/counts/revision, console result, live-integration status, Linux-gate
status, local commits if made, and concrete remaining blockers. Do not
claim zero regressions or platform support beyond the evidence obtained.
```

For a later authorized live check, the maintainer must explicitly permit the one read described in W-06. This is a human authorization, not a new application flag or feature.
