# Specification: make-the-review-verdict-transition-record

## Problem Statement

An APPROVED overnight review can record nothing. The overnight lifecycle arms hand
`advance`'s `from_state` gate a phase derived from the **artifact-presence** detector
(`common.detect_lifecycle_phase`, the documented legacy fallback) while the gate itself resolves
phase **events-first** (`common.resolve_lifecycle_phase`, ADR-0025). The two disagree on any
realistic log, so the gate refuses and neither the `review_verdict` row nor the
`phase_transition review→complete` row is written — they share one gated emission list, so a
refusal loses both. The visible symptom lands hours later in a different tool:
`cortex-morning-review-advance-lifecycle` reports `missing-review` for a feature that was in
fact reviewed and approved, which on 2026-07-28 led an operator to conclude a passing feature had
merged unreviewed and to hold PR #27 on that false basis. Beneficiaries: the overnight
runner's completion record, morning review's accuracy, and `metrics.py`'s completion detection —
all three read rows that currently never land.

## Phases

- **Phase 1: Gate agreement** — stop supplying an artifact-derived `from_state` at every call
  site, so the events-first gate accepts the transitions the arms actually perform.
- **Phase 2: Morning-review correctness** — fire the correct arm for un-reviewed features, keep
  the two derivations of the review predicate aligned, and make a refusal at that call site
  audible instead of reported as success.

## Requirements

1. **Neither pipeline arm supplies `from_state`.** `_advance_to_review` and
   `_advance_review_complete` (`cortex_command/pipeline/review_dispatch.py`) call `advance`
   without a `from_state` argument, letting it use the closed transition table's own
   `from_state` (`advance.py:947`). Acceptance: on a lifecycle dir seeded with a realistic log
   (`specify→plan`, `plan_approved`, `plan→implement`, and for the review arm
   `implement→review`), plus `plan.md` with all boxes `[x]` and an APPROVED `review.md`, both
   arms return `state` ≠ `"refused"` and append their rows. **Phase**: Gate agreement

2. **`_current_phase` is deleted.** The helper (`review_dispatch.py:39-48`) and its
   `detect_lifecycle_phase` import are removed; it has no other caller repo-wide. Acceptance:
   `grep -rn "_current_phase\|detect_lifecycle_phase" cortex_command/pipeline/review_dispatch.py`
   returns no matches. **Phase**: Gate agreement

3. **The morning-review call site stops supplying an artifact-derived `from_state`.**
   `cortex_command/overnight/advance_lifecycle.py:225`'s
   `from_state = str(detect_lifecycle_phase(feature_dir).get("phase") or "review")` is removed
   and the `advance` call omits `from_state`. Acceptance: on a realistic crash-recovery log
   (long road, `implement→review` present, `review_verdict` cycle ≥ 1 present, no
   `phase_transition{to: "complete"}`), `advance_lifecycle` appends exactly one
   `phase_transition{from: "review", to: "complete"}` and no duplicate `review_verdict`.
   **Phase**: Gate agreement

4. **The no-review branch fires the implement-exit arm, not the review arm.** When
   `review_required` is false, `advance_lifecycle` fires the `implement-transition` verb in
   transition mode — which resolves its own route — instead of the `review-verdict` arm.
   Acceptance: on a realistic short-road log (`lifecycle_start` simple/medium, `spec_approved`,
   `phase_transition{from: "specify", to: "implement"}`), the call appends exactly one
   `phase_transition{from: "implement", to: "complete"}` and **no** `review_verdict` row, and
   `advance_lifecycle` returns `state == "advanced-complete"`. Additionally, `advance_lifecycle`
   asserts the route it actually got: when the emitted `phase_transition` carries a `to` other
   than `"complete"`, it must **not** return `advanced-complete`. Acceptance: a test in which the
   arm routes to `review` asserts the returned `state` is not `advanced-complete`.
   **Phase**: Morning-review correctness

5. **`review_required` is corrupted-aware, matching the route resolver.** `advance_lifecycle`
   currently computes `review_required` from `reduction.state.get("tier", "simple")` /
   `.get("criticality", "medium")` (`advance_lifecycle.py:197-200`) and never consults
   `reduction.corrupted`, while `implement_transition._resolve_route` (`:139-162`) treats
   `corrupted` as `("review", "complex")`. On a corrupted reduction the two therefore disagree:
   `advance_lifecycle` takes the no-review branch and the arm routes to `review`, landing
   `phase_transition{to: "review"}` while the caller reports `advanced-complete` — and because
   `_is_machine_complete` matches only `to: "complete"`, every later run replays and reports
   completion forever. `review_required` must treat a corrupted reduction as review-required, so
   a corrupted feature routes to `missing-review` rather than being auto-completed. Acceptance:
   on a log with a torn line and no recoverable tier axis (`reduction.corrupted` is True),
   `advance_lifecycle` returns `state == "missing-review"` and appends no `phase_transition` row.
   **Phase**: Morning-review correctness

6. **A refused advance at the morning-review call site is audible and returns `advance-refused`.**
   `advance_lifecycle` inspects `advance`'s returned envelope (it currently discards it,
   `advance_lifecycle.py:226-238`). On `state == "refused"` it logs a warning naming the feature,
   the refusal, and the events log, and returns the literal state `"advance-refused"`. That
   literal is added to `KNOWN_STATES` (`advance_lifecycle.py:82-89`) and to the module
   docstring's `States:` list (`:38-59`), both of which are closed enumerations that
   `tests/test_cortex_morning_review_advance_lifecycle.py:244` already treats as authoritative
   (`assert seen <= set(al.KNOWN_STATES)`). Acceptance: on a lifecycle dir seeded with
   `lifecycle_start` (complex/high) and a `review_verdict{cycle: 1, verdict: "APPROVED"}` row —
   **no `phase_transition` row, so `_is_machine_complete` does not short-circuit** — plus an
   on-disk `review.md` carrying an APPROVED verdict (so the artifact fallback reports `complete`
   against the arm's table `from_state` of `review`), `advance_lifecycle` returns
   `state == "advance-refused"`, `caplog` contains a warning naming the feature, and
   `"advance-refused" in al.KNOWN_STATES` is True. **Phase**: Morning-review correctness

7. **The morning-review walkthrough documents the new state and a fallback rule.** Both mirrored
   copies — `skills/morning-review/references/walkthrough.md` (Section 2b's state table) and
   `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md` — gain a row for
   `advance-refused` **and** a catch-all instruction for any state absent from the table (which
   also covers the pre-existing `error` state, reachable via `main()`'s except-clause at
   `advance_lifecycle.py:263` and today unmapped). Their stale pre-fold event-count prose ("four
   synthetic events when review isn't required; two when...") is corrected to match what the arms
   now emit (one `phase_transition` for the no-review branch; `review_verdict` +
   `phase_transition`, or `phase_transition` alone on crash recovery). Acceptance:
   `grep -c "advance-refused" <each file>` returns ≥ 1; each file contains an instruction for an
   unlisted state; neither file still contains the string "four synthetic events".
   **Phase**: Morning-review correctness

8. **The unrepresentative test fixtures are rebuilt to carry machine rows.** Three fixtures
   currently exercise only the degenerate artifact-fallback path and so cannot see this bug:
   `cortex_command/pipeline/tests/test_review_verdict_recording.py:43-45` (seeds
   `from_phase`/`to_phase`, which `common.py:535` cannot read — the sole repo-wide occurrence of
   those keys), and `tests/test_cortex_morning_review_advance_lifecycle.py:67-106` and `:145-173`
   (seed no `phase_transition` rows at all). Each is reseeded with a realistic
   `phase_transition` chain using `"from"`/`"to"`. Acceptance:
   `grep -rn "from_phase\|to_phase" --include="*.py" .` returns no matches; each rebuilt fixture
   asserts `resolve_lifecycle_phase(fd)["phase"]` equals the intended pre-transition state before
   the call. **Phase**: Gate agreement

9. **`test_review_verdict_recording.py` pins a single outcome.** Its
   `if appended: ... else: assert REFUSED` structure (`:62-76`) passes on either branch and
   therefore protects nothing. It is rewritten to assert the rows landed — no conditional.
   Acceptance: `grep -n "if appended" cortex_command/pipeline/tests/test_review_verdict_recording.py`
   returns no matches, and the test's assertions run unconditionally: after
   `_advance_review_complete(_FEATURE, 1, log)` on the Requirement 8 fixture, `log.read_text()`
   contains an appended `review_verdict` line with `"verdict": "APPROVED"` and `"cycle": 1`, and
   an appended `phase_transition` line with `"from": "review"` and `"to": "complete"`; the test
   fails if either line is absent. **Phase**: Gate agreement

10. **The per-verb `from_state` invariant is pinned by a test.** Phase 1's whole safety argument
    is that a verb has exactly one departure state, so the table's `from_state` is always the
    right expected value. Nothing enforces this today: `_check_invariants`
    (`transition_table.py:546-583`) asserts only that `(owning_verb, decision_state)` arm keys
    are unique, and a rogue row giving `review_verdict` a second, divergent `from_state` passes
    it cleanly (measured). A test asserts that every `Transition` sharing an `owning_verb`
    declares the same `from_state`. Acceptance: a test in
    `cortex_command/lifecycle/tests/test_transition_table.py` groups `TRANSITIONS` by
    `owning_verb` and asserts each group's `from_state` set has exactly one member; it fails when
    a divergent row is added. **Phase**: Gate agreement

11. **`advance`'s refusal text names omission as the sanctioned option for programmatic callers.**
    `advance.py:1007-1011`'s `preferred_remedy` currently offers only "thread
    `advance_contract.expected_from_state` through `--from-state`", which reads as the sole remedy
    and does not cover a caller that already knows which verb it is firing. It gains a clause
    stating that such a caller should omit `--from-state` and let the table's `from_state` stand.
    The existing "never pass the detected phase" warning is retained verbatim. Acceptance: the
    refusal envelope's `preferred_remedy` contains both the re-sync clause and the omission
    clause. **Phase**: Gate agreement

12. **Downstream readers see the feature as complete.** After an APPROVED overnight review,
    `advance_lifecycle._has_real_review_verdict` returns True (a `review_verdict` row with
    integer `cycle >= 1` is present) and `_is_machine_complete` returns True (a
    `phase_transition{to: "complete"}` row is present), so morning review reports
    `already-complete` rather than `missing-review`. Acceptance: an end-to-end test seeds a
    realistic post-review log, runs the approved path, then asserts
    `advance_lifecycle(...)["state"] == "already-complete"`. **Phase**: Morning-review
    correctness

## Non-Requirements

- **No change to `detect_lifecycle_phase`, `resolve_lifecycle_phase`, or
  `_phase_from_machine_rows`.** Every mismatch found originates in a caller; the resolvers behave
  coherently and `resolve.py:257` already uses the correct one. This preserves the ticket's
  stated non-goal.
- **No routing around the gate.** `cortex-lifecycle-event log` is not used to assert a refused
  row. It skips `_consent_cross_check` (`advance.py:606-650`) and `_project_status`
  (`advance.py:688-777`), so a feature "completed" that way would never leave `in_progress` in
  the backlog — and `cortex/requirements/project.md` makes events authoritative wherever machine
  rows exist, so a correct refusal must not be overridden.
- **No adoption of the `next` envelope at these call sites.** `next_state` runs full
  `resolve_invocation` identity resolution with eight non-resume passthrough states the pipeline
  would have to branch on, and on an already-complete feature it would serve
  `expected_from_state="complete"`, which *matches* and would let the arm append a fabricated
  `phase_transition{from: "review", to: "complete"}`. The table default refuses that for free.
- **Validation of the review agent's `cycle` field is out of scope.** `dispatch_review` passes
  `cycle = verdict_dict.get("cycle", 0)` straight from agent-authored JSON
  (`review_dispatch.py:408`); a missing or non-integer cycle fails
  `_has_real_review_verdict`'s `cycle >= 1` check even for a genuine APPROVED review. This is an
  independent route to the same `missing-review` symptom and needs a validation-policy decision
  for agent-authored verdict JSON. **File as a follow-up ticket.**
- **No new state surfaces beyond `advance-refused`** (Requirement 6).
- **No change to `_check_invariants` itself.** Requirement 10 pins the per-verb `from_state`
  invariant with a test rather than an import-time assertion, so a table edit fails in CI rather
  than breaking every import of the module mid-edit.

## Edge Cases

- **A corrupted reduction.** `reduction.corrupted` is True when a torn or vocab-rejected line
  leaves tier or criticality unknowable (`common.py:828-843`). Expected (post-Requirement 5):
  treated as review-required, so the feature routes to `missing-review` and is never
  auto-completed. Before Requirement 5 this is the divergence that would land
  `phase_transition{to: "review"}` under an `advanced-complete` report.
- **An enforcement-bearing pause is active.** `_pause_refusal` (`advance.py:272-305`) refuses any
  crossing verb whose slug is unmapped in `_PAUSE_OWNING_VERBS` (only `plan-approval` is mapped).
  Expected: the advance still refuses, and — post-fix — that refusal is audible at all three call
  sites. This is correct behavior, not a regression.
- **A recorded PR is not merged.** `_consent_cross_check` (`advance.py:606-650`) refuses
  `review.approved` when a `pr_opened` row exists whose gh state is not `MERGED`. Expected:
  refusal, audibly. The fix's guarantee is therefore conditional: the rows land whenever the
  gate's own preconditions hold.
- **`_advance_to_review` refused, so the log never reached `review`.** Expected: the later
  `_advance_review_complete` also refuses (the feature genuinely is not at `review`), audibly.
  Both arms must be fixed together; fixing only the second changes nothing.
- **Degenerate log with zero machine rows** (the shape of the observed 2026-07-28 sessions).
  `resolve_lifecycle_phase` falls back to the artifact detector. Expected: the table's
  `from_state` is compared against that fallback value; where they differ the advance refuses
  audibly rather than silently, and the operator has a named warning to act on.
- **A feature already machine-complete.** `_is_machine_complete` (`advance_lifecycle.py:168-176`)
  short-circuits at `:194`, before the `advance` call. Expected: `already-complete`, unchanged —
  this path is not the refusal path and must not be used to exercise Requirement 6.
- **Replay / re-invocation.** Every planned emission already present short-circuits as a benign
  replay before gating (`advance.py:958-963`). Expected: re-running any arm is idempotent and
  returns `advanced: True` with an empty `emitted` list.
- **A refusal must never fail an overnight run.** Expected: `_advance_or_warn` keeps swallowing
  refusals and exceptions; the new envelope check at the morning-review call site likewise
  returns a state rather than raising.

## Changes to Existing Behavior

- **MODIFIED** — `review_dispatch.py`'s two arms and `advance_lifecycle.py`'s advance call no
  longer pass `from_state`; the closed transition table becomes the sole source of the expected
  departure state at these call sites.
- **REMOVED** — `_current_phase` (`review_dispatch.py:39-48`) and its `detect_lifecycle_phase`
  import.
- **MODIFIED** — a no-review feature advanced by morning review now records a single
  `phase_transition{from: "implement", to: "complete"}` and **no longer receives a synthetic
  `review_verdict{verdict: "APPROVED", cycle: 0}` row**. That row was a byproduct of firing the
  review arm at a feature that was never reviewed; `_has_real_review_verdict` already excludes
  `cycle: 0` as not-a-real-verdict, and `metrics.py` reads verdicts separately from completion
  (absent verdict → `None`, which does not block completion detection). The events log becomes
  more truthful, not less complete.
- **MODIFIED** — a corrupted reduction now routes to `missing-review` instead of being treated as
  a simple/medium no-review feature. This is a behavior change for corrupted logs specifically:
  they stop being auto-completed.
- **ADDED** — the `advance-refused` state in `advance_lifecycle.KNOWN_STATES`, the module
  docstring, and both morning-review walkthrough copies, alongside a catch-all rule for any
  unlisted state.
- **ADDED** — an omission clause in `advance`'s `preferred_remedy` refusal text.
- **ADDED** — a test pinning per-verb `from_state` consistency across the transition table.
- **MODIFIED** — three test fixtures reseeded with realistic machine rows; one test's
  either-branch-passes structure replaced with a single pinned outcome.

## Technical Constraints

- **The fix must go through `advance`.** `tests/test_fold_completion.py:33-41,94-102,140-163`
  fails if `review_dispatch.py` or `advance_lifecycle.py` calls `log_event`/`log_event_at` with
  an event in `{phase_transition, review_verdict, feature_complete, spec_approved,
  plan_approved}`, and requires each module to retain a call whose name contains `"advance"`.
- **`from_state` is invariant per verb across today's table, but that invariant is not
  structurally enforced.** All three `review_verdict` arms are `from_state="review"`
  (`transition_table.py:339,352,365`); all three `implement_transition` arms — including the
  batch arm at `:447` — are `"implement"` (`:457,474`). `_check_invariants`
  (`transition_table.py:546-583`) asserts only that `(owning_verb, decision_state)` arm keys are
  unique; a rogue row giving an existing verb a divergent `from_state` passes it cleanly
  (measured). Omitting `from_state` is therefore correct against the current table, and
  Requirement 10 converts that from an unguarded design belief into a pinned invariant.
- **Two independent derivations of the review predicate must stay aligned.**
  `advance_lifecycle`'s `review_required` and `implement_transition._resolve_route` read the same
  `reduce_lifecycle_state` reduction but historically diverge on `reduction.corrupted`;
  Requirement 5 closes that gap. Any future edit to either rule must change both.
- **Best-effort is the contract.** `advance` never raises (house style); `_advance_or_warn`
  logs on refusal without re-raising, pinned by
  `test_review_verdict_recording.py::test_advance_failure_never_raises` (`:79-82`).
- **Both required rows share one gated emission list** (`advance.py:388-403`, `986-1013`,
  `1029-1038`), so they land together or not at all.
- **`cortex_command/common.py` is lifecycle-gated** per `CLAUDE.md`; this spec does not modify it
  (see Non-Requirements), so no additional gate applies.
- **Dual-source mirroring**: `plugins/cortex-overnight/skills/morning-review/` is a mirror
  surface — edit the canonical `skills/morning-review/` source and let the pre-commit hook
  regenerate, per `CLAUDE.md`.

## Open Decisions

None. The two candidates research could not resolve from the source — whether the third call
site is in scope, and what its no-review branch should do — were resolved by operator decision
and by direct measurement respectively.

## Proposed ADR

None. The governing decision already exists: ADR-0025 makes events the phase authority wherever
machine rows exist, and this work is an application of it rather than a new trade-off. The one
genuinely surprising element — that `advance`'s own `preferred_remedy` names only the
thread-the-contract route, which would lead a future maintainer back into this bug — is carried
by Requirement 11's change to that text, which is cheaper and closer to the failure than an ADR.
