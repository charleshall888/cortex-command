---
schema_version: "1"
uuid: cf4444d3-be30-453b-8d60-53776e43b237
title: "Adopt grill-with-docs progressive-disclosure system"
status: backlog
priority: high
type: epic
tags: [requirements, skills, grill-me-with-docs-learnings]
created: 2026-05-15
updated: 2026-05-15
discovery_source: cortex/research/grill-me-with-docs-learnings/research.md
---

## Context

Discovery on Matt Pocock's `/grill-with-docs` skill identified three pieces that compose into a layered progressive-disclosure system on top of the existing requirements/area-doc structure: better requirements interview cadence, a project glossary, and an ADR mechanism. Each layer answers exactly one question (rule / definition / why / how) and stays small enough to be re-readable. Discipline rules in the ADR policy doc prevent content duplication and signal-flag drift. Maintenance follows Pocock's producer-consumer posture: the cadence-uplifted interview surfaces write inline; all consumer skills read with a vocabulary-or-signal prose rule.

See `cortex/research/grill-me-with-docs-learnings/research.md` for the full analysis, decision records (DR-1 through DR-6), feasibility assessment, and the critical-review pass plus subsequent investigation of how Pocock himself handles maintenance and new-repo creation that reframed the original "build hybrid write timing + maintained area-doc indices" recommendation into the current simpler shape.

## Children

- **Cadence/posture refresh** — interview-time changes to /requirements-gather and lifecycle/specify
- **Project glossary** — new file at cortex/requirements/glossary.md with Pocock CONTEXT-FORMAT discipline applied per-entry; inline-write at both interview surfaces; consumer-rule prose in lifecycle/specify and critical-review
- **ADR mechanism + 3 seeds** — new docs/adr/ directory, three seed ADRs from existing CLAUDE.md prose, emission rule in lifecycle/specify, consumer-rule prose in docs/adr/README.md

## Out of scope

- **Interrupt-driven behaviors** (challenge-against-glossary mid-sentence, fuzzy-language sharpening, real-time code contradiction surfacing) — held pending effort=high evidence per CLAUDE.md MUST-escalation policy. See research artifact DR-5 for the reasoning. Tracked separately as a needs-discovery item to be filed alongside this epic.
- **Maintained per-area "Related ADRs / glossary terms" indices** at the head of each area doc — Pocock doesn't do this. His posture is consumer-rule prose ("use ADR vocabulary; grep area: frontmatter for area-scoped decisions") in the policy doc rather than hand-maintained per-area indices that drift. Cortex follows the same posture.
- **New-repo bootstrap of glossary template via cortex init** — Pocock's `setup-matt-pocock-skills` does not create the glossary file; it scaffolds consumer-rule docs and lets the producer skill create the file lazily on first term. Cortex follows the same lazy-creation posture.

## Tangential issues surfaced during discovery (already in flight)

Two related skill-design problems surfaced during this discovery. Both already have lifecycle work in flight as of 2026-05-15 (do NOT file duplicate backlog tickets):

- **Discovery R4 gate template fights user comprehension** — already tracked in `cortex/lifecycle/redesign-discovery-output-presentation/` (Phase 2; Phase 1 was `cortex/lifecycle/improve-discovery-gate-presentation/` completed 2026-05-12). Empirical evidence in that lifecycle's research.md confirms the post-Phase-1 template under-delivered.
- **/critical-review Step 4 lacks "user-already-disagreed" affordance** — already tracked in `cortex/lifecycle/reduce-critical-review-influence/` (research phase, started 2026-05-15).
