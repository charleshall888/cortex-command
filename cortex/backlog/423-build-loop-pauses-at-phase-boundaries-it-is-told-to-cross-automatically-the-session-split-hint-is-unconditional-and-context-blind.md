---
schema_version: "1"
uuid: 757b1a7a-2076-4726-9e50-80dc592d5e98
title: build loop pauses at phase boundaries it is told to cross automatically; the session-split hint is unconditional and context-blind
status: complete
priority: medium
type: bug
created: 2026-07-28
updated: 2026-07-29
tags: ['harness', 'lifecycle', 'interactive-loop']
areas: ['build-skill']
---
## Why

**The build loop tells itself to stop at exactly the boundaries it is also told to cross automatically.**
`skills/build/SKILL.md:65` carries both instructions in one paragraph:

> Proceed automatically — announce and continue, no confirmation at boundaries. […] Entering Plan or
> Implement, append the served `session_split_hint` as one line — a suggestion, not a gate.

And the served text (`cortex_command/lifecycle/next_verb.py:154-158`) is:

> "Consider ending this session and resuming fresh — re-invoking /cortex-core:build <feature> routes
> back to this phase, and a fresh session avoids superlinear context carry."

A loop that ends its turn with "consider ending this session" has, in operator-visible terms, paused —
whatever the neighbouring sentence says about not gating. The two sentences do not conflict logically
(a suggestion is not a gate), but they conflict *behaviourally*, and the hint wins because it is the
last thing in the summary.

**Observed 2026-07-28, wild-light #409.** A `build` run reached the implement→review boundary at ~26%
context and stopped to ask whether to proceed, costing an operator round-trip. The operator's
instruction was explicit: *"It should just proceed at review phase and complete stage boundaries
always."*

**The hint is unconditional and has no context signal.** `_SESSION_SPLIT_STATES = ("plan", "implement")`
gates it on *phase*, never on actual context usage — `next_verb.py` takes no such input and cannot
compute one. So the advice fires identically at 26% and at 85%. At 26% it is noise that costs a
round-trip; the one case it exists to serve (genuine superlinear carry) is exactly the case it cannot
detect.

Note the boundaries the operator named — review and complete — are already *outside* `_SESSION_SPLIT_STATES`
and are served no hint at all. That is worth stating plainly, because it locates the defect: the
loop stopped at a boundary where nothing told it to. The hint at the *previous* boundary is what
establishes "pausing to hand off is the house style", and the loop generalised it forward. A fix that
only edits the plan/implement hint text will not, on its own, stop the review/complete pause.

## Role

Make phase-boundary progression unconditional in the interactive loop, and stop emitting advice the
verb has no evidence for.

## Integration

- `cortex_command/lifecycle/next_verb.py:152-158` — `_SESSION_SPLIT_STATES`, `_SESSION_SPLIT_HINT`.
- `skills/build/SKILL.md:65` and its mirror `plugins/cortex-core/skills/build/SKILL.md:65` —
  § Phase transitions. **Both copies must change together**; they are byte-identical today and a
  single-file edit silently ships the old text to plugin consumers.
- `skills/build/references/review.md:53` (`approved` → "announce briefly and auto-advance") and
  `complete.md` — the arms that must stay non-pausing.
- Any `references/*.md` carrying a `<!-- pause: … -->` marker is a *sanctioned* pause and out of scope;
  this ticket is about the unmarked, emergent kind.

## Edges

- **Overnight/headless runs have no operator to ask**, so a boundary pause there is a silent stall
  rather than a question. Whatever the fix, it must not depend on someone answering.
- **Removing the hint entirely is a real option** and should be weighed, not assumed away: it is
  advice the emitter cannot substantiate. The counter-argument is that long `build` runs genuinely do
  degrade, and a fresh session at a phase boundary is cheap because re-invoking `/cortex-core:build
  <feature>` routes straight back. If the hint survives, it needs a context signal to gate on, which
  means a new input to `next_verb` rather than a prose edit.
- **A pause is legitimate when the phase itself demands consent** (plan approval, batch-failure
  triage). Those are marked with `<!-- pause: … -->` and must keep working.
- **Do not fix this by adding a "never stop" instruction alone.** The loop already had one and
  stopped anyway. The instruction that competes with it has to go or be gated.

## Touch-points

- `cortex_command/lifecycle/next_verb.py`
- `skills/build/SKILL.md` + `plugins/cortex-core/skills/build/SKILL.md` (keep in sync)
- `skills/build/references/review.md`, `skills/build/references/complete.md`
- Tests covering `next_verb`'s envelope shape — a removed or newly-gated `session_split_hint` key will
  move any assertion that pins the plan/implement envelope.