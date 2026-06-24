# Plan: review-gate-flag-coherence-a-feature

## Overview
Add a fail-loud write-boundary guard `_guard_review_flag_coherence(details, *, site)` to
`cortex_command/overnight/outcome_router.py` (mirroring the in-module
`_guard_no_review_qualifying_sync_merge` idiom) that raises when a `feature_deferred` `details` dict
co-sets both `could_not_run` and `review_dispatch_crashed`, and invoke it immediately before each of the
six review-gate `FEATURE_DEFERRED` emits. Regression insurance for the ADR-0015/R6 mutual-exclusion — the
combo is unreachable today, so under correct code the guard is a no-op. Its value is that a future edit
which co-sets the flags cannot write an incoherent event: at the three crash-`except` sites the guard
raises (surfacing as a one-feature failure); at the three in-band sites the raise is caught by the
crash-`except` below and healed into a coherent emit. R2 proves the guard's raise-logic; R4 proves the
crash-site wiring and the in-band heal end-to-end.

## Outline

### Phase 1: Guard predicate (tasks: 1, 2)
**Goal**: Add the coherence guard helper and its direct done-criterion unit test (the incident reproducer).
**Checkpoint**: `_guard_review_flag_coherence` is defined in `outcome_router.py`; its direct unit test
passes and *errors* if the guard's `raise` is deleted (genuine mutation tripwire). No `assert` added.

### Phase 2: Wire & prove (tasks: 3, 4, 5)
**Goal**: Invoke the guard before all six review-gate emits, prove the wiring per-path, and confirm the
full suite + registry parity stay green.
**Checkpoint**: Six guard calls wired; `TestReviewDeferralFlagCoherence` proves the crash-site wiring
(guard called before each emit, on the emitted dict) and proves the three in-band sites heal a simulated
co-setting edit into a coherent emit; `just test` exits 0 with `bin/.events-registry.md` unchanged.

## Tasks

### Task 1: Add the coherence guard helper
- **Files**: `cortex_command/overnight/outcome_router.py`
- **What**: Add a module-level message constant plus `_guard_review_flag_coherence(details, *, site)` that
  raises when both flags are truthy and returns `None` otherwise. (R1)
- **Depends on**: none
- **Complexity**: simple
- **Context**: Mirror the existing fail-loud idiom — the message constant `_REVIEW_QUALIFYING_SYNC_MERGE_MSG`
  (`outcome_router.py:1319`) + the `None`-returning validator `_guard_no_review_qualifying_sync_merge`
  (`:1328`). Place the new constant + helper adjacent to that pair (≈`:1319-1341`). Signature:
  `def _guard_review_flag_coherence(details: dict, *, site: str) -> None`. Raise when
  `details.get("could_not_run") and details.get("review_dispatch_crashed")` are both truthy; the message
  must name the `site` and the offending flag pair. Use a fail-loud `RuntimeError` — implementer latitude
  to introduce a named `class ReviewFlagCoherenceError(RuntimeError)` for greppability (spec Open
  Decisions). **Never `assert`** — overnight spawns plain `python` (no `-O`/`PYTHONOPTIMIZE`), so an
  `assert` would run and abort with a bare `AssertionError`; precedent for the assert→raise conversion is
  `cortex_command/pipeline/dispatch.py:270-277`. The MUST-escalation policy does not apply (it governs
  prose model-directives, not code raises).
- **Verification**: (b) `grep -c "_guard_review_flag_coherence" cortex_command/overnight/outcome_router.py`
  ≥ 1 AND `grep -cE "^[[:space:]]*assert\b" cortex_command/overnight/outcome_router.py` = 0 — pass if the
  helper is present and no `assert` was added.
- **Status**: [ ] pending

### Task 2: Direct done-criterion unit test of the guard logic
- **Files**: `cortex_command/overnight/tests/test_outcome_router.py`
- **What**: Add a sync `TestCase` that imports `_guard_review_flag_coherence` and calls it directly,
  asserting it raises on the incident reproducer and does not raise on the single-flag / neither cases. (R2)
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: New class `TestGuardReviewFlagCoherence(unittest.TestCase)` (import the guard from
  `cortex_command.overnight.outcome_router`). Four cases:
  `{"could_not_run": True, "review_dispatch_crashed": True, "merge_reverted": True}` → `assertRaises`;
  `{"could_not_run": True}` → no raise; `{"review_dispatch_crashed": True}` → no raise; `{}` → no raise.
  Because the test invokes the guard directly, a green run *executes* the `assertRaises` — it is not
  satisfiable by a suite that never touches the guard.
- **Verification**: (a)+(b) `python -m pytest cortex_command/overnight/tests/test_outcome_router.py -q -k
  TestGuardReviewFlagCoherence` exits 0 AND `grep -c "class TestGuardReviewFlagCoherence"
  cortex_command/overnight/tests/test_outcome_router.py` = 1. Mutation tripwire: deleting the guard body's
  `raise` (Task 1) makes the `assertRaises` case error.
- **Status**: [ ] pending

### Task 3: Wire the guard before all six review-gate emits
- **Files**: `cortex_command/overnight/outcome_router.py`
- **What**: Insert a `_guard_review_flag_coherence(<dict>, site=...)` call immediately **before** each of
  the six review-gate `overnight_log_event(FEATURE_DEFERRED, ...)` emits, passing the exact local dict that
  the adjacent emit serializes. (R3)
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Anchors are authoring-time hints — locate each site by function + emit role, not line
  number. Two emits in each of three functions (confirmed local dict names):
  - `_recovery_review_gate` (`:1057`): in-band emit serializing `deferred_details` (≈`:1210`) and the
    crash-`except` emit serializing `crash_details` (≈`:1259`).
  - `_repair_completed_review_gate` (`:1344`): in-band `deferred_details` (≈`:1566`) and crash-`except`
    `crash_details` (≈`:1638`).
  - `apply_feature_result` (`:1716`): in-band `deferred_details` (≈`:1954`) and crash-`except`
    `crash_details` (≈`:2020`).
  Pass `deferred_details` on each in-band path and `crash_details` on each crash path — **the same dict the
  adjacent `overnight_log_event(..., details=<dict>)` serializes** (binding the wrong dict is the miswiring
  R4 catches). Give each call a distinct `site=` string (e.g. `"recovery in-band"`, `"recovery crash"`,
  `"repair in-band"`, `"repair crash"`, `"apply in-band"`, `"apply crash"`). Do **not** wire the four
  non-review emits (`_apply_feature_result` CI-error/merge-conflict/passthrough ≈`:759/801/842` and the
  sync top-level CI-error ≈`:2130`) — they set none of the three flags, so the guard would be vacuous.
- **Verification**: (b) `grep -c "_guard_review_flag_coherence(" cortex_command/overnight/outcome_router.py`
  ≥ 7 (1 definition + 6 calls) — pass if ≥7; AND each call resides inside one of
  `_recovery_review_gate` / `_repair_completed_review_gate` / `apply_feature_result` (none inside the four
  non-review emit functions). Behavioral correctness is proven by Task 4, not by this count.
- **Status**: [ ] pending

### Task 4: Per-path behavioral wiring-proof
- **Files**: `cortex_command/overnight/tests/test_outcome_router.py`
- **What**: Add `TestReviewDeferralFlagCoherence` with three assertion layers — (a) a crash-site
  wiring-identity proof, (a′) an in-band heal end-to-end proof under a simulated co-setting edit, and (b) a
  coherent single-flag sweep. (R4)
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**: Place near `TestCouldNotRunPreservesMerge` (≈`:2601`); reuse `_could_not_run_review`,
  `_crash_review`, `_run_recovery`, `_ff_subprocess_side_effect`, `_deferred_event_details`. Likely an
  `IsolatedAsyncioTestCase` (the paths are async). The forbidden both-flags combo is unreachable by the
  real assembly, so the proof must **not** try to manufacture it upstream: at the crash sites the flags are
  co-set inline by a single `if preserved/else` driven by one boolean (no separable "flag-set step"), and
  any state injected before that block is overwritten before the guard runs. Use the proof each site type
  actually admits:
  - **(a) Crash-site wiring-identity proof (the 3 crash-`except` emits, load-bearing):** wrap or
    `mock`-replace `_guard_review_flag_coherence`; drive each genuine-crash path (coherent, single-flag);
    assert the guard was invoked **(i)** *before* the matching `overnight_log_event` (call-order on a
    shared mock) and **(ii)** with the *same dict object* the emit serializes as `details=`
    (`guard_spy.call_args.args[0] is emit_spy.call_args.kwargs["details"]`). **Fail-closed:** a driven path
    producing zero `FEATURE_DEFERRED` emits fails the assertion (no vacuous pass). This catches the exact
    miswirings the Task 3 grep cannot — guard removed (spy never called), guard *after* the emit
    (call-order), guard bound to the wrong dict (identity mismatch) — without manufacturing an unreachable
    state; R2 proves the raise-logic, so the composition proves the guard rejects an incoherent dict at
    each crash site.
  - **(a′) In-band heal end-to-end (the 3 in-band emits, where a real seam exists):** monkeypatch
    `_set_review_error_detail_flags` to *additionally* set `review_dispatch_crashed` (simulating the future
    edit the in-band wiring insures against); drive each in-band `ERROR` path; spy on `overnight_log_event`
    and assert **no** emitted `FEATURE_DEFERRED` carries both flags — the in-band guard raises, the
    crash-`except` below heals (`preserved=True` on the ERROR path → coherent `could_not_run` emit).
    Deleting the in-band guard makes the in-band emit write the incoherent both-flags event directly (a
    normal emit does not raise, so no heal fires) → this assertion fails. This is the present/absent
    discriminator for the in-band wiring.
  - **(b) Coherent single-flag sweep:** drive primary/recovery/repair through the could-not-run and
    genuine-crash cases and assert each emitted `FEATURE_DEFERRED` carries **at most one** of
    {`could_not_run`, `review_dispatch_crashed`} — generalizing the existing single-flag pin
    `test_error_verdict_event_carries_could_not_run_marker` (`:1822`).
  `**Depends on** [2]` also serializes the shared edit of `test_outcome_router.py` so Tasks 2 and 4 never
  co-schedule on the same file.
- **Verification**: (a)+(b) `grep -c "class TestReviewDeferralFlagCoherence"
  cortex_command/overnight/tests/test_outcome_router.py` = 1 AND `python -m pytest
  cortex_command/overnight/tests/test_outcome_router.py -q -k TestReviewDeferralFlagCoherence` exits 0;
  layer (a) fails if a crash-site guard is deleted/mis-placed/mis-bound, and layer (a′) fails if an in-band
  guard is deleted.
- **Status**: [ ] pending

### Task 5: Full suite green, parity verified
- **Files**: none (verification-only gate; no file edits — if `just test` fails, route the failure back to
  the responsible task rather than patching here)
- **What**: Run the full `just test` suite and confirm exit 0, which *runs* (not merely asserts) the
  events-registry parity tests. (R5)
- **Depends on**: [2, 3, 4]
- **Complexity**: simple
- **Context**: `just test` runs the full suite including `tests/test_check_events_registry.py` and
  `tests/test_events_registry_glob_parity.py`. This change adds no new event type or `details` field, so
  `bin/.events-registry.md` must remain unmodified — a green run verifies no registry/parity regression.
  If a failure appears that is a known external flake (concurrent-session fixture contention, or
  sandbox-network DNS for an MCP-touching test — both seen in prior lifecycles), confirm it is unrelated to
  this change and not a guard regression before treating it as external.
- **Verification**: (a) `just test` exit code = 0.
- **Status**: [ ] pending

## Risks
- **Emit-site breadth: 6 (chosen) vs 3 (Open Decision).** The guard is wired at all six review-gate emits,
  including the three in-band emits that are vacuous *today* (the in-band helper `_set_review_error_detail_flags`
  cannot set `review_dispatch_crashed`). They are **not** dead weight: a future edit that makes the in-band
  path co-set both flags would, *without* the in-band guard, write the incoherent event directly (a normal
  emit does not raise, so the crash-`except` heal never fires); *with* it, the guard raises and the heal
  rewrites a coherent emit. Task 4 layer (a′) proves exactly this present/absent discriminator. The leaner
  alternative — guard only the three crash-`except` sites — drops that future-in-band-edit insurance (the
  literal ticket ask) at half the footprint. Resolved toward 6; the operator may still trim to 3 at plan
  approval if proportionality is preferred over the in-band insurance.
- **Altitude residual (accepted, stated plainly):** no automated test catches a *new* unguarded
  `FEATURE_DEFERRED` emit site added inline — the ordinary way deferral emits are written today. Only a
  `log_event`-level guard would be bypass-proof, and that was declined for cohesion (a domain rule in the
  generic event sink). This is the accepted residual of the review-gate-altitude choice, not full
  "fourth-site" coverage.
- **Fired-guard production posture (accepted):** a raise at a crash-`except` emit fires *after* the
  revert/preserve decision, so it leaves the worktree consistent but loses that one feature's deferral file
  and backlog write-back (both run after the emit); the feature surfaces as `FEATURE_FAILED` / `failed`
  status (not a silent drop). Blast radius is one feature (or at most one round's batch subprocess) — never
  the session; `ctx.lock` releases via `async with __aexit__`. Degraded but non-corrupting, and only
  reachable on a future regression.

## Acceptance
`_guard_review_flag_coherence` is defined and called immediately before all six review-gate
`FEATURE_DEFERRED` emits; the direct unit test raises on the `{could_not_run, review_dispatch_crashed,
merge_reverted}` reproducer (and errors if the guard's `raise` is deleted); and
`TestReviewDeferralFlagCoherence` proves the crash-site wiring (guard called before each emit, on the
emitted dict object — failing on a deleted/after-emit/wrong-dict guard), proves the three in-band sites
heal a simulated co-setting edit into a coherent emit (failing if an in-band guard is deleted), and
confirms every coherent path emits at most one of the two flags. `just test` exits 0 with the
events-registry/parity tests green and `bin/.events-registry.md` unchanged — and no reachable path's
behavior changes (under correct code the guard is a no-op).
