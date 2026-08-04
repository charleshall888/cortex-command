# Review: nearly-all-work-is-rated-complex

## Status of this review

**Independent review was waived by operator decision.** No fresh reviewer agent was dispatched, so nothing here is an independent assessment — the implementing agent wrote this file. It records the mechanical verification that was actually executed and nothing more. The verdict below is `APPROVED` because that is the only value routing to Complete; read it as "operator elected to complete without review", not as "an independent reviewer approved this".

What that leaves unchecked is judgment-level, not mechanical: whether the added sentence will actually change assessor behavior, and whether R3's reading of the spec's self-contradiction (see plan.md Risks) is the right one. Both are recorded rather than resolved.

## What was verified

Commit `46652bc0`. Changed: `skills/refine/references/{clarify-critic.md, clarify.md, size-pin.txt}` plus the three generated `plugins/cortex-core/` mirrors.

| Req | Check | Result |
|---|---|---|
| R1 | `grep -c 'complexity/criticality calibration' clarify-critic.md` | `0` ✓ |
| R1 | Instructions section names only intent clarity, scope boundedness, requirements alignment | ✓ |
| R2 | `grep -c 'Soft cap of 5 rubric dimensions'` | `1`, paragraph byte-identical ✓ |
| R3 | `critic` in §5's Complexity item (delimiter-exclusive slice) | `0` ✓ |
| R3 | `next tier down` in that item | `1` ✓ |
| R4 | `grep -c 'When torn, take the lower tier'` | `1`, unchanged ✓ |
| R4 | quota / target-rate / aim-for language | `0` ✓ |
| R5 | MUST/CRITICAL/REQUIRED tokens added by the diff | `0` ✓ |
| R6 | directory 20568 vs pin 20588 → pin lowered to 20568; `# raised:` count `0` | ✓ |
| R6 | `uv run pytest tests/test_reference_size_ratchet.py` | 9 passed ✓ |
| R7 | `uv run pytest tests/ -q` | 2473 passed, 19 skipped, 1 xfailed — equals baseline ✓ |

The test baseline was run against a working tree byte-identical to the commit (`git diff HEAD -- skills/ plugins/` empty), so it was not re-run after committing.

Both spec phases landed in one commit, satisfying the ordering constraint that Phase 1 must not ship alone.

## Deviations from plan.md, corrected during implementation

- **Task 2's verification instrument was wrong.** `awk '/a/,/b/'` includes its terminating line, so the slice pulled in item 3's literal `` `critical` `` and reported a false positive. Corrected to a delimiter-exclusive slice; the content requirement was satisfied all along.
- **Task 3's Context understated the mirror sequence.** The pre-commit hook rebuilds mirrors from staged blobs, but `test_mirror_dirs_deduplicate` reads the *working tree*, so the suite fails before any commit unless mirrors are synced first. Measured sequence recorded in plan.md: `ratchet-refs` → `build-plugin` → `ratchet-refs`. `build-plugin` does not carry `size-pin.txt`, so the mirror pin had to be committed explicitly or a fresh clone would fail dedupe.
- **Builders were not dispatched.** Tasks ran in-session under this session's standing no-Agent instruction.

## Requirements Drift

**State**: none

**Findings**: None. `cortex/requirements/project.md:40` already ratifies the direction this change implements — "The complexity escalator is the safety valve: doubt classifies down at Clarify, evidence ratchets up." The change operationalizes the "doubt classifies down at Clarify" half, which had no mechanism behind it. No new behavior is introduced that the requirements do not capture, and the short-road predicate is untouched.

**Update needed**: None

**Caveat on coverage**: `cortex-load-requirements` returned `no area docs matched for tags: [lifecycle, tiering, ceremony]` and loaded `project.md` + `glossary.md` only. This is not the index-missing-tags defect review.md §1 describes — `cortex-lifecycle-enter` reported `index: skipped`, and no area doc in `cortex/requirements/` carries tags at all, so no tag can ever match. `pipeline.md` is the doc that governs the refine pipeline; it was read directly for this check. Its tier references (lines 76–80, 118–122) describe the review gating matrix and metrics aggregates, neither of which this change touches.

```
{"verdict": "APPROVED", "cycle": 1, "issues": ["Independent review waived by operator decision — this file is a self-review by the implementing agent, not an independent assessment"], "requirements_drift": "none"}
```
