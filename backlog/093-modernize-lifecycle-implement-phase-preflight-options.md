---
schema_version: "1"
uuid: 16067c99-27ab-4c9f-ad0b-a968cc27af95
title: "Modernize lifecycle implement-phase pre-flight options"
status: complete
priority: high
type: epic
created: 2026-04-20
updated: 2026-04-22
tags: [lifecycle, daytime-pipeline, worktree, preflight]
discovery_source: cortex/research/revisit-lifecycle-implement-preflight-options/research.md
areas: [lifecycle, skills, pipeline]
---

# Modernize lifecycle implement-phase pre-flight options

Revisits the four-option pre-flight in `skills/lifecycle/references/implement.md §1` ("Implement in worktree" / "Implement in autonomous worktree" / "Implement on main" / "Create feature branch") based on lived-experience evidence since epic #074 shipped.

## Scope

Four children:

1. **#094** — Fix daytime pipeline worktree atomicity and stderr logging (DR-4)
2. **#095** — Replace daytime log-sentinel classification with structured result file (DR-2)
3. **#096** — Add uncommitted-changes guard to lifecycle implement-phase pre-flight (DR-3)
4. **#097** — Remove single-agent worktree dispatch and flip recommended default to current branch (DR-1, user override)

Dependency graph:

```
094 ─┐
095 ─┤
096 ─┴─ 097 (blocked by 096)
```

Tickets 094 and 095 are independent of 096/097 and can land in parallel.

## End state

After all four ship, the pre-flight drops from four options to three when the user is on `main`:

1. **Implement on current branch** — recommended (with uncommitted-changes guard demoting when working tree is dirty)
2. **Implement in autonomous worktree** — daytime pipeline, now with crash-safe output contract and atomic worktree creation
3. **Create feature branch** — unchanged

The single-agent worktree dispatch path (option 1 in the current pre-flight; `§1a` in `implement.md`) is removed entirely.

## Research Context

See `research/revisit-lifecycle-implement-preflight-options/research.md`. Decision records:

- **DR-1**: research recommended *demote* option 1 on thin-evidence grounds; user overrode to *remove* based on maintenance-cost judgment.
- **DR-2**: structured `daytime-result.json` with atomic writes + freshness token; log-sentinel rejected due to crash/buffering failure modes.
- **DR-3**: single guard (uncommitted-changes); plan-complexity and phased rollout rejected as uncalibrated.
- **DR-4**: fix atomicity + logging defects first; do not assert a root cause for the exit-128 failure until stderr is visible.

This epic reverses epic #074's DR-2 ("co-exist single-agent and autonomous paths"). The research-level justification is evidence-thin for removal; the user override accepts one-way-door cost in exchange for not carrying two parallel dispatch mechanisms indefinitely.
