---
schema_version: "1"
uuid: 4b8690e5-7efd-431b-bec5-b45ef64dcc66
title: "Migrate complexity-escalation gates to deterministic Python hook (cortex-complexity-escalator)"
type: feature
status: backlog
priority: medium
parent: 172
blocked-by: [174, 177]
tags: [lifecycle, hooks, complexity-escalation, token-efficiency, deterministic-execution, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
---

# Migrate complexity-escalation gates to deterministic Python hook (`cortex-complexity-escalator`)

Move the Research → Specify and Specify → Plan auto-escalation gates from model-executed protocol steps to a deterministic Python hook. Removes the gate logic from SKILL.md context entirely (additional ~25 lines saved beyond ticket 177's Tier 1 compression), and converts gate execution from model-judgment to deterministic file inspection.

## Context from discovery

Per Hold 1 resolution: both complexity-escalation gates are kept (user said "I like these gates still"). The audit's Tier 3 gate-compression option proposed migrating the gates from a model-executed protocol step to a deterministic hook.

Trade-offs identified:
- **Model tokens at gate-evaluation time**: drop to ~zero (hook runs in Python, not in model context)
- **Determinism**: gate fires consistently regardless of model temperature or surrounding context
- **Infrastructure cost**: adds a new hook to deploy/test/maintain
- **Precedent**: cortex already has hooks for similar deterministic work (`cortex-validate-commit.sh`, lifecycle-scanning hooks)

Audit § *"Tier 3 — Move execution out of the model entirely"*.

## What to land

### 1. `cortex-complexity-escalator` hook

A Python script (likely `claude/hooks/cortex-complexity-escalator.py` or `bin/cortex-complexity-escalator`) that:

- Triggers on phase-transition events (mechanism TBD — either a hook firing on file-write to `lifecycle/{feature}/events.log` matching `phase_transition` events, or a `PostToolUse` matcher, or invoked explicitly from the protocol step that transitions phases)
- Reads `lifecycle/{feature}/events.log` to detect current tier (skips if already `complex`)
- For research → specify transitions: reads `lifecycle/{feature}/research.md`, counts `## Open Questions` bullets, escalates if ≥2
- For specify → plan transitions: reads `lifecycle/{feature}/spec.md`, counts `## Open Decisions` bullets, escalates if ≥3
- Appends `complexity_override` event to events.log on escalation
- Emits announcement text (consumed by the model via the hook's `additionalContext` or stderr output)

Implementation pattern: follow the existing `claude/hooks/cortex-validate-commit.sh` shape — Python script, atomic write to events.log, structured stdout for the model to surface.

### 2. SKILL.md gate-prose collapse

After the hook is in place and verified:
- Delete the gate-description prose from `skills/lifecycle/SKILL.md` (the inline protocol step at lines 244–260 + any residual mention; ticket 177's Tier 1 compression already deduplicated to one location)
- Replace with a one-line note: *"Auto-escalation fires via the `cortex-complexity-escalator` hook on research→specify and specify→plan transitions; see `claude/hooks/`."*

### 3. Hook tests

Add tests for:
- Hook reads events.log correctly and identifies current tier
- Hook counts bullets correctly for both research.md (Open Questions, ≥2 threshold) and spec.md (Open Decisions, ≥3 threshold)
- Hook skips silently when tier is already complex
- Hook emits well-formed `complexity_override` event matching the existing schema in `cortex_command/overnight/events.py`
- Hook handles missing files / missing sections gracefully (no escalation, no error)

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

- A fresh research → specify transition with `lifecycle/{feature}/research.md` containing ≥2 `## Open Questions` bullets fires the hook, escalates to Complex tier, appends `complexity_override` event, and emits the announcement
- A fresh specify → plan transition with `lifecycle/{feature}/spec.md` containing ≥3 `## Open Decisions` bullets fires the hook, escalates, logs event, announces
- Both transitions in a context where the active tier is already `complex` skip the hook silently (no event emitted)
- `wc -l skills/lifecycle/SKILL.md` shows ~315 lines or fewer (down from ~340 post-ticket 177)
- All hook tests pass
- Pre-commit dual-source drift hook passes after `just build-plugin`
