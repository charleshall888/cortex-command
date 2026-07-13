---
schema_version: "1"
uuid: 84506324-4fe3-4ae3-8228-770b3f5c5b68
title: 'Phase-C gate: decide the served next/advance loop on post-composition evidence'
status: complete
priority: medium
type: spike
created: 2026-07-10
updated: 2026-07-11
parent: "371"
tags: ['cli-served-lifecycle-state-machine']
discovery_source: cortex/research/cli-served-lifecycle-state-machine/research.md
blocked-by: 373
lifecycle_phase: complete
lifecycle_slug: "374"
complexity: complex
criticality: high
spec: cortex/lifecycle/374/spec.md
areas: ['lifecycle']
---
## Why

The served next/advance loop guards a failure class — the model misrouting the lifecycle phase sequence — with zero recorded occurrences, while carrying real costs: a version-skew surface it creates itself, a fragment-flavor dilemma, new hazard classes, and a governance ADR. Deciding it now would be prediction rather than knowledge. But the design is fully specified by research and should not rot in a drawer; the decision needs criteria, evidence, and a home. Compounding this, incident capture stopped when the retro skills were removed, so today the gate would decide blind.

## Role

An evidence-based go/no-go on funding the served loop, evaluated after living with the verb-completion composition. The ticket restores an incident-capture signal so misrouting evidence can exist at all, defines the decision against the research's candidate criteria (a recorded misrouting incident, cross-verb drift the generators miss, resume friction the existing conventions don't cover, or the later stages independently justifying a shared core), and on go spawns the loop build — protocol handshake, next and advance verbs, centralized transition table, flavor decision — as its own lifecycle carrying the research's operator-experience requirements, coherence requirements, and hazard-register mitigations as spec obligations. On no-go, it records the verdict on the epic and closes it with the composition shipped.

## Integration

Blocked by the composition tickets — the loop composes their verb bodies and pause data unchanged. Consumes the research artifact's Holistic Design Review as its spec baseline. The later stages (pause runtime tooth, overnight core-sharing, entry-point configs) decompose only after a go verdict.

## Edges

- No-go is a legitimate, expected outcome — the ticket is not a commitment to build.
- The loop must not fund without the go-criteria met; the criteria live in this ticket, not in ambient judgment.
- Delivery mechanism is settled as CLI verbs; the gate re-opens only the fragment-flavor and handshake-closure questions.
- The go-path build must satisfy the hazard-register mitigations (single log-resolver decision, compare-and-swap advance, monotonic status lattice, most-restrictive legacy-pause default) as non-negotiable spec requirements.

## Touch points

- `cortex/research/cli-served-lifecycle-state-machine/research.md` — §Holistic Design Review (operator requirements, coherence requirements, hazard register) and §Open Questions (candidate go/no-go criteria); Feasibility Phase C row for the loop's internal step sequence