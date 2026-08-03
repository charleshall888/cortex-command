---
schema_version: "1"
uuid: 3a1202a7-57ae-4e93-a323-caef43150ebd
title: A refined idea child licenses the epic footer's overnight sentence, contradicting its own discovery row
status: complete
priority: low
type: bug
created: 2026-08-03
updated: 2026-08-03
tags: ['backlog', 'triage', 'idea', 'footer']
areas: ['backlog']
---
## Why

Observed by direct render against the shipped code (2026-08-03, during #425's review phase):

    ### Epic 1 — T1 _(epic, not directly workable)_

    - **2** T2 — refined `/cortex-core:discovery`
    - **3** T3 — refined `/cortex-core:build`

    Run `/cortex-overnight:overnight` — it will auto-select them via its own readiness scan.

The idea child is told `/cortex-core:discovery` on its own row and, three lines later, is
swept into "auto-select them" — a route overnight's readiness scan will not honor for a
discovery topic. This is the same contradiction class #425 eliminated for the unrefined case.

#425 requirement 6 excluded `idea` children from the footer's unrefined-refine bucket, but the
exclusion is keyed on *unrefined* ideas only (`triage.py` footer partition). A refined `idea`
— an idea carrying a `spec:`, a shape #425 requirement 5 explicitly treats as real and tests —
falls into the all-refined bucket and licenses the overnight sentence.

Milder than the case #425 fixed: the overnight sentence lists no child ids, so the reader is
not pointed at the idea by name. That is why it was rated PARTIAL rather than FAIL and deferred
here rather than widened into #425.

## Scope

Decide whether the footer's all-refined arm should exclude `idea`-typed children regardless of
readiness, or whether a refined idea is a real state that should route somewhere else entirely.
The second reading is worth weighing: it is not obvious that an `idea` with a spec should keep
rendering `/cortex-core:discovery` on its row at all.

## Touch-points

- `cortex_command/backlog/triage.py` — the footer partition and `_recommendation`
- `tests/test_triage_render.py` — requirement 6 coverage; add the refined-idea case
- `cortex/lifecycle/triage-routes-ready-items-by-ticket/review.md` — the review finding
