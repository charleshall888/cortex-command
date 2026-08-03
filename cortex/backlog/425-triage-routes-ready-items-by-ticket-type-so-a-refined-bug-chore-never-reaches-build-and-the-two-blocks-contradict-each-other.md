---
schema_version: "1"
uuid: d7894ec3-bf36-454c-812b-73010fe3674f
title: Triage routes Ready items by ticket type, so a refined bug/chore never reaches build and the two blocks contradict each other
status: refined
priority: medium
type: bug
created: 2026-08-03
updated: 2026-08-03
tags: ['triage', 'dev', 'routing', 'readiness']
areas: ['backlog']
complexity: complex
criticality: high
spec: cortex/lifecycle/triage-routes-ready-items-by-ticket/spec.md
---
## Why

**One `cortex-backlog-triage` invocation gave two contradictory routings for the same ticket type.**
Triaging wild-light on 2026-08-03, the Ready block rendered:

```
`high` `bug` **432** Survivor ENet detection skew … → direct implementation
`medium` `chore` **433** c_live_parity checks nothing … → direct implementation
```

while the Epic 344 block in the *same output* rendered `#413` — also `type: chore` — as
`[needs /cortex-core:refine]`, and its footer said "Run `/cortex-core:refine` on each unrefined child:
… 413 …". Same run, same repo, same type, opposite advice.

The routing is type-only (`triage.py:78-84`):

```python
def _workflow(item: dict) -> str:
    kind = item.get("type", "feature")
    if kind == "idea":
        return "`/cortex-core:discovery`"
    if kind in ("bug", "chore"):
        return "direct implementation"
    return "`/cortex-core:build`" if _is_refined(item) else "`/cortex-core:refine`"
```

`type` is a label for *what kind of problem* a ticket is, not *how much design it needs*. #432 is typed
`bug` and changes host-migration election semantics across `migration_coordinator.gd` and
`network_manager.gd`; #327 is typed `chore` and forces a `GEN_VERSION` bump with ~8 golden/digest
recaptures. Both rendered "direct implementation".

**Live exposure is in consuming projects, not here.** In wild-light the type-only path covers **15 of
18** ready items. This repo has only 5 active tickets today (3 `backlog` + 2 `deferred`; the other 414
`.md` files are terminal and are not indexed), so almost nothing here is currently affected — but
`bug`/`chore` is **192 of the 418-file corpus** (120 `chore` + 72 `bug`), which is the share of work
that has historically flowed through this branch and will again. Fix it for the consumers.

Three distinct defects fall out of that one branch:

1. **It contradicts the skill it renders for.** `skills/dev/SKILL.md:18` (Step 1 rule 5) routes on
   *readiness*, type-blind: "no `spec:` field … → `/cortex-core:refine`; `status: refined` with a
   `spec:` → `/cortex-core:build`". `_workflow()` never consults readiness for `bug`/`chore`.
2. **It contradicts the epic block beside it.** `_render_epic_block` marks children purely on
   `_is_refined()` with no type check, so a `chore` child of an epic is told to refine while an
   identical `chore` in Ready is told to implement directly.
3. **A refined `bug`/`chore` can never route to `/cortex-core:build`.** The `bug`/`chore` branch returns
   *before* `_is_refined()` is consulted, so a ticket that already has an approved spec is still
   rendered "direct implementation" — silently orphaning the spec someone paid an interactive refine to
   produce. Reachable and live: wild-light **#281** is `type: chore` with
   `spec: cortex/lifecycle/gdscript-warning-baseline-cleanup-real-per/spec.md`. It sits at
   `in_progress` today (so `_ready_items` skips it), but any `bug`/`chore` reaching `status: refined`
   lands in Ready and hits this.

Defect 3 is the unambiguous bug — no reading of the type heuristic justifies discarding an existing
spec. Defects 1 and 2 are the inconsistency that makes the output untrustworthy.

## Role

Make the Ready block's workflow recommendation agree with the dev skill's documented readiness rule and
with the epic block's own marks, so a ticket's rendered route does not depend on which block it happens
to appear in.

## Integration

`cortex_command/backlog/triage.py:78-84` is the whole surface. `_workflow()` is called once, at `:176`:

```python
f"**{item['id']}** {item['title']} → {_workflow(item)}"
```

The returned string is human-facing only — nothing in the repo parses it (grep for
`"direct implementation"` finds only `triage.py` itself plus prose in `docs/skills-reference.md:19,:78`
and two archived lifecycle docs). So the return value can change shape without breaking a consumer.

The minimum correct change is to consult readiness before type — i.e. let `_is_refined()` win for every
type, so a refined `bug`/`chore` routes to `/cortex-core:build`. That alone fixes defect 3 and narrows
defect 1 to the unrefined case.

## Edges

- **Do not simply delete the `bug`/`chore` branch.** It exists for a real reason: most bugs and chores
  genuinely are small, and forcing a one-line typo fix through an interactive refine (two unconditional
  human pauses — `spec-interview-gapfill`, `spec-approval`) is friction that would make triage worse,
  not better. Whatever replaces it must keep a cheap path.
- **A mechanical renderer cannot judge scope.** `SKILL.md:17` (Step 4) already has the right model — a
  *judgment-based* "trivial change (single file, existing pattern, one obvious approach)" escape hatch
  applied by the agent reading the ticket. `_workflow()` has only the index row (id, title, type,
  priority, status, spec) and cannot make that call. The honest options are: (a) route on readiness
  only and let Step 4 handle triviality, or (b) keep type as a visible *hint* while showing the
  readiness-derived route — but not (c) let type silently override readiness, which is today.
- **The `idea` → discovery branch is fine and should stay.** `idea` genuinely is a readiness statement
  ("not yet understood"), unlike `bug`/`chore` which are problem-kind labels.
- **Epic-block consistency is part of the fix, not a follow-up.** If `_workflow()` starts honoring
  readiness, `_render_epic_block` should use the same helper rather than its own inline
  `_is_refined()` mark, so the two blocks cannot drift apart again.
- **`type` values are not a closed set.** The corpus carries `feature`, `chore`, `bug`, `epic`, `spike`,
  `task`, plus singletons `fix`, `enhancement`, `discovery`, `needs-discovery`. `_workflow()`'s
  `item.get("type", "feature")` default means every unrecognized type falls through to the
  refine/build path — check that is still right for `task` and `fix` after the change.

## Touch points

- `cortex_command/backlog/triage.py:78-84` — `_workflow()`, the type-only branch and its ordering
  against `_is_refined()`.
- `cortex_command/backlog/triage.py:176` — the sole call site.
- `cortex_command/backlog/triage.py:95` — `_render_epic_block`'s inline `[refined]` /
  `[needs /cortex-core:refine]` mark, the second and disagreeing rule.
- `cortex_command/backlog/triage.py:73-75` — `_is_refined()`, the readiness predicate (likely unchanged).
- `cortex_command/backlog/triage.py:277` — the `flat` payload already emits a per-item `refined` boolean,
  so machine consumers get readiness while the rendered string does not. Useful precedent for the fix.
- `skills/dev/SKILL.md:18` — Step 1 rule 5, the readiness rule this must agree with; `:17` Step 4, the
  judgment-based trivial-change hatch that should own the cheap path.
- `tests/test_dev_triage_refs_wired.py:99-105` — `test_verb_renders_the_blocks` asserts the
  `/cortex-core:refine` token survives across `render` + `_render_epic_block` + `_workflow`. Low
  regression risk, but a new test belongs here asserting a refined `bug` routes to `/cortex-core:build`.

## Acceptance

- A `type: bug` or `type: chore` item with a non-empty `spec:` and `status: refined` renders
  `/cortex-core:build` in the Ready block, not "direct implementation".
- For a given (type, status, spec) triple, the Ready block and the Epic block recommend the same
  workflow — verified by a test that renders one item through both paths and compares.
- The `idea` → `/cortex-core:discovery` branch is unchanged.
- A cheap path for genuinely trivial bugs/chores still exists and is documented — either preserved in
  the renderer or explicitly delegated to `SKILL.md` Step 4, with the delegation stated in the skill.
- `tests/test_dev_triage_refs_wired.py` stays green.
