---
schema_version: "1"
uuid: 79d84275-ae0a-4ace-8398-ac14fca43497
title: "Promote refine/references/clarify-critic.md to canonical with schema-aware migration"
type: feature
status: complete
priority: high
parent: 172
blocked-by: []
tags: [lifecycle, refine, dual-source, schema-migration, clarify-critic, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: cortex/research/vertical-planning/research.md
complexity: complex
criticality: high
spec: cortex/lifecycle/promote-refine-references-clarify-criticmd-to-canonical-with-schema-aware-migration/spec.md
areas: [skills]
session_id: null
lifecycle_phase: complete
---

# Promote refine/references/clarify-critic.md to canonical with schema-aware migration

Promote refine's clarify-critic.md (215 lines, superset) to canonical and delete lifecycle's copy (167 lines). Distinct from ticket 174's byte-identical collapses because the refine version includes a schema change (`findings` becomes `array of {text, origin}` objects, not strings) and a new REQUIRED `parent_epic_loaded` field.

## Context from discovery

The audit's pressure-test pass verified that refine's clarify-critic.md is **NOT a clean superset** — it interleaves changes via 7+ splice points across the body, changes the `findings` schema from bare strings to `{text, origin}` objects, adds a new REQUIRED `parent_epic_loaded: <bool>` field, and changes the Constraints table row at line 164 to mention `cortex-load-parent-epic`.

Risk: legacy lifecycle-side `clarify_critic` events emitted before this adoption lack `parent_epic_loaded` and use bare-string findings. If any consumer relies on the new schema unconditionally, archived events break.

Audit § *"Pressure-test corrections — Falsified or weakened — `clarify-critic.md` lifecycle ↔ refine — refine is a clean superset → NOT CLEAN."*

## What to land

### Phase 1: Consumer audit (precondition for safe deletion)

Identify every consumer of `clarify_critic` events and verify each handles the legacy bare-string `findings` shape gracefully. Sources to grep:
- `cortex_command/` (Python)
- `skills/` (markdown that reads events)
- `tests/`
- `bin/cortex-*`
- `claude/hooks/`

For each consumer found, verify legacy-tolerant fallback (e.g., reads `finding["text"] if isinstance(finding, dict) else finding`). Document findings in lifecycle/{feature}/research.md or a section of the spec.

### Phase 2: Adoption

Once Phase 1 confirms consumers are legacy-tolerant:
- Delete `skills/lifecycle/references/clarify-critic.md` (canonical)
- Update `skills/lifecycle/references/clarify.md` §3a "Critic Review" to point at `skills/refine/references/clarify-critic.md` instead
- Run `just build-plugin` to prune mirror

If Phase 1 finds non-legacy-tolerant consumers, fix them first before deletion (those fixes may need to be sub-tasks of this ticket or a precursor ticket).

### Phase 3: Schema-version field for replay tolerance (per epic-172-audit C5)

The post-decomposition critical-review (`research/epic-172-audit/research.md` C5) identified a structural test-coverage gap: `tests/test_clarify_critic_alignment_integration.py:388–427` hardcode the event shape via injection (not replay), so legacy archived events from before this adoption can break replay-side consumers without producer-side test-failure detection.

Add as part of acceptance:
- Add a `schema_version: <int>` field to the `clarify_critic` event schema in `cortex_command/overnight/events.py`
- Bump from implicit `v1` (bare-string findings) to `v2` (`{text, origin}` object findings + `parent_epic_loaded`)
- Producer emits `schema_version: 2` going forward; consumers branch on field presence to handle legacy events
- Add a replay test (distinct from existing injection test) that loads an archived `clarify_critic` event from `lifecycle/archive/*/events.log` and verifies downstream consumers process it without error

## Touch points

- `skills/lifecycle/references/clarify-critic.md` (delete after consumer audit)
- `skills/lifecycle/references/clarify.md` (update §3a reference)
- Any non-legacy-tolerant consumers identified in Phase 1
- `plugins/cortex-core/skills/lifecycle/references/clarify-critic.md` (auto-pruned by build-plugin)

## Verification

- Phase 1 consumer audit produces a documented list of `clarify_critic` consumers, each with legacy-tolerance status
- All non-legacy-tolerant consumers are fixed before Phase 2 deletion
- `test ! -f skills/lifecycle/references/clarify-critic.md` after Phase 2
- A fresh lifecycle run with criticality=critical (which triggers clarify-critic) completes without error and emits `clarify_critic` events with the new `{text, origin}` schema + `parent_epic_loaded` field
- Replaying an archived `clarify_critic` event (from before adoption) through downstream consumers produces no errors
- New events emit `schema_version: 2`; consumers handle missing/legacy `schema_version` via fallback branch
- Replay-tolerance test (distinct from injection test) at `tests/test_clarify_critic_alignment_integration.py` covers archived event shape
