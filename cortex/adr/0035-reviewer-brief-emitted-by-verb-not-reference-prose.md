---
status: accepted
---

# 0035 — Reviewer brief emitted by verb, not reference prose

_Decision date: 2026-08-07 (#455 — a rework re-review re-reads the whole spec with no way to scope it)._

## Context

The review phase's output shape — stage definitions, the Requirements Drift section format, the
Verdict JSON schema — has always lived in `skills/build/references/review.md`, prose re-read in full on every
review dispatch. That directory is at its down-only ratchet ceiling with zero headroom, and a second,
independent copy of the same specification lives in `cortex_command/pipeline/prompts/review.md` for the
overnight path, where it has already drifted (the overnight cycle-2 path appends a sentence rather than scoping,
and never passes the prior issues).

## Decision

A wheel-side verb emits the reviewer brief for both modes and both consumers; the prose keeps only
control flow and the call.

## Trade-off

Gains: one source of truth across two consumers that have already drifted; the byte budget the
restructure needs; and removal of a perverse incentive to hide prose in the unmeasured prompts directory. Costs:
it tightens wheel↔prose coupling — today a stale wheel cannot change what a reviewer is told, afterwards it can
— so the brief's shape becomes protocol-governed and a shape change is a `PROTOCOL_VERSION` floor bump. It also
makes the review's instructions less greppable, since a reader of `review.md` will no longer find the output
shape there. Hard to reverse: unwinding means restoring deleted prose into a directory with no bytes to spare
and moving the protocol floor back.

## Consequence: `PROTOCOL_VERSION` is not bumped by this ticket

Introducing the verb itself does not move `cortex_command/lifecycle/protocol.py`'s `PROTOCOL_VERSION`. Requirement
9 governs *shape* changes to the served payload, and standing up the verb changes no served payload — it moves
where existing prose lives, not what a reviewer is ultimately told. Requirement 19 additionally makes a stale
wheel degrade gracefully: an absent, erroring, or unreadable verb falls open to a full review rather than
halting the loop. A floor bump would contradict that fail-open design by forcing every out-of-repo consumer
running an older wheel to halt on version skew instead of degrading, stranding installs this ticket is explicitly
built not to strand. A future change to the brief's *shape* — not its point of origin — is what would move the
floor.

## Cross-references

- Spec: `cortex/lifecycle/a-rework-re-review-re-reads/spec.md` — Requirements 5, 9, 12, 19; Proposed ADR
  (originally numbered 0030 there; renumbered to 0035 here, as 0030 was already taken by
  `0030-mode-agnostic-interactive-dispatch.md`).
- Ticket: #455 — a rework re-review re-reads the whole spec with no way to scope it.
