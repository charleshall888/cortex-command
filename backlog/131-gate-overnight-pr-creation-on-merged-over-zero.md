---
schema_version: "1"
uuid: 5e103f2e-fd3d-4890-84a5-c67d6adac785
title: "Gate overnight PR creation on merged>0 (draft on zero-merge)"
status: complete
priority: medium
type: feature
tags: [overnight-runner, pr, orchestrator-worktree-escape]
areas: [overnight-runner]
created: 2026-04-21
updated: 2026-04-22
lifecycle_slug: gate-overnight-pr-creation-on-merged-over-zero
lifecycle_phase: complete
session_id: null
blocks: []
blocked-by: []
discovery_source: cortex/research/orchestrator-worktree-escape/research.md
complexity: simple
criticality: high
spec: cortex/lifecycle/archive/gate-overnight-pr-creation-on-merged-over-zero/spec.md
---

# Gate overnight PR creation on merged>0 (draft on zero-merge)

## Context from discovery

`cortex_command/overnight/runner.sh:1149` runs `gh pr create` unconditionally whenever `INTEGRATION_BRANCH` is set (line 1124 gate). `MC_MERGED_COUNT` is computed at lines 1134-1142 but used only in the PR body template — not as a gate.

Session `overnight-2026-04-21-1708` is the live artifact: all 3 features failed at `feature_start`, `MC_MERGED_COUNT` was 0, and PR #4 was still created (OPEN, MERGEABLE, CLEAN). Its only unique content vs main is 3 lines of `session_id: null` frontmatter mutations on backlog 094/095/096 — content that should not land on main.

**This is not a worktree-escape bug** and is intentionally scoped outside the parent epic #126 (per research DR-1). `MC_MERGED_COUNT` is computed and ignored — the PR would have been created identically even if every worktree-invariant bug were fixed. It surfaced in the same session by coincidence, not shared mechanism.

## Value

One session has already created a zombie PR (#4). The fix is small and removes an ongoing operator-attention tax: zero-merge sessions produce PRs that have to be manually closed. Gating fires only on the failure path; no impact on healthy sessions.

## Research context

- Full analysis: `research/orchestrator-worktree-escape/research.md` DR-2
- Design choice: create the PR as `--draft` with an explicit "ZERO PROGRESS" title rather than skipping entirely — skipping hides the failure from the morning-review workflow, whereas draft blocks auto-merge while keeping the branch surfaced for operator cleanup

## Acceptance criteria

- `runner.sh:1149` creates the PR as `--draft` and with an explicit zero-progress title/body when `MC_MERGED_COUNT == 0`
- Healthy sessions (`MC_MERGED_COUNT > 0`) produce a non-draft PR with the existing content
- A failed-session integration test (or manual dry-run) confirms the draft state and title
