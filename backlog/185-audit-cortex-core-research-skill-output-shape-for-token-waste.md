---
schema_version: "1"
uuid: e6002f93-1c9a-4ff6-a7d8-125279879d2a
title: "Audit /cortex-core:research skill output shape for token waste in research.md sections"
type: chore
status: complete
priority: medium
blocked-by: []
tags: [research-skill, token-efficiency, artifact-densification, sub-agent-output-shape]
created: 2026-05-06
updated: 2026-05-11
discovery_source: research/epic-172-audit/research.md
complexity: complex
criticality: high
spec: lifecycle/audit-cortex-coreresearch-skill-output-shape-for-token-waste-in-researchmd-sections/spec.md
areas: [lifecycle,skills]
session_id: null
lifecycle_phase: complete
---

# Audit /cortex-core:research skill output shape for token waste in research.md sections

Per `research/epic-172-audit/research.md` Q-G: real-world `lifecycle/<feature>/research.md` artifacts contain ~3,000 token average of sub-agent-invented sections that aren't in any documented template. The lifecycle template (formerly at `skills/lifecycle/references/research.md`; deleted in 2026-05-11 per backlog/185 — canonical schema source now at `skills/research/SKILL.md` Step 4 `### Output structure`) documented the schema, but the actual artifacts that ship contain entirely different sections.

## Context from discovery

The epic-172-audit's empirical sample (5 recent lifecycle dirs) found:

- `Requirements & Constraints` section in 5/5 samples (~720 tok avg) — re-quotes `requirements/project.md` verbatim; 0 retro mentions; 0 downstream consumers; **NOT in lifecycle template**
- `Tradeoffs & Alternatives` section in 5/5 samples (~990 tok avg) — surfaces alternatives; 0 retro mentions; **NOT in lifecycle template**
- `Adversarial Review` section in 4/5 samples (~1170 tok avg) — caught real issues in unify sample; 0 retro mentions but evidently load-bearing; **NOT in lifecycle template**
- `Considerations Addressed` section in 1/5 samples (~300 tok avg) — meta-narrative; **NOT in lifecycle template**

These sections are emitted by `/cortex-core:research`'s parallel-agent angles (formerly documented in `skills/lifecycle/references/research.md`; deleted in 2026-05-11 per backlog/185 — angle prescription now lives in `skills/research/SKILL.md` Step 3), which prescribe the angles but don't pin output shape. The result: each agent invents section structure, the synthesizer surfaces it, and the lifecycle template's documented schema is not what gets written.

**Implication**: trimming the lifecycle template's research.md schema (per ticket #182's vertical-planning adoption) doesn't move the needle on per-feature research.md token cost. The actual schema is owned by `/cortex-core:research`, not by lifecycle.

This is the **largest single per-feature waste source identified in the audit** — ~3,000 tokens / artifact across all lifecycle features. Net tokens at corpus scale (assuming ~2 features/week through lifecycle) is substantial.

## What to land

### 1. Document the actual research.md schema as currently emitted

Sample 10 recent `lifecycle/<feature>/research.md` artifacts and produce a "what sections actually appear" inventory. Reconcile against the documented schema (formerly at `skills/lifecycle/references/research.md`; deleted in 2026-05-11 per backlog/185 — canonical at `skills/research/SKILL.md` Step 4 `### Output structure`). Identify which invented sections are load-bearing (e.g., Adversarial Review caught real issues) vs. ceremonial (e.g., Requirements & Constraints re-quotes upstream).

### 2. Decide canonical schema

Choose between:
- **(α) Update lifecycle template to match current emission** — codify the de facto schema. Loses the cleanup opportunity.
- **(β) Tighten `/cortex-core:research` to emit only the documented schema** — restores schema discipline. Requires research-skill changes.
- **(γ) Hybrid** — keep load-bearing invented sections (Adversarial Review), drop ceremonial ones (Requirements & Constraints, redundant with downstream `requirements/` re-loads), add the kept ones to lifecycle template.

Recommendation (per epic-172-audit): (γ) hybrid. Adversarial Review has empirical value; Requirements & Constraints / Tradeoffs & Alternatives can be cut.

### 3. Update `/cortex-core:research` skill prose

Per the chosen canonical schema:
- Update `skills/research/SKILL.md` (or wherever `/cortex-core:research` lives) to prescribe the canonical sections in agent prompts
- Add WHAT/WHY/HOW classification to each prescribed section so future audits can re-grade
- Keep the parallel-agent angle structure but pin the output shape

### 4. Update lifecycle template

Update the lifecycle research template (formerly at `skills/lifecycle/references/research.md`; deleted in 2026-05-11 per backlog/185 — canonical at `skills/research/SKILL.md` Step 4 `### Output structure`) to match the canonical schema chosen in step 2.

### 5. Backwards compatibility

Existing archived research.md files have the old invented schema. Don't migrate them; just ensure new emissions follow the canonical schema.

## Touch points

- `skills/research/SKILL.md` (or wherever `/cortex-core:research` skill lives — verify path)
- `skills/lifecycle/references/research.md` (template alignment — file deleted in 2026-05-11 per backlog/185; canonical at `skills/research/SKILL.md` Step 4)
- `skills/discovery/references/research.md` (if discovery uses the same skill)
- All `plugins/cortex-core/skills/*` mirrors auto-regenerated

## Risks

- **Adversarial Review section is sub-agent invention**: it's not in any template but caught real issues in 1/5 samples. Removing it as "ceremonial" risks losing a load-bearing affordance. Apply the audit's evidence carefully — Adversarial Review goes in the keep bucket.
- **Cross-skill dependency**: `/cortex-core:research` is invoked by both lifecycle and discovery. Schema changes affect both consumers.
- **Token cost claims rest on the same problem-only retro template caveat**: per epic-172-audit's revised inference rule, "0 retro mentions" alone doesn't establish low value. Use orthogonal evidence (no programmatic consumer, duplicates upstream content) to discriminate keep-vs-cut.

## Verification

- Inventory document lists ≥10 research.md samples with section presence/absence and per-section token estimates (satisfied by `lifecycle/audit-cortex-coreresearch-skill-output-shape-for-token-waste-in-researchmd-sections/research.md` § "Empirical inventory — 19 recent lifecycle/*/research.md artifacts")
- ~~`skills/lifecycle/references/research.md` schema documents exactly the sections the canonical chosen schema prescribes~~ — Superseded by audit findings — see lifecycle/audit-cortex-coreresearch-skill-output-shape-for-token-waste-in-researchmd-sections/spec.md (file is deleted; canonical schema source moved to `skills/research/SKILL.md` Step 4)
- A fresh `/cortex-core:research` invocation produces a research.md matching the canonical schema (no inventions)
- ~~Net per-feature research.md token cost reduces by ≥40% (target: ~3,000 tok savings if (β)/(γ) chosen)~~ — Superseded by audit findings — see lifecycle/audit-cortex-coreresearch-skill-output-shape-for-token-waste-in-researchmd-sections/spec.md (premise misdiagnosed: load-bearing sections cannot be cut to hit ≥40%; replaced by no-regression criterion in spec Requirement 7)
- ~~Adversarial Review section, if kept (per recommendation γ), appears in a fresh research.md with the documented format~~ — Superseded by audit findings — see lifecycle/audit-cortex-coreresearch-skill-output-shape-for-token-waste-in-researchmd-sections/spec.md (γ rejected; Adversarial Review preserved unchanged per spec Non-Requirement 1)
- Existing archived research.md files continue to be parseable by any code that reads them
- `pytest` passes after migration
- Pre-commit dual-source drift hook passes after `just build-plugin`

> Verification criteria superseded by lifecycle/audit-cortex-coreresearch-skill-output-shape-for-token-waste-in-researchmd-sections/spec.md Requirements 1–9; see Problem Statement for rationale.
