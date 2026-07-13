---
schema_version: "1"
uuid: 0604375c-04bf-4ea3-914d-e4a01676f732
title: "Trim lifecycle config instance: delete narration, lazy-load Branch Mode blocks"
status: complete
priority: low
type: chore
tags: ['skill-value-scorecard']
areas: ['lifecycle']
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "347"
lifecycle_phase: complete
lifecycle_slug: trim-lifecycle-config-instance-delete-narration
complexity: simple
criticality: medium
spec: cortex/lifecycle/trim-lifecycle-config-instance-delete-narration/spec.md
---

## Why
cortex/lifecycle.config.md — this repo's own config instance, read by lifecycle at start — carries five verified trim verdicts totaling ~3.3k weighted tokens. The normalization-rules section (s7, value 1 at 920 weighted, the worst value-per-token section in the corpus) narrates parser mechanics the config parser module enforces and its tests cover individually. The Branch Mode intro, values closed-set, and carve-outs blocks (s4, s5, s6 — all LAZY_REF) and the edge-cases section (s8, DELETE) are likewise verified. One correction to the audit's top-level claim, per the s7 behavioral-necessity verdict and the code: an out-of-set branch-mode value produces NO stderr warning — the picker simply fires silently. The deletion is still safe; the fail-safe is the silent picker, not a warning.

## Role
Apply the five verdicts to cortex/lifecycle.config.md per their keep-lists. This is a single-file edit: the sections exist ONLY in this repo's instance — neither the lifecycle skill asset nor the cortex-init template contains the normalization or Branch Mode blocks, so there is no template or asset change and no mirror regeneration. For the three LAZY_REF blocks, research decides the cold home: a reference the picker path reads on demand, or deletion if the closed set is fully owned by the picker-decision verb.

## Integration
The 335 parity gate compares the asset and init-template to each other and never touches the repo instance — it stays green untouched. Candidate ids are file-scoped: these s4-s8 live under file cortex/lifecycle.config.md in master_candidates.json (sibling tickets cite different candidates with the same ids).

## Edges
- lifecycle SKILL.md reads this file at start — confirm nothing routes on the deleted prose before cutting.
- ADR-0017 still reads status proposed although its parity gate is implemented and green; correct in passing if touched.

## Touch points
- cortex/lifecycle.config.md (the only file that changes)
- cortex/research/skill-value-scorecard/master_candidates.json (verdict source)
