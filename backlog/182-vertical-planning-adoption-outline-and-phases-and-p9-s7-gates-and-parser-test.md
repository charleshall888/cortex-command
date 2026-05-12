---
schema_version: "1"
uuid: 4a8a0d7b-3ccb-4576-9f81-387f68cf4e20
title: "Vertical-planning adoption as REPLACEMENT: ## Outline absorbs Scope Boundaries + Verification Strategy; ## Risks preserves Veto Surface; tier-conditional ## Acceptance"
type: feature
status: complete
priority: high
parent: 172
blocked-by: []
tags: [lifecycle, plan-template, spec-template, vertical-planning, orchestrator-review, parser, metrics-parser]
created: 2026-05-06
updated: 2026-05-11
discovery_source: cortex/research/vertical-planning/research.md
complexity: complex
criticality: high
spec: cortex/lifecycle/vertical-planning-adoption-as-replacement-outline-absorbs-scope-boundaries-verification-strategy-risks-preserves-veto-surface-tier-conditional-acceptance/spec.md
areas: [lifecycle]
session_id: null
lifecycle_phase: plan
---

# Vertical-planning adoption as REPLACEMENT (per epic-172-audit DR-1)

The original goal of the discovery — adopt the structure-outline / vertical-slice patterns from Dexter Horthy's CRISPY/QRSPI framework into cortex's lifecycle artifact templates. **Per epic-172-audit DR-1: re-framed as REPLACEMENT, not addition.** The `## Outline` section absorbs `## Scope Boundaries` + `## Verification Strategy` in plan.md (Candidate A); a new `## Risks` section preserves the Veto Surface affordance (per Q-C critical-review fix); a tier-conditional `## Acceptance` section preserves whole-feature acceptance contract for complex-tier features (per Q-C Verification critical-review fix).

**Lands AFTER cross-skill collapse (174–176)** so the new sections live in one canonical home rather than getting added to duplicated copies.

## Context from discovery

`research/vertical-planning/research.md` documents the CRISPY framework, the comparison with cortex's current plan/spec templates, and the design alternatives. Key recommendations:

- **Differentiated outline shapes for spec vs plan** (DR-4): spec gets "Phases at a Glance" (vertical-slice grouping + per-requirement phase tags); plan gets "Phase Outline" (phases + checkpoints + task IDs per phase).
- **Mermaid optional, text-outline required** (DR-3): allow Mermaid where it adds value but don't require it. The optional `cortex plan-outline` topological renderer is deferred to future work, not in this ticket.
- **All tiers** per Hold 1 resolution: outlines apply to every plan/spec regardless of tier. Gates fire wherever orchestrator-review runs (i.e., not on `low+simple` per the existing skip rule).
- **Provenance disclosure** (DR-6): explicitly mark the outline pattern as community-derived (CRISPY/QRSPI v2) rather than primary-source verified, since the YouTube transcript wasn't retrieved and Horthy's actual production prompts don't contain "structure outline."

Empirical caveat to honor in the implementation: the rigor claim ("outline-first forces better agent reasoning") is practitioner-grade evidence quality (1/5), not peer-reviewed. The human-skim claim is well-supported. Don't quote the unverified "more reliable than any prompt instruction" superlative as fact in cortex docs.

## What to land

### 1. `## Outline` section in plan.md template — REPLACES Scope Boundaries + Verification Strategy

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

**Replacement scope (per Candidate A):**
- **DELETE `## Scope Boundaries` from plan.md template entirely.** Scope decisions live in spec.md `## Non-Requirements` (canonical enumerative-excludes source); plan.md's mirror has no programmatic consumer. Per epic-172-audit C1 critical-review fix: this is mirror deletion, not signal deletion — the named-excludes survive in spec.md.
- **DELETE `## Verification Strategy` from plan.md template** for simple/medium/high tier. Last-phase `Checkpoint` becomes the user-runnable end-to-end command for these tiers (one-line update at `cortex_command/overnight/report.py:725` to read last-phase Checkpoint instead of Verification Strategy).
- **Add tier-conditional `## Acceptance` top-level section for complex-tier only** (~3 lines per complex-tier plan). Captures whole-feature acceptance criterion explicitly when the per-phase Checkpoint chain isn't sufficient. Per Q-C critical-review fix: whole-feature acceptance ≠ per-phase Checkpoint semantically; complex features need the explicit contract.

Include a brief provenance note: *"This outline format is community-derived from CRISPY/QRSPI (HumanLayer); the exact field shape is cortex's adaptation. The empirical case for vertical-slice planning is practitioner-grade — adopt because it helps human review and forces explicit phase thinking, not because the research literature mandates it."*

### 1a. `## Risks` section in plan.md template — PRESERVES Veto Surface affordance

Per Q-C critical-review fix: the existing `## Veto Surface` is the most-cited section in the corpus (13 retro mentions) and documents cross-cutting acknowledged-risk callouts (shared-failure-mode acknowledgments, side-effect surfacing, scope-drift framing) that don't attach to phase outcomes by construction. Per-phase `Goal`/`Checkpoint` cannot absorb these.

**Rename `## Veto Surface` to `## Risks`** in `skills/lifecycle/references/plan.md §3` canonical template. Keep the section's purpose, content shape, and ~5–10 line cost per feature. The rename is cosmetic (matches the new vocabulary of "phases" and "outline"); the affordance is preserved unchanged.

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

### 3. P9 (plan outline) + S7 (spec phases) + P10 (Acceptance for complex) orchestrator-review gates

Add to `skills/lifecycle/references/orchestrator-review.md`:

- **P9**: Plan contains `## Outline` section with at least 2 phases; each phase names tasks; each phase has a checkpoint.
- **P10** (complex-tier only): Plan contains `## Acceptance` section with whole-feature acceptance criterion. Skip on simple/medium/high tier — last-phase `Checkpoint` is the contract there.
- **S7**: Spec contains `## Phases` section with at least 2 phases; each requirement has a `**Phase**` tag matching one of the declared phases.

P9 and S7 fire wherever orchestrator-review runs (not on `low+simple` per existing skip rule). P10 fires only on critical-tier plans.

### 3a. Parser hardening at `metrics.py:221` (per #178 R5 amendment)

`cortex_command/pipeline/metrics.py:221` parses verdict-JSON field names directly. Per #178's R3 OQ3 soften (which removed the parser-cite MUST framing on `review.md`'s 4 verdict-JSON imperatives), this ticket's scope expands to include alias-lookup or normalized field-name parsing in `metrics.py:221` so the consumer tolerates harmless field-name drift without silently degrading `review_verdicts: None` in the morning report. This protects the FM-7 silent-degradation failure mode flagged in #178 spec Edge Cases.

### 4. Plan parser regression test

The existing parser at `cortex_command/pipeline/parser.py:282-329` was verified by the audit's pressure-test pass to be soft-OK on top-of-doc `## Outline` sections (parser is task-heading-anchored, doesn't terminate on the new section). Add a regression test that confirms:

- A plan with `## Outline` section above `## Tasks` parses successfully — all tasks discovered, all fields extracted
- The `Overview` extractor still finds the right section (not `Outline`)
- A plan with `## Phase N:` headings nested INSIDE `## Tasks` still hard-breaks (this is the documented limitation; the test locks in current behavior so a future "support nested phase headings" change is intentional)

## Touch points

- `skills/lifecycle/references/plan.md` (template — add Outline + Risks; delete Scope Boundaries + Verification Strategy; add tier-conditional Acceptance; provenance note)
- `skills/lifecycle/references/specify.md` (template — add Phases)
- `skills/refine/references/specify.md` — note: ticket 174 deleted this; if 174 lands first, edit only the lifecycle copy
- `skills/lifecycle/references/orchestrator-review.md` (P9, P10, S7)
- `cortex_command/overnight/report.py:725` (one-line update: read last-phase Checkpoint instead of Verification Strategy for non-critical tiers; read `## Acceptance` for critical tier)
- `cortex_command/pipeline/tests/test_parser.py` (or new test file)
- All `plugins/cortex-core/skills/*` mirrors auto-regenerated

## Verification

- A fresh plan-phase run (any tier) produces a plan.md with `## Outline` section containing ≥2 phases, each with checkpoint
- A fresh plan-phase run produces a plan.md WITHOUT `## Scope Boundaries` and WITHOUT `## Verification Strategy` (replaced by Outline)
- A fresh plan-phase run produces a plan.md WITH `## Risks` section (preserved Veto Surface affordance)
- A fresh complex-tier plan-phase run produces a plan.md with `## Acceptance` section
- A fresh non-critical-tier plan-phase run does NOT contain `## Acceptance` (last-phase Checkpoint is the contract)
- A fresh specify-phase run produces a spec.md with `## Phases` section + per-requirement `**Phase**` tags
- Orchestrator-review P9 fires (flag) on a plan that omits the Outline section
- Orchestrator-review P10 fires (flag) on a critical-tier plan that omits the Acceptance section
- Orchestrator-review S7 fires (flag) on a spec that omits Phases
- `cortex_command/overnight/report.py` reads correct field per tier (last-phase Checkpoint or `## Acceptance`)
- Existing legacy plans (without Outline) continue to parse correctly via the parser regression test
- A plan with phase headings nested inside `## Tasks` still hard-breaks (regression test documents the limitation)
- Provenance note is present and accurate; doesn't quote unverified Horthy claims as fact
- Net per-feature plan.md reduction: ~40–90 lines (down from original ~50–100 estimate; preserves Risks + tier-conditional Acceptance)
