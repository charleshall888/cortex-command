# Review: review-gate-flag-coherence-a-feature

## Stage 1: Spec Compliance

### Requirement R1: Coherence guard helper
- **Expected**: Add `_guard_review_flag_coherence(details, *, site)` to `outcome_router.py`, mirroring
  the `_guard_no_review_qualifying_sync_merge` idiom (module-level message constant + `None`-returning
  validator that **raises**). Raises a fail-loud `RuntimeError` (never `assert`) when both
  `details.get("could_not_run")` and `details.get("review_dispatch_crashed")` are truthy; otherwise
  returns `None`. Message names the offending `site` and the flag pair. Acceptance:
  `grep -c "_guard_review_flag_coherence"` ≥ 1 AND `grep -cE "^[[:space:]]*assert\b"` = 0.
- **Actual**: `_REVIEW_FLAG_COHERENCE_MSG` (`outcome_router.py:1346`) + `_guard_review_flag_coherence`
  (`:1355`) sit directly adjacent to the existing `_REVIEW_QUALIFYING_SYNC_MERGE_MSG` /
  `_guard_no_review_qualifying_sync_merge` pair (`:1321`/`:1330`), mirroring the idiom exactly. The body
  is `if details.get("could_not_run") and details.get("review_dispatch_crashed"): raise
  RuntimeError(_REVIEW_FLAG_COHERENCE_MSG.format(site=site))` — a plain `RuntimeError`, no `assert`. The
  message names both flags by name, cites ADR-0015/R6, and interpolates `site`. Grep: guard total = 7
  (≥1 met); `assert` count = 0.
- **Verdict**: PASS
- **Notes**: Plain `RuntimeError` (not a named subclass) is explicit implementer latitude per the spec's
  Open Decisions. Docstring records the `raise`-not-`assert` rationale (no `-O`/`PYTHONOPTIMIZE` on
  overnight spawns).

### Requirement R2: Direct done-criterion unit test of the guard logic
- **Expected**: A test imports `_guard_review_flag_coherence` and calls it directly, asserting (via
  `assertRaises`) it raises on `{could_not_run, review_dispatch_crashed, merge_reverted}` and does NOT
  raise on each single-flag case nor on neither. Deleting the guard's `raise` makes the `assertRaises`
  case error. Acceptance: `just test` exits 0; binary exit 0.
- **Actual**: `TestGuardReviewFlagCoherence` (`test_outcome_router.py:2603`) imports the guard and
  exercises all four cases directly: `test_raises_when_both_flags_set` (the incident reproducer →
  `assertRaises(RuntimeError)`), and three `assertIsNone` cases (`could_not_run` alone,
  `review_dispatch_crashed` alone, `{}`). Ran the targeted subset: 7 passed. Mutation tripwire verified —
  neutering the guard body's `raise` failed `test_raises_when_both_flags_set` with "True is not false".
- **Verdict**: PASS
- **Notes**: Genuine mutation tripwire, not a prose claim. The test calls the guard directly, so a green
  run executes the `assertRaises`.

### Requirement R3: Wire the guard at every review-gate emit
- **Expected**: Call `_guard_review_flag_coherence(<dict>, site=...)` immediately before each of the SIX
  review-gate `FEATURE_DEFERRED` emits, passing the same local dict the adjacent emit serializes
  (`deferred_details` in-band, `crash_details` on crash), with distinct `site=` labels. The four
  non-review FEATURE_DEFERRED emits are NOT wired. Acceptance: guard grep ≥ 7 (1 def + 6 calls); every
  call inside one of the three review-gate functions.
- **Actual**: Six call sites, each immediately before its emit, guarding the exact dict the emit
  serializes (verified by reading each `details=<dict>` pairing):
  - `_recovery_review_gate`: `:1209` guards `deferred_details` (emit `:1210` `details=deferred_details`),
    site `"recovery in-band"`; `:1259` guards `crash_details` (emit `:1260`), site `"recovery crash"`.
  - `_repair_review_or_revert` (the helper for `_repair_completed_review_gate()`): `:1594` guards
    `deferred_details` (emit `:1595`), site `"repair in-band"`; `:1667` guards `crash_details` (emit
    `:1668`), site `"repair crash"`.
  - `apply_feature_result`: `:1984` guards `deferred_details` (emit `:1985`), site `"apply in-band"`;
    `:2051` guards `crash_details` (emit `:2052`), site `"apply crash"`.
  Six distinct `site=` labels. Guard grep = 7 (1 def + 6 calls). All four non-review emit sites
  (CI-error/merge-conflict/passthrough/sync top-level) have no adjacent guard call. Each crash block sets
  exactly one flag via `if preserved/else`, so the guard is a no-op on every reachable path.
- **Verdict**: PASS
- **Notes**: The spec's stable anchor named `_repair_completed_review_gate` for the repair emits, but the
  emits actually live in its callee `_repair_review_or_revert` (the in-source comment at `:1634` confirms
  the lineage: `pipeline_attempted="dispatch_review() in _repair_completed_review_gate()"`). The spec
  warned line numbers are authoring-time hints, not contracts; the dict-binding and emit-role identity
  are what matters and both are correct. The fourth non-review anchor (≈2130) has shifted to CI-error
  text, but the grep confirms no guard leaked into any non-review function.

### Requirement R4: Per-path behavioral wiring-proof
- **Expected**: A `TestReviewDeferralFlagCoherence` class with (a) crash-site wiring-identity proof —
  guard invoked before the emit and on the same dict object, fail-closed on zero emits; (a′) in-band heal
  end-to-end under a simulated co-setting edit; (b) coherent single-flag sweep. Must genuinely
  discriminate, not be self-sealing. Acceptance: `grep -c "class TestReviewDeferralFlagCoherence"` = 1
  AND `just test` exits 0; layer (a) errors if a crash-site guard is deleted/mis-placed, layer (a′) if an
  in-band guard is deleted.
- **Actual**: `TestReviewDeferralFlagCoherence` (`test_outcome_router.py:2624`, `IsolatedAsyncioTestCase`,
  exactly 1 occurrence) drives all three real paths (primary/recovery/repair) via `apply_feature_result`:
  - **(a)** `test_a_crash_emits_are_guard_wired`: spies record, per FEATURE_DEFERRED emit, `(details,
    guarded_before)` where `guarded_before` is `any(d is seen for seen in guard_seen)` — an **identity**
    check (`is`), so it catches guard-removed (spy never ran), guard-after-emit (call order), and
    wrong-dict binding. `_assert_wired` requires at least one emit (fail-closed, no vacuous pass).
  - **(a′)** `test_aprime_inband_coset_edit_heals_to_coherent_emit`: patches
    `_set_review_error_detail_flags` to also set `review_dispatch_crashed` (the simulated future edit),
    drives each in-band ERROR path, and asserts no emitted event co-sets both flags AND that a coherent
    `could_not_run` event is emitted (proving the crash-`except` heal fired).
  - **(b)** `test_b_coherent_paths_emit_at_most_one_flag`: sweeps could-not-run and genuine-crash across
    all three paths, asserting every emit carries ≤1 of the two flags.
  Targeted run: 7 tests + 12 subtests passed. The proof does NOT manufacture the unreachable upstream
  state — (a) drives coherent single-flag paths and proves wiring identity; (a′) injects the co-set at
  the one real seam (`_set_review_error_detail_flags`) and proves the heal.
- **Verdict**: PASS
- **Notes**: Genuine discriminator, not self-sealing — confirmed by two mutations: (1) removing the
  guard's `raise` fails (a′) on all three subpaths (the incoherent both-flags event gets written); (2)
  deleting the `repair crash` guard call fails (a) specifically for the `repair` subpath (the identity
  check sees `guarded_before == False`). The `is`-identity check plus the fail-closed "at least one emit"
  assertion are what make this catch the exact miswirings a grep cannot — a real wiring proof.

### Requirement R5: Full suite green, parity verified
- **Expected**: `just test` exits 0 after all changes; the events-registry parity tests run and verify no
  registry/parity regression; the change adds no new event type or `details` field, so
  `bin/.events-registry.md` is untouched.
- **Actual**: `git diff 8770f03f..HEAD --stat -- bin/.events-registry.md` is empty — untouched. The two
  registry-parity suites (`tests/test_check_events_registry.py`, `tests/test_events_registry_glob_parity.py`)
  pass: 25 tests green. Full `outcome_router` suite: 65 tests + 12 subtests green. The change introduces
  no new event type and no new `details` key (the guard only inspects existing `could_not_run` /
  `review_dispatch_crashed`).
- **Verdict**: PASS
- **Notes**: The plan recorded two full-suite failures as pre-existing/external
  (`test_no_order_drift_against_baseline` backlog-baseline drift, `test_log_invocation_fast_path_budget`
  latency flake), neither referencing `outcome_router` or the guard. The change-owned suites
  (outcome_router + registry-parity) are all green, which is what R5's acceptance gates.

## Stage 2: Code Quality
- **Naming conventions**: `_REVIEW_FLAG_COHERENCE_MSG` / `_guard_review_flag_coherence` follow the
  module's existing `_REVIEW_QUALIFYING_SYNC_MERGE_MSG` / `_guard_no_review_qualifying_sync_merge` naming
  to the letter. Test class names (`TestGuardReviewFlagCoherence`, `TestReviewDeferralFlagCoherence`) and
  the `site=` label strings are descriptive and consistent. The `_OR` module-prefix constant for patch
  targets is a clean local idiom.
- **Error handling**: Fail-loud `RuntimeError` with a self-describing message (names both flags, the
  site, and the ADR). No `assert` (verified = 0), correctly motivated by the no-`-O` overnight spawn
  constraint. The guard is a pure predicate-and-raise with no side effects — appropriate for a
  write-boundary check.
- **Test coverage**: Strong. R2 covers the predicate's four logical cases directly; R4 covers all three
  real paths across both crash and in-band seams with three orthogonal assertion layers, all fail-closed.
  Both mutation tripwires demonstrated live (raise-removal and call-deletion both fail the right tests).
  The reuse of `_make_ctx`, `FeatureResult`, and `ExitStack`-based patching matches the surrounding test
  module's style.
- **Pattern consistency**: Excellent — the helper is placed adjacent to the sibling guard, mirrors its
  shape, and the six call sites each follow the identical "build the local dict → guard it → emit it"
  ordering already present at the emit sites. The crash blocks' pre-existing `if preserved/else`
  single-flag discipline is preserved untouched; the guard is purely additive.

## Requirements Drift
**State**: none
**Findings**:
- None — the change is regression insurance codifying a derived invariant of the already-recorded
  ADR-0015/R6 mutual-exclusion policy. It adds no new behavior on any reachable path (no-op under correct
  code), no new event type or `details` field, and introduces no new architectural decision or trade-off
  (the spec's Proposed-ADR section correctly concluded no ADR is warranted). It reuses the existing
  fail-loud-guard idiom already represented in `cortex/requirements/project.md` (the ADR-back-pointing
  pattern at line 40 and the `_guard_no_review_qualifying_sync_merge` R12 precedent).
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
