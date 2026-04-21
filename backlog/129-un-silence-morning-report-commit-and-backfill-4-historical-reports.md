---
schema_version: "1"
uuid: 503f9a80-0ec5-4d12-b7b1-3e56b2b5e879
title: "Un-silence morning-report commit and backfill 4 historical reports"
status: backlog
priority: critical
type: feature
parent: 126
tags: [overnight-runner, morning-report, gitignore, orchestrator-worktree-escape]
areas: [overnight-runner]
created: 2026-04-21
updated: 2026-04-21
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
discovery_source: research/orchestrator-worktree-escape/research.md
---

# Un-silence morning-report commit and backfill 4 historical reports

## Context from discovery

**Every overnight session in this machine's history has failed to commit its morning report.** Verified by direct inspection: 4 session directories exist at `lifecycle/sessions/overnight-*/`; 0 of them have a tracked `morning-report.md` in git history on any branch. The files exist locally at 8 KB each but have never entered version control.

Mechanism:

- `.gitignore:41` contains `lifecycle/sessions/` ("Overnight session archives"). All per-session artifacts are gitignored.
- `runner.sh:1220-1226` runs inside a `(cd "$REPO_ROOT"; ...)` subshell:
  ```
  git add "lifecycle/sessions/${SESSION_ID}/morning-report.md" 2>/dev/null || true
  git add "lifecycle/morning-report.md"                        2>/dev/null || true
  git diff --cached --quiet || git commit -m "..."
  ```
- `git add` without `-f` silently skips ignored files.
- `lifecycle/morning-report.md` is not gitignored but is not produced anywhere — there is no writer.
- `git diff --cached --quiet` returns true (nothing staged), so the commit step is never taken.

`docs/overnight-operations.md:413`'s claim *"The morning-report commit is the only runner commit that stays on local main"* is aspirational — that commit has never happened. `sync-allowlist.conf:36` listing `lifecycle/sessions/*/morning-report.md` for `--theirs` conflict resolution is dead code: files that are never tracked cannot conflict.

## Value

Morning reports are the operator's review artifact for autonomous overnight work (per `requirements/pipeline.md`). A 20-day silent audit-trail loss undermines the product's "autonomous multi-hour development" north star: the operator has been making post-merge decisions against files that existed only on one machine's disk. This fix is ~1 hour once the storage decision is made, and unblocks the historical backfill.

## Research context

- Full analysis: `research/orchestrator-worktree-escape/research.md` RQ3 and Fact-Section Correction #4
- Earlier research draft framed this as a "push-target bug" — critical review and direct gitignore inspection corrected the mechanism

## Scope

This ticket covers two things: the forward-path fix and the backfill.

**Forward path**: Pick a storage decision and apply it consistently:
- (a) un-ignore `lifecycle/sessions/*/morning-report.md` specifically in `.gitignore`, OR
- (b) relocate morning-report output to a non-ignored path (with a `runner.sh:1220-1226` update if paths change)
- (c) use `git add -f` in the runner — least preferred; couples runner to gitignore layout

The choice affects `sync-allowlist.conf` (the dead-code entry at line 36 either becomes live again or is cleaned up) and any documentation referencing the commit target.

**Backfill**: Once the forward fix lands, commit the 4 existing local morning-report files (`lifecycle/sessions/overnight-2026-04-01-2112/morning-report.md`, `overnight-2026-04-07-0008`, `overnight-2026-04-11-1443`, `overnight-2026-04-21-1708`) to `main` — one operator invocation, not an ongoing process.

## Acceptance criteria

- After this ticket lands, a new overnight session's `runner.sh:1220-1226` block actually commits the morning report — no silent skip
- `git log -- lifecycle/sessions/*/morning-report.md` for the 4 historical sessions shows the backfill commits
- The chosen storage decision is reflected in `.gitignore`, `sync-allowlist.conf`, and any documentation that referenced the prior (aspirational) behavior
