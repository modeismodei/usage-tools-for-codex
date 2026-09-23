# Agent Instructions — Usage Tools for Codex

## Scope and execution

This repository contains `codex-usage`, `codex-quota`, and `codex-limit-estimator`, with shared Python modules.

Read this file, applicable nested instructions, and `.MODEI.md` if present before changing files or creating commits. Treat `.MODEI.md` as private local project instructions, subject to higher-priority instructions. Never copy its contents into tracked files, commit messages, logs, or reports. If absent, continue without inventing personal identity settings.

Use `tasks/Codex-Limit-Estimator-Tasks.md` as the implementation backlog. Implement authorized tasks in dependency order, using the existing architecture and preserving unrelated work. The listed new commands are specifications, not claims that features already exist.

Make routine reversible decisions autonomously. Ask only when essential missing information, conflicting instructions, unavailable access, or a destructive action prevents safe progress. Do not ask for approval after every task. Do not deploy, publish, push, create remote repositories, or rewrite existing history without explicit authorization.

## First steps

1. Inspect repository status and relevant diffs. Identify existing user work without changing it.
2. Read the task overview and the next applicable task. Inspect only the implementation files needed for that task.
3. Check the existing test entry point and Python version. Use isolated temporary data directories for tests.
4. If making commits, inspect the effective Git author identity locally and follow `.MODEI.md` if present. Do not print personal identity details in progress reports. If identity is missing or conflicts with explicit privacy instructions, continue implementation and report the commit blocker once. Never invent an identity or edit global Git configuration.
5. Begin the next ready task. Reuse existing verification evidence when the tested code and environment have not changed.

## Architecture and data invariants

- Preserve independent CLI commands, shared modules, SQLite history, and external JSON prices.
- Keep observation, analysis, rendering, and command parsing separate. Put reusable calculation logic in the analysis layer.
- Preserve historical data and frozen run price snapshots. Do not silently reprice past runs.
- Migrations must be transactional, versioned, backed up, and coordinated with the daemon lock.
- Aggregate with a ratio of summed metric deltas to summed consumed quota points. Never use an unweighted mean of segment estimates.
- Do not bridge resets, pauses, errors, or unknown gaps as if continuously observed. Do not fabricate quota crossings or historical snapshots.
- Account for cached input and reasoning output as subsets of their respective totals.
- Distinguish descriptive estimates, partial pricing, coverage, and conditional rounding bounds. Never invent confidence percentages or claim to establish an official allowance.
- Retain backward compatibility for documented commands and export fields unless the task explicitly requires a documented migration.

## Read-only quota protocol

These tools observe usage; they must not create usage.

- Never send prompts, enqueue messages, start model turns, or generate workloads to test allowance consumption.
- Retain the quota RPC allowlist: `initialize`, `initialized`, `account/read`, and `account/rateLimits/read`.
- Never inject heartbeat messages into an agent session, including through tmux or a queue command.
- Do not change or automatically launch a separate `watch-codex-quota`, alter its state, or require a project-specific quota state file as a prerequisite for this repository.
- Use fake RPC responses and synthetic local records for tests. Live account checks require explicit user authorization; report that they are unverified when unavailable.
- Do not install or upgrade the user's active installation, start persistent real-account monitors, or migrate their real tracking database unless the user requests that operation. Implementation and temporary-directory tests remain authorized.

## Testing and token efficiency

Test regularly at meaningful boundaries, not after every small edit.

- Run focused tests after a coherent calculation, persistence, or control-flow change.
- Run the full suite before completing the implementation milestone. Repeat only when subsequent changes affect its validity or a concrete failure warrants it.
- Prefer deterministic standard-library tests and reusable non-agentic commands. The user must be able to execute all checks without an agent.
- Redirect verbose output to ignored local logs and inspect aggregate results first. Read a bounded failure excerpt when needed; read full logs only when essential. Brief default unittest output may be read directly.
- Check process exit codes. Never infer success merely from the absence of visible error text, and do not mask a failed command with a logging pipeline.
- Avoid repeated repository-wide reads, dependency scans, test runs, and full transcript replay. Use targeted searches and diffs.
- Keep routine progress reports short: completed behavior, relevant verification, and any concrete blocker.
- Do not delegate to additional agents unless the user explicitly requests delegation.

## Commit policy

Local commits are authorized when the user asks to implement this backlog. Remote pushes are not authorized by that request.

- Commit after coherent, reviewable milestones with relevant checks passing. A milestone may cover one task or several tightly coupled tasks.
- Use explicit file paths or reviewed patch staging. Never use blanket staging without inspecting every included file.
- Preserve pre-existing edits. If unrelated changes share a file, stage only the task's reviewed hunks or leave that file uncommitted and explain why.
- Before each commit, inspect the staged diff and run `git diff --cached --check`.
- Exclude private instructions, credentials, local account data, transcripts, runtime state, SQLite databases, exports, backups, and detailed test logs.
- Follow the repository's author/privacy policy. Do not change global Git identity or add attribution trailers unless required by the user or applicable instructions.
- Use concise messages describing the behavior, for example `feat(analysis): aggregate compatible observation intervals`.
- Do not amend, squash, force-push, or discard existing work unless explicitly authorized.
- Do not claim commits were created without checking their actual IDs.

## Conditional personal commit requirements

Personal commit identity, pseudonym, privacy, and attribution requirements
apply only when a `.MODEI.md` file is present and readable in the repository
root.

When present, follow its instructions before creating commits, subject to
higher-priority instructions. Keep its contents private and untracked.

When absent, ignore requirements specific to the original maintainer.
Use the current contributor's configured Git identity and normal workflow.
Do not require `.MODEI.md`, ask contributors to create it, or impose the
original maintainer's identity or approval requirements.

If `.MODEI.md` exists but cannot be read, do not treat it as absent:
continue work that does not depend on its contents and report the issue
before creating commits.

General repository rules still apply, including preserving unrelated work,
reviewing staged changes, excluding secrets, and not pushing without
authorization. Missing Git identity should be handled as ordinary Git
configuration, not as a missing personal-policy file.

## Checkpoints and stopping

Do not introduce an arbitrary quota threshold in this file. A threshold or reset-stop rule supplied in the current launch prompt applies to that run only, using the already authorized observation mechanism. Do not recreate a missing watcher or invent quota state.

When an explicit stop condition is observed, stop starting new work. Use the available budget to reach the nearest small safe checkpoint, run relevant checks, and commit coherent changes. Do not continue a large task solely to finish it, and do not run optional checks or additional model work after a reset-stop request.

Aim for a clean task-owned working tree. Never obtain cleanliness by deleting work, reverting user edits, blindly stashing, or committing unrelated files. If a safe commit is not possible, preserve the changes and describe their status honestly.

Maintain `docs/NEXT-RUN.md` only at meaningful handoff points, not after every edit. Keep it under roughly 60 lines with:

- completed task IDs and relevant commit IDs;
- next ready task and one concrete next action;
- tests already run and the revision they validate;
- actual blockers and any intentionally uncommitted work.

Do not include personal paths, account identifiers, quota-state contents, full logs, or transcripts. Update task checkboxes only when acceptance criteria are satisfied. Do not mark partially implemented work complete.

## Completion report

State implemented behavior, relevant test results, local commits, remaining limitations, and the next task if any. Distinguish simulated verification from live account verification. Do not push automatically.
