---
schema_version: "1"
uuid: aedb5311-2ade-4292-a40a-1f165e1c91a9
title: "Calibration probes for synthesizer selector confidence"
status: open
priority: medium
type: chore
created: 2026-05-04
updated: 2026-05-04
parent: "158"
blocked-by: ["160"]
tags: [competing-plan-synthesis, lifecycle, plan, testing]
discovery_source: research/competing-plan-synthesis/research.md
---

## Background

The synthesizer in #160 returns a `selector_confidence` field and defers to morning when confidence is below a calibrated threshold. The threshold and the confidence-rating itself are not derivable a priori — they need empirical calibration against probes that exercise known-good and known-bad inputs.

Per research.md Open Questions, the calibration probes literature does not formalize a planted-flaw probe for plan-synthesis judges (`NOT_FOUND(query="planted-flaw probe for plan-synthesis judge calibration", scope="published methodology)`), so this ticket designs probes from scratch grounded in the published methodology for LLM-as-judge calibration that DOES exist (identical-answer test, repetitive-list adversarial test, order-swap consistency).

## What this ticket delivers

Three probe types and a calibration harness that runs them against the synthesizer from #160:

1. **Identical-variants tie test**: present the same plan as two variants. The synthesizer must return a tie or low-confidence sentinel — anything else is a calibration failure.
2. **Position-swap consistency**: present the same two variants in both orders. Per `[Judging the Judges, arXiv:2406.07791]` Claude-3.5-Sonnet has 82% position consistency on MTBench; below that threshold for plan-synthesis is a calibration failure.
3. **Planted-flaw probe**: take a real plan from the `lifecycle/*/plan.md` corpus, inject a known structural defect into one variant (e.g., circular dependency in `Depends on`, file referenced in Verification but not in Files), present alongside the original. The synthesizer must select the original and flag the planted flaw — failure here is a calibration failure.

Calibration outputs:
- A pass/fail report against the three probes
- A recommended `selector_confidence` threshold for the defer-to-morning gate
- A documented baseline in `research/competing-plan-synthesis/calibration.md` (or similar) that future work can re-test against

## Value

Without calibration, the defer-to-morning fallback in #160 is firing on an arbitrary confidence threshold — the synthesizer's "low confidence" output is uncorrelated with actual difficulty. Calibration grounds the threshold empirically and produces a re-runnable test suite that detects regressions if the synthesizer prompt or model changes.

Without this ticket, #162's overnight wiring would ship without empirical evidence that the synthesizer behaves correctly under stress. The calibration is the validation gate per research.md DR-1.5.

## Scope

- Probe implementation as scripts (likely in `tests/competing_plan_synthesis/` or similar)
- Test corpus selection — pull from existing `lifecycle/*/plan.md` files for the planted-flaw probe
- Calibration harness that runs all three probes and produces a report
- Documented baseline + threshold recommendation

## Out of scope

- The synthesizer itself (in #160)
- Live monitoring of synthesizer behavior in production (separate observability ticket if/when needed)
- Calibration of any DR-3 axes-of-comparison taxonomy — that's part of #160 if axes are wired in, or future work if not

## Pre-shipment gate for #162

Per research.md DR-1.5, this ticket's pass/fail report is the gate for #162 (overnight wiring). The calibration must pass before the synthesizer ships into the unattended path.
