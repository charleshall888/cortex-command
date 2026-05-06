---
schema_version: "1"
uuid: ab917a16-dbcc-47f2-9541-56d29bbee26a
title: "Extract morning-review deterministic sequences (C11-C15 bundle)"
status: complete
priority: medium
type: feature
parent: "101"
blocked-by: []
tags: [harness, scripts, morning-review]
created: 2026-04-21
updated: 2026-04-28
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
complexity: complex
criticality: high
spec: lifecycle/archive/extract-morning-review-deterministic-sequences-c11-c15-bundle/spec.md
areas: [skills]
session_id: null
lifecycle_phase: complete
---

# Extract morning-review deterministic sequences (C11–C15 bundle)

## Context from discovery

Round-2 sweep surfaced five deterministic sequences in the morning-review and complete-phase flows that were missed in Round 1:

- **C11** session completion + state update — `skills/morning-review/SKILL.md:23-48`
- **C12** stale worktree garbage sweep — `:50-75`
- **C13** backlog-closure loop (per-feature `cortex-update-item status=complete`) — `:109-128`, `references/walkthrough.md:447-481`
- **C14** git preflight sync — `:132-138` (fold preflight mode into existing `bin/cortex-git-sync-rebase`)
- **C15** backlog-index regeneration fallback chain — `skills/lifecycle/references/complete.md:42-71` + `morning-review/SKILL.md:130-151`

Bundled because all fire during a single morning-review invocation and share the same acceptance test (one morning-review run). Consolidation follows Decompose §3(a) for C11/C12/C13 (same-file overlap); C14 is cross-file into an existing script; C15 touches `complete.md`. The bundled trade-off was flagged in CR2 — may split at plan phase if scope proves too large.

## Research context

- C11–C15 candidate table rows in `research/extract-scripts-from-agent-tool-sequences/research.md`.

## Scope

- `bin/cortex-morning-review-complete-session` (or similar) for C11 atomic state update.
- Worktree GC helper (new `bin/cortex-worktree-gc` or extension of `bin/cortex-git-sync-rebase`) for C12.
- Parallel `cortex-update-item` dispatch for C13 — already adopted in current SKILLs; close any remaining gaps.
- Fold preflight mode into `bin/cortex-git-sync-rebase` for C14 (may be SKILL.md edit only).
- Simplify backlog-index regen chain for C15 (requires `cortex-generate-backlog-index` in PATH as invariant; existing fallback to `~/.local/bin/generate-backlog-index` in `skills/lifecycle/references/complete.md` is dead post-113 and should be removed here).
- Fix existing drift: `skills/morning-review/references/walkthrough.md` references `git-sync-rebase.sh` (5 occurrences) — actual binary is `cortex-git-sync-rebase`. Repoint as part of C14.
- All new scripts must be `cortex-*` prefixed — `just build-plugin` filters with `--include='cortex-*'` to ship them via the `cortex-interactive` plugin.

## Out of scope

- Refactoring the lifecycle advancement judgment logic (§2b in walkthrough) — stays as agent reasoning.
