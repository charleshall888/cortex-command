---
schema_version: "1"
uuid: 964da654-63d8-45e6-b29e-79a8598a1b2c
title: "Trim verbose lifecycle skill content (implement.md §1a + plan.md §1b.b + SKILL.md gate compression)"
type: chore
status: in_progress
priority: high
parent: 172
blocked-by: []
tags: [lifecycle, content-trim, token-efficiency, gate-compression, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
complexity: complex
criticality: high
spec: lifecycle/trim-verbose-lifecycle-skill-content-implementmd-1a-planmd-1bb-skillmd-gate-compression/spec.md
areas: [skills]
session_id: d5a1f1a3-ebfe-4fe8-a0d1-de09e171b202
lifecycle_phase: plan
---

# Trim verbose lifecycle skill content (implement.md §1a + plan.md §1b.b + SKILL.md gate compression)

Three independent in-skill content trims bundled because each touches a single skill file, has similar low-medium risk profile, and ships in one PR worth of work.

## Context from discovery

Audit + pressure-test pass identified three in-file content trims with concrete savings:

### 1. `implement.md §1a` Daytime Dispatch (~15 lines, preserve contract prose)

Original audit claimed §1a could collapse from 118 to 25 lines. Pressure-test corrected to ~30–40 lines. **Post-decomposition critical-review correction (C4):** the audit's ~30–40 line target itself overstates the cut — lines 82–101 (atomic-write recipe) document the skill↔module contract (dispatch_id semantics, recovery-after-compaction behavior); lines 156–164 (outcome map) document a schema contract Python can't enforce. `tests/test_daytime_preflight.py:326,379` pin this contract.

**Realistic cut: ~15 lines** — only the inline Python one-liner can be replaced with a "see module for canonical recipe" pointer. **Preserve**: dispatch_id semantics rationale, outcome map (schema contract), uncommitted-changes guard, runtime probe, double-dispatch guard, overnight-concurrent guard, polling-loop user-pause behavior, `dispatch_complete` log-writing.

### 2. `plan.md §1b` Competing Plans dedup + HOW-prose trim (~100 lines total)

Original audit claimed 60 lines via §1b.b ↔ §3 dedup; pressure-test corrected to ~20 lines. **Post-decomposition critical-review (DR-5 / U3):** push significantly beyond simple dedup. §1b is ~122 lines of HOW-orchestration prose (envelope schemas, last-occurrence anchor pattern, swap-and-require-agreement, eight worked downgrade examples) that mostly duplicates content in `cortex_command/overnight/prompts/plan-synthesizer.md`.

**Realistic cut: ~100 lines** — ~20 from §1b.b ↔ §3 dedup + ~80 from collapsing §1b's envelope-schema prose to a pointer at `cortex_command/overnight/prompts/plan-synthesizer.md`. The WHAT (for critical tier, run multiple plans + pick best) and WHY (single Opus plan can be wrong) are ~5 lines; the rest is HOW that capable models can derive from the synthesizer prompt.

**Preserve**: critical-tier-specific Architectural Pattern directive, swap-and-require-agreement WHAT (the gate, not the verbatim regex), §3 Veto Surface and Scope Boundaries.

### 3. `lifecycle/SKILL.md` complexity-escalation gate descriptions — single-gate version (~50 lines via Tier 1 compression + Gate 2 removal)

The two complexity-escalation gates (Research → Specify and Specify → Plan) are described **twice** in SKILL.md — once at the inline protocol step (lines 244–260, ~17 lines) AND again in a standalone "Complexity Override" section (lines 294–312, ~19 lines). Same logic, two places. Plus 3 inlined `complexity_override` JSON event examples.

**Per epic-172-audit Q-A partial reversal: Gate 2 is being removed entirely.** Only Gate 1 (Research → Specify, ≥2 Open Questions) survives.

Tier 1 compression with Gate 2 removal:
- Delete Gate 2 prose entirely (the Specify→Plan ≥3 Open Decisions check)
- Deduplicate the surviving Gate 1 description (delete the standalone "Complexity Override" section, keep the inline protocol-flow version)
- Collapse Gate 1 prose to ~3-line: *"Auto-escalate `simple` → `complex` if research.md has ≥2 `## Open Questions` bullets at end of research phase. Skip if already complex. Append `complexity_override` event (schema in `cortex_command/overnight/events.py`), announce briefly, proceed at complex tier."*
- Replace the 3 inlined `complexity_override` JSON examples with a single canonical schema pointer

**Realistic cut: ~50 lines** off SKILL.md, single-gate behavior preserved, Gate 2 behavior removed (per epic-172-audit DR-2).

## Touch points

- `skills/lifecycle/references/implement.md` (§1a)
- `skills/lifecycle/references/plan.md` (§1b.b)
- `skills/lifecycle/SKILL.md` (complexity-escalation gate descriptions, lines 244–260 + 294–312)
- `plugins/cortex-core/skills/lifecycle/references/implement.md` (auto-regenerated)
- `plugins/cortex-core/skills/lifecycle/references/plan.md` (auto-regenerated)
- `plugins/cortex-core/skills/lifecycle/SKILL.md` (auto-regenerated)

## Verification

- `wc -l skills/lifecycle/references/implement.md` shows ~286 lines (down from 301), inline Python recipe removed, contract prose still present
- `wc -l skills/lifecycle/references/plan.md` shows ~210 lines (down from 309) — §1b orchestration prose collapsed to synthesizer-prompt pointer
- `wc -l skills/lifecycle/SKILL.md` shows ~330 lines (down from 380) — Gate 2 removed, Gate 1 deduplicated
- `grep -c "complexity_override" skills/lifecycle/SKILL.md` returns 1–2 (down from ~5 inlined examples)
- `grep -c "Specify.*Plan.*Open Decisions" skills/lifecycle/SKILL.md` returns 0 (Gate 2 removed)
- A fresh implement-phase run via daytime dispatch still hits the uncommitted-changes guard, runtime probe, double-dispatch guard
- A fresh critical-tier plan-phase run still emits a plan with `Architectural Pattern` set to a value in the closed enum (and §1b synthesizer behavior preserved via `cortex_command/overnight/prompts/plan-synthesizer.md`)
- A fresh research→specify transition with ≥2 Open Questions still auto-escalates to Complex tier and emits `complexity_override` (Gate 1 surviving)
- A fresh specify→plan transition with ≥3 Open Decisions does NOT auto-escalate (Gate 2 removed; orchestrator-review S-checklist evaluates spec quality in main context)
- Pre-commit dual-source drift hook passes after `just build-plugin`
