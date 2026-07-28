# Plan: make-the-review-verdict-transition-record

## Overview

Delete caller-supplied `from_state` at all three `advance` call sites so the closed transition
table's own per-verb `from_state` is the expected departure state, pin that per-verb invariant with
a test, fix the morning-review call site's arm selection / corrupted-gate / silent-refusal defects,
and rebuild the three fixtures whose missing or misspelled `phase_transition` rows made the bug
invisible to CI.

## Outline

### Phase 1: Gate agreement (tasks: 1, 2, 3)
**Goal**: the events-first gate accepts the transitions the overnight pipeline arms actually
perform, and the invariant that makes omission safe is enforced in CI.
**Checkpoint**: on a lifecycle dir seeded with a realistic machine-row chain, `_advance_to_review`
and `_advance_review_complete` both return `state` ≠ `"refused"` and append their rows, pinned by a
test with no either-branch escape; `_current_phase` is gone repo-wide.

### Phase 2: Morning-review correctness (tasks: 4, 5)
**Goal**: `cortex-morning-review-advance-lifecycle` fires the right arm for each branch, treats a
corrupted reduction as review-required, and reports a refusal instead of success.
**Checkpoint**: the no-review branch records one `phase_transition` implement→complete and no
`review_verdict`; a corrupted reduction returns `missing-review`; a refused advance returns
`advance-refused` with a warning naming the feature; the walkthrough documents both that state and
a catch-all for any unlisted one.

## Tasks

### Task 1: Drop caller-supplied `from_state` from both pipeline arms and pin the result
- **Files**: `cortex_command/pipeline/review_dispatch.py`,
  `cortex_command/pipeline/tests/test_review_verdict_recording.py`
- **What**: Both overnight arms call `advance` without a `from_state` argument, so the table's own
  `from_state` stands; `_current_phase` and its `detect_lifecycle_phase` import are deleted; the
  test's fixture is reseeded with realistic `"from"`/`"to"` machine rows and its
  either-branch-passes structure is replaced with a single pinned outcome. (Spec R1, R2, R8 in
  part, R9.)
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `_current_phase` at `review_dispatch.py:39-48`; its only callers are `_advance_to_review`
    (`:103`) and `_advance_review_complete` (`:140`) — no other importer repo-wide.
  - `advance` falls back to `effective_from = transition.from_state` when `from_state is None`
    (`advance.py:947`). Table values: `implement.review` → `"implement"`
    (`transition_table.py:457`); `review.approved` → `"review"` (`:339`).
  - `_advance_review_complete`'s docstring carries a "KNOWN DEFECT (unfixed…)" paragraph
    (`:113-131`) asserting a hardcoded `"review"` "was tried and rejected". Research disproved that
    claim (it rested on the misspelled-key fixture below, and no commit ever tried it). Rewrite the
    paragraph to state what now holds; do not leave it stale.
  - Keep `_advance_or_warn` (`:51-83`) and both call shapes — only the `from_state=` kwarg goes.
    `tests/test_fold_completion.py:33-41,94-102,140-163` requires this module to retain a call whose
    name contains `"advance"` and forbids any `log_event`/`log_event_at` call naming
    `phase_transition`/`review_verdict`/`feature_complete`/`spec_approved`/`plan_approved`.
  - Fixture: `test_review_verdict_recording.py:_seed_feature` (`:31-46`) seeds
    `{"from_phase": "implement", "to_phase": "review"}`, but `common.py:535` reads `event.get("to")`
    — the row is invisible to `resolve_lifecycle_phase`, forcing artifact fallback in both
    detectors. This is the sole repo-wide occurrence of those keys. Reseed a realistic chain with
    `"from"`/`"to"`: `lifecycle_start`, `phase_transition` specify→plan, `plan_approved`,
    `phase_transition` plan→implement, `phase_transition` implement→review; keep the existing
    `plan.md` (all `[x]`) and APPROVED `review.md`.
  - The rebuilt test asserts `resolve_lifecycle_phase(log.parent)["phase"] == "review"` before the
    call, then unconditionally asserts that `_advance_review_complete(_FEATURE, 1, log)` appended a
    `review_verdict` line carrying `"verdict": "APPROVED"` and `"cycle": 1` and a `phase_transition`
    line carrying `"from": "review"` and `"to": "complete"`. Retain
    `test_advance_failure_never_raises` (`:79-82`) — best-effort is still the contract.
  - The module docstring (`:1-17`) narrates the unfixed defect; update it to describe what the file
    now pins.
- **Verification**: `git grep -n '_current_phase\|detect_lifecycle_phase' -- cortex_command/pipeline/review_dispatch.py`
  and `git grep -n 'from_phase\|to_phase' -- '*.py'` and
  `grep -n 'if appended' cortex_command/pipeline/tests/test_review_verdict_recording.py` each return
  no matches; `uv run pytest cortex_command/pipeline/tests/test_review_verdict_recording.py tests/test_fold_completion.py -q`
  exits 0 (baseline: 79 passed across the five affected files).
- **Status**: [ ] pending

### Task 2: Name omission as a sanctioned remedy in the from-state refusal
- **Files**: `cortex_command/lifecycle/advance.py`, `cortex_command/lifecycle/tests/test_advance.py`
- **What**: The gate-mismatch refusal's `preferred_remedy` gains a clause telling a caller that
  already knows which verb it is firing to omit `--from-state` and let the table's `from_state`
  stand, so a future maintainer reading the refusal is not led back into this bug. (Spec R11.)
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - The string is the `preferred_remedy` value inside the `phase != effective_from` refusal envelope
    at `advance.py:1007-1011`. The existing re-sync clause and its "never pass the detected phase"
    warning are retained verbatim; the omission clause is added alongside, not instead.
  - The interactive re-sync route the current text describes is real and stays correct — it is what
    `skills/build/SKILL.md` § Advance-verb routing and `skills/build/references/plan.md:116` thread
    through `--from-state`. The new clause is for programmatic callers only.
  - The existing gate-mismatch test is `cortex_command/lifecycle/tests/test_advance.py:366-374`
    (asserts `state == "refused"`, `refusal == "gate-mismatch"`); extend it to assert both clauses
    are present in `preferred_remedy` rather than adding a parallel test.
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_advance.py -q` exits 0 and
  `grep -c 'preferred_remedy' cortex_command/lifecycle/tests/test_advance.py` ≥ 1.
- **Status**: [ ] pending

### Task 3: Pin the per-verb `from_state` invariant
- **Files**: `cortex_command/lifecycle/tests/test_transition_table.py`
- **What**: A test groups `TRANSITIONS` by `owning_verb` and asserts each group's `from_state` set
  has exactly one member, converting the unguarded design belief that Tasks 1 and 5 rely on into a
  CI-enforced invariant. (Spec R10.)
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `_check_invariants` (`transition_table.py:546-583`) asserts only that `(owning_verb,
    decision_state)` arm keys are unique; a rogue row giving an existing verb a divergent
    `from_state` passes it cleanly (measured). Do **not** modify `_check_invariants` — spec
    Non-Requirements: an import-time assert would break every import of the module mid-edit, so the
    invariant is pinned by a test that fails in CI instead.
  - Today's table satisfies it: all three `review_verdict` arms are `from_state="review"`
    (`:339,352,365`); all three `implement_transition` arms, including the batch arm, are
    `"implement"` (`:447,457,474`).
  - Sibling structural assertions live at `:199-218` (`test_transition_ids_and_arms_are_unique`,
    `test_all_edge_endpoints_are_declared_states`) — follow their shape and placement.
  - The grouping check must be discriminating, not vacuous: factor it into a helper the test applies
    to `tt.TRANSITIONS`, and add a second test applying the same helper to a locally constructed
    list containing a divergent row and asserting it fails. Do not prove discriminating power by
    editing the real table.
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_transition_table.py -q`
  exits 0 with two more tests collected than the baseline.
- **Status**: [ ] pending

### Task 4: Document `advance-refused` and correct the stale event-count prose
- **Files**: `skills/morning-review/references/walkthrough.md`,
  `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md` (generated output of
  `just build-plugin` — regenerate it to verify, never hand-edit and never `git add` it)
- **What**: Section 2b's state table gains an `advance-refused` row plus a catch-all instruction for
  any state absent from the table, and the stale synthetic-event-count prose is corrected to what
  the arms now emit. (Spec R7.)
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Edit the canonical source only. `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md`
    is a build-output mirror rebuilt from staged blobs by `.githooks/pre-commit` and folded into the
    commit (`justfile:633-671`, `cortex-overnight` → `SKILLS=(overnight morning-review)`); never
    stage it by hand (CLAUDE.md).
  - Stale prose at `:186`: "four synthetic events when review isn't required; two when a real
    `cycle >= 1` review already ran but `feature_complete` is missing". Post-fix truth: the
    no-review branch emits one `phase_transition` implement→complete; the crash-recovery branch
    emits `review_verdict` + `phase_transition` review→complete, or `phase_transition` alone when a
    real verdict row is already present.
  - State table at `:191-196` maps five states; `error` (reachable via `main()`'s except clause,
    `advance_lifecycle.py:263`) is already unmapped today, which is what the catch-all closes. The
    `advance-refused` line must tell the operator that no completion row landed and the feature
    needs attention — not merely name the state.
  - `docs/policies.md` owns the overnight docs ownership map and the tone policy; read it before
    editing this file (CLAUDE.md).
- **Verification**: `grep -c 'advance-refused' skills/morning-review/references/walkthrough.md` ≥ 1
  and `grep -c 'four synthetic events' skills/morning-review/references/walkthrough.md` = 0; after
  `just build-plugin` (working tree only, nothing staged) both checks hold for
  `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md`.
- **Status**: [ ] pending

### Task 5: Make the morning-review call site route, gate, and report correctly
- **Files**: `cortex_command/overnight/advance_lifecycle.py`,
  `tests/test_cortex_morning_review_advance_lifecycle.py`
- **What**: `advance_lifecycle` stops deriving `from_state` from artifacts, fires the
  implement-exit arm on the no-review branch and asserts the route it got, treats a corrupted
  reduction as review-required, and turns a refused advance into an audible `advance-refused`; its
  two fixtures are reseeded with realistic machine rows. (Spec R3, R4, R5, R6, R8 in part, R12.)
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - **R3** — delete `from_state = str(detect_lifecycle_phase(feature_dir).get("phase") or "review")`
    (`:225`) and the `detect_lifecycle_phase` import (`:74-78`); the `advance` call omits
    `from_state`.
  - **R4** — when `review_required` is false, call
    `advance(verb="implement-transition", mode="transition", feature=..., project_root=root)` rather
    than the `review-verdict` arm. That arm resolves its own route from the reduction
    (`advance.py:445` → `implement_transition._resolve_route`) and emits
    `phase_transition{from: implement, to: <route>, tier}`; its envelope's `state`/`to_state` is the
    route. The crash-recovery branch keeps the `review-verdict` arm with
    `verdict="APPROVED"`, the `_last_real_review_cycle` cycle, and `drift="none"`.
  - **R4 route assertion** — when the arm's route is not `complete`, `advance_lifecycle` must not
    return `advanced-complete`. Return the existing `missing-review` state (the arm's own verdict is
    that this feature needs review); spec Non-Requirements forbid any new state beyond
    `advance-refused`, so do not invent one.
  - **R5** — `review_required` (`:197-200`) must additionally be true when `reduction.corrupted` is
    true, matching `implement_transition._resolve_route`'s `corrupted → ("review", "complex")`
    (`implement_transition.py:139-162`). Without this the caller and the arm disagree: the caller
    takes the no-review branch, the arm routes to `review`, and because `_is_machine_complete`
    (`:168-176`) matches only `to: "complete"` every later run replays and reports completion
    forever. Any future edit to either rule must change both.
  - **R6** — inspect `advance`'s envelope (today discarded, `:226-238`). On `state == "refused"`,
    log a warning naming the feature, the refusal/reason, and the events log path, and return the
    literal `"advance-refused"`. Add that literal to `KNOWN_STATES` (`:82-89`) and to the module
    docstring's `States:` list (`:38-59`) — both are closed enumerations that
    `tests/test_cortex_morning_review_advance_lifecycle.py:244` treats as authoritative
    (`assert seen <= set(al.KNOWN_STATES)`). `_advance_or_warn`
    (`review_dispatch.py:51-83`) is the shape to follow; it lives in a sibling module and is not
    imported here. Best-effort stays the contract: return a state, never raise.
  - **R8/R12 fixtures** — `:67-106` (`test_simple_medium_advances_via_folded_advance_body`) and
    `:145-173` (`test_crash_recovery_appends_two_events`) seed no `phase_transition` rows at all, so
    both exercise only the degenerate artifact-fallback path; `:104` pins
    `complete_row["from"] == "review"` for a feature that was never reviewed. Reseed each with a
    realistic chain using `"from"`/`"to"` (short road for the no-review case:
    `lifecycle_start` simple/medium, `spec_approved`, `phase_transition` specify→implement; long
    road for crash recovery: through `implement→review` with a real `review_verdict` cycle ≥ 1), and
    assert `resolve_lifecycle_phase(fd)["phase"]` equals the intended pre-transition state before
    the call.
  - Expected post-fix assertions: no-review branch → exactly one `phase_transition{from: implement,
    to: complete}`, **no** `review_verdict` row, `state == "advanced-complete"`; crash recovery →
    `phase_transition{from: review, to: complete}` only, no duplicate verdict.
  - New tests to add: corrupted reduction (torn line, no recoverable tier axis) → `missing-review`
    and no `phase_transition` appended; refusal path → seed `lifecycle_start` complex/high plus
    `review_verdict{cycle: 1, verdict: "APPROVED"}` with **no** `phase_transition` row (so
    `_is_machine_complete` does not short-circuit at `:194`) and an on-disk APPROVED `review.md`,
    expect `state == "advance-refused"`, a `caplog` warning naming the feature, and
    `"advance-refused" in al.KNOWN_STATES`; a route-diverged case asserting the returned state is
    not `advanced-complete`; and an end-to-end case seeding a realistic post-review log, running the
    approved path, then asserting a second `advance_lifecycle` call returns `"already-complete"`.
  - `test_every_state_is_known` (`:213-247`) asserts an exact `seen == {...}` set as well as the
    subset relation — extend it to reach `advance-refused` or leave its set intact deliberately, but
    do not let it silently drift.
  - `tests/test_fold_completion.py` applies the same no-`log_event`-transition-vocabulary
    discriminator to this module; the fix must go through `advance`.
  - Consumers of the returned `state` (enumerated repo-wide, measured): `main()` in this same file,
    `skills/morning-review/references/walkthrough.md`'s Section 2b table (Task 4 owns it), and
    `tests/test_cortex_morning_review_advance_lifecycle.py`. No dashboard, report, or metrics module
    reads it — adding `advance-refused` breaks no other reader.
- **Verification**: `just test` exits 0; and both
  `git grep -n 'detect_lifecycle_phase' -- cortex_command/overnight/advance_lifecycle.py` and
  `git grep -n 'from_state=' -- cortex_command/overnight/advance_lifecycle.py` return no matches
  (the kwarg and the import, not explanatory prose).
- **Status**: [ ] pending

## Risks

- **Returning `missing-review` on a diverged route (Task 5)** is a design call the spec constrains
  but does not name: R4 requires only "not `advanced-complete`", and Non-Requirements forbid a new
  state. `missing-review` is the closest existing meaning; the alternative would be a new state the
  spec rules out.
- **A no-review feature stops receiving a `review_verdict` row.** Spec-sanctioned (that row was a
  byproduct of firing the review arm at an unreviewed feature, and `_has_real_review_verdict`
  already excludes `cycle: 0`), but it is a visible change to the events log's shape for anyone
  reading it by eye.
- **Corrupted logs stop auto-completing** and now route to `missing-review`. That is the point of
  R5, but it converts silent (wrong) completions into operator work.
- **The guarantee is workflow-conditional.** An enforcement-bearing pause with an unmapped slug, or
  a recorded-but-unmerged PR, still refuses by design; post-fix those refusals are audible rather
  than silent, which is the whole improvement at those paths.
- **Task 4's mirror is regenerated, not authored.** If the pre-commit hook is not installed
  (`just setup-githooks`), the mirror will not land in the commit and R7's second file stays stale.

## Acceptance

On a realistic machine-row chain, an APPROVED overnight review lands both a
`review_verdict{cycle >= 1}` and a `phase_transition{from: review, to: complete}`, so
`cortex-morning-review-advance-lifecycle` reports `already-complete`, not `missing-review`.
A no-review feature records one `phase_transition{from: implement, to: complete}` and no verdict; a
corrupted reduction returns `missing-review`; a refusal returns `advance-refused` with a warning
naming the feature. `just test` exits 0.
