---
schema_version: "1"
uuid: 25255dee-b16e-43b8-a926-f72cdb289c88
title: Auto-close-parent fires on last-child-terminal alone, closing a parent that has open work of its own
status: backlog
priority: medium
type: bug
created: 2026-08-13
updated: 2026-08-13
tags: ['backlog', 'epic', 'parent', 'auto-close', 'cli']
areas: ['lifecycle']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-08-13, found by sweeping its open backlog for cortex defects that were never
filed upstream. This one had no ticket in either repo — it survived only as a defensive blockquote inside
the affected wild-light ticket, which is why it recurred.

## Why

`_check_and_close_parent` (`cortex_command/backlog/update_item.py:276`) closes a parent as soon as every
child is terminal. It never asks whether the parent has open work of its own — the only parent state it
reads is `status`, and only to decline *reopening* an already-terminal parent.

That is correct when a parent is a pure aggregate (an epic that is nothing but its children). It is wrong
when a parent is a work item that happens to have acquired a child, because the parent's own acceptance
criteria are invisible to the check. The model conflates the two.

## Evidence

wild-light #549 (`the-inventory-surfaces-are-programmer-art…`), `status: in-progress`, carries three
genuinely open acceptance items of its own, all deliberately left to the operator and listed in the ticket
under "What is left, and why this stays `in-progress`". It has exactly one child, #552. When #552 closed,
#549 was flipped `in-progress` → `complete` **twice** — once via `cortex-lifecycle-review-verdict` and once
via `cortex-lifecycle-finalize` — and was reverted by hand both times on 2026-08-13.

Verified still live on **v4.9.3**: the sibling scan collects statuses and parked flags, and nothing in the
path consults the parent beyond `TERMINAL_STATUSES`.

The wild-light ticket's own note is the tell:

> This ticket keeps getting auto-closed, and it should not be. … The rule appears to be "last child closed
> → close parent", and it does not consult this section. … **Expect the next child that completes under
> #549 to close it again — revert, don't accept.**

A standing instruction to revert an automated action, written into the record because there is nowhere
else to put it, is the cost being paid.

## Role

Stop closing a parent that has open work of its own, without giving up the aggregate-epic close that
works.

## Edges

- **The already-closed branch is deliberate and should not be touched.** Its comment states the reasoning —
  reopening would be a read-modify-write with no compare-and-swap, so a race could undo a human close.
  Whatever this ticket does must preserve that asymmetry: decline to close, never auto-reopen.
- **The distinction to make is parent-as-epic vs parent-as-work-item**, and it may already be expressible:
  `build_epic_map.py` exists, and `_is_deferred`/parked handling shows the sibling scan already
  distinguishes child *kinds*. Prefer reading an existing signal over adding a `no-auto-close` opt-out
  field, which puts the burden on every ticket author to predict this.
- **Silence is half the defect.** The already-closed branch prints a `Note:` to stderr precisely because
  "without this the event is invisible". The close leg has no equivalent — the parent flips with no line
  saying it happened, so the operator finds out by noticing a ticket they were working on has gone.
- **Two verbs reach this, not one** (`review-verdict` and `finalize`), so a fix at either call site rather
  than in `_check_and_close_parent` will leave the other live. That is presumably how it got reverted
  twice.

## Touch-points

- `cortex_command/backlog/update_item.py` — `_check_and_close_parent` at `:276`, the `TERMINAL_STATUSES`
  branch at `:318`, the sibling scan following it
- `cortex_command/lifecycle/review_verdict.py`, `cortex_command/lifecycle/finalize.py` — the two callers
  observed flipping the parent
- `cortex_command/backlog/build_epic_map.py` — existing epic-shape knowledge worth reusing
