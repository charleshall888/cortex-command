---
schema_version: "1"
uuid: b5e42675-8feb-4b0b-b5d0-1f4e26a6388a
title: 'Triage marks and recommends closed tickets: epic blocks list every child regardless of status'
status: complete
priority: high
type: bug
created: 2026-08-06
updated: 2026-08-06
tags: ['triage', 'backlog', 'dev-skill', 'epic-map']
areas: ['backlog']
complexity: moderate
---
## Why

`/cortex-core:dev` Step 3 prints `cortex-backlog-triage`'s epic blocks so the operator can pick something
to work on. Roughly half that output is closed work, and a third of the *instructions* it emits point at
tickets that shipped weeks ago.

Two things go wrong, independently.

**1 — `_recommendation()` never reads `status`.** `cortex_command/backlog/triage.py:78-87` routes purely on
`type` and `spec:` presence:

```python
def _recommendation(item: dict) -> str:
    if item.get("type", "feature") == "idea":
        return "`/cortex-core:discovery`"
    return "`/cortex-core:build`" if _is_refined(item) else "`/cortex-core:refine`"
```

`_render_epic_block` calls it on every child (line 103), and `render()`'s own docstring commits to listing
"every child regardless of status". So a completed ticket gets a route mark for exactly the same reason a
backlog one does — nothing on that path asks whether the work is done. The verb it lands on is archaeology
on `spec:`, not a judgement: a ticket closed *with* a lifecycle spec reads `complete /cortex-core:build`,
one closed without reads `complete /cortex-core:refine`.

**2 — the footer's held-status filter omits the terminal statuses.** Line 38:

```python
_HELD_STATUSES = frozenset({"in_progress", "implementing", "review", "in-progress"})
```

Only in-flight states. `complete`, `done`, `abandoned` and `deferred` fall straight through the
`recommendable` / `active` partitions at lines 111-117 and into the sentence:

> Run `/cortex-core:refine` on each unrefined child, one at a time (each needs interactive spec approval
> before the next): 345 Widen scene guards…, 346 Decouple sim queries…, 347 Bring main up on Godot 4.7.1…

All three of those are complete. This one is not cosmetic — it is a direct instruction to re-refine
finished work, and it also inflates the adjacent "recommendations apply to the remaining 48" note, which
counts closed children as candidates.

Measured on a consumer repo (467 items, 65 active, 6 epics in the ready set):

| | rendered | workable | dead |
|---|---|---|---|
| epic-child rows | 130 | 24 | **106 (82%)** |
| footer-named IDs | 49 | 17 | **32 (65%)** |
| `blocks` payload | 24,666 chars | — | **12,151 chars (49%)** |

Two of the six epics (236, 284) rendered 16 rows and two refine footers between them while having **zero**
workable children.

## Role

The epic blocks should show what is available to work on. Closed and abandoned children are history; they
belong in the backlog files, not in a pick-your-next-task prompt — and they must never carry a route mark
or appear in a "run refine on each of these" list.

## Integration

Two changes in `cortex_command/backlog/triage.py`:

- **Filter epic children to workable statuses** before rendering rows, so `_render_epic_block` lists only
  what can be picked up. This reverses `render()`'s current "every child regardless of status" contract —
  that docstring and the module docstring both need to change with it.
- **Widen the held-status set** (or add a terminal-status set) so the footer partition and the blocked-count
  note are computed over workable children only.

With children filtered, `_recommendation()` only ever sees workable items and needs no `status` awareness of
its own — worth confirming rather than assuming, since it is also reachable from the flat `## Ready` block
at line 210. That path is already safe: `_ready_set` restricts to `refined` / `backlog` / `open` / `blocked`,
which is why no closed ticket has ever appeared in `## Ready`.

## Edges

- **Losing the progress signal is the real cost.** Today the full child list doubles as "how far along is
  this epic" — 38 of 53 complete on epic 344 reads at a glance. Dropping the rows drops that. A one-line
  count per section (`14 complete, 2 abandoned, 3 workable`) keeps it for a fraction of the output, and is
  probably the right shape rather than a straight deletion.
- **An epic whose children are all closed then renders empty**, hitting the existing `if not active:` branch
  and its "consider `/cortex-core:discovery` to decompose this epic" line. That is arguably the correct
  message for epics 236 and 284 — but check it reads right, because the epic itself is still `backlog` and
  the wording implies it was never decomposed at all. Suppressing the section entirely may be better.
- **`deferred` is not `complete` and may not want the same treatment.** `_is_deferred` already excludes it
  from the ready set, so it is unworkable *now* — but it is a parked decision, not a finished one, and an
  operator scanning an epic may well want to see it. Decide explicitly rather than sweeping it in with the
  closed rows.
- **Status vocabulary is not normalized.** `done` and `complete` both appear in real data (`345` is `done`,
  `348` is `complete`), and `_HELD_STATUSES` already carries both `in_progress` and `in-progress`. Any new
  set has to cover the variants or it will half-work. Worth asking whether normalization belongs upstream in
  `generate_index` instead of another hand-maintained frozenset.
- **Latent, and subsumed by the fix:** `main()` builds the epic map from `index-full.json` (467 items) but
  calls `render(items, epic_map)` with the active-only index (65) at line 313. `_resolve_child` therefore
  misses on every closed child and falls back to the epic-map envelope — `{id, spec, status, title}`, which
  carries **no `type`** (the code comments know this). `spec` survives, so the build/refine verb is
  unaffected, but the `idea → /cortex-core:discovery` precedence documented at lines 134-141 silently cannot
  fire for a closed child. Filtering them out removes the exposure; passing `full_items` to `render()` would
  close it properly. Do one or the other knowingly.

## Touch points

- `cortex_command/backlog/triage.py` — `_HELD_STATUSES` (38), `_recommendation` (78-87), `_resolve_child`
  (90-92), `_render_epic_block` (95-164), `render` (167-217), `main`'s `render(items, ...)` call (313)
- `cortex_command/backlog/build_epic_map.py` — child envelope `{id, spec, status, title}` (~160); the source
  of the missing `type`
- `tests/` — existing triage render tests will pin the current every-child behaviour and must be updated,
  not deleted
- `skills/dev/SKILL.md` § Step 3 — tells the caller to print `blocks` verbatim; unchanged in shape, but the
  epic-map docstring it leans on ("listing every child regardless of status") will no longer be true

## Provenance

Observed in a consumer repo, 2026-08-06: a `/cortex-core:dev` triage whose epic blocks marked 106 closed
tickets with route verbs and whose footers named 32 of them as refine candidates, including three that had
shipped in the same epic being read.
