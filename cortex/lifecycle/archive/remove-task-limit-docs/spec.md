# Specification: Remove Task Limit Docs

## Problem Statement

`docs/overnight.md` contains three blocks of guidance that discourage running many features per session: a "3–5 features is the sweet spot" advisory under Best Practices, a "2 is the safe default" closing sentence in the Best Practices Concurrency section, and a duplicate conservative passage in the Advanced/Operator Reference Concurrency section. The system owner asserts these limits are inaccurate — the runner scales well with many tasks. These passages should be removed or replaced with accurate guidance.

## Requirements

1. **Replace the Session size block** (`### Session size`, Best Practices): Remove the "3–5 features is the sweet spot" framing and both rationales for an upper bound (cascading conflicts, context overflow). Replace the entire block with:

   > The runner scales well — you can queue as many features as you like. There is no recommended upper limit.

2. **Remove the conservative closing sentence from Best Practices Concurrency**: Remove the sentence "which is why 2 is the safe default and 3 should only be used for clearly non-overlapping feature sets" from the end of the conflict-detection paragraph. Preserve everything before it (merge time detection, fast-path, repair agent dispatch, `paused` on failure).

3. **Replace the Operator Reference Concurrency advisory** (`### Concurrency`, lines 250–253): The current text reads:

   > The batch runner uses a `ConcurrencyManager` from `throttle.py` to cap parallel workers. Default is 2. Setting it higher than 3 risks git conflicts and API rate limiting — keep it at 2 for most sessions, 3 only when features are clearly independent (non-overlapping file sets).

   Remove the conservative advisory ("Setting it higher than 3 risks...keep it at 2..."). Replace with:

   > The batch runner uses a `ConcurrencyManager` from `throttle.py` to cap parallel workers. Default is 2. The runner scales well at higher concurrency; increase via the plan approval step in `/overnight`.

## Non-Requirements

- Do not change operational defaults (the concurrency default of 2 in `skills/overnight/SKILL.md` is a technical parameter with validation range 1–8, not advisory guidance — leave it as-is).
- Do not modify `requirements/project.md` — it contains no session-size limits.
- Do not change any other section of the Best Practices or Operator Reference sections beyond the three targeted edits.

## Edge Cases

- The Best Practices conflict-detection paragraph spans several sentences ending with "which is why 2 is the safe default and 3 should only be used for clearly non-overlapping feature sets." Remove only that closing sentence — preserve all preceding sentences in the paragraph.

## Technical Constraints

- Edit only `docs/overnight.md`.
