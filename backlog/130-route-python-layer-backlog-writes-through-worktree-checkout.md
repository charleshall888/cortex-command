---
schema_version: "1"
uuid: a98f7141-94ee-4479-85b3-75187deff6d9
title: "Route Python-layer backlog writes through worktree checkout"
status: complete
priority: high
type: feature
parent: 126
tags: [overnight-runner, backlog, worktree, orchestrator-worktree-escape]
areas: [overnight-runner]
created: 2026-04-21
updated: 2026-04-22
lifecycle_slug: route-python-layer-backlog-writes-through-worktree-checkout
lifecycle_phase: research
session_id: null
blocks: []
blocked-by: []
discovery_source: cortex/research/orchestrator-worktree-escape/research.md
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/route-python-layer-backlog-writes-through-worktree-checkout/spec.md
---

# Route Python-layer backlog writes through worktree checkout

## Context from discovery

Two Python modules write to backlog files via the home-repo filesystem path, bypassing the overnight runner's worktree-isolation model. Both were observed to cause silent data loss in session `overnight-2026-04-21-1708`:

**`report.py:272-360` — `create_followup_backlog_items()`**: wrote 3 followup items at IDs 101/102/103 via the home-repo path at the end of session 1708. The runner's artifact commit at `runner.sh:1002-1008` only `git add`-s worktree files, so the items landed as untracked files in `$REPO_ROOT`. Later the same day a `/discovery` decompose allocated IDs 101/102/103 to unrelated content, silently overwriting the overnight's structured followup content. The morning report at `morning-report.md:96-98` still references the original titles; the body content — parse-error context, failure rationale — is permanently lost.

**`backlog.py:321,365` — `session_id` frontmatter mutation**: writes `session_id: <uuid>` on session start and `session_id: null` (or similar) on session transitions via the home-repo path. When session 1708 failed, the mutations landed both on the integration branch (via the runner's worktree git-add) AND as uncommitted working-tree changes on local `main` (from the home-repo write). PR #4's integration-branch content is entirely this: 3 lines of `session_id: null` on backlog 094/095/096.

## Shared root cause and fix

Both failure modes stem from the same architectural drift: Python helpers writing via `HOME_PROJECT_ROOT` or an equivalent home-repo path constant, instead of through the active session's worktree checkout. The fix is structural: route Python backlog writes through the worktree path so mutations travel with the integration branch and discard cleanly on a failed/closed branch — eliminating the "uncommitted main changes" and "untracked home-repo files" failure modes in one change.

## Value

Addresses two observed data-loss vectors with one fix. #3 is the larger symptom (permanent content loss on ID collision); #5 is the zombie-state nuisance (mutations linger on main until operator cleanup). Consolidating these into a single ticket — rather than the separate "followup persistence" + "frontmatter rollback" items originally proposed — reflects that the fix is shared: the rollback becomes unnecessary once writes are scoped to the worktree.

## Research context

- Full analysis: `research/orchestrator-worktree-escape/research.md` §Current Session State → Followup items 101/102/103 and §"No worktree GC, no session-failure rollback"
- The research's earlier draft listed these as two separate tickets (#4 followup persistence + #5 frontmatter rollback); consolidation during decomposition follows the research's "same root cause" observation

## Acceptance criteria

- After this ticket lands, `create_followup_backlog_items()` writes to a path that the runner's worktree-scoped `git add` at `runner.sh:1002-1008` picks up — confirmed by a failed-session test showing followup items land on the integration branch, not as untracked home-repo files
- `backlog.py:321,365` (and any other `session_id` mutation site) writes via the same worktree-scoped path so mutations are scoped to the integration branch
- A simulated failed session leaves no uncommitted backlog-file changes in the home-repo working tree
- Morning-report rendering is unchanged (report.py still reads backlog state the same way)
