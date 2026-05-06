---
schema_version: "1"
uuid: cc130eb5-8439-4012-a52e-1b7c39ee08e8
title: "Extract conditional content blocks to references/ (state-init split, plan-competing, research-parallel, implement-daytime, a-b-downgrade-rubric, parallel-execution)"
type: chore
status: backlog
priority: medium
parent: 172
blocked-by: [174, 175, 176, 177]
tags: [lifecycle, refine, critical-review, conditional-extraction, hot-path-context, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
---

# Extract conditional content blocks to references/

Move six conditional content blocks (loaded on every invocation but only relevant in specific contexts) from SKILL.md and reference files into dedicated `references/*.md` files with explicit trigger prose. Reduces hot-path context by ~300 lines per invocation. **Lands AFTER** Stream A (174–176) and Stream B (177) so the canonical structure is settled before extraction.

## Context from discovery

The skill-creator-lens audit identified that several conditional content blocks are loaded into model context on every invocation but only execute on specific paths (first invocation per feature, critical-tier only, daytime-dispatch only, etc.). Extracting these to dedicated reference files reduces hot-path context burn.

The pressure-test pass corrected several aspects of the extraction:
- Original `~440 lines reducible` figure was unsourced arithmetic
- `state-init.md` cannot be a single file — must split because Backlog Write-Back fires every phase transition AND Open Decisions bullet-count is re-read for the Specify→Plan escalation gate (re-entrant, not first-invocation-only)
- After Stream B trims `implement.md §1a` from ~115 to ~75 lines, the extraction target shrinks proportionally
- The "worked examples" extraction conflicts with the prior audit's per-file cut #3 — pick extraction (this ticket), drop the in-place cut

Realistic net savings after corrections: **~300 lines off hot-path context** (revised down from 440).

Audit § *"Critical-Review correction: extraction requires explicit trigger prose in parent SKILL.md"* — cortex's progressive-disclosure model has no runtime mechanism to gate reference loading on conditions like "first invocation per feature" or "critical-tier only." Each extracted file's parent SKILL.md must add explicit "if X, read references/Y.md" prose, OR the extracted file is loaded every time anyway (no savings) OR skipped when needed (correctness regression).

## What to extract

| Source | Lines | Target | Trigger condition (parent must specify) |
|---|---|---|---|
| `lifecycle/SKILL.md` Step 2 first-invocation logic only (Discovery Bootstrap, initial Create index.md) | ~70 | `references/state-init.md` | "if no prior `phase_transition` event in events.log, read references/state-init.md" |
| `lifecycle/SKILL.md` Step 2 re-entrant logic (Backlog Write-Back, Open Decisions bullet-count re-read) | — | **STAYS in SKILL.md** | re-entrant, fires every phase transition |
| `lifecycle/SKILL.md` Parallel Execution + Worktree Inspection (lines 350–380) | ~30 | `references/parallel-execution.md` | "if running concurrent lifecycles, read references/parallel-execution.md" |
| `lifecycle/references/plan.md §1b` Competing Plans (22–144) | ~122 | `references/plan-competing.md` | "if criticality is `critical`, read references/plan-competing.md" |
| `lifecycle/references/research.md §1a` Parallel Research (45–140) | ~95 | `references/research-parallel.md` | "if criticality is `critical`, read references/research-parallel.md" |
| `lifecycle/references/implement.md §1a` Daytime Dispatch (after Stream B trim, ~75 lines) | ~75 | `references/implement-daytime.md` | "if user picks daytime-dispatch path, read references/implement-daytime.md" |
| `critical-review/SKILL.md` 8 worked examples (212–260) | ~49 | `critical-review/references/a-b-downgrade-rubric.md` | "during A→B downgrade rubric application, read references/a-b-downgrade-rubric.md" |

## Risks

- **Trigger-prose drift**: if the trigger condition in parent SKILL.md becomes inaccurate over time, model loads or skips incorrectly. Mitigation: include trigger condition as part of the extracted file header so the model can self-verify it's the right context.
- **Parity-test creation cost**: 6 new dual-sourced files = 12 mirror entries, 6 new pre-commit drift checks, 6 new edit-coordination cases. Risk re-rated from "Low-medium" to **Medium** in audit corrections.
- **State-init bundling caveat**: the `state-init.md` extraction is the trickiest — only first-invocation logic moves; re-entrant logic stays. Verify the split is correct before deletion from SKILL.md.

## Touch points

- `skills/lifecycle/SKILL.md` (extract first-invocation + parallel-execution; keep re-entrant)
- `skills/lifecycle/references/plan.md` (§1b → references/plan-competing.md)
- `skills/lifecycle/references/research.md` (§1a → references/research-parallel.md)
- `skills/lifecycle/references/implement.md` (§1a → references/implement-daytime.md)
- `skills/lifecycle/references/state-init.md` (NEW)
- `skills/lifecycle/references/parallel-execution.md` (NEW)
- `skills/lifecycle/references/plan-competing.md` (NEW)
- `skills/lifecycle/references/research-parallel.md` (NEW)
- `skills/lifecycle/references/implement-daytime.md` (NEW)
- `skills/critical-review/SKILL.md` (extract worked examples)
- `skills/critical-review/references/a-b-downgrade-rubric.md` (NEW)
- All `plugins/cortex-core/skills/*` mirrors auto-regenerated

## Verification

- Net SKILL.md sizes after extraction: lifecycle 380→~280, critical-review 365→~250, plan.md 309→~190, research.md 204→~110, implement.md ~225 (post Stream B trim)
- All new reference files have a header noting the trigger condition that gated their extraction
- Parent SKILL.md / reference file has explicit trigger prose pointing at each new reference
- `pytest tests/test_dual_source_reference_parity.py` passes (collected pairs increase by 6)
- Pre-commit dual-source drift hook passes after `just build-plugin`
- A fresh critical-tier lifecycle run with parallel research path correctly loads references/research-parallel.md (verify in transcript)
- A fresh simple-tier lifecycle run does NOT load references/plan-competing.md or references/research-parallel.md
