---
schema_version: "1"
uuid: 964da654-63d8-45e6-b29e-79a8598a1b2c
title: "Trim verbose lifecycle skill content (implement.md §1a + plan.md §1b.b + SKILL.md gate compression)"
type: chore
status: backlog
priority: high
parent: 172
blocked-by: []
tags: [lifecycle, content-trim, token-efficiency, gate-compression, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
---

# Trim verbose lifecycle skill content (implement.md §1a + plan.md §1b.b + SKILL.md gate compression)

Three independent in-skill content trims bundled because each touches a single skill file, has similar low-medium risk profile, and ships in one PR worth of work.

## Context from discovery

Audit + pressure-test pass identified three in-file content trims with concrete savings:

### 1. `implement.md §1a` Daytime Dispatch (~30–40 lines, preserve guards)

Original audit claimed §1a could collapse from 118 to 25 lines by replacing with a pointer to `cortex_command/overnight/daytime_pipeline.py`. Pressure-test corrected this — §1a contains genuine skill-side logic the pipeline module does NOT implement: uncommitted-changes guard with demote-and-warn logic, runtime probe with explicit fail-open (lines 19–38), double-dispatch guard via PID liveness, overnight-concurrent guard, polling loop with user-pause-at-30-iterations, `dispatch_complete` event log writing.

**Realistic cut: ~30–40 lines** — the atomic-write recipe at lines 82–101 + verbatim outcome map at lines 156–164 — these duplicate what `cortex_command/overnight/daytime_pipeline.py` and `cortex_command/overnight/daytime_result_reader.py` already implement and can be replaced with a one-line "see module for canonical recipe."

**Preserve**: uncommitted-changes guard, runtime probe, double-dispatch guard, overnight-concurrent guard, polling-loop user-pause behavior, `dispatch_complete` log-writing.

### 2. `plan.md §1b.b` Plan Format dedup with §3 (~20 lines)

Original audit claimed 60 lines via dedup. Pressure-test corrected to ~20 lines. §1b.b is the critical-tier dual-plan format — it includes `**Architectural Pattern**: {category} — {1-sentence differentiation}` (line 75) and the closed-enum directive (line 47) that §3 doesn't have. §3 is the standard format with Veto Surface and Scope Boundaries that §1b.b doesn't have.

**Realistic cut: ~20 lines of overlap** — common task-template structure that can be replaced with a "produce a plan in the §3 format with the additions noted above" pointer.

**Preserve**: the critical-tier-specific Architectural Pattern directive in §1b.b.

### 3. `lifecycle/SKILL.md` complexity-escalation gate descriptions (~40 lines via Tier 1 compression)

The two complexity-escalation gates (Research → Specify and Specify → Plan) are described **twice** in SKILL.md — once at the inline protocol step (lines 244–260, ~17 lines) AND again in a standalone "Complexity Override" section (lines 294–312, ~19 lines). Same logic, two places. Plus 3 inlined `complexity_override` JSON event examples.

Tier 1 compression:
- Deduplicate the gate description (delete the standalone "Complexity Override" section's redundant prose, keep the inline protocol-flow version)
- Collapse the two-gate prose into one unified ~5-line paragraph: *"Auto-escalate `simple` → `complex` if: (a) research.md has ≥2 `## Open Questions` bullets, OR (b) spec.md has ≥3 `## Open Decisions` bullets. Skip if already complex. Append `complexity_override` event (schema in `cortex_command/overnight/events.py`), announce briefly, proceed at complex tier."*
- Replace the 3 inlined `complexity_override` JSON examples with a single canonical schema pointer

**Realistic cut: ~40 lines** off SKILL.md, zero behavior change.

## Touch points

- `skills/lifecycle/references/implement.md` (§1a)
- `skills/lifecycle/references/plan.md` (§1b.b)
- `skills/lifecycle/SKILL.md` (complexity-escalation gate descriptions, lines 244–260 + 294–312)
- `plugins/cortex-core/skills/lifecycle/references/implement.md` (auto-regenerated)
- `plugins/cortex-core/skills/lifecycle/references/plan.md` (auto-regenerated)
- `plugins/cortex-core/skills/lifecycle/SKILL.md` (auto-regenerated)

## Verification

- `wc -l skills/lifecycle/references/implement.md` shows ~260 lines (down from 301), atomic-write recipe + verbatim outcome map removed, guards still present
- `wc -l skills/lifecycle/references/plan.md` shows ~290 lines (down from 309)
- `wc -l skills/lifecycle/SKILL.md` shows ~340 lines (down from 380)
- `grep -c "complexity_override" skills/lifecycle/SKILL.md` returns 1–2 (down from ~5 inlined examples)
- A fresh implement-phase run via daytime dispatch still hits the uncommitted-changes guard, runtime probe, double-dispatch guard
- A fresh critical-tier plan-phase run still emits a plan with `Architectural Pattern` set to a value in the closed enum
- A fresh research→specify transition with ≥2 Open Questions still auto-escalates to Complex tier and emits `complexity_override`
- A fresh specify→plan transition with ≥3 Open Decisions still auto-escalates to Complex tier and emits `complexity_override`
- Pre-commit dual-source drift hook passes after `just build-plugin`
