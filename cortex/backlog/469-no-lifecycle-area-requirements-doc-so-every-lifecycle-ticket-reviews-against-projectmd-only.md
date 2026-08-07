---
schema_version: "1"
uuid: 288b9a46-1393-4797-9191-d397abdd610e
title: No lifecycle area requirements doc, so every lifecycle ticket reviews against project.md only
status: refined
priority: medium
type: chore
created: 2026-08-07
updated: 2026-08-07
tags: ['requirements', 'lifecycle', 'review']
areas: ['lifecycle', 'tests']
complexity: complex
criticality: high
spec: cortex/lifecycle/no-lifecycle-area-requirements-doc-so/spec.md
---
## Why

Measured 2026-08-07 during #454s review phase. `cortex-load-requirements --feature escalated-is-terminal-so-operator-direction` printed:

```
no area docs matched for tags: [lifecycle, review, escalation, state-machine]; loaded project.md only
```

Ticket #454 declares `areas: [lifecycle]`, and there is no `cortex/requirements/lifecycle.md`. Every other area in the repo has both a doc and a `## Conditional Loading` row: observability, pipeline, remote-access, multi-agent, backlog, training. The lifecycle state machine — the largest subsystem here, and the one the build/refine skills exist to drive — has neither.

The concrete cost, observed rather than hypothetical: the review phase treats the no-match note as a warning precisely because the requirements-drift check silently narrows to project.md, leaving area-level requirements unassessed. In #454 it also meant `cortex/requirements/observability.md` never loaded, even though it names `claude/statusline.sh` as its Statusline subsystem and #454 modified that exact file — the reviewer only assessed it because it was handed the path manually. A tag-driven loader cannot reach observability.md from lifecycle tags, so this recurs for every lifecycle ticket that touches a narration surface.

#454 landed a partial mitigation: the `## Conditional Loading` row now exists and names the doc as NOT YET WRITTEN, so the loader prints `lifecycle.md (...) (skipped: file absent)` instead of a silent narrow. The gap is now **visible** but not closed.

## Role

Give the lifecycle area a real requirements doc so lifecycle tickets have area-level requirements to be reviewed against, and so drift detection has somewhere to land other than project.md.

## Integration

Most of the content already exists but is scattered as bullets in `project.md` Architectural Constraints — including the phase-vocabulary invariant #454 added, lifecycle identity, the closed transition table, and the served-verb protocol. Moving material out of project.md into an area doc is a relocation, not net new prose, and should shrink project.md. Existing area docs are the format model. ADRs 0008 and 0024-0026 carry the ratified decisions.

## Edges

- Decide whether `escalation` and `review` tags route here or stay unrouted; #454s tag set was `[lifecycle, review, escalation, state-machine]`.
- Narration of lifecycle phase on the statusline and dashboard is legitimately governed by `observability.md`, not here — the two docs need an explicit boundary so the same surface is not specified twice.
- Watch the token cost: this doc loads for every lifecycle ticket, so it is subject to the same conditional-loading discipline as the others.

## Touch-points

New `cortex/requirements/lifecycle.md`; `cortex/requirements/project.md` (the NOT-YET-WRITTEN routing row at `## Conditional Loading`, and whatever Architectural Constraints bullets relocate); `cortex_command/requirements/` loader if the tag map is data-driven.
