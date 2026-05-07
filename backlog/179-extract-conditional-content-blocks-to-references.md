---
schema_version: "1"
uuid: cc130eb5-8439-4012-a52e-1b7c39ee08e8
title: "Extract conditional content blocks to references/ (a-b-downgrade-rubric + implement-daytime — trimmed scope)"
type: chore
status: backlog
priority: medium
parent: 172
blocked-by: []
tags: [lifecycle, refine, critical-review, conditional-extraction, hot-path-context, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
---

# Extract conditional content blocks to references/ (trimmed scope)

Move TWO conditional content blocks from SKILL.md and reference files into dedicated `references/*.md` files with explicit trigger prose. Reduces hot-path context by ~100 lines per invocation. **Lands AFTER** Stream A (174–176) and Stream B (177) so the canonical structure is settled before extraction.

**Trimmed scope per epic-172-audit C7.** Original ticket scoped 6 extractions for ~300-line hot-path reduction. Post-decomposition critical-review noted: cortex has no runtime gate for "first invocation" / "critical-tier only" — relies on Claude reading parent-skill prose; 12 mirror entries; pre-commit drift hook fires on each; state-init.md split lacks correctness test; Opus 4.7 literalism risk on trigger prose. Halved to the 2 cleanest extractions for ~1/3 the maintenance burden.

## Context from discovery

The skill-creator-lens audit identified that several conditional content blocks are loaded into model context on every invocation but only execute on specific paths (first invocation per feature, critical-tier only, daytime-dispatch only, etc.). Extracting these to dedicated reference files reduces hot-path context burn.

After multiple correction passes (initial pressure-test + post-decomposition critical-review), realistic net savings shrinks to **~100 lines off hot-path context** at lower maintenance cost.

Audit § *"Critical-Review correction: extraction requires explicit trigger prose in parent SKILL.md"* — cortex's progressive-disclosure model has no runtime mechanism to gate reference loading on conditions like "first invocation per feature" or "critical-tier only." Each extracted file's parent SKILL.md must add explicit "if X, read references/Y.md" prose, OR the extracted file is loaded every time anyway (no savings) OR skipped when needed (correctness regression).

## What to extract (trimmed scope)

| Source | Lines | Target | Trigger condition (parent must specify) | Why kept (vs deferred) |
|---|---|---|---|---|
| `lifecycle/references/implement.md §1a` Daytime Dispatch (after Stream B trim) | ~70 | `references/implement-daytime.md` | "if user picks daytime-dispatch path, read references/implement-daytime.md" | User-gated condition is unambiguous; trigger prose is reliable |
| `critical-review/SKILL.md` 8 worked examples (212–260) | ~49 | `critical-review/references/a-b-downgrade-rubric.md` | "during A→B downgrade rubric application, read references/a-b-downgrade-rubric.md" | Single clean conditional fired only during specific synthesis subtask |

## Deferred extractions (per C7)

The following four extractions are explicitly deferred from this ticket. Open separate backlog tickets if the maintenance cost / context savings tradeoff shifts:

- `lifecycle/SKILL.md` Step 2 first-invocation logic — `state-init.md` split. Deferred: trickiest split (re-entrant vs first-invocation logic intertwined); split-correctness has no test design.
- `lifecycle/SKILL.md` Parallel Execution + Worktree Inspection — `parallel-execution.md`. Deferred: concurrent-lifecycle gate prose unreliable under Opus 4.7 literalism.
- `lifecycle/references/plan.md §1b` Competing Plans — `plan-competing.md`. Deferred: ticket #177 now collapses §1b to a synthesizer-prompt pointer (~80 lines off in-place); extraction becomes redundant.
- `lifecycle/references/research.md §1a` Parallel Research — `research-parallel.md`. Deferred: critical-tier gate prose unreliable under Opus 4.7 literalism.

## Risks

- **Trigger-prose drift**: if the trigger condition in parent SKILL.md becomes inaccurate over time, model loads or skips incorrectly. Mitigation: include trigger condition as part of the extracted file header so the model can self-verify it's the right context.
- **Parity-test creation cost**: 6 new dual-sourced files = 12 mirror entries, 6 new pre-commit drift checks, 6 new edit-coordination cases. Risk re-rated from "Low-medium" to **Medium** in audit corrections.
- **State-init bundling caveat**: the `state-init.md` extraction is the trickiest — only first-invocation logic moves; re-entrant logic stays. Verify the split is correct before deletion from SKILL.md.

## Touch points

- `skills/lifecycle/references/implement.md` (§1a → references/implement-daytime.md)
- `skills/lifecycle/references/implement-daytime.md` (NEW)
- `skills/critical-review/SKILL.md` (extract worked examples)
- `skills/critical-review/references/a-b-downgrade-rubric.md` (NEW)
- All `plugins/cortex-core/skills/*` mirrors auto-regenerated

## Verification

- `skills/lifecycle/references/implement.md` ~210 lines (down from ~286 post-#177)
- `skills/critical-review/SKILL.md` ~315 lines (down from 365)
- Both new reference files have a header noting the trigger condition that gated their extraction
- Parent SKILL.md / reference file has explicit trigger prose pointing at each new reference
- `pytest tests/test_dual_source_reference_parity.py` passes (collected pairs increase by 2)
- Pre-commit dual-source drift hook passes after `just build-plugin`
- A fresh daytime-dispatch implement-phase run correctly loads references/implement-daytime.md (verify in transcript)
- A fresh overnight implement-phase run does NOT load references/implement-daytime.md
