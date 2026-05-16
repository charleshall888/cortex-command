# Decomposition: grill-me-with-docs-learnings

## Epic

- **Backlog ID**: 221
- **Title**: Adopt grill-with-docs progressive-disclosure system

## Work Items

| ID  | Title                                                                       | Priority | Size | Depends On |
|-----|-----------------------------------------------------------------------------|----------|------|------------|
| 221 | Adopt grill-with-docs progressive-disclosure system (epic)                  | high     | —    | —          |
| 222 | Adopt one-at-a-time grilling cadence in requirements interview              | medium   | S    | —          |
| 223 | Add project glossary at cortex/requirements/glossary.md                     | high     | M    | —          |
| 224 | Add docs/adr/ with 3 seed ADRs and emission rule                            | high     | S    | —          |

## Suggested Implementation Order

#222, #223, and #224 are independent and can run in parallel. No blocked-by chain. Suggested sequencing if running serially: #224 (ADR seeds — fastest, lowest risk, immediate value from `0001` through `0003` capturing CLAUDE.md rationale) → #222 (cadence — small in-place edits, lowest blast radius) → #223 (glossary — wires through `load-requirements.md` and the critical-review reviewer-prompt context block).

## Out of scope (explicitly named in epic body)

- **Interrupt-driven behaviors** (challenge-against-glossary mid-sentence, fuzzy-language sharpening, real-time code contradiction surfacing) — held pending effort=high evidence per CLAUDE.md MUST-escalation policy. Tracked as a needs-discovery item to be filed alongside this epic by a future research/refine cycle.
- **Maintained per-area "Related ADRs" indices** at the head of each area doc — Pocock's posture is consumer-rule prose ("use ADR vocabulary; grep `area:` frontmatter for area-scoped decisions") in `docs/adr/README.md` rather than hand-maintained per-area indices that drift.
- **New-repo bootstrap of glossary template via `cortex init`** — Pocock's `setup-matt-pocock-skills` does not create the glossary file; it scaffolds consumer-rule docs and lets the producer skill create the file lazily on first term. Cortex follows the same lazy-creation posture.

## Tangential issues already in flight (NOT filed as new tickets)

Two related skill-design problems surfaced during this discovery and turned out to be already tracked in active lifecycles. No duplicate tickets filed:

- **Discovery R4 gate template fights user comprehension** — tracked in `cortex/lifecycle/redesign-discovery-output-presentation/` (Phase 2; Phase 1 was `cortex/lifecycle/improve-discovery-gate-presentation/` completed 2026-05-12). The Phase 2 research artifact has empirical evidence (171-word "Headline Finding" entries violating the template's "one paragraph" directive).
- **/critical-review Step 4 lacks "user-already-disagreed" affordance** — tracked in `cortex/lifecycle/reduce-critical-review-influence/` (research phase, started 2026-05-15).

## Created Files

- `cortex/backlog/221-adopt-grill-with-docs-progressive-disclosure-system.md` — epic
- `cortex/backlog/222-adopt-one-at-a-time-grilling-cadence-in-requirements-interview.md` — child
- `cortex/backlog/223-add-project-glossary.md` — child
- `cortex/backlog/224-add-adr-mechanism-with-3-seeds-and-emission-rule.md` — child
- `cortex/research/grill-me-with-docs-learnings/decomposed.md` — this file
