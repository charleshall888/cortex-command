---
schema_version: "1"
uuid: c89de1af-5086-4d00-b459-f7455b872523
title: "Harness friction triage: distribution, contracts, slugs, gates"
status: complete
priority: high
type: epic
created: 2026-05-20
updated: 2026-05-25
tags: [harness, cli, plugin-distribution, skill-authoring, gate-policy]
discovery_source: cortex/research/harness-friction-triage/research.md
---

## Role

Tracks the five child tickets that close the accumulated multi-session harness friction surfaced by the `harness-friction-triage` discovery. The epic exists to keep the five enforcement layers visible as a coherent body of work; each child ships independently. The five children comprise four enforcement layers operating at different lifecycle moments (install/session-start, pre-commit, every CLI invocation, every gate-protected operation) plus one targeted validator fix that resolves a 0/7-corpus-success-rate gate.

## Integration

The five children are independent enforcement layers and can ship in any order; they do not depend on each other for correctness. They share exactly one explicit input surface: a canonical enumeration of `cortex-*` invocations across skill prose, owned by the contract-lint child and consumed as a derived artifact by the installation-integrity child's PATH self-test. All other inter-child relationships are conceptual rather than structural.

## Edges

- Shared input surface: the skill-prose grep enumeration is owned by the contract-lint child; the installation-integrity child consumes it for the PATH self-test rather than re-implementing the grep.
- Each child names its own contract surfaces; the epic does not own a contract surface of its own.
- Epic closure criterion: all five children reach `complete`. Partial completion does not close the epic.

## Touch points

- `cortex/research/harness-friction-triage/research.md` — canonical research artifact; Architecture section's Pieces sub-section defines the five-piece decomposition; Decision Records DR1–DR4 and the Reconciliation matrix are the canonical input.
- Children: tickets 252 (installation integrity), 253 (skill-prose contract lint), 254 (slug resolver), 255 (gate-policy taxonomy + critical-review fixes), 256 (validate_brief substring anchors).
