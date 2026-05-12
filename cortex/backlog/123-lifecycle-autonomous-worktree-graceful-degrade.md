---
schema_version: "1"
uuid: 4ed319f6-98e0-48ff-ace6-8e1023b1cfbb
title: "Lifecycle skill gracefully degrades autonomous-worktree option when runner absent"
status: complete
priority: high
type: feature
parent: 113
tags: [distribution, plugin, lifecycle, overnight-layer-distribution]
areas: [skills]
created: 2026-04-21
updated: 2026-04-24
lifecycle_slug: lifecycle-skill-gracefully-degrades-autonomous-worktree-option-when-runner-absent
lifecycle_phase: complete
session_id: null
blocks: []
blocked-by: []
discovery_source: cortex/research/overnight-layer-distribution/research.md
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/lifecycle-skill-gracefully-degrades-autonomous-worktree-option-when-runner-absent/spec.md
---

# Lifecycle skill gracefully degrades autonomous-worktree option when runner absent

## Context from discovery

The lifecycle skill has four execution modes; one of them ("Implement in autonomous worktree") dispatches to `python3 -m cortex_command.overnight.daytime_pipeline` — a module that ships with the runner CLI, not with `cortex-interactive`. Users who install `cortex-interactive` alone (skipping `cortex-overnight-integration` + the CLI tier) will hit a ModuleNotFoundError if they pick that option.

The plugin-split decision (DR-2) keeps `lifecycle` in `cortex-interactive` to preserve the "interactive-only install" value proposition. That requires the skill to detect runner absence at runtime and hide the autonomous-worktree menu item instead of erroring.

## Scope

- Lifecycle skill's implement-phase menu performs a runtime probe: `cortex --version` on PATH, plus import check for `claude.overnight.daytime_pipeline`
- If probe fails → hide "Implement in autonomous worktree" from the menu (silently; no error)
- If probe succeeds → show all four options as today
- Documentation in `skills/lifecycle/references/implement.md` explaining the degrade behavior
- Minimal: no telemetry, no "you could get this by installing cortex-overnight-integration" nag (the plugin description can explain the upgrade path)

## Out of scope

- Other skills that might have similar runner dependencies (`critical-review`, `morning-review`) — handled in ticket 120's codebase-check step
- Re-probing mid-session (users who install the runner mid-lifecycle are an edge case not worth handling here)

> **2026-04-22 (ticket #097) — scope amendment.** The lifecycle implement-phase menu is now three options (post-#097: "Implement on current branch" / "Implement in autonomous worktree" / "Create feature branch"), not four. The "four execution modes" framing above (line 25) and the "show all four options as today" probe-success branch (line 33) are superseded — the post-probe-success state shows three options. On the degrade path, hiding "Implement in autonomous worktree" now leaves **two** options ("Implement on current branch" / "Create feature branch"), not three. `/refine` must re-evaluate whether the two-option graceful-degrade still meets the UX intent of this ticket.

## Research

See `research/overnight-layer-distribution/research.md` — DR-2 dependency matrix row for autonomous-worktree, Risks Acknowledged ("Autonomous-worktree graceful degrade is a new runtime behavior the lifecycle skill must learn"). Current implementation at `skills/lifecycle/references/implement.md:14` documents the autonomous-worktree option.
