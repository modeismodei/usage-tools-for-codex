# Codex Limit Tools — Initial and Intermediate Commits

## Repository layout

Use a dedicated development repository for this bundle. Run the commands below from its root: the directory containing `install.sh`, `prices.json`, the three executables, and `codex_limit_tools/`.

DoPlace `AGENTS.md` at the bundle repository root and `Codex-Limit-Estimator-Tasks.md` in `tasks/`. This guide may also be stored there as `COMMIT-GUIDE.md`.

The initial commit should capture the existing working bundle and its implementation backlog. The backlog is not implemented merely because its Markdown file is committed.

## 1. Check the repository boundary

```bash
git rev-parse --show-toplevel
```

If the output is the intended bundle directory, use that repository. If it reports a parent repository, stop and move the bundle to its intended independent development directory before initialization. If no repository exists, initialize it:

```bash
git init -b main
```

For an existing repository, preserve its current branch and history. Do not reinitialize it merely to rename the branch.

NB: THIS REPOSITORY IS ACTUALLY STANDALONE.

## 2. Check the commit identity locally

```bash
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

These commands display the identity that will be recorded in commits. Inspect the output locally; do not paste private identity details into an agent conversation or a public issue.

If necessary, configure the approved public/pseudonymous identity for this repository only, following `.MODEI.md` when present:

```bash
git config --local user.name "YOUR_APPROVED_PUBLIC_NAME"
git config --local user.email "YOUR_APPROVED_PUBLIC_COMMIT_EMAIL"
```

Replace the placeholders before running. Never use an invented GitHub noreply address; copy the exact address from the account's email settings if that is your chosen identity. A private ignored instruction file cannot remove identity information already recorded in commit metadata.

## 3. Exclude local and private files

Merge the following patterns into the repository's existing `.gitignore`. Do not overwrite unrelated rules. All patterns are relative to this repository and intentionally preserve source files and `prices.json`.

```gitignore
# Private local agent instructions
.MODEI.md
.MODEI-exhaustive.md
.private/

# Python generated files and local environments
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.coverage
htmlcov/

# Secrets and machine-specific configuration
.env
.env.*
!.env.example

# Local runtime state, raw transcripts, and generated reports
.runtime/
.local-state/
.codex/
logs/
exports/
backups/
*.log
*.sqlite3
*.sqlite3-*
*.sqlite
*.sqlite-*
*.db
*.db-*
*.jsonl
*.backup-*
/history.json
/history.csv
/estimates.json
/estimates.csv
/segments.csv
/snapshots.csv
/analysis.json

# Generated distribution archives
/dist/
/build/
/Codex-Limit-Tools*.zip
```

Use synthetic fixtures in an explicitly reviewed test location. If a future test genuinely requires a JSONL fixture, add a narrow exception for that fixture rather than removing the general transcript exclusion.

Confirm private instructions are ignored:

```bash
git check-ignore -v .MODEI.md
```

Ignore rules do not untrack existing files. Check for already tracked private/runtime files:

```bash
git ls-files -- .MODEI.md .env .codex .runtime logs exports backups
```

If an unwanted file is tracked, review the exact path before removing it from the index with `git rm --cached -- PATH`. This keeps the local file but does not remove its contents from prior commits. Do not rewrite history automatically; exposed credentials require separate handling.

## 4. Validate the baseline and inspect the working tree

For the original bundle, run from the repository root:

```bash
python3 -m unittest discover -s tests
git status --short
git diff --check
```

The default unittest summary is short. Stop on test failures and inspect only the relevant diagnostics. Do not run `install.sh` as a test against the active installation.

If the repository has changed since the original bundle, use its current documented test entry point instead. Do not assume previous test counts still apply.

## 5. Stage explicit source and documentation paths

For a fresh extracted bundle with the new documentation placed at its root:

```bash
git add -- .gitignore AGENTS.md COMMIT-GUIDE.md Codex-Limit-Estimator-Tasks.md
git add -- README.md install.sh prices.json
git add -- codex-usage codex-quota codex-limit-estimator
git add -- codex_limit_tools/ tests/
```

Include the preview only if it is the original synthetic image and is present:

```bash
git add -- TUI-preview.png
```

Omit optional/missing paths rather than inventing files. In an existing repository, inspect directory contents before staging directories, and use `git add -p` for files containing mixed changes. Never stage local tracking data or real transcript fixtures.

Review exactly what the commit will contain:

```bash
git diff --cached --stat
git diff --cached --name-only
git diff --cached --check
git diff --cached
```

Inspect names, email addresses, personal paths, credentials, and real account data as well as code correctness. This review does not require printing secrets into a report.

## 6. Commit the current baseline

For a new repository containing the original bundle:

```bash
git commit -m "chore: establish Codex limit tools baseline and analysis backlog"
git log -1 --oneline
git status --short
```

For an existing repository where the bundle is already committed, commit only the new instructions and task specification with a message such as:

```bash
git commit -m "docs: define extended allowance analysis tasks and agent policy"
```

Do not create an empty commit if nothing changed. A clean status is expected for a fresh baseline, but unrelated pre-existing edits must remain untouched. These steps create a local commit only; they do not publish or push anything.

## 7. Intermediate implementation commits

Recommended reviewable milestones, adjusted to actual dependencies:

| Milestone | Tasks | Example commit message |
| --- | --- | --- |
| Contracts and deterministic fixtures | T01 | `test(analysis): define interval aggregation fixtures` |
| Run identity and migration | T02 | `feat(history): preserve run identity with versioned migrations` |
| Aggregation, continuity, and quality | T03–T05 | `feat(analysis): aggregate observed intervals with coverage bounds` |
| Analysis commands and range selection | T06–T07 | `feat(cli): analyze runs and observed quota ranges` |
| Manual checkpoints | T08 | `feat(tracker): acknowledge bounded checkpoint requests` |
| Aggregate terminal view | T09 | `feat(tui): display run-level allowance estimates` |
| Upgrade guidance and final verification | T10 | `docs: document history analysis and safe upgrades` |

For each milestone: run relevant checks, stage task-owned changes, inspect the staged diff, check whitespace, then commit. Avoid committing knowingly broken intermediate states merely to match this table.

After a meaningful milestone or before stopping, update the task checkboxes and concise `docs/NEXT-RUN.md` handoff. Commit those updates with the associated work or a small documentation checkpoint.

## Launch instruction for the implementation agent

Paste the following into the agent session opened at this repository root:

> Follow AGENTS.md and any applicable private local instructions. Implement Codex-Limit-Estimator-Tasks.md in dependency order, preserving the existing bundle and historical-data compatibility. Work autonomously on routine decisions, test at coherent milestones, and create local intermediate commits using the repository's approved identity. Preserve unrelated changes, keep test output concise, and maintain a minimal handoff. Do not push, install into my active environment, migrate my real database, send agent heartbeat messages, or consume model quota through generated workloads. Complete as much authorized implementation as possible and report concrete blockers only when they prevent further safe progress.

Any quota threshold or reset-stop condition should be added explicitly to the launch prompt for that run. These repository instructions do not invent a threshold or depend on a particular external watcher's state path.
