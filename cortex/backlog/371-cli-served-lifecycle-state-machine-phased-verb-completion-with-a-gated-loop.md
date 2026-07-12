---
schema_version: "1"
uuid: 5021c6a3-96c2-4dd3-9d5e-849cf7d002fb
title: 'CLI-served lifecycle state machine: phased verb-completion with a gated loop'
status: complete
priority: high
type: epic
created: 2026-07-10
updated: 2026-07-11
tags: ['cli-served-lifecycle-state-machine']
discovery_source: cortex/research/cli-served-lifecycle-state-machine/research.md
---
## Why

The lifecycle's sequencing knowledge is split between skill prose and CLI verbs, and the failures on record are exactly the split's symptoms: hand-maintained prose drifting from the code it describes, and multi-event transitions hand-written in ordered sequences that occasionally strand or misorder events. The prose-trim lever closed at audited floors, so the remaining fix is structural — but a full served state machine would guard a failure class (the model misrouting the phase sequence) with zero recorded occurrences, at two to three times the cost of fixing the recorded classes.

## Role

Parent for the phased delivery decided by discovery: writer-discipline point fixes that land immediately, a verb-completion composition that moves every multi-event transition and the pause inventory into code and data (a strict prefix of the eventual machine), and an evidence-gated decision on the served next/advance loop itself. The epic closes either when the gate resolves no-go with the composition shipped, or when the gate's go spawns the loop build.

## Integration

Adopts the existing identity-resolver bug ticket as a child (its fix is the machine's identity core either way). Children deliver in phase order; the gate ticket is blocked by the composition tickets and consumes the research artifact's Holistic Design Review as its spec baseline.

## Edges

- The loop's later stages (pause runtime tooth, overnight core-sharing, entry-point configs) are not ticketed until the gate resolves go — pre-creating them would pre-commit past evidence.
- Judgment-dense prose (plan authoring rules, checklists, reviewer prompts) never migrates to code under any phase.
- Delivery mechanism is settled: CLI verbs; MCP-server and hooks-only flavors were evaluated and rejected in research.

## Touch points

- `cortex/research/cli-served-lifecycle-state-machine/research.md` — full research artifact (Feasibility phases, Holistic Design Review, hazard register)