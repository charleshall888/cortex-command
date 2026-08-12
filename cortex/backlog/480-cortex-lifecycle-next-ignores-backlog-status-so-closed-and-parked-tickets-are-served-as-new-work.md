---
schema_version: "1"
uuid: 3e12f78f-4c7a-4546-a932-f8034b0ea630
title: cortex-lifecycle-next ignores backlog status, so closed and parked tickets are served as new work
status: complete
priority: high
type: bug
created: 2026-08-12
updated: 2026-08-12
tags: ['lifecycle-resolver', 'backlog-status', 'routing']
areas: ['lifecycle', 'backlog']
---
## Why

A backlog item's recorded outcome does not reach the lifecycle resolver. `cortex-lifecycle-next` opens the item only to resolve its title and slug, then decides routing on whether a lifecycle directory exists. When the directory is absent — never created, or archived as closure hygiene — a completed, abandoned, or parked ticket returns `state: "new"` carrying the directive "New feature — start the /cortex-core:refine flow at research."

Measured in a consumer repo (wild-light) on 2026-08-12:

| ticket | backlog `status:` | lifecycle dir | `next` state |
|---|---|---|---|
| 326 | `complete` | live | `complete` (correct) |
| 424 | `complete` | absent | `new` -> refine |
| 491 | `complete` | absent | `new` -> refine |
| 526 | `done` | absent | `new` -> refine |
| 327 | `wontfix` | archived | `new` -> refine |
| 419 | `deferred` | absent | `new` -> refine |
| 329 | `deferred` | absent | `new` -> refine |

Only the row with a live directory routes correctly, and it does so because the events log carries a terminal event — not because the status was read.

## Role

Makes the resolver's routing directive agree with the item's recorded outcome, so a finished or deliberately parked ticket is not served as new work.

## Integration

Extends to the resolver the same correction #435/#436 applied to the index renderer and triage. #434's Integration enumerated the surfaces that work reached — read-time normalization, the deferred-item predicate, the readiness predicate, the parent-closing cascade, the epic map — and the lifecycle resolver is not among them, which is why it kept the pre-#434 behaviour. Triage is correct today on exactly these items; the resolver disagrees with it.

## Edges

- Parked must not become terminal (#436's second Edge): a deferred item is genuinely unfinished, so it likely wants a state distinct from both `wontfix` and the served phase states.
- The existing `wontfix` routing state keys on the lifecycle `feature_wontfix` event, not on backlog frontmatter. Measured: #327 carries `status: wontfix` and still returns `new`. Conflating the two would change the event-driven arm's meaning.
- `KNOWN_STATES` is a closed set asserted by the test suite and declared in two places (`resolve.py`, `next_verb.py`); a new state touches both.
- `cortex/lifecycle/archive/<slug>` is not consulted. Archiving a closed ticket's directory is the sanctioned closure hygiene, and doing so moves the item from a frozen-phase verdict to `new` — one lie for another. A fix keyed only on live-directory absence would not notice this interaction.
- The served envelope has more than one consumer since #390, so the change reaches callers beyond `/cortex-core:dev`.
- Read-time correction is preferable to a stored-file migration, per #434's first Edge — the wrong routing is derived, not stored.

## Touch points

- `cortex_command/backlog/resolve_item.py:273-282` — `_build_json` already receives the fully parsed frontmatter `fm` and returns only `filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`. `status` is in hand and discarded.
- `cortex_command/lifecycle/resolve.py:133` — the call site that passes `_parse_frontmatter(res.item)` into `_build_json`.
- `cortex_command/lifecycle/next_verb.py:107-118` — `_ROUTING_PASSTHROUGH` and `KNOWN_STATES`.
- `cortex_command/backlog/generate_index.py:89-103` — `_is_deferred`, the predicate triage already consults for both the `deferred` tag and `status: deferred`.
- `cortex_command/common.py:190-199` — `TERMINAL_STATUSES`.

Sibling: the `/cortex-core:dev` explicit-id path has an independent instance of this blind spot — its rule 5 routes on the `spec:` field without calling this resolver at all, so fixing the resolver alone does not close it.
