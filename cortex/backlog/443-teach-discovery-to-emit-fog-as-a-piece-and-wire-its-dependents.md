---
schema_version: "1"
uuid: f893afae-aba6-484a-805e-e74199436ae1
title: Teach discovery to emit fog as a piece and wire its dependents
status: backlog
priority: medium
type: feature
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
---
## Why

ADR-0034 decided that uncertainty becomes a piece at planning time and its dependents declare `blocked-by` when they are authored. Nothing implements it yet: the research phase has no fog test, so a piece that cannot be stated precisely is written as though it could be, and `#411`, `#412` and `#415` each ran a full refine against a body that later needed reconciling.

## Role

Teaches the research phase to recognize fog and emit it as a piece, and makes decompose wire the dependency so downstream tickets are authored already blocked.

## Integration

Rides two contracts that already exist. `### Pieces` is research-owned and decompose never re-derives it (`decompose.md:9`), so the fog piece enters through the same door as every other piece. `### How they connect` is already where decompose reads dependencies from, so the blocker needs no new channel — ADR-0007's grouping contract is untouched.

## Edges

- The fog test is wayfinder's: whether the question can be stated precisely now, not whether it can be answered. A piece failing that test becomes a fog piece; one that passes does not.
- A fog piece must name its resolution route, because the two kinds are answered by different instruments — intent fog by `/cortex-core:requirements` or `/cortex-core:interview`, fact fog by `/cortex-core:research`. Each terminates in an artifact, which is the fog ticket's definition of done. The routes compose: intent fog often needs a research step first so the questions put to the human are worth their turn.
- The calibration is ADR-0034's — fog is what more than one sibling rests on; a fact only one ticket depends on stays a refine-phase check. Epic #434 is the worked example to test any implementation against, since it shipped with three tickets corrupted by one unchecked fact.
- `/cortex-core:requirements` carries `disable-model-invocation: true`. An agent cannot clear intent fog unprompted, and the implementation must not route around that.
- Over-application is the live failure mode: naming fog too eagerly yields long blocker chains and an epic that reads as unworkable. Whatever calibration ships should be checkable on the existing corpus rather than asserted.
- Non-goal: retroactive fog detection on the 35 existing epics. This changes what new discoveries emit.
- `skills/discovery/` is lifecycle-gated, so this runs through `/cortex-core:dev` rather than direct edits.

## Touch points

- The research-phase Architecture template — where `### Pieces` is authored and the fog test belongs.
- `skills/discovery/references/decompose.md:9` — the piece-set contract and the `### How they connect` dependency read.
- `skills/discovery/SKILL.md` — gate-option inventory if the fog test surfaces a gate.
- `cortex/adr/0034-fog-becomes-a-piece-and-dependents-declare-the-blocker.md` — the decision this implements.
