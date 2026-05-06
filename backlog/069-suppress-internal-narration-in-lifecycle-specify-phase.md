---
id: 69
title: "Suppress internal narration in lifecycle specify phase"
type: feature
status: complete
priority: high
parent: 66
tags: [output-signal-noise, lifecycle, specify]
discovery_source: research/audit-interactive-phase-output-for-decision-signal/research.md
created: 2026-04-11
updated: 2026-04-17
session_id: null
lifecycle_phase: research
lifecycle_slug: suppress-internal-narration-in-lifecycle-specify-phase
complexity: simple
criticality: high
spec: lifecycle/archive/suppress-internal-narration-in-lifecycle-specify-phase/spec.md
areas: [lifecycle]
---

Four noise locations in the specify phase have no suppress or format constraint:

1. **§2a clean-pass path**: No "say nothing" instruction — agents announce "confidence check passed" when the gate passes cleanly.

2. **§2a failure-path announcement**: "Announce the flagged signals to the user, explaining why Research must be re-run" — no length constraint, agents produce unconstrained prose per signal. The user needs the actionable message (research is re-running and why); they do not need prose expansion of each C1/C2/C3 signal description.

3. **§2b pre-write checks**: The orchestrator verifies code facts inline before drafting the spec. No "don't narrate" constraint. Agents walk through verification step-by-step ("Checking function X... confirming file path Y...").

4. **§3a orchestrator-review fix-agent report**: When orchestrator-review dispatches a fix (Step 5), the fix-agent returns "Report: what you changed and why." `orchestrator-review.md` has no instruction for what the orchestrator does with that report. Agents relay it verbatim. The orchestrator should absorb the fix-agent report, re-run the checklist silently, and only surface the pass/fail result.

Files affected: `skills/lifecycle/references/specify.md` (§2a, §2b, §3a) and `skills/lifecycle/references/orchestrator-review.md` (Step 5 fix-agent disposition instruction).

## Context from discovery

DR-4 establishes the mechanism principle: removing the output *requirement* is more reliable than adding "be compact" instructions for in-context orchestrator work. The §2a clean-pass case is straightforward suppression; the §2b case is a behavioral instruction competing with in-context narration tendency; the §3a case requires adding a disposition instruction to orchestrator-review.md.

Note: `orchestrator-review.md §4`'s one-line pass assessment ("Show the user a one-line assessment...") is NOT a target for suppression — one line is acceptable.
