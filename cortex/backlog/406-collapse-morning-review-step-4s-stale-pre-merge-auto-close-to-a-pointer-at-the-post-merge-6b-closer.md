---
schema_version: "1"
uuid: 96dd4553-41dd-45cd-9740-1beacd97861d
title: Collapse morning-review Step 4's stale pre-merge auto-close to a pointer at the post-merge §6b closer
status: superseded
priority: medium
type: bug
created: 2026-07-21
updated: 2026-07-27
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

## Resolution

Superseded by #342 ("Fix morning-review pre-merge auto-close ordering bug", complete), which landed this exact change in `d54c197b` on 2026-07-01 — twenty days before this ticket was filed. `skills/morning-review/SKILL.md` Step 4 already reads "Backlog ticket closure runs post-merge in walkthrough §6b, not here."; the pre-merge close body, its backend routing, and the `cortex-update-item` close literals were all removed. The `plugins/cortex-overnight/` mirror is in sync, so no stale copy survives.

The Edges question — whether closure silently vanishes on the no-PR / declined-merge path — was answered by the same fix: walkthrough §6 states the invariant ("Until a merge is confirmed, completed features' backlog tickets stay open — the work sits on the integration branch, not main") and §6b carries the explicit skip-guard, so the skip is deliberate and documented rather than silent.

Why it was re-filed: this ticket was spun out of epic #340 at its 2026-07-21 closure directly from the R7 research (written 2026-06-30), whose line citations predate the fix. The stated line numbers never matched the tree at filing time. Lesson for epic-closure spinouts: re-verify cited line numbers against the current tree before filing, since #340's other R7 survivors (#341, #343) had also already shipped.

One cosmetic vestige was found and deliberately left: SKILL.md Step 5 still lists `cortex/backlog/` "closed/archived tickets" in its pre-merge commit scope, though §6b's `cortex-morning-review-push-closures` now owns committing closes. The rest of that clause stays live (§4 can create an investigation ticket pre-merge), and `skills/` is lifecycle-gated — a full refine→build cycle for three words does not clear the evidence bar.