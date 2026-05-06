---
schema_version: "1"
uuid: 4a8a0d7b-3ccb-4576-9f81-387f68cf4e20
title: "Vertical-planning adoption: ## Outline in plan.md + ## Phases in spec.md + P9/S7 gates + parser regression test"
type: feature
status: backlog
priority: high
parent: 172
blocked-by: [174, 175, 176]
tags: [lifecycle, plan-template, spec-template, vertical-planning, orchestrator-review, parser]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
---

# Vertical-planning adoption: `## Outline` in plan.md + `## Phases` in spec.md + P9/S7 gates + parser regression test

The original goal of the discovery — adopt the structure-outline / vertical-slice patterns from Dexter Horthy's CRISPY/QRSPI framework into cortex's lifecycle artifact templates. **Lands AFTER cross-skill collapse (174–176)** so the new sections live in one canonical home rather than getting added to duplicated copies.

## Context from discovery

`research/vertical-planning/research.md` documents the CRISPY framework, the comparison with cortex's current plan/spec templates, and the design alternatives. Key recommendations:

- **Differentiated outline shapes for spec vs plan** (DR-4): spec gets "Phases at a Glance" (vertical-slice grouping + per-requirement phase tags); plan gets "Phase Outline" (phases + checkpoints + task IDs per phase).
- **Mermaid optional, text-outline required** (DR-3): allow Mermaid where it adds value but don't require it. The optional `cortex plan-outline` topological renderer is deferred to future work, not in this ticket.
- **All tiers** per Hold 1 resolution: outlines apply to every plan/spec regardless of tier. Gates fire wherever orchestrator-review runs (i.e., not on `low+simple` per the existing skip rule).
- **Provenance disclosure** (DR-6): explicitly mark the outline pattern as community-derived (CRISPY/QRSPI v2) rather than primary-source verified, since the YouTube transcript wasn't retrieved and Horthy's actual production prompts don't contain "structure outline."

Empirical caveat to honor in the implementation: the rigor claim ("outline-first forces better agent reasoning") is practitioner-grade evidence quality (1/5), not peer-reviewed. The human-skim claim is well-supported. Don't quote the unverified "more reliable than any prompt instruction" superlative as fact in cortex docs.

## What to land

### 1. `## Outline` section in plan.md template

Add to `skills/lifecycle/references/plan.md §3` canonical template:

```markdown
## Outline

[Vertical-slice phase grouping. Each phase is a thin end-to-end thread that produces a testable checkpoint. Phases sequence so that early phases produce a working-but-mocked end-to-end thread that later phases progressively replace with real implementations.]

### Phase 1: <name> (tasks: 1, 2, 3)
- **Goal**: <1-line outcome>
- **Checkpoint**: <observable state when phase complete>

### Phase 2: <name> (tasks: 4, 5, 6)
...
```

Include a brief provenance note: *"This outline format is community-derived from CRISPY/QRSPI (HumanLayer); the exact field shape is cortex's adaptation. The empirical case for vertical-slice planning is practitioner-grade — adopt because it helps human review and forces explicit phase thinking, not because the research literature mandates it."*

### 2. `## Phases` section + per-requirement phase tags in spec.md template

Add to `skills/lifecycle/references/specify.md §3` canonical template:

```markdown
## Phases

- **Phase 1: <name>** — <one-line goal>
- **Phase 2: <name>** — <one-line goal>
...

## Requirements

1. [Requirement] — **Phase**: <name>. [Acceptance criteria — binary-checkable per existing format]
2. [Requirement] — **Phase**: <name>. [Acceptance criteria]
...
```

### 3. P9 (plan outline) + S7 (spec phases) orchestrator-review gates

Add to `skills/lifecycle/references/orchestrator-review.md`:

- **P9**: Plan contains `## Outline` section with at least 2 phases; each phase names tasks; each phase has a checkpoint.
- **S7**: Spec contains `## Phases` section with at least 2 phases; each requirement has a `**Phase**` tag matching one of the declared phases.

Both gates fire wherever orchestrator-review runs (i.e., not on `low+simple` per existing skip rule).

### 4. Plan parser regression test

The existing parser at `cortex_command/pipeline/parser.py:282-329` was verified by the audit's pressure-test pass to be soft-OK on top-of-doc `## Outline` sections (parser is task-heading-anchored, doesn't terminate on the new section). Add a regression test that confirms:

- A plan with `## Outline` section above `## Tasks` parses successfully — all tasks discovered, all fields extracted
- The `Overview` extractor still finds the right section (not `Outline`)
- A plan with `## Phase N:` headings nested INSIDE `## Tasks` still hard-breaks (this is the documented limitation; the test locks in current behavior so a future "support nested phase headings" change is intentional)

## Touch points

- `skills/lifecycle/references/plan.md` (template + provenance note)
- `skills/lifecycle/references/specify.md` (template)
- `skills/refine/references/specify.md` — note: ticket 174 deleted this; if 174 lands first, edit only the lifecycle copy
- `skills/lifecycle/references/orchestrator-review.md` (P9, S7)
- `cortex_command/pipeline/tests/test_parser.py` (or new test file)
- All `plugins/cortex-core/skills/*` mirrors auto-regenerated

## Verification

- A fresh plan-phase run produces a plan.md with `## Outline` section containing ≥2 phases, each with checkpoint
- A fresh specify-phase run produces a spec.md with `## Phases` section + per-requirement `**Phase**` tags
- Orchestrator-review P9 fires (flag) on a plan that omits the Outline section in a context where review runs
- Orchestrator-review S7 fires (flag) on a spec that omits Phases in a context where review runs
- Existing legacy plans (without Outline) continue to parse correctly via the parser regression test
- A plan with phase headings nested inside `## Tasks` still hard-breaks (regression test documents the limitation)
- Provenance note is present and accurate; doesn't quote unverified Horthy claims as fact
