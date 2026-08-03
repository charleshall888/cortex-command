---
schema_version: "1"
uuid: b0f04331-b8a0-41fc-a00d-e484fdbcda07
title: The implement-rework state is a dead end, so every review rework cycle needs an out-of-band event append
status: backlog
priority: medium
type: bug
created: 2026-08-03
updated: 2026-08-03
tags: ['lifecycle', 'state-machine', 'review', 'rework']
areas: ['backlog']
---
## Why

Observed 2026-08-03 during #425's review phase, on the first rework cycle this lifecycle ran.

`review.rework` moves a feature `review -> implement-rework`. The closed transition table then
has **zero** outgoing edges from `implement-rework`:

    uv run python -c "
    from cortex_command.lifecycle import transition_table as tt
    print(list(tt.transitions_from(\"implement-rework\")))"
    # -> []

All three `implement_transition` arms (`implement.dispatched`, `implement.review`,
`implement.complete`) depart from `implement`, not `implement-rework`. `cortex-lifecycle-next`
agrees — it served `state: implement-rework` with `path_overview.outgoing: []`.

So the rework loop that `skills/build/references/implement.md` §3 prescribes ("dispatch a fresh
sub-task per flagged task ... return to Review") is not representable in the state machine. The
attempt to record the cycle-2 verdict was refused:

    {"state":"refused","refusal":"gate-mismatch",
     "reason":"from_state gate: detected phase 'implement-rework' does not match expected from_state 'review'"}

The documented re-sync remedy does not help: re-running `cortex-lifecycle-next` and threading its
`advance_contract.expected_from_state` just returns `implement-rework` again, which no verb accepts
as a departure state. The only way forward was the envelope's `sanctioned_override` —
hand-appending a `phase_transition` row via `cortex-lifecycle-event log`.

That is a real cost: every review rework on every feature must leave the verb layer and hand-write
an event, which is precisely the hand-written-emission failure mode the served-loop work (#374)
was built to remove.

## Scope

Add the missing edge (or edges) out of `implement-rework`. The natural shape mirrors `implement`:
a rework-completion arm returning to `review`, owned by `implement_transition` so the existing
`--mode transition` call site works unchanged from either state. Worth deciding whether
`implement-rework -> complete` should also exist, or whether rework must always be re-reviewed.

## Edges

- A rework that is abandoned rather than completed — is there a cancel edge from `implement-rework`?
- `tests/test_lifecycle_*` should gain a structural guard that no non-terminal state has an empty
  outgoing set, so the next dead end fails a test rather than a live lifecycle.

## Touch-points

- `cortex_command/lifecycle/transition_table.py` — `TRANSITIONS`, the `review.rework` edge
- `cortex_command/lifecycle/advance.py` — `implement_transition` from_state gate
- `skills/build/references/implement.md` §3 — prescribes the loop that is unrepresentable
- `cortex/lifecycle/triage-routes-ready-items-by-ticket/events.log` — the hand-appended row
