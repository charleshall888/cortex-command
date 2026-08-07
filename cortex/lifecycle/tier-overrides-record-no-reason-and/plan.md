# Plan: tier-overrides-record-no-reason-and

## Overview

Four small changes to `_cmd_reconcile_clarify` in the wheel, one flag appended to two skill-prose invocations, and three tests. The wheel-side work is independent of the prose-side work (disjoint files), so both land in one wave; the tests depend on both and follow. No new tag is added to `_ALLOWED_REASON_CLAUSES`, so `project.md:64`'s three-site co-edit does not fire.

## Outline

### Phase 1: Verb correctness (tasks: 1, 2)
**Goal**: `_cmd_reconcile_clarify` reports both bad clause tags, omits empty reasons instead of writing `""`, announces a discarded reason, and stops claiming a parity it no longer has — while Step 4 starts passing `--tier-reason`.
**Checkpoint**: the four behaviors are observable from the CLI, and `grep -c -- '--tier-reason' skills/refine/SKILL.md` returns `2`.

### Phase 2: Wire and pin (tasks: 3)
**Goal**: the new behaviors and the prose wiring are pinned by tests, discharging the deletion-bias presumption of removal.
**Checkpoint**: `just test` passes, and deleting the `--tier-reason` argparse block turns the suite red.

## Tasks

### Task 1: Fix the four defects in `_cmd_reconcile_clarify`
- **Files**: `cortex_command/refine.py`
- **What**: De-short-circuit the two-flag validation so both bad tags report in one run; change both reason emit guards from `is not None` to truthiness so an empty reason omits the key; correct the comment that will otherwise claim a cross-writer parity the change removes; and emit one stderr line when a supplied reason is discarded by the no-op guard. Satisfies spec R1–R4.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The validation site is the `or` expression at `:353-356`, calling the `_reason_clause_ok` predicate at `:299-320` (which prints to stderr and returns bool, so de-short-circuiting needs no signature change — assign both results before testing them). The two emit guards are the dict-spreads at `:404` (tier, inside the `_TIER_RANK` comparison block) and `:420-424` (criticality, inside the `_CRITICALITY_RANK` block). The comment to correct is at `:399-403`; it currently ends "matching that module's optional-field handling", which becomes false because `lifecycle_event.py:364` keeps the `is not None` shape and is out of scope — the replacement must state the divergence rather than delete the note. The discard diagnostic belongs where a reason was supplied but its rank comparison did not fire; follow the module's existing stderr idiom (`_UNSAFE_SLUG_MSG` at `:37-39`, used at `:344-346`): one formatted line to stderr. Exit code and the JSON payload on stdout must not change — the payload keys are `{state, rows, tier, criticality}` plus `overrides`. No caller enumeration needed: no signature changes, and `_cmd_reconcile_clarify` is reached only through the `reconcile-clarify` subparser.
- **Verification**: (a) In a scratch lifecycle under the scratchpad, using working-tree code (`uv run python -m cortex_command.refine`, never the PATH binstub which runs the installed wheel): (i) `reconcile-clarify … --tier-reason "badA: x" --criticality-reason "badB: y"` prints **both** a `--tier-reason` and a `--criticality-reason` line to stderr and exits 2; (ii) `… --tier-reason "" --criticality-reason ""` appends rows in which `grep -c '"reason"' events.log` returns `0`; (iii) re-running a reconcile whose tier is already at rank, with `--tier-reason "other: x"`, prints a discard line naming the tier reason and exits 0; (iv) `grep -c "that module's optional-field handling" cortex_command/refine.py` returns `0`. All four fail on HEAD today.
- **Status**: [x] done (93e19551 2026-08-07T15:24:22-04:00)

### Task 2: Pass `--tier-reason` from Step 4's two arms
- **Files**: `skills/refine/SKILL.md`; `tests/test_refine_reconcile_clarify.py` (read-only — run to confirm the existing contiguous pins still match after the flag is appended; do not modify, that is Task 3's job)
- **What**: Append `--tier-reason "{tag}: {why}"` to the Context A and Context B `reconcile-clarify` invocations in Step 4, after the existing `--criticality-reason`, and extend the surrounding sentence so the four clause tags are stated as governing both flags. Satisfies spec R5.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The two invocations are the Context A / Context B bullets in Step 4. The flag **must** be appended after `--criticality-reason`, not interleaved: `tests/test_refine_reconcile_clarify.py:357-368` pins contiguous prefixes of both invocations, and appending leaves them matching (verified). The prose already names the tag set for `--criticality-reason`; extend that sentence rather than adding a second one. Do not add a new tag. Editing this file triggers the pre-commit mirror rebuild into `plugins/cortex-core/skills/refine/SKILL.md` from the staged blob — never hand-stage the mirror. The file is 94 of its 500-line cap, and `skills/refine/references/` is not touched (it sits at zero ratchet headroom).
- **Verification**: (b) `grep -c -- '--tier-reason' skills/refine/SKILL.md` returns `2`; and (a) `uv run python -m pytest tests/test_refine_reconcile_clarify.py::test_refine_non_local_reconcile_branch_is_value_aware` passes, confirming the existing contiguous pins still match.
- **Status**: [x] done (f0cf4ec1 2026-08-07T15:23:17-04:00)

### Task 3: Pin the new behaviors and the wiring
- **Files**: `tests/test_refine_reconcile_clarify.py`; `cortex_command/refine.py` (mutation-check only — the Verification transiently deletes and restores the `--tier-reason` argparse block; no substantive edits, must be byte-identical to Task 1's output when the task ends)
- **What**: Add three tests — one asserting the emitted `complexity_override` row carries a supplied `--tier-reason` (the consumer that discharges the deletion-bias presumption), one asserting both stderr messages appear when both flags carry bad tags, and one bare-existence assertion that `--tier-reason` appears in the SKILL.md body. Satisfies spec R6–R8.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: `test_reconcile_clarify_records_criticality_reason_per_axis` (starts `:399`) is the template for the row-shape tests — same fixture construction, same `main([...])` invocation, same `capsys` envelope read. Assert exact exit codes and positive row shapes, never absence alone. **Do not extend the contiguous pins at `:357-368`**: `docs/policies.md:43` states existing prose pins "hold no standing … do not cite an existing pin as precedent for a new one". The SKILL.md assertion must be a *new, separate* test function containing a bare `--tier-reason in body` check, with a docstring naming the silent failure it prevents — that tier override reasons are never recorded and nothing surfaces the omission — which is what `CLAUDE.md`'s machine-token carve-out requires. Also add the empty-string case (`--tier-reason ""` omits the key), which no existing test covers.
- **Verification**: (a) `just test` passes. (a) Mutation check: delete the `--tier-reason` argparse block from `cortex_command/refine.py`, run `uv run python -m pytest tests/test_refine_reconcile_clarify.py`, observe at least one failure, restore the block and confirm green again. A suite that stays green through that deletion has not discharged the presumption and the task is not done.
- **Status**: [x] done (46600bb7 2026-08-07T15:40:35-04:00)

## Risks

- **The efficacy bet is unproven and this plan cannot prove it.** The change assumes prose wiring makes authors fill the field; the only comparable evidence is the tier axis's own manual `--reason` at 11.6% fill. The spec's re-measure trigger is the mitigation, and it must reach the implementation commit body — it is not enforceable by any task here.
- **Task 1 changes behavior of an already-shipped flag.** `--criticality-reason ""` currently writes `"reason": ""` and will stop. No reader observes the difference (dashboard, report, and overnight readers use `.get()`/truthy access) and no test pins it, but it is a real behavior change beyond the ticket's stated scope, taken because the bug is symmetric and already live.
- **The discard diagnostic is new user-visible output** on a path that was silent, firing in roughly a fifth of real invocations. If it proves noisy the honest fix is to quiet it, not to re-silence the drop.
- **Task 3's `just test` criterion was unsatisfiable as written.** The suite is red on `main` for reasons predating this work: 19 failures in `cortex_command/init/tests/test_handler_ensure.py`, 1 in `tests/test_log_invocation_perf.py`, and 1 in `cortex_command/lifecycle/tests/test_init_ensure.py`. Verified byte-identical at base commit `b8eb8f8f` in a detached probe worktree, so this change introduces zero new failures. The meaningful signal — `tests/test_refine_reconcile_clarify.py` green (14 passed), red under mutation (12 failed) — was confirmed directly. A future plan should name the specific test file rather than the whole suite while `main` is red.
- **Scope deliberately excludes `lifecycle_event.py`'s unvalidated second writer**, so after this lands the two writers of an override row diverge on empty-string handling. Task 1's comment fix records that divergence rather than hiding it; the follow-up is named in the spec's Non-Requirements.
