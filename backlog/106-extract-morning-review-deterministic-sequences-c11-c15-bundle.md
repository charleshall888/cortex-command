---
schema_version: "1"
uuid: ab917a16-dbcc-47f2-9541-56d29bbee26a
title: "Extract morning-review deterministic sequences (C11-C15 bundle)"
status: backlog
priority: medium
type: feature
parent: "101"
blocked-by: ["102", "103"]
tags: [harness, scripts, morning-review]
created: 2026-04-21
updated: 2026-04-21
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
---

# Extract morning-review deterministic sequences (C11–C15 bundle)

## Context from discovery

Round-2 sweep surfaced five deterministic sequences in the morning-review and complete-phase flows that were missed in Round 1:

- **C11** session completion + state update — `skills/morning-review/SKILL.md:23-48`
- **C12** stale worktree garbage sweep — `:50-75`
- **C13** backlog-closure loop (per-feature `update-item status=complete`) — `:109-128`, `references/walkthrough.md:447-481`
- **C14** git preflight sync — `:132-138` (fold preflight mode into existing `bin/git-sync-rebase.sh`)
- **C15** backlog-index regeneration fallback chain — `skills/lifecycle/references/complete.md:42-71` + `morning-review/SKILL.md:130-151`

Bundled because all fire during a single morning-review invocation and share the same acceptance test (one morning-review run). Consolidation follows Decompose §3(a) for C11/C12/C13 (same-file overlap); C14 is cross-file into an existing script; C15 touches `complete.md`. The bundled trade-off was flagged in CR2 — may split at plan phase if scope proves too large.

## Research context

- C11–C15 candidate table rows in `research/extract-scripts-from-agent-tool-sequences/research.md`.

## Scope

- `bin/morning-review-complete-session` (or similar) for C11 atomic state update.
- Worktree GC helper (new `bin/worktree-gc` or extension of `git-sync-rebase.sh`) for C12.
- Parallel `update-item` dispatch for C13 — also closes `update-item` adoption gap.
- Fold preflight mode into `bin/git-sync-rebase.sh` for C14 (may be SKILL.md edit only).
- Simplify backlog-index regen chain for C15 (requires `generate-backlog-index` in PATH as invariant).

## Out of scope

- Refactoring the lifecycle advancement judgment logic (§2b in walkthrough) — stays as agent reasoning.
