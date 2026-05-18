---
schema_version: "1"
uuid: 5d540aa8-015b-4fbb-83ff-049748708005
title: "Ship discovery-output-density Phase 2: cross-skill brief framework + corpus regression lint"
status: complete
priority: medium
type: feature
tags: [discovery, lifecycle, skills, prose-density]
created: 2026-05-18
updated: 2026-05-18
parent: "232"
complexity: complex
criticality: high
---

# Ship discovery-output-density Phase 2: cross-skill brief framework + corpus regression lint

## Context

Phase 1 of the discovery-output-density lever (parent: `cortex/lifecycle/discovery-output-density-investigate-author-centric/`) shipped a narrow-scope gate-brief generator at the discovery research→decompose gate. The Phase 1 spec named two Phase 2 candidates and deferred them via trigger ticket #232 with a 6-month review date.

Trigger #232 fired at d+1 from merge: corpus measurement showed both Phase 2 conditions are already satisfied empirically. This ticket bundles the implementation of both deferred candidates.

## Empirical justification (recorded at #232 closure)

- `python3 -m cortex_command.discovery score-corpus --root cortex/research/`: 12 of 13 files flag ≥1 of the six reader-study patterns reproducing.
- `python3 -m cortex_command.discovery score-corpus --root cortex/lifecycle/`: 56 of 56 lifecycle research.md files flag ≥1 pattern; 30 of 56 flag ≥3 patterns.

Both trigger conditions named in #232 are satisfied:
- Candidate G's gate condition (≥1 pattern reproducing across live corpus) — passed loudly.
- The empirical version of Candidate C's gate condition (density patterns reproducing in lifecycle artifacts, not just discovery) — passed.

## Candidate C — Cross-skill brief framework

Extend the Phase 1 gate-brief generator pattern from `skills/discovery/SKILL.md`'s research→decompose gate to lifecycle gates that present dense artifacts to the operator for approval: clarify (intent + criticality surface), specify (the spec.md approval surface), and plan (the plan.md approval surface where applicable).

Each gate that currently displays a dense artifact wholesale should display a fresh-context generated brief in front of the dense artifact, with the same fallback semantics as Phase 1 (brief failure → fall back to dense artifact, four operator options preserved).

Key Phase 1 mechanisms to reuse:
- `cortex_command/discovery.py:generate-brief` generator pattern
- `GATE_BRIEF_RUBRIC` and `GATE_BRIEF_WORD_CAP` constants
- Multi-fixture pre-merge test suite scoring the six reader-study patterns
- Fallback-on-failure behavior preserving operator-blocking options

Open scoping questions for research/spec:
- Which specific lifecycle gates present dense artifacts (clarify outputs §5, specify approval surface §4, plan approval, review)?
- Per-gate rubric variation: does spec.md need a different rubric from research.md, or is one rubric sufficient?
- Where does the brief artifact persist? (Discovery wrote `cortex/research/<topic>/brief.md`; lifecycle gates may need parallel paths.)
- How does this interact with the refine flow (which already wraps clarify + research + spec)?

## Candidate G — Corpus regression lint

Wire `python3 -m cortex_command.discovery score-corpus` into a recurring check so drift surfaces automatically rather than via manual quarterly invocation. Options to consider in research:

- Pre-commit gate (fires on every commit touching `cortex/lifecycle/*/research.md` or `cortex/research/*/research.md`)
- Periodic `just`-recipe + cron / overnight-runner job
- Statusline integration surfacing flagged-artifact counts

Open scoping questions:
- Does the lint block or warn? (Pre-commit gating implies block; quarterly surveillance implies warn.)
- Threshold tuning: at what pattern count does a file "trigger" reporting?
- Should the lint cover lifecycle artifacts too (not just `cortex/research/`)?

## References

- Phase 1 spec: `cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` (Requirements 1–15)
- Phase 1 research: `cortex/lifecycle/discovery-output-density-investigate-author-centric/research.md`
- Phase 1 review: `cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md`
- Word-cap derivation: `cortex/lifecycle/discovery-output-density-investigate-author-centric/word-cap-derivation.md`
- Parent trigger: `cortex/backlog/232-re-evaluate-cross-skill-brief-framework-discovery-output-density-phase-2-trigger.md`

## Closure (2026-05-18) — Phase 2 not shipped

Refine ran Clarify + Research, then halted at the Research Exit Gate. The adversarial agent surfaced two falsifying findings against the bundled Phase 2 premise:

1. **Genre-transfer empirically fails**. Phase 1's six reader-study pattern detectors fire on ~50% of legitimate spec.md/plan.md prose (case-insensitive `does not` regex matches Non-Requirements clauses; `DR-N` / `§N` forward-ref detector flags specs that reference the discovery framework or use section anchors). Six real lifecycle artifacts tested; mean ≈ 2.5 patterns per file, all on prose that is structurally sound for its genre. The corpus measurement that justified firing the trigger (#232 closure) is therefore a leading indicator of "pattern matches" rather than "real-problem density."

2. **Phase 1 binding hypothesis unfalsified**. Req 9's post-merge corpus check (the falsifier Phase 1 explicitly built to validate its hypothesis) has not yet produced any data — zero production briefs exist in `cortex/research/*/brief.md` since the 2026-05-17 merge. Phase 2 would build at 3× scale (research + spec + plan rubrics) on an unvalidated premise. Precedent (the prior `improve-discovery-gate-presentation` fix from 2026-05-12) is that test-pinned binding does not guarantee production fidelity.

**Decision**: abandon Phase 2 for now. Wait for Req 9 to produce ≥ 3 clean production briefs across the next quarter. If Phase 1's binding hypothesis is validated in production, re-evaluate whether to ship C and/or G — likely with a pattern-recalibration sub-phase for spec.md and plan.md given finding (1). If Phase 1's hypothesis is falsified by Req 9, neither C nor G ships in their current form.

No future-scheduled trigger ticket is created (per the user's preference for noticing real signal organically over scheduled re-evaluation, established during the #232 evaluation).

**Research artifact retained**: `cortex/lifecycle/ship-discovery-output-density-phase-2/research.md` — contains the full Codebase / Web / Requirements / Tradeoffs / Adversarial Review synthesis plus the empirical pattern-detector results. Re-readable if Phase 2 re-opens.
