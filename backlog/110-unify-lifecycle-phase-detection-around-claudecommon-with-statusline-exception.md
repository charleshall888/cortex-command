---
schema_version: "1"
uuid: 111b819b-1129-40d4-bf59-9845fe4b6d01
title: "Unify lifecycle phase detection around claude.common with statusline exception"
status: backlog
priority: medium
type: feature
parent: "101"
blocked-by: ["102", "103"]
tags: [harness, scripts, lifecycle]
created: 2026-04-21
updated: 2026-04-21
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
---

# Unify lifecycle phase detection around claude.common with statusline exception (C2+C3)

## Context from discovery

Lifecycle phase-detection logic currently lives in **four** places:

1. `hooks/cortex-scan-lifecycle.sh:170-207` — hook with `implement:N/M` format
2. `skills/lifecycle/SKILL.md:41-100` — skill Step 2 pseudo-ladder
3. `claude/common.py:detect_lifecycle_phase()` — canonical Python (already called by dashboard + backlog-index)
4. `claude/statusline.sh:377-402` — bash re-implementation for per-prompt refresh latency

Round-2 semantic diff confirmed all four agree on the phase model. `claude.common` is already canonical for Python callers. **Statusline stays bash** — subprocess-to-Python adds ~100ms per prompt refresh, which is not acceptable. This leaves a documented drift-prone mirror (DR-6). Net drift: 4 → 3 implementations (not 4 → 1).

## Research context

- C2+C3 and DR-6 in `research/extract-scripts-from-agent-tool-sequences/research.md`.
- Statusline parses `implement:N/M` back apart for a progress bar at lines 535-546 — the format is an inter-component contract, not caller-specific wrapping.
- Canonical API must return `{phase, checked, total, cycle}` to preserve the contract. DR-2 narrow-schema exception documented.
- Effort: L. Touches `claude/common.py`, hook, skill, and adds new CLI `python3 -m claude.common detect-phase <dir>`.

## Scope

- Extend `claude.common.detect_lifecycle_phase()` return type to `{phase, checked, total, cycle}`.
- Add CLI entry point: `python3 -m claude.common detect-phase <dir>`.
- Hook: replace `determine_phase()` function body with subprocess call; format `implement:N/M` label from structured result.
- Skill: replace Step 2 pseudo-ladder with reference to the CLI; retain `.dispatching` marker check and worktree-aware override (those are phase overrides, not detection).
- Statusline: add comment documenting it is a deliberate bash-only mirror; include phase-model sync reminder.
- Consumer audit update: dashboard + backlog-index unaffected (already call canonical).

## Out of scope

- Statusline migration to Python (structural constraint).
- Overhaul of `.dispatching` or worktree-override logic (they are override signals, not phase detection).

> **2026-04-22 (ticket #097) — scope amendment.** The `.dispatching` marker check and Worktree-Aware Phase Detection override have been deleted in full from SKILL.md Step 2. The "retain `.dispatching` marker check and worktree-aware override" language above (line 41) and the "Overhaul of `.dispatching` or worktree-override logic" out-of-scope entry (line 48) no longer apply — neither override exists in post-#097 SKILL.md. `/refine` should re-evaluate scope against the reduced surface before planning.
