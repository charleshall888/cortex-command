---
schema_version: "1"
uuid: 8c14b7f2-9e60-4d3a-b5a1-72f9de3c8e04
title: review-brief can overwrite the prior cycle's review.md with no copy anywhere
status: backlog
priority: medium
type: bug
created: 2026-08-12
updated: 2026-08-12
tags: ['lifecycle', 'review', 'cli', 'data-loss']
areas: ['lifecycle']
---
Filed from wild-light, 2026-08-12, during `/cortex-core:build` on ticket #478
(`wet-sand-darkening-on-the-terrain`). Related to #484 but separable — this one bites even when the log
anchor is correct.

## Why

`cortex-lifecycle-review-brief` is documented as the verb that *"archives the prior cycle's `review.md`,
selects full or rework-scoped mode, records the dispatch baseline, and emits the brief"*. The reviewer is
then told to write `review.md`, and the single-writer rule means it overwrites in place.

**If the archive step does not fire, the previous cycle's review is destroyed with no copy anywhere.** In
the observed run it did not fire: the verb emitted `cycle 1 · full review` for what was really cycle 2,
and `review.md` was still the cycle-1 file, unarchived. Had the reviewer been dispatched on that brief,
cycle 1's findings — the ones that caught a real defect — would have been gone.

They survived only because the orchestrating agent noticed the cycle label was wrong, checked the
authoritative log, and ran `cp review.md review-cycle-1.md` by hand.

## Role

Make the archive unconditional and independent of the cycle computation, so a mis-derived cycle number
cannot cause data loss.

## Edges

- **The two failures are coupled today and should not be.** The cycle number is derived (from
  `events.log`) and the archive decision keys off it. A wrong cycle number therefore silently disables the
  archive. Archiving whenever `review.md` exists is unconditional, cheap, and correct regardless.
- **The loss is total and silent.** There is no `.bak`, no git safety net (the file is typically
  uncommitted at that moment — it was written by the reviewer during the same phase), and no message.
- **Rework-scoped mode has the same dependency.** The verb also selects full vs rework-scoped from the
  cycle; a mis-derived cycle sends a *fresh full* review at a rework boundary, which is wasteful but
  survivable — unlike the overwrite, which is not.
- **A caller cannot detect this from the brief alone.** The brief's own header is the only cycle signal it
  emits, and that header is the thing that is wrong.

## Suggested shape

1. Archive `review.md` → `review-cycle-<n>.md` **whenever the file exists**, before emitting anything,
   independent of what `n` is believed to be. Fall back to a timestamp if the cycle is unknown.
2. Emit the resolved cycle and the archive path in the verb's output so the caller can sanity-check both.
3. Refuse to emit a brief at all if `review.md` exists and could not be archived.

## Touch points

- `cortex_command/lifecycle/` — the `review-brief` entry point (archive step + cycle derivation)
- The review phase reference's single-writer rule, which is what makes the overwrite total
