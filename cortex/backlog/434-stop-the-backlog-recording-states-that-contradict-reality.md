---
schema_version: "1"
uuid: afc093ee-d8e7-469f-8951-fbce31413b78
title: Stop the backlog recording states that contradict reality
status: complete
priority: medium
type: epic
created: 2026-08-03
updated: 2026-08-03
tags: ['staged-epic-gate-tickets']
discovery_source: cortex/research/staged-epic-gate-tickets/research.md
---
## Why

The backlog's records disagree with what happened. Finished items render as work remaining. An epic reads as delivered when its scope was dropped. A closed epic absorbs new children silently. Five declarations claim to define the status vocabulary and three are read by nothing. And a ticket can be worked against an understanding a sibling has already invalidated.

## Role

Parent for the work that makes the backlog's recorded state match its real state — first in the status vocabulary, then in epic membership and outcome, and last in whether a ticket can be worked once its premise has changed.

## Integration

Reaches the read-time status normalization, the deferred-item predicate, the readiness predicate, the parent-closing cascade, and the epic map — the surfaces every index, triage, and dashboard consumer already routes through.

## Edges

- Corrections are read-time wherever possible: the wrong values arrive by direct frontmatter edit rather than through the creation verb, and a read-time fix reaches consumer repos retroactively without touching their stored files.
- No new ticket type and no new status value is introduced; the vocabulary narrows rather than grows.
- The final child produces a decision and its rationale, not an implementation.
- Ordering across children is load-bearing: normalization lands before the vocabulary narrows, and epic visibility lands before the decision that consumes the census it enables.

## Outcome (2026-08-03): complete, with scope dropped

Eight of ten children shipped. Two did not, and `status: complete` alone does not say so:

- **#443** (`wont-do`) — teach discovery to emit fog as a piece. Retracted; the harness already had it.
- **#444** (`superseded`) — catch a decompose body that contradicts its source research. Folded
  into #429 after checking whether one auditor covers it; it does not. See #444's Disposition.

Recorded by hand because the cascade that closed this epic ran from the installed wheel, which
predates the mixed-outcome note #442 added. Once the next release is installed, a close of this
shape names the dropped children on stderr at the moment it happens.
