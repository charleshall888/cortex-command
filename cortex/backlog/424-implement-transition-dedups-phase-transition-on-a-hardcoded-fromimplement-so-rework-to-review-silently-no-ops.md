---
schema_version: "1"
uuid: a147090a-4423-436e-a953-d469bca58443
title: implement-transition dedups phase_transition on a hardcoded from=implement, so rework to review silently no-ops
status: backlog
priority: medium
type: fix
created: 2026-07-29
updated: 2026-07-29
tags: ['lifecycle', 'advance', 'idempotency']
areas: ['lifecycle']
---
## Why

**Observed twice, in two separate features, both times costing a stalled lifecycle that only a hand-append
cleared.** After a `CHANGES_REQUESTED` rework lands and the orchestrator returns rework → Review,
`cortex-lifecycle-advance implement-transition --mode transition` returns a **success-shaped envelope that
wrote nothing**:

```json
{"state":"review","feature":"...","from_state":"implement","to_state":"review","advanced":true,"replay":"already-emitted","emitted":[]}
```

`advanced: true` and `state: "review"` both read as success. But `emitted: []` means no row was written, so
`cortex-lifecycle-next` keeps serving `implement-rework` forever and the feature cannot reach Review.

- **wild-light #367**, cycle 1→2, 2026-07-27.
- **wild-light #375**, cycle 1→2, 2026-07-29 — identical envelope, identical remedy.

Passing `--from-state implement-rework` does **not** help (tried in both). The only thing that clears it is
the sanctioned hand-append:

```bash
cortex-lifecycle-event log --event phase_transition --feature <slug> --set from=implement-rework --set to=review
```

Two independent reproductions with the same workaround make this a defect to fix at the root rather than a
per-session ritual. The cost is not just the workaround: an operator who trusts the success envelope and
does not re-check the served state will believe the feature advanced when it did not.

## Role

Makes the implement arm's idempotent-replay check distinguish its two legal departure states, so a genuine
second transition is emitted instead of being swallowed by the first one's row.

## Integration

`cortex_command/lifecycle/advance.py:472-474`, the `implement-transition` / `transition` arm:

```python
emissions = [
    {"event": "phase_transition",
     "fields": [("from", "implement"), ("to", route), ("tier", tier)],
     "match": {"from": "implement", "to": route}},
]
```

Both `fields` and `match` hardcode the string literal `"implement"`. The replay guard at `:982` then asks
`_row_present(rows, "phase_transition", {"from": "implement", "to": "review"})` — and cycle 1's genuine
`implement → review` row satisfies it, so the arm short-circuits at `:984` and emits nothing.

The neighbouring `review-verdict` arm at `:426` hardcodes `{"from": "review", "to": target}` and is
**correct**, because `review-verdict` has exactly one departure state. The implement arm has **two** —
`implement` and `implement-rework` — which is why this arm alone breaks. That asymmetry is the whole bug.

Note the emitted row is also wrong on its own terms when it does fire from rework: `fields` would record
`from: "implement"` for a transition that actually departed `implement-rework`, so the event log
misattributes provenance even in the non-deduped case.

## Edges

- **The fix must stay idempotent for the case the guard exists for.** A true retry of the *same*
  rework→review transition must still replay cleanly; only a *different* `(from, to)` pair should be
  treated as new. Keying the match on the effective departure state rather than the literal gives both.
- **`--from-state` is already threaded into the function** as `effective_from` (`advance.py:971`), but it is
  computed *after* the emissions list is built at `:474`. Either hoist that resolution above the arm
  dispatch or resolve the departure state inside the arm.
- **Back-compat with existing logs.** Live `events.log` files already contain `phase_transition` rows
  written with `from: "implement"` for transitions that departed `implement-rework`. A stricter match will
  see those as non-matching and could re-emit on replay against an old log. Decide whether that is
  acceptable (a duplicate row is benign and the reducer takes the latest) or whether the match should
  tolerate a legacy `from: "implement"` row when the effective from-state is `implement-rework`.
- Cycles ≥3 are not reachable today — a second `CHANGES_REQUESTED` escalates — so the only pair that needs
  to be distinguishable is `implement→review` vs `implement-rework→review`.

## Touch points

- `cortex_command/lifecycle/advance.py:472-474` — the hardcoded `from` in `fields` and `match`.
- `cortex_command/lifecycle/advance.py:978-987` — the replay short-circuit that consumes `match`.
- `cortex_command/lifecycle/advance.py:248-260` — `_row_present`, the matcher itself (likely unchanged).
- `cortex_command/lifecycle/tests/test_advance.py:254, :300, :506` — existing `already-emitted` assertions;
  a regression test belongs here asserting that `implement-rework → review` emits after
  `implement → review` already exists in the log.
- `skills/build/references/implement.md` §4 — documents this transition; may warrant a line telling callers
  to treat `emitted: []` as a no-op and re-check the served state.

## Acceptance

- Against a log already containing `phase_transition{from: implement, to: review}`, invoking
  `implement-transition --mode transition` from `implement-rework` **emits** a
  `phase_transition{from: implement-rework, to: review}` row, and `cortex-lifecycle-next` subsequently
  serves `review`.
- Re-invoking that same rework transition a second time returns `already-emitted` with `emitted: []` and
  writes no duplicate.
- The existing `already-emitted` behaviour for `implement → review` and for batch dispatch is unchanged
  (`test_advance.py` stays green).
