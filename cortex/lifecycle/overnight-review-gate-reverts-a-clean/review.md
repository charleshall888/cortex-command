# Review: overnight-review-gate-reverts-a-clean

## Stage 1: Spec Compliance

### Requirement 1: Thread the review dispatch result into the verdict decision (latent stale-verdict fix)
- **Expected**: `dispatch_review()` consults the review agent's `DispatchResult.success`; on `success == False` the ERROR sentinel is forced WITHOUT parsing `review.md`, at both cycle-1 and cycle-2.
- **Actual**: `review_dispatch.py:292-295` resolves cycle-1 with `if result.success: parse_verdict(...) else: dict(_ERROR_RESULT)`. Cycle-2 mirrors it at `:562-565`. The stale-APPROVED test (`test_failed_dispatch_ignores_stale_approved_review`, `test_review_dispatch.py:379`) writes a real APPROVED `review.md`, forces `success=False`, and asserts `approved == False` / `verdict == "ERROR"`.
- **Verdict**: PASS
- **Notes**: Net-new wiring as the spec describes (not a mirror of the fix/re-merge `result.success` reads). The test is genuinely load-bearing — it would fail if the file were parsed.

### Requirement 2: Add the orthogonal `ReviewResult.could_not_run` boolean and set it at every ERROR-producing site
- **Expected**: `could_not_run: bool = False` on the dataclass; set True only when `success == True` AND verdict is the ERROR sentinel, at cycle-1 and cycle-2; cycle-2 non-canonical normalization closed; threaded into `_write_review_deferral`.
- **Actual**: Field at `review_dispatch.py:65`. Cycle-1 ERROR site `could_not_run = result.success` (`:339`); catch-all non-canonical site `could_not_run = result.success` (`:654`). Cycle-2 normalization added (`:578-586`) routing any non-canonical string to ERROR; cycle-2 flag `cycle2_result.success and cycle2_verdict_str == "ERROR"` (`:623-625`). Deferral carries the flag (`:347-350`, `:633-636`; `_write_review_deferral` param at `:682`, recorded in Context at `:710-720`). Tests cover cycle-1 no-artifact, cycle-2 no-artifact, cycle-2 file-present `BLOCKED`→ERROR (the L578 bug cell), APPROVED/REJECTED/CHANGES_REQUESTED-cycle2 → False, and success=False crash → False (`test_review_dispatch.py:623-686`).
- **Verdict**: PASS
- **Notes**: The full discriminator truth table is exercised, including the cycle-1/cycle-2 normalization symmetry the orchestrator flagged as load-bearing item #1.

### Requirement 3: Preserve the merge for could-not-run by guarding the UPSTREAM revert at all three gate sites
- **Expected**: per-site revert-skip when `rr.could_not_run`; shared flag-helper for coherent detail flags; crash-`except` at each site made could-not-run-aware (`preserved = rr is not None and rr.could_not_run`) so a preserve-path exception does not revert-as-crash; unbound `rr` (dispatch crash) still reverts.
- **Actual**: All three sites verified:
  - Recovery `_recovery_review_gate`: per-site skip `if rr.could_not_run` (`:1135`); `except` guard `preserved = rr is not None and rr.could_not_run` (`:1236`), revert skipped when preserved (`:1237`).
  - Repair `_repair_review_or_revert`: per-site skip (`:1537`); `except` guard (`:1619`), `_reset_ff_merge` skipped when preserved (`:1620-1624`).
  - Primary `apply_feature_result`: per-site skip via `live_merge_sha = None` (`:1853-1861`); `except` guard (`:1992`), revert skipped when preserved (`:1993`).
  - Shared helper `_set_review_error_detail_flags` (`:1023-1048`) sets `could_not_run=True` + `merge_reverted`, never `review_dispatch_crashed`. `rr` is bound to `None` before each `try`, so an unbound `rr` (dispatch crash) reverts.
- Tests: per-site preserve / crash-reverts / preserve-exception-does-not-revert for all three paths (`test_outcome_router.py:2637-3050`). The exception-safety tests force the in-band block to raise by patching `_set_review_error_detail_flags` with `side_effect=RuntimeError` and assert `m_revert.assert_not_called()`.
- **Verdict**: PASS
- **Notes**: Load-bearing items #2 (revert skipped at all three sites, crash reverts) and #3 (each crash-`except` is could-not-run-aware) both verified in code and by non-self-sealing tests.

### Requirement 4: Render preserved-unreviewed merges distinctly in the morning report — both report blocks
- **Expected**: a `could_not_run` branch in `render_deferred_questions()` ordered AHEAD of the `merged_to_integration` "do NOT re-run" branch; the second `render_failed_features()` block does not mis-render; an exec-summary sub-count; `.get(..., False)` for archived-log tolerance.
- **Actual**: `report.py` builds `preserved_could_not_run` from `feature_deferred` events with `details.get("could_not_run", False)` (`:1282-1289`), and the ladder branches on it (`:1305`) BEFORE `merged_to_integration` (`:1313`) — after `reverted_from_integration`. Second block `render_failed_features` checks `preserved_could_not_run` BEFORE `merged_to_integration` for both the warning line (`:1512`) and the suggested-next-step (`:1525`). Exec-summary sub-count at `:583-587`. Tests assert the new annotation and the ABSENCE of both the "do NOT re-run" and generic re-run text in both blocks, using a feature that emits BOTH `feature_merged` and a `could_not_run` deferral (`test_report.py:264-323`).
- **Verdict**: PASS
- **Notes**: Load-bearing item #4 verified — the precedence guard (preserved feature is also in `merged_to_integration`) is explicitly exercised.

### Requirement 5: Flag the integration PR when the batch contains a preserved unreviewed merge
- **Expected**: a runtime producer sets `integration_degraded`/equivalent and writes the warning file naming the feature(s); marker write must fail safe (draft-on-failure), not silently publish unmarked.
- **Actual**: Producer `_preserved_could_not_run_features` (`runner.py:1877`) reads `feature_deferred` events with `details.could_not_run is True`, session-filtered, deduped/sorted. `integration_degraded = state.integration_degraded or bool(preserved_could_not_run)` (`:2130-2132`). Warning-file write with `except OSError → draft_flag="--draft"` + notify (`:2189-2208`); body-compose with `except OSError → draft on preserved` + notify (`:2214-2232`). Success path stays advisory non-draft (deliberate). Tests: producer-driven `test_could_not_run_sets_pr_marker` (copies the PLAIN `state-nonzero-merge.json`, seeds a real deferred event, asserts the runner derives the marker, body non-draft) and `test_could_not_run_marker_write_failure_forces_draft` (injects a real `IsADirectoryError`, asserts `--draft`) (`test_runner_pr_gating.py:910-1000`).
- **Verdict**: PASS
- **Notes**: Load-bearing item #5 verified. The tests avoid the self-sealing trap the plan flagged (no fixture-clone + manual `warning_file.write_text`). `state.py` was NOT modified — the producer is derived at PR-creation time from the authoritative deferral events. This is a sound simplification, not a gap: a persisted state field would be redundant since the events are read at the exact site that needs them, and it keeps the producer and the report annotation reading the same source (so they cannot disagree).

### Requirement 6: Split `review_dispatch_crashed` so it is accurate
- **Expected**: could-not-run path sets `could_not_run` but NOT `review_dispatch_crashed`; crash path sets `review_dispatch_crashed`; the inverted marker test is updated.
- **Actual**: `_set_review_error_detail_flags` sets only `could_not_run` (never `review_dispatch_crashed`) at all three in-band ERROR sites. Each crash-`except` sets `review_dispatch_crashed=True` ONLY when `not preserved` (`:1255`, `:1633`, `:2014`); when `preserved` it sets `could_not_run` instead. `test_error_verdict_event_carries_could_not_run_marker` (`:1822`) now asserts `could_not_run` True AND `review_dispatch_crashed` NOT in details — the inversion the spec required.
- **Verdict**: PASS
- **Notes**: Load-bearing item #6 verified.

### Requirement 7: Feed the systemic breaker for could-not-run under a distinct cause-class, wired end-to-end
- **Expected**: `REVIEW_NO_ARTIFACT` constant + `_SYSTEMIC_ERROR_TYPES` membership; `_record_review_crash_systemic` parameterized; could-not-run records `review_no_artifact`; aggregate threshold; both labels surfaced in the event.
- **Actual**: `constants.py:26` defines `REVIEW_NO_ARTIFACT`, `:40` adds it to `_SYSTEMIC_ERROR_TYPES`. `_record_review_crash_systemic(name, ctx, cause_class=REVIEW_DISPATCH_CRASH)` (`:938-1003`) appends the passed class; the three in-band ERROR sites pass `REVIEW_NO_ARTIFACT` (`:1219`, `:1574`, `:1966`), the crash-`except` blocks pass `REVIEW_DISPATCH_CRASH` (`:1288`, `:1678`, `:2054`). Threshold on aggregate `systemic_pauses_in_batch`; cause_class derived from combined arrival window. Tests: `test_threshold_no_artifact_trips_breaker_preserving_merges` (3 no-artifact → trips, `cause_class == [REVIEW_NO_ARTIFACT]*3`, merges preserved) and `test_mixed_crash_and_no_artifact_trips_with_both_labels` (2 crash + 1 no-artifact → trips at 3 with both labels in arrival order). Both drive the real `apply_feature_result` end-to-end.
- **Verdict**: PASS
- **Notes**: Load-bearing item #7 verified.

### Requirement 8: Register the signals and amend the documented contract
- **Expected**: `feature_deferred` detail keys + `review_no_artifact` cause-class in `bin/.events-registry.md`; re-pin the three `pipeline_systemic_failure` producer lines; amend `pipeline.md` + `docs/internals/pipeline.md`.
- **Actual**: `bin/.events-registry.md` documents `could_not_run` (`:174`) and `merge_reverted` (`:175`) field-additive, and `review_no_artifact` in the `cause_class` field note (`:180`) and the producer row (`:144`). The producer row pins `outcome_router.py:924,997,2357` — which EXACTLY match the three actual `PIPELINE_SYSTEMIC_FAILURE` emit sites (verified via grep). `cortex/requirements/pipeline.md:86` amended to the crash-vs-no-artifact split. `docs/internals/pipeline.md` amended and cross-links the ADR. `grep` for `review_no_artifact` returns matches in both required files.
- **Verdict**: PASS
- **Notes**: The re-pinned line numbers are accurate, not stale.

### Requirement 9: Record the decision as an ADR
- **Expected**: ADR capturing the split + honest safety relocation; pipeline.md back-points to it.
- **Actual**: `cortex/adr/0015-review-could-not-run-vs-dispatch-crash-split.md` exists (numbered 0015 because #313 shipped 0014, per the plan note), with Context / Decision / Trade-off / Consequences. The Trade-off section honestly states unreviewed code may remain on the integration branch and that safety relocates to three surfaces (report + PR marker + breaker), and that it supersedes the prior revert-all-unreviewed posture. `docs/internals/pipeline.md:180` references ADR 0015; `pipeline.md` back-points via the ADR-directory mention.
- **Verdict**: PASS
- **Notes**: The verification predicate (`test -f ... && grep -lq '0015' docs/internals/pipeline.md`) holds.

## Stage 2: Code Quality

- **Naming conventions**: Consistent with the module. `could_not_run` is the positive discriminator named throughout; `REVIEW_NO_ARTIFACT`/`REVIEW_DISPATCH_CRASH` mirror the existing cause-class naming; helpers (`_set_review_error_detail_flags`, `_preserved_could_not_run_features`) follow the underscore-private + descriptive convention. The `preserved = rr is not None and rr.could_not_run` idiom is used identically at all three sites, aiding readability.
- **Error handling**: Strong. The exception-safety design (bind `rr=None` before the `try`, guard the `except` revert on `preserved`) is the subtlest correctness point and is implemented coherently at all three divergent-revert sites. The PR-marker producer fails safe in BOTH failure modes (write failure and body-compose failure each force `--draft`) rather than silently publishing an unmarked non-draft PR. `_write_review_deferral` threads the flag into the on-disk Context so the deferral and the event cannot disagree.
- **Test coverage**: Excellent and NOT self-sealing. The plan's per-task verification steps are genuinely exercised: the stale-verdict test writes a real on-disk APPROVED and forces success=False; the exception-safety tests force the in-band block to raise and assert no revert; the systemic tests drive the real `apply_feature_result` through `_record_review_crash_systemic`; the PR-marker tests drive the producer from a plain (non-degraded) fixture + a seeded event and inject a real `IsADirectoryError`. The report tests use a feature that emits both `feature_merged` and a `could_not_run` deferral, exercising the load-bearing precedence guard. The pre-existing real-git revert tests were correctly updated with `could_not_run=False` so they keep exercising the revert path.
- **Pattern consistency**: The new signal is threaded through dispatch → outcome-router → report/runner exactly as the plan's pipeline pattern describes, with no new state machine or persisted state field. The report and runner producers both read `feature_deferred` / `could_not_run` identically, so the three surfaces (report annotation, exec-summary count, PR marker) share one source of truth. The cycle-1/cycle-2 normalization symmetry closes a real latent asymmetry rather than papering over it.

## Requirements Drift
**State**: none
**Findings**:
- None. Task 8 amended `cortex/requirements/pipeline.md:86` as part of this feature, and the amended contract accurately reflects the implemented behavior: genuine crash reverts + feeds the breaker as `review_dispatch_crash`; could-not-run preserves the merge, flags it on the report AND the integration PR, and feeds the breaker as `review_no_artifact`; aggregate threshold with per-kind labels; revert-skip guarded per-site at all three merge sites. The `state.py`-not-modified simplification introduces no behavior absent from the docs (the integration-PR degraded marker is documented as the merge-decision-surface signal; how `integration_degraded` is derived is an internal detail, owned by `docs/internals/pipeline.md`). No implemented behavior is missing from the requirements docs.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
