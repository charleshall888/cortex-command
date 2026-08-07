---
schema_version: "1"
uuid: 52164303-54b2-47a0-abd3-3fbcbbec0f53
title: Session-split hint reads as a question and repeats at every implement batch boundary
status: complete
priority: medium
type: bug
created: 2026-08-07
updated: 2026-08-07
tags: ['session-split', 'build-skill']
areas: ['lifecycle']
complexity: simple
criticality: high
---
## Why

Operator feedback, direct quote, mid-implement on a 15-task lifecycle:

> "Keep going here and stop pausing to ask about continuing in a fresh session."

The hint is *intended* as non-blocking operator information — `skills/build/SKILL.md:65` is explicit
that it is "operator information, never a question to wait on". It does not land that way. Two
compounding causes, one in the verb and one in the skill prose.

**Cause 1 — the verb serves it unconditionally, on every call.**
`cortex_command/lifecycle/next_verb.py:399-400`:

```python
if state in _SESSION_SPLIT_STATES:      # ("plan", "implement") — :162
    envelope["session_split_hint"] = _SESSION_SPLIT_HINT
```

There is no once-per-phase suppression and no record that it has already been served. Every
`cortex-lifecycle-next` in plan or implement carries it, however deep into the phase the session is.

**Cause 2 — the skill's wording invites re-emission at every boundary.**
`SKILL.md:65` says to place it "Entering Plan or Implement", but it sits inside the **Phase
transitions** paragraph that governs *every* boundary summary, immediately beside the mandatory
**Decisions / Scope delta / Blockers / Next** block. A long implement phase has many
batch boundaries and each one renders that block, so the natural reading is to include the hint each
time. On a 15-task plan with 9 topological levels that is up to nine repetitions of the same
sentence.

## The failure

Repetition converts information into a prompt. The sentence names an action only the operator can
take ("re-invoking /cortex-core:build"), so restating it every few minutes reads as the agent
angling to stop — especially at a batch checkpoint, which is exactly where an operator would expect
a genuine gate. The operator then has to spend a turn saying "no, keep going", which is the cost the
hint's non-blocking framing was supposed to avoid.

The irony is that the hint is most repetitive precisely in the long phases where a split would
actually help, so its value and its annoyance scale together.

## Edges

- Serving it once per *phase entry* is not sufficient on its own: `resume` re-enters an in-progress
  implement and should still surface it once, and a genuinely fresh session has no memory that a
  previous one was already told.
- Suppression must not be time-based. A session that has been running for hours across two batches
  wants it less than one entering implement cold.
- The plan arm is not affected in practice — plan has no internal boundaries — so a fix aimed only
  at implement would cover the observed case.
- Do not simply delete the hint. Superlinear context carry is real and the affordance is worth
  surfacing; the defect is cadence, not content.

## Touch-points

- `cortex_command/lifecycle/next_verb.py:162-166` — `_SESSION_SPLIT_STATES` / `_SESSION_SPLIT_HINT`
- `cortex_command/lifecycle/next_verb.py:399-400` — the unconditional attach
- `skills/build/SKILL.md:65` — the "Entering Plan or Implement" clause, currently inside the
  every-boundary Phase-transitions paragraph
- `skills/build/references/implement.md` §2f ("Report the batch before dispatching the next") — the
  per-batch report that inherits the boundary-summary shape

## Sketch

Two candidate shapes, not yet chosen:

1. **Serve once per phase entry.** Attach the hint only when the served state differs from the
   last-recorded phase in `events.log`, or gate it on `at_resume` / first-entry the way
   `path_overview` is already gated at `:401`. Cheap, and the plumbing precedent is right there.
2. **Leave the verb alone, fix the prose.** Move the clause out of the Phase-transitions paragraph
   into Step 2 (entering the resolved state) so it is structurally tied to phase entry rather than
   to boundary summaries. Cheaper still, and it is where the "Entering" wording already points.

(2) alone may be enough, since the envelope field being present is harmless if the skill only reads
it at entry. Prefer it unless a consumer other than the build skill reads the field.
