---
schema_version: "1"
uuid: 7150663f-298c-46c0-ab12-6033b083e2be
title: Orchestrator-review rates against two checklists that no longer exist
status: complete
priority: high
type: bug
created: 2026-07-27
updated: 2026-07-27
tags: ['orchestrator-review', 'lifecycle', 'quality-gates']
areas: ['skills']
---
## Why

`skills/build/references/orchestrator-review.md` opens its Execute step with "Rate every item in the phase checklist — Post-Specify (`spec.md`) or Post-Plan (`plan.md`) — **pass** or **flag**", and scopes its binary-checkable rule to "checklist items S1 and P4". **Neither checklist exists.** `orchestrator-checklist-specify.md` was deleted in `3feec553` ("Trim cortex-core and cortex-backlog skills for Opus 5") and `orchestrator-checklist-plan.md` in `737f62b7` ("Split lifecycle into build and route entry points by ticket status") — both on 2026-07-27. The instruction to rate against them survived both deletions.

This is a **blocking** gate: "nothing reaches the user until the artifact passes its checklist or hits the cycle cap." With no rubric it degrades to whatever the reviewing agent improvises, and the degradation is invisible in the transcript because the protocol still reads as though a checklist were consulted. Two sessions can review the same spec against different bars and both report "pass".

Observed downstream in a consumer repo (wild-light #332, 2026-07-27): the improvised review covered S1's binary-checkability and essentially nothing else. The deleted checklists were substantial — Post-Specify carried 7 items (S1 binary-checkable criteria, S2 edge cases, S3 MoSCoW justified, S4 non-requirements are concrete boundaries, S5 constraints grounded, S6 behavioural changes documented, S7 spec phases present) and Post-Plan carried 13 (P1–P13, including P7 self-sealing verification and P11 concurrent-edit seams). Roughly five and twelve items respectively went unrated.

## Role

Restores the orchestrator-review gate to a fixed shared rubric instead of per-session improvisation, and closes the dangling-reference class that survived two trims on the same day.

## Integration

Two viable shapes: restore both files (last content recoverable from `3feec553^` and `737f62b7^`) under `skills/build/references/` and repoint the prose at them; or inline the item tables into `orchestrator-review.md` and drop the cross-file reference. Inlining suits the Opus-5 trim direction that deleted them; restoring keeps the shared protocol thin. Either way the items need reconciling against the *current* templates before they are re-armed.

## Edges

- **Do not restore the tables unreconciled.** S3 ("MoSCoW justified") rates a must/should/won't field the shipped `specify.md` template no longer carries — a stale checklist produces confident flags against fields that do not exist, which is worse than the current silence.
- SP003 already catches dangling `${CLAUDE_SKILL_DIR}` targets (`3b67c5d3`) but could not catch this: the reference is prose ("the phase checklist"), not a path. Naming the files explicitly so SP003 sees them, or extending the lint to prose references, is the durable fix — otherwise the next trim reopens it.
- The two deletions were separate commits with separate motivations; this is not one bad revert to undo.
- The packaged mirror under `plugins/` carries the same text and must not drift from the source copy.

## Touch points

- `skills/build/references/orchestrator-review.md:9,11` — the surviving references to Post-Specify/Post-Plan and to items S1/P4
- `plugins/cortex-core/skills/build/references/orchestrator-review.md` — packaged mirror, same lines
- `3feec553^:skills/lifecycle/references/orchestrator-checklist-specify.md` — last content (S1–S7)
- `737f62b7^:skills/lifecycle/references/orchestrator-checklist-plan.md` — last content (P1–P13)
- `cortex_command/lint/skill_path.py:243` — SP003 existence check, where a prose-reference guard would attach