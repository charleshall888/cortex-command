---
schema_version: "1"
uuid: 4b8690e5-7efd-431b-bec5-b45ef64dcc66
title: "Migrate Gate 1 (research→specify Open-Questions escalation) to Python hook; remove Gate 2 entirely"
type: feature
status: backlog
priority: medium
parent: 172
blocked-by: [177]
tags: [lifecycle, hooks, complexity-escalation, token-efficiency, deterministic-execution, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
---

# Migrate Gate 1 (research→specify Open-Questions escalation) to Python hook; remove Gate 2 entirely

Per epic-172-audit Q-A partial reversal (DR-2): re-scoped from "migrate both gates" to **migrate Gate 1 only; remove Gate 2 entirely**. Move the Research → Specify auto-escalation gate from a model-executed protocol step to a deterministic Python hook. Drop the Specify → Plan gate (Gate 2) — empirical evidence shows 0 fires across 153 lifecycles and the source section is 88% "None"; redundant with §2b Pre-Write Checks and orchestrator-review S-checklist.

## Context from discovery + critical-review

Original Hold 1 resolution: keep both gates and migrate both. **Post-decomposition critical-review (DR-2):** events.log scan across 153 lifecycle dirs shows Gate 1: 11 tentative fires (~7% rate); Gate 2: 0 fires. Per CLAUDE.md OQ3 evidence policy applied symmetrically, Gate 2 has no F-row evidence supporting it. Removing Gate 2 unblocks #180 D4 (Open Decisions optional) immediately.

**Methodology caveat (per critical-review):** the events.log payload schema lacks a trigger field on `complexity_override`; Gate 1 vs. Gate 2 vs. manual override are not separately distinguishable from the event payload alone. The 11-vs-0 contrast is produced by timing-pattern heuristics. Gate 1's value-case is N=1 with inferred causation (the cited `gate-overnight-pr-creation-on-merged-over-zero` case has a `spec_revision` labeled "critical-review Q1/Q2 resolution" but no `critical_review` event in events.log). **Migration justification: structural — Gate 1 is the same-session forcing function for overnight contexts where there is no user-decides path; without it, complexity uncovered in research has no auto-escalation mechanism for downstream phases.** Empirical evidence is thin; structural role is the load-bearing argument.

Trade-offs identified:
- **Model tokens at gate-evaluation time**: drop to ~zero (hook runs in Python, not in model context)
- **Determinism**: gate fires consistently regardless of model temperature or surrounding context
- **Infrastructure cost**: adds a new hook to deploy/test/maintain
- **Precedent**: cortex already has hooks for similar deterministic work (`cortex-validate-commit.sh`, lifecycle-scanning hooks)

Audit § *"Tier 3 — Move execution out of the model entirely"*.

## What to land

### 1. `cortex-complexity-escalator` hook (single-gate scope)

A Python script (likely `claude/hooks/cortex-complexity-escalator.py` or `bin/cortex-complexity-escalator`) that:

- Triggers on the research → specify phase-transition event (mechanism TBD — either a hook firing on file-write to `lifecycle/{feature}/events.log` matching `phase_transition` events, or a `PostToolUse` matcher, or invoked explicitly from the protocol step that transitions phases)
- Reads `lifecycle/{feature}/events.log` to detect current tier (skips if already `complex`)
- Reads `lifecycle/{feature}/research.md`, counts `## Open Questions` bullets, escalates if ≥2
- Appends `complexity_override` event to events.log on escalation, with new `gate: "research_open_questions"` field for future event-source attribution (per critical-review methodology caveat)
- Emits announcement text (consumed by the model via the hook's `additionalContext` or stderr output)

**Out of scope:** Gate 2 (specify→plan ≥3 Open Decisions). Removed entirely from cortex; no hook code, no skill prose. See ticket #177 for the gate-prose deletion in `skills/lifecycle/SKILL.md`.

Implementation pattern: follow the existing `claude/hooks/cortex-validate-commit.sh` shape — Python script, atomic write to events.log, structured stdout for the model to surface.

### 2. SKILL.md gate-prose collapse

After the hook is in place and verified:
- Delete the surviving Gate 1 prose from `skills/lifecycle/SKILL.md` (ticket #177's Tier 1 compression already collapsed to one location and removed Gate 2 prose)
- Replace with a one-line note: *"Auto-escalation fires via the `cortex-complexity-escalator` hook on research→specify transitions; see `claude/hooks/`."*

### 3. Hook tests

Add tests for:
- Hook reads events.log correctly and identifies current tier
- Hook counts bullets correctly for research.md `## Open Questions` (≥2 threshold)
- Hook skips silently when tier is already complex
- Hook emits well-formed `complexity_override` event matching the existing schema in `cortex_command/overnight/events.py`, with new `gate: "research_open_questions"` field
- Hook handles missing files / missing sections gracefully (no escalation, no error)
- Hook does NOT fire on specify→plan transitions (Gate 2 removed)

## Risks

- **Hook trigger mechanism**: cortex's existing hooks fire on Claude Code lifecycle events (PreToolUse, PostToolUse, etc.). A hook tied to phase transitions may need a custom trigger pattern. If implementation requires significant Claude Code hook-system extension, scope-down to invoking the hook script explicitly from a one-line protocol step in SKILL.md (still saves the gate-description prose; preserves determinism without needing a new hook trigger pattern).
- **Sandbox / permissions**: the hook writes to `lifecycle/{feature}/events.log`; verify the sandbox allowlist permits this. cortex-init already registers `lifecycle/` in `sandbox.filesystem.allowWrite`.
- **Backwards compatibility**: existing in-flight lifecycle features that have not yet hit the escalation transition will need the hook installed before the next transition. Ensure `cortex init` (or the plugin install) deploys the hook.

## Touch points

- `claude/hooks/cortex-complexity-escalator.py` (NEW; or `bin/cortex-complexity-escalator`)
- `skills/lifecycle/SKILL.md` (gate-prose collapse to one-line pointer)
- `tests/test_complexity_escalator_hook.py` (NEW)
- Hook deployment / settings.json hook registration if needed
- `plugins/cortex-core/hooks/cortex-complexity-escalator.py` (auto-mirrored)

## Verification

- A fresh research → specify transition with `lifecycle/{feature}/research.md` containing ≥2 `## Open Questions` bullets fires the hook, escalates to Complex tier, appends `complexity_override` event with `gate: "research_open_questions"`, and emits the announcement
- A fresh specify → plan transition does NOT fire any complexity-escalation hook regardless of `## Open Decisions` count (Gate 2 removed)
- A research → specify transition where active tier is already `complex` skips the hook silently (no event emitted)
- `wc -l skills/lifecycle/SKILL.md` shows ~310 lines or fewer (down from ~330 post-ticket 177)
- `grep -c "Open Decisions" skills/lifecycle/SKILL.md` returns ≤1 (mention only in optional spec template guidance, not as gate)
- All hook tests pass
- Pre-commit dual-source drift hook passes after `just build-plugin`
