---
schema_version: "1"
uuid: de06774f-c109-4bfb-819d-95d47996c23b
title: "Reference-file hygiene (cross-skill + ceremonial + #179 extractions)"
type: chore
status: open
priority: medium
parent: 187
blocked-by: []
tags: [skills, references, cross-skill-collapse, ceremony, process-gap]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/lifecycle-discovery-token-audit/research.md
---

# Reference-file hygiene (cross-skill + ceremonial + #179 extractions)

## Problem

Three distinct hygiene gaps in `skills/*/references/`:

- **Cross-skill duplication**: `skills/discovery/references/orchestrator-review.md` (133 lines) and `skills/lifecycle/references/orchestrator-review.md` (172-184 lines) contain near-parallel content. Same filename, two skills, no canonical home. Mirrors the duplication pattern epic #172's #174 collapsed for refine.
- **Ceremonial reference content**: small reference files whose contents could be inlined cheaper than maintained as separate files. Specifically:
  - `skills/lifecycle/references/requirements-load.md` — 11 lines, says "load `requirements/project.md` + relevant area docs." Two callsites (`clarify.md:33`, `specify.md:9`). The reference indirection costs more in cross-file traffic than the inline cost would.
  - `skills/refine/references/clarify-critic.md` parent-epic branch table (lines 14-26) — 5 branches for parent-epic loading; 4 of 5 branches just say "omit section." Could collapse to one branch + an outright warning.
- **Process gap from ticket #179**: ticket #179 was marked `status: complete` 2026-05-11, but the deliverables (`skills/critical-review/references/a-b-downgrade-rubric.md` and `skills/lifecycle/references/implement-daytime.md`) do not exist. `skills/critical-review/SKILL.md:229-278` still contains the 8 worked examples inline; `skills/lifecycle/references/implement.md` is 283 lines (target was ~210). Net: ~120 lines of conditional content remain on the hot path that #179 was supposed to extract.

Additionally:
- **Duplicated prompt fragment**: `skills/research/SKILL.md` lines 84-85, 108-109, 128-129, 150-151, 173-174 — same 3-line injection-resistance paragraph appears five times across parallel-agent prompt templates.

## Why it matters

- Cross-skill duplication is the architectural smell epic #172 explicitly worked to eliminate; the orchestrator-review.md pair was missed.
- Reference indirection for trivial content has the worst maintenance-to-value ratio in the corpus.
- The #179 gap is a closure-quality concern (see #194 for the broader investigation). For *this* ticket the question is narrow: land the work the spec called for.
- The injection-resistance duplication is ~1.5k tok per `/cortex-core:research` invocation across 5 sibling agent prompts.

## Constraints

- **Cross-skill canonical choice** must match the #172 precedent: pick the canonical home; the other skill references it. Don't introduce a new pattern.
- **Inline-vs-keep-reference** decision must consider whether the reference file's content might grow (in which case keeping it is right) or is genuinely static.
- **#179 extractions**: the original spec (`backlog/179-...md`) named the exact files to create and the exact line ranges to extract. Honor that scope unless research surfaces a reason to deviate.
- **Mirror sync**: extractions land in canonical `skills/` paths; the pre-commit drift hook auto-regenerates `plugins/cortex-core/skills/` mirrors via `just build-plugin`. Don't hand-edit mirrors.

## Out of scope

- Re-examining whether the conditional content in #179's extractions was correctly identified (the original spec did this work). If research surfaces clear evidence the original choice was wrong, surface as an Open Decision — but defaulting is "land what #179 specified."
- Other suspected cross-skill duplication beyond `orchestrator-review.md`. (Spot-check during research; file separately if found.)
- Compressing `clarify-critic.md` content beyond the 5-branch table.

## Acceptance signal

- One canonical `orchestrator-review.md`; the duplicate skill references it.
- `requirements-load.md` is gone and its callsites have the content inlined (or research-phase justifies keeping it).
- The 5-branch parent-epic table in `clarify-critic.md` is collapsed.
- `skills/critical-review/references/a-b-downgrade-rubric.md` and `skills/lifecycle/references/implement-daytime.md` exist; the corresponding inline content is removed from parent files; `implement.md` line count matches the #179 spec target (~210) or research-phase documents why a different target.
- The injection-resistance paragraph is defined once in `skills/research/SKILL.md` and parameter-substituted into agent prompts.
- Pre-commit drift hook passes; plugin mirrors regenerate cleanly.

## Research hooks

- For `requirements-load.md`: is the inline form genuinely cheaper than the reference, or does the indirection serve a discoverability purpose I'm missing? Sample the callsites and decide.
- For #179: re-validate the original spec's extraction line ranges against current `critical-review/SKILL.md` and `lifecycle/references/implement.md` (both may have shifted since #179 was authored).
- For the injection-resistance hoist: what's the parameter-substitution mechanism? Skill-prompt templates currently support variable interpolation in some places; verify before assuming.
- Are there other small reference files (any of `skills/*/references/` ≤30 lines) worth examining for similar "ceremony over content" patterns?
