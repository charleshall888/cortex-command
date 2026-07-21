---
schema_version: "1"
uuid: 96dd4553-41dd-45cd-9740-1beacd97861d
title: Collapse morning-review Step 4's stale pre-merge auto-close to a pointer at the post-merge §6b closer
status: backlog
priority: medium
type: bug
created: 2026-07-21
updated: 2026-07-21
tags: ['morning-review', 'correctness']
areas: ['skills']
---
## Why

`skills/morning-review/SKILL.md` Step 4 (line 105) runs a full pre-merge auto-close of backlog tickets ("no additional confirmation is needed"), while `references/walkthrough.md:275` states closure runs in Section 6b — post-merge, on confirmed-merge success only — because closing tickets before confirming the PR has merged was a bug. The model receives two contradictory orderings of a destructive action on every read, and the Section 6b closer's own skip-guard means a pre-merge Step-4 close reintroduces the exact bug the walkthrough says was fixed. A correctness fix, not a token cut: near-zero bytes, maximum clarity-harm, because the contradiction misleads on every read.

## Role

Collapse SKILL.md Step 4's stale pre-merge auto-close to a pointer at the post-merge closer (walkthrough Section 6b), so the walkthrough owns closure ordering and the skill carries a single source of truth.

## Edges

- Section 6b must remain the *sole* closer. Trace the no-PR / declined-merge path through its skip-guard: closure must not silently vanish in that branch once Step 4 stops closing (the research flags this as the one question to answer during the fix, not before).
- `skills/morning-review/` is lifecycle-gated — route via /cortex-core:lifecycle (small scope, low criticality).

## Touch points

- skills/morning-review/SKILL.md:105 (Step 4), plus the closure mentions at lines 18 and 131 if ordering prose needs alignment
- skills/morning-review/references/walkthrough.md §5 (line 275) and §6b (line 378)
- Provenance: spun out of epic #340 (closed 2026-07-21); evidence in cortex/research/skill-efficiency-remaining-work/research.md (R7).