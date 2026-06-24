# Specification: review-gate-flag-coherence-a-feature

## Problem Statement

The overnight review gate's `feature_deferred` events carry three flags — `could_not_run`,
`review_dispatch_crashed`, `merge_reverted` — whose mutual exclusion (per ADR-0015/R6: a could-not-run
review *preserves* the merge and is never a dispatch crash) the morning report and the integration-PR
marker rely on to tell the operator whether unreviewed code was preserved or reverted. An overnight
incident emitted a `feature_deferred` co-setting `could_not_run` **and** `review_dispatch_crashed` (and
`merge_reverted`) together — incoherent under the policy and apt to mislead the operator's merge
decision. That combination is **unreachable in current code** (the in-band helper never sets
`review_dispatch_crashed`; the three crash-`except` sites set the two flags in disjoint
`if preserved/else` branches), so this is **regression insurance**: a fail-loud write-boundary guard so
the coherence cannot silently regress as future review-gate emit sites or edits accrue. The incident
event is almost certainly a stale pre-ADR-0015 build artifact.

> **Line numbers in this spec are authoring-time anchors, not contracts.** Inserting the guard calls
> shifts every line below the first insertion, so the cited numbers (e.g. the emit at `≈1259`) will not
> name the same construct after implementation. Each reference is therefore pinned to a **stable anchor**
> — a function name plus the emit's role (in-band `if rr.verdict == "ERROR"` emit, or crash-`except`
> emit) — with the line number as an at-authoring hint only.

## Phases

<!-- ≥2 phases for complexity=complex. Names match the **Phase** tags in ## Requirements. -->
- **Phase 1: Guard predicate** — add the coherence guard helper and its direct done-criterion unit test (the incident reproducer).
- **Phase 2: Wire & prove** — invoke the guard before all six review-gate `feature_deferred` emits and add the per-path behavioral wiring-proof.

## Requirements

**Priority**: all five requirements are **must-have**. R2 (unit test of the guard predicate) and R4 (the
per-path behavioral wiring-proof) are *both* load-bearing and not interchangeable: R2 proves the guard's
*logic*, R4 proves the guard is actually *wired* (called before each emit, against the live dict) — a
miswiring R2 cannot detect. The leaner-scope lever is not "drop a requirement" but the separate 3-vs-6
emit-site breadth question (see `## Open Decisions`). Won't-do boundaries are in `## Non-Requirements`.

1. **Coherence guard helper** *(must-have)*: add `_guard_review_flag_coherence(details, *, site)` to
   `cortex_command/overnight/outcome_router.py`, mirroring the existing
   `_guard_no_review_qualifying_sync_merge` idiom (module-level message constant + a `None`-returning
   validator that raises; ≈`outcome_router.py:1319-1341` at authoring). It **raises** (a fail-loud
   `RuntimeError`, or a named `RuntimeError` subclass for greppability — **never `assert`**) when both
   `details.get("could_not_run")` and `details.get("review_dispatch_crashed")` are truthy; otherwise
   returns `None`. The error message names the offending `site` and the flag pair.
   *Acceptance* (structural — behavior is proven by R2/R4, not here): `grep -c "_guard_review_flag_coherence"
   cortex_command/overnight/outcome_router.py` ≥ 1 AND no `assert` statement is added
   (`grep -cE "^[[:space:]]*assert\b" cortex_command/overnight/outcome_router.py` = 0).
   **Phase**: Guard predicate

2. **Direct done-criterion unit test of the guard logic** *(must-have)*: a new test **imports
   `_guard_review_flag_coherence` and calls it directly**, asserting (via `assertRaises`) that it raises on
   the incident reproducer `{"could_not_run": True, "review_dispatch_crashed": True, "merge_reverted": True}`
   and does NOT raise on `could_not_run`-alone, `review_dispatch_crashed`-alone, or neither. Because the
   test invokes the guard directly, a green run *executes the assertRaises* — it is not satisfiable by a
   suite that never touches the guard.
   *Acceptance*: `just test` exits 0 with this test present; deleting the guard body's `raise` makes the
   `assertRaises` case error (the test is a genuine mutation tripwire, run as part of the suite, not a
   prose claim). Binary: `just test` exit code = 0.
   **Phase**: Guard predicate

3. **Wire the guard at every review-gate emit** *(must-have)*: call `_guard_review_flag_coherence(details, site=...)`
   immediately **before** each of the **six** review-gate `overnight_log_event(FEATURE_DEFERRED, ...)`
   emissions, passing **the same local dict** that emit serializes (each site builds its own —
   `deferred_details` on the in-band path, `crash_details` on the crash path; the guard must receive the
   one being emitted). Stable anchors — two emits in each of three functions:
   - `_recovery_review_gate`: the in-band `if rr.verdict == "ERROR"` emit (≈1210) and the crash-`except`
     emit (≈1259).
   - `_repair_completed_review_gate`: the in-band emit (≈1566) and the crash-`except` emit (≈1638).
   - `apply_feature_result`: the in-band emit (≈1954) and the crash-`except` emit (≈2020).

   The four non-review `FEATURE_DEFERRED` emits (CI-error/merge-conflict/passthrough, ≈759/801/842/2130)
   are **not** wired.
   *Acceptance* (correct wiring is proven behaviorally by **R4**, not by occurrence count): `just test`
   exits 0 with R4 present. Structural sanity: `grep -c "_guard_review_flag_coherence"
   cortex_command/overnight/outcome_router.py` ≥ 7 (1 definition + 6 calls); and the four non-review emit
   functions contain no guard call — verifiable by confirming each `_guard_review_flag_coherence(` call is
   inside one of the three named review-gate functions.
   **Phase**: Wire & prove

4. **Per-path behavioral wiring-proof** *(must-have)*: a new `TestReviewDeferralFlagCoherence` class in
   `cortex_command/overnight/tests/test_outcome_router.py` (placed near `TestCouldNotRunPreservesMerge`,
   ≈`test_outcome_router.py:2601`; reusing `_could_not_run_review`, `_crash_review`, `_run_recovery`,
   `_ff_subprocess_side_effect`, `_deferred_event_details`). Two assertion layers:
   - **(a) Wiring-proof (the load-bearing half):** for each of the three crash paths, drive the path so the
     assembled crash `details` *would* co-set both flags (force it — e.g. monkeypatch the flag-set step or
     inject crafted state) and assert the path **raises before** `overnight_log_event` emits the incoherent
     event (spy on `overnight_log_event`; assert it was NOT called with a both-flags `details`, i.e. the
     guard intercepted). This fails if the guard is removed, placed *after* the emit, or bound to the wrong
     dict — the exact miswirings a grep cannot see.
   - **(b) Coherent-single-flag sweep:** drive primary/recovery/repair through the could-not-run and
     genuine-crash cases and assert each emitted `FEATURE_DEFERRED` carries **at most one** of
     {`could_not_run`, `review_dispatch_crashed`} — generalizing the existing single-flag pin at
     `test_outcome_router.py:1822` (`test_error_verdict_event_carries_could_not_run_marker`).
   *Acceptance*: `grep -c "class TestReviewDeferralFlagCoherence" cortex_command/overnight/tests/test_outcome_router.py` = 1
   AND `just test` exits 0; layer (a) errors if the guard is deleted or mis-placed.
   **Phase**: Wire & prove

5. **Full suite green, parity verified** *(must-have)*: `just test` exits 0 after all changes. `just test`
   **runs** the events-registry parity tests (`tests/test_check_events_registry.py`,
   `tests/test_events_registry_glob_parity.py`), so a green run **verifies** (not merely asserts) that no
   registry/parity regression was introduced — the change adds no new event type or `details` field, so
   `bin/.events-registry.md` is untouched.
   *Acceptance*: `just test` exit code = 0.
   **Phase**: Wire & prove

## Non-Requirements

- Does **not** change the ADR-0015 preserve-vs-revert *policy* or any flag's meaning — it only rejects
  the incoherent *emission*.
- Does **not** fix the read-side asymmetry: `report.py` (the `could_not_run`-keyed deferral renderers,
  ≈`:535/1286/1476`) keys only on `could_not_run` and never cross-checks `review_dispatch_crashed`. The
  write guard prevents the *cause* going forward; it does not retro-fix the already-archived incident
  event's misread (the #319 misdiagnosis). Out of scope per the ticket Boundary; an optional separate
  follow-up could add a read-side cross-check.
- Does **not** touch `cortex_command/pipeline/review_dispatch.py` (it carries `could_not_run` only as a
  `ReviewResult` field and writes none of the event-detail flags).
- Does **not** make the guard bypass-proof against *any* future emit. The operator chose the **review-gate
  altitude** (a per-call-site guard) over a `log_event`-level guard. The honest consequence: a future
  author who adds a new `FEATURE_DEFERRED` emit inline — *the ordinary way deferral emits are written
  today* — does **not** inherit the guard unless they remember to call it. "Raw `overnight_log_event`" is
  not a special bypass; it is the default for any unwired new site. **No automated test catches a new
  unguarded emit site at this altitude** (only a `log_event`-level guard would, and that was declined for
  cohesion — see Open Decisions). This is the accepted residual of the altitude choice, stated plainly so
  it is not mistaken for full "fourth-site" coverage.
- Does **not** add or modify any `events.log` event type or `details` field → no `bin/.events-registry.md`
  edit.
- Does **not** wire the guard into any read/replay path (report, metrics, status, dashboard) — those
  stay `.get(..., False)`-tolerant of pre-R6 archived events that legitimately co-set both flags.

## Edge Cases

- **Pre-R6 archived `feature_deferred` events** that legitimately co-set both flags: replayed/read
  without rejection — the guard is write-boundary only; readers keep `.get(..., False)`.
- **Guard fires at a crash-`except` emit** (only on a future regression): the raise propagates out of
  `apply_feature_result`. It is **caught by `asyncio.gather(..., return_exceptions=True)`** in the
  orchestrator's per-feature dispatch, which captures the exception and re-routes the feature; the
  orchestrator's reconciliation re-call of `apply_feature_result` with `status="failed"` then routes
  through the `failed` branch → `FEATURE_FAILED`. (On the post-gather reconciliation path specifically,
  an uncaught raise surfaces as the batch-runner subprocess exiting non-zero, which the runner's
  round-loop tolerates by logging `ORCHESTRATOR_FAILED` and continuing.) **Blast radius: one feature**, or
  at most one round's batch subprocess — **never the session**; `ctx.lock` releases via `async with`
  `__aexit__` (no lock leak). The revert/reset has already run *before* the emit, so the merge state is
  consistent. The lost signals for that one feature: its deferral file (`write_deferral`), its
  `_record_review_crash_systemic` systemic-breaker increment, and its `deferred` backlog write-back — all
  of which run *after* the emit. The operator still sees a `FEATURE_FAILED` event and `failed` backlog
  status (not a silent drop). Degraded but non-corrupting, and acceptable for a provably-unreachable path.
- **Guard fires at an in-band emit** (future edit wrongly co-sets on the in-band path): the raise is
  caught by the crash-`except` below it, which **rebuilds `crash_details` coherently** via its strict
  `if preserved/else` (sets *either* flag, never both) and re-emits — so the guard does **not** re-fire,
  and the feature reaches the normal crash-`except` deferral terminus as a coherent **`deferred`** (not
  `failed`). Net: the incoherent event is never written — coherence is *preserved by the heal*, just not
  loudly surfaced at the in-band site. This is why wiring the in-band emits still serves the coherence
  goal (the crash sites are where a raise surfaces loudly; the in-band sites convert a would-be incoherent
  emit into the coherent crash-path emit).
- **The four non-review `feature_deferred` emits** set none of the three flags → guard not wired there;
  the conjunction would be vacuous regardless.
- **No reachable legitimate state** co-sets both flags (ADR-0015 makes them definitionally disjoint), so
  the guard cannot false-positive on live traffic.

## Changes to Existing Behavior

- **ADDED**: a fail-loud coherence guard at the six review-gate `feature_deferred` emit sites; on the
  (currently-unreachable) incoherent combination it raises (crash sites: surfaces as a one-feature
  failure) or triggers the crash-path heal (in-band sites: coherent `deferred`) instead of silently
  emitting an incoherent event.
- No **MODIFIED**/**REMOVED** behavior on any reachable path — under correct code the guard is a no-op.

## Technical Constraints

- **`raise`, never `assert`** — overnight runs Python with no `-O`/`PYTHONOPTIMIZE` in any production
  spawn (the runner self-spawn argv and the `cortex-batch-runner` console-script both invoke plain
  `python`), so an `assert` would run and abort with a bare `AssertionError`. Precedent:
  `cortex_command/pipeline/dispatch.py` (a spec'd `assert` → `ValueError` conversion for this exact
  reason, ≈`:270-277`).
- **Write-boundary only**; never wired into a read/replay surface.
- Mirror the in-module `_guard_no_review_qualifying_sync_merge` convention: a module-level message
  constant + a `None`-returning validator that raises.
- The module header forbids importing `batch_runner`/`orchestrator`; the guard is self-contained in
  `outcome_router.py`.
- Editing `cortex_command/overnight/` is gated by this lifecycle (in progress). Implement via **sequential
  dispatch on trunk, not worktree** — `just test` runs the editable install, so a worktree would verify
  stale code.
- The **MUST-escalation policy does not apply** (it governs prose imperatives aimed at model behavior,
  not deterministic code raises).

## Open Decisions

- **Emit-site breadth: 6 (chosen) vs 3.** The guard is wired at all six review-gate emits, including the
  three in-band emits that are vacuous *today* (the in-band helper cannot set `review_dispatch_crashed`).
  Wiring them is justified by the ticket's explicit ask to catch *"a future edit"* that wrongly co-sets,
  and by the in-band heal behavior above (it converts a would-be incoherent in-band emit into a coherent
  crash-path emit). The leaner alternative — guard only the three crash-`except` sites (the sole places
  the combo can arise today) — delivers identical *reachable*-combo protection at half the footprint, at
  the cost of the future-edit insurance on the in-band path. **Resolved toward 6** per the operator's
  spec-interview altitude selection and the ticket's future-edit ask; surfaced here so the operator can
  trim to 3 at approval if proportionality is preferred over future-edit insurance.

The guard-placement *altitude* fork (review-gate emit guard vs setter-internal vs `log_event`-level) was
resolved during the spec interview. Exception type (plain `RuntimeError` vs named subclass) and the
fired-guard production posture (one-feature-degraded, accepted) are implementer latitude.

## Proposed ADR

None considered. ADR-0015 already records the policy this guard protects; the change codifies that
policy's derived invariant without a new architectural decision (it does not meet the three-criteria
gate — not surprising-without-context given ADR-0015, and it introduces no new trade-off beyond the
documented review-gate-altitude residual, which is captured in Non-Requirements/Open Decisions).
