---
schema_version: "1"
uuid: 4cdc489b-1d76-4de5-8d26-e7a34ebfe834
title: Clarify writes the tier but reconcile-clarify emits the event, so 160 of 314 lifecycles carry a tier with no complexity_override
status: complete
priority: medium
type: bug
created: 2026-08-08
updated: 2026-08-11
tags: ['lifecycle', 'tiering', 'telemetry']
areas: ['lifecycle']
complexity: simple
criticality: low
---
## Why

`#450` states its detector plainly: a tier at `backlog` status is not the signal, *"absence of a corresponding event is."* That detector cannot be used as written, and the cause is in the sanctioned in-lifecycle path rather than in any bypass.

`cortex-update-item --complexity` writes frontmatter and emits nothing. Refine writes the tier back at **Step 2 (Clarify)**, but the only `complexity_override` emitters are `cortex-lifecycle-event complexity-override` and `refine.py`'s `reconcile-clarify`, which runs at **Step 4 (Specify entry)**. Every lifecycle that stops before Specify — and every one whose tier was never re-assessed after research — therefore carries a tier with no event, having been assessed correctly.

Measured 2026-08-08 over `cortex/lifecycle/**/events.log` including `archive/`: **314 lifecycles carry a `lifecycle_start`; 154 also carry a `complexity_override`; 160 do not.** The detector is ~51% false-positive on properly-tracked work alone, before any bypass is considered.

This is the finding that `#459` misattributed to dev rule 4. Rule 4's footprint is ~11 tickets; this is 160, and it is the harness's own path.

## Role

Make "a tier with no corresponding event" mean something, so `#450`'s detector is usable — or retire the detector as unbuildable and say so in `#450`.

## Integration

The natural capture point is Clarify's write-back itself: the moment the tier is decided is the moment it could be recorded, rather than deferring to a reconcile step that half of lifecycles never reach. `refine.py`'s `reconcile-clarify` already appends `to`-keyed `complexity_override` rows and owns the closed clause-tag vocabulary for `reason`, so the emitter exists and the question is where it fires, not whether it needs building.

Weigh against Deletion bias before adding an emission: `#447` (wontfix) concluded the simple bucket is unmeasurable, and no consumer currently reads a backlog `complexity:` except `refine.py:141`'s seed. If nothing reads the event either, retiring `#450`'s detector claim is the cheaper answer and should be priced first.

## Edges

- Do not backfill the 160 historical lifecycles. Their tiers were assessed; only the record's shape is inconsistent, and a retroactive sweep over unknown provenance is the unbounded clause `#459` was trimmed of.
- A Clarify-time emission fires on lifecycles that stop at `simple` and never proceed, which is the majority case — check that this does not just move the noise rather than remove it.
- `#450` remains wontfix on its own (filing-time) grounds regardless of what lands here; this ticket touches only its detector sentence.

## Touch points

- `cortex_command/refine.py:409` — the `complexity_override` row, emitted at reconcile-clarify
- `skills/refine/SKILL.md` Step 2 vs Step 4 — where the tier is written vs where the event fires
- `cortex_command/backlog/update_item.py:625` — writes `complexity:`, emits nothing
- `cortex/backlog/450-*.md` — the detector sentence this either rescues or retires

## Resolution (2026-08-11)

Closed on the Role's **second** arm — the detector was retired in `#450`, and no emission was added. The core diagnosis held; the quantification and three supporting claims did not.

**Held.** Clarify writes the tier at Step 2 while `reconcile-clarify` emits at Step 4, so a lifecycle stopping before Specify carries an assessed tier with no event, and `#450`'s Edge asserting such a ticket "will have both a tier and a matching `complexity_override` event" was false. That sentence is now corrected in place.

**Did not hold.**

- *The populations are disjoint.* `#450`'s detector runs over backlog tickets carrying a tier; its observed case had "no lifecycle directory, no `events.jsonl`, and no `complexity_override` event". This ticket measured lifecycles that already carry a `lifecycle_start`. Of 472 backlog tickets, 323 carry `complexity:` but **0 at `status: backlog` do** — the detector's population is empty, so the "~51% false-positive" rate was computed against a set it never runs on.
- *The Edge's simple-stop assumption is backwards.* The no-event population splits **119 `complex` / 40 `simple`**, not the "majority case" of simple stops the Edge predicted.
- *The Integration's retire-if-unread test never fires.* It is a conditional; `complexity_override` has readers (`common.py:982`'s tier reducer, `complexity_escalator.py:101`, `dashboard/data.py:2114` via `poller.py:297`, pipeline metrics' `initial_tier`), so the antecedent is false and the ticket was left with no criterion for choosing between its arms. None of those readers clears `project.md:23`'s discharge bar anyway — the dashboard is display, the escalator is "Advisory — it writes nothing", the reducer feeds a report verb — so Deletion bias's burden on adding the emission stayed undischarged. That is why this closed unbuilt.
- *Citations drifted.* `refine.py:141` is `seeded.add("criticality")`, not the frontmatter read (that is `:135`); `update_item.py:625` is `("--complexity", None)`, an argparse `_SCALAR_FLAGS` entry, not a write site.

**Unmentioned and relevant.** `lifecycle_start` already carries a `seeded` key (`refine.py:551`) and the override row a `from_seeded` flag (`:407`). They separate a *defaulted* tier from a *frontmatter-derived* one — but not an assessed tier from an unearned one, which is `#450`'s actual complaint — and `seeded` is present on only 19 of 330 rows, a field era rather than a bypass.

**Left open.** The 119 lifecycles holding an unassessed `complex` tier that no `seeded` key can identify is a real corpus finding this ticket surfaced but does not address. File separately if it earns a ticket; it is not the detector problem.
