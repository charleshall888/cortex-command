---
schema_version: "1"
uuid: 214f63da-2ab6-4497-81b1-fd76f8523c53
title: Dashboard triage board builds its epic map from the active index, so a closed epic's live children render as Unparented
status: complete
priority: low
type: bug
created: 2026-08-06
updated: 2026-08-06
tags: ['dashboard', 'triage', 'epic-map']
areas: ['dashboard']
complexity: moderate
---
## Why

Ticket #438 established that an epic gains children *after* it closes — epic #9 absorbed child
#207 thirty-nine days after being marked complete — and fixed the consequence for the triage
verb by widening its corpus to `index-full.json`. The dashboard's triage board has the same
hole, unfixed.

`cortex_command/dashboard/ticket_feed.py:202` builds its epic map from `active_items`:

```python
epics = build_epic_map(active_items, strict_schema=False)
```

`build_epic_map` detects epics by scanning the list it is given for `type: epic`. A *closed*
epic is not in `active_items`, so it is not detected as an epic at all — and its still-active
children, whose `parent:` points at an id the map has never heard of, fall through
`triage_board.html`'s child-id exclusion into the "Unparented" flat list.

Measured today:

| | epics detected | of corpus | active children shown as Unparented |
|---|---|---|---|
| wild-light | 5 | 24 | **1** (#425, parent #344's sibling epic) |
| cortex-command | 1 | 35 | 0 |

The 5-of-24 and 1-of-35 ratios overstate the harm on their own, and should not be quoted as
the cost: most undetected epics are closed epics whose children are also closed, and an
active-only board is *right* not to render those. The defect is only the active children, and
today that is one row on one repo.

It is worth fixing anyway because the rate rises monotonically with project age and never
falls. The parent-closing cascade closes an epic when its last child closes, so every
subsequent child filed against that epic is orphaned on this board — permanently, and by
design. wild-light is the oldest corpus in the sample and is the leading indicator, not the
ceiling.

## Role

The board groups tickets under their epic so an operator can see what belongs together. A
ticket with a `parent:` should never render as "Unparented" — that is not a missing nicety,
it asserts something false about the ticket.

## Integration

Not a one-line corpus swap. The snapshot's contract is that **every per-row display field
resolves through `snap['items'][id]`** (`triage_board.html:20-27`), and `items` is built from
`active_items`. Feeding `build_epic_map` the full corpus alone would produce group headings
for epics with no record behind them, and child ids that subscript to a Jinja `Undefined`
which renders blank rather than raising — the exact silent-failure mode that docstring exists
to prevent.

So the fork to decide is:

- **Detect epics over the full corpus, group only active children.** Keeps `items`
  active-only; needs the closed epic's own record (id, title, type, status) carried into the
  snapshot so the group heading has something to render. Smallest change consistent with the
  existing contract.
- **Widen `items` to the full corpus** and let the board filter. Larger blast radius —
  `item_order`, `ready`, `ineligible`, and the counts all key off the same list, and the
  board's active-only framing is deliberate.

The first looks right, but the closed epic's heading still has to say something honest: it is
a finished epic with unfinished children, which is a state the current heading vocabulary
("epic / N active") does not express.

## Edges

- **`strict_schema=False` is load-bearing** and must survive the change — the comment at
  `ticket_feed.py:198-201` explains that the default raises on any schema version this process
  did not write, which in a corpus it does not control would kill the poll permanently.
- **The duplicate-row fix at `triage_board.html:229-238` depends on epic ids being in the
  exclusion set.** Adding newly-detected closed epics to `epic_map` widens that set; check the
  `#ticket-{id}` uniqueness that `base.html`'s sessionStorage restore requires still holds,
  since a closed epic has no active row to suppress in the first place.
- **`collect_items` already returns the full corpus** as its fourth value, and `ticket_feed`
  already binds it as `all_items` for the status lookup. The data is in hand; nothing new needs
  reading from disk.
- **Do not reuse the triage verb's rendering.** `cortex_command/backlog/triage.py` now filters
  epic children by status and draws dependency waves for a *text* board consumed once per
  session. The dashboard is a persistent surface with its own row vocabulary, and the two
  should stay independent — #343's boundary was about prose versus code, not about merging
  these two renderers.

## Touch points

- `cortex_command/dashboard/ticket_feed.py` — `build_epic_map(active_items, ...)` (~202); the
  `items`/`item_order` build below it; the schema docstring at the top, which pins `epics` as
  "`build_epic_map` envelope verbatim" and would no longer be true
- `cortex_command/dashboard/templates/triage_board.html` — `epic_map` (215), the child-id
  exclusion (~229-240), the group heading
- `cortex_command/dashboard/tests/test_templates.py` — the grouping-shape and epic-head tests
  (~651-770) pin the current active-only behaviour
- `cortex_command/dashboard/tests/test_seed.py` — `epics["6"]["children"]` (~326-330)
- `cortex_command/dashboard/seed.py` — the fixture corpus needs a closed epic with an active
  child, or the regression cannot be seen in the demo

## Provenance

Found while fixing #456, which removed the same class of blind spot from `cortex-backlog-triage`.
That fix passed the full corpus to `render()`; this is the one consumer of `build_epic_map`
that was not carried along, and the only one left reading the active-only index.
