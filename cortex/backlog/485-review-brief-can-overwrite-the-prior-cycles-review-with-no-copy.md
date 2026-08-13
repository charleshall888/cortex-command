---
schema_version: "1"
uuid: 8c14b7f2-9e60-4d3a-b5a1-72f9de3c8e04
title: review-brief can overwrite the prior cycle's review.md with no copy anywhere
status: complete
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

## Resolution (2026-08-12)

Implemented as suggested, with one addition the suggested shape did not cover.

1. **The archive is unconditional.** `_archive_prior_cycle` fired only at `cycle >= 2`; it now fires
   whenever `review.md` exists. The old guard made the one input *known* to be untrustworthy — the
   derived cycle — decide whether the prior review survived. Loss of the artifact is unrecoverable
   and a surplus archive costs one small tracked file, so the error directions are not close.

2. **The name, not the copy, absorbs a wrong cycle.** At `cycle >= 2` the target is
   `review-cycle-{N-1}.md`, byte-for-byte the historical behaviour, so the happy path and the rework
   brief's own read are unchanged. Only in the `cycle < 2`-with-a-`review.md` case (the #485 shape)
   does the name come from elsewhere: the artifact's own fenced verdict block declares the cycle its
   author believed it was writing, falling back to `review-cycle-prior.md` when unparseable. The
   derived cycle is preferred where it is trustworthy and never trusted where it is not.

3. **Convergence moved from the name to the content.** The old idempotency (`target.exists()` → no-op)
   keyed off a name derived from the cycle, so an unconditional archive keyed the same way would grow
   the tree on every re-dispatch — trading data loss for litter. An existing `review-cycle-*.md`
   byte-identical to `review.md` now *is* the archive. Only when no archive holds those bytes **and**
   the preferred name is occupied by different content does the name take an `-a`/`-b`… suffix; that
   is exactly the branch where the old code overwrote. `stage-artifacts` globs `review-cycle-*.md`,
   so suffixed archives are staged without change.

4. **An unarchivable `review.md` refuses.** Exit 1, nothing on stdout. Emitting the brief is what
   licenses the reviewer to overwrite, so failing open here would reach the same total loss through
   the fail-open path instead of through the cycle guard.

5. **The resolved cycle and archive path are emitted** — `cycle N · {mode} · log {path} · archived
   {name}` on stderr, after any `DEGRADED:` line. The ticket's last edge is right that the brief's own
   header was the only cycle signal and was itself the wrong thing; this line adds the two independent
   facts a caller can check it against.

The rework-scoped-mode dependency the third edge names is unchanged and still keys off the cycle. That
is the survivable half (a wasteful full review at a rework boundary), and #484's anchor fix removes the
observed cause of a mis-derived cycle at the source.

### Verification

Five new tests in `cortex_command/lifecycle/tests/test_review_brief_cli.py`: archive-at-cycle-1, the
unparseable-verdict fallback name, re-run convergence, no-clobber under a suffix, and the refusal path.
`test_running_twice_produces_an_identical_tree` and `test_preexisting_archive_checksum_is_unchanged`
(the pre-existing convergence pins) still pass unmodified.
