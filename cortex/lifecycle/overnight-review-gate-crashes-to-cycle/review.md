# Review: overnight-review-gate-crashes-to-cycle

## Stage 1: Spec Compliance

### Requirement R1: Capture child stderr + exit_code in the dispatch_error event
- **Expected**: The `ProcessError`/`Exception` branches of `dispatch_task` record the already-collected, redacted/capped `_stderr_lines` and the subprocess `exit_code` into the `dispatch_error` payload (not only the placeholder `error_detail`).
- **Actual**: `dispatch.py:802-813` (ProcessError branch) and `:825-836` (Exception branch) build `child_stderr = "\n".join(_stderr_lines)` and `exit_code = getattr(exc, "exit_code", None)` and add both as payload fields. `tests/test_dispatch.py` seeds a recognizable marker and asserts it survives into the payload with a non-null exit_code. The `dispatch_error` registry producer-line row was updated to `776,807,830` (accurate).
- **Verdict**: PASS
- **Notes**: Real child stderr is sourced from `_stderr_lines` (the SDK hardcodes `ProcessError.stderr` to a placeholder), exactly as the spec requires.

### Requirement R2: Every roll-back-able merge site returns its merge SHA
- **Expected**: Primary merge → `MergeResult.merge_sha`; rework re-merge → `merge_sha` on `ReviewResult`; recovery re-merge → recovery result's `merge_sha` — each the integration-branch MERGE commit (two parents), `None` when no merge landed.
- **Actual**: `merge.py:50` adds `MergeResult.merge_sha`, populated at `:331-337` by `git rev-parse HEAD` in the integration `repo_path` immediately after the `--no-ff` merge, surfaced only on the success return (`:380`), never on the inline test-failure revert path. `review_dispatch.py:54` adds `ReviewResult.merge_sha`, threaded from `remerge_result.merge_sha` at `:561,581`. `merge_recovery.py:43` adds `MergeRecoveryResult.merge_sha`, sourced from `MergeResult.merge_sha` (flaky `:293`, recovered `:399`) — explicitly NOT `_get_branch_sha` (the feature-branch tip). `tests/test_merge_sha_capture.py` asserts each result exposes the merge commit (two-parent) and `None` on non-landing.
- **Verdict**: PASS
- **Notes**: The captured SHA is the merge commit at every site, so `git revert -m 1 <sha>` is valid and position-independent. Capture sites are correct.

### Requirement R3: Revert the LIVE merge on every non-APPROVED outcome, SHA-anchored under the lock
- **Expected**: On the review-deferred AND review-crash `except` paths, revert the feature's live SHA via `git revert -m 1 --no-edit <sha>` (capture-not-check) before worktree cleanup, while `ctx.lock` is held; rewritten SHA-anchored `revert_merge`; abort + blocking deferral on a non-zero revert.
- **Actual**: `merge.py:413-525` rewrites `revert_merge(merge_sha, repo_path, log_path, feature)` SHA-anchored, capture-not-check, with a `RevertResult` and an abort branch (`git revert --abort` → `aborted=True`) on a genuine conflict. Both async non-APPROVED paths wire it under the held lock: deferred at `outcome_router.py:1709-1717` and `except` at `:1819-1826`, both inside `async with ctx.lock:` (opened `:1597`). Mock-spy tests (`test_deferred_path_reverts_live_merge_sha`, `test_except_path_reverts_live_merge_sha`) assert the live SHA; the real-git harness (`tests/test_revert_merge_real_git.py`) asserts tree state after revert plus the abort branch.
- **Verdict**: PASS
- **Notes**: ERROR detection keys off the verdict STRING (`rr.verdict == "ERROR"`), never `cycle`. The revert runs under the lock on every path.

### Requirement R4: Rework-path rollback reverts the live re-merge SHA, not a stale one
- **Expected**: Revert the re-merge's live SHA (threaded onto `ReviewResult`), accounting for `merge_feature` having possibly already inline-reverted on a test failure; query branch state, do not double-revert.
- **Actual**: The defer path prefers the threaded `rr.merge_sha` over the primary SHA (`outcome_router.py:1698-1700`, `:1065`). `revert_merge` queries `_revert_in_progress` (REVERT_HEAD via `git rev-parse --git-path`, worktree-layout-safe) at `merge.py:490`; an already-reverted no-op returns `RevertResult(success=True, already_reverted=True)` with no abort/escalation. `tests/test_revert_rework_remerge_real_git.py` drives a cycle-1 re-merge → cycle-2 defer and asserts no feature code remains and no failed double-revert.
- **Verdict**: PASS
- **Notes**: The query-then-revert is not a TOCTOU race because the lock is held throughout.

### Requirement R5: Remove the dead sync review-defer branch
- **Expected**: `grep -c "review_result = "` returns 0; the dead `:657` branch gone or annotated unreachable.
- **Actual**: `grep -c "review_result = " cortex_command/overnight/outcome_router.py` returns `0`. The sync `_apply_feature_result` `completed` flow proceeds straight from merge handling to deferred/failed/paused with no `review_result` branch.
- **Verdict**: PASS

### Requirement R6: Could-not-run review writes a blocking deferral file, surfacing reconciled to the revert
- **Expected**: The live ERROR/deferred path writes a `SEVERITY_BLOCKING` deferral; the surface says "reverted — safe to re-review" for a successfully-reverted feature and reserves "do NOT re-run" for the dependent-conflict abort case.
- **Actual**: `review_dispatch.py:314-322` writes the deferral on the ERROR path via `_write_review_deferral` (severity `blocking`). `report.py:1056-1063` builds `reverted_from_integration` from `feature_deferred` events where `details.merge_reverted is True`; the warning gate (`:1071-1086`) emits "Merge reverted — safe to re-review/re-run" for reverted features and retains "do NOT re-run" only for `merged_to_integration` features not reverted (the R-edge). The R-edge deferral text (`:1739-1759`, `:1092-1112`) names dependent feature(s) Y via `_overlapping_features` and keeps the "do NOT re-run" annotation. `tests/test_report.py` covers the reconciled and R-edge surfaces.
- **Verdict**: PASS
- **Notes**: The recovery-path R-edge carries its "do NOT re-run" annotation in the deferral `context` text (it does not emit a `FEATURE_MERGED` event, so it relies on the file text rather than the report action line) — a coherent design since the deferral file is the authoritative surface.

### Requirement R7: Deferral-file write is resume-idempotent with a single ID source
- **Expected**: Re-running the defer path does not mint a duplicate `-q00N.md`; review-defer and `except` paths use a single reconciled question-id source.
- **Actual**: `deferral.py:214-217` short-circuits on an existing `{feature}-q*.md` (`_existing_deferral_for_feature`, lowest ID) when `idempotent=True`. `_write_review_deferral` (`review_dispatch.py:651`) uses `question_id=0` + `idempotent=True` (the deferred-dir scan as the single source); the `except` path (`outcome_router.py:1845-1861`) also uses `question_id=0` + `idempotent=True`. `tests/test_deferral.py` asserts exactly one file after a double defer.
- **Verdict**: PASS

### Requirement R8: Review-deferred backlog write-back uses status `deferred`
- **Expected**: The review-deferred path writes backlog status `deferred` (not `in_progress`).
- **Actual**: The `rr.deferred` review-deferred path writes `"deferred"` (`outcome_router.py:1803-1804`); recovery and repair_completed defer paths likewise write `"deferred"`. `test_review_deferred_writes_back_status_deferred` confirms.
- **Verdict**: PASS
- **Notes**: Minor observation (not a FAIL): the review-CRASH `except` path (`:1869-1870`) still writes `"in_progress"`, while the deferral file is written and the feature lands in `features_deferred`. R8's stated acceptance targets the review-DEFERRED path, which is correct; the crash path is a separate arm. The residual `in_progress` on the crash arm reads as ordinary active work despite the feature being deferred — a small inconsistency worth a follow-up, but outside R8's acceptance scope.

### Requirement R9: Distinguish could-not-run from review-ran-and-said-no
- **Expected**: The `FEATURE_DEFERRED` event for verdict `ERROR` carries a distinguishing marker; detection keys off the verdict STRING, not `cycle`.
- **Actual**: All three review gates set `deferred_details["review_dispatch_crashed"] = True` and `["could_not_run"] = True` only when `rr.verdict == "ERROR"` (`outcome_router.py:1782-1784`, `:1125-1127`, `:1450-1452`). A REJECTED outcome carries neither. `test_error_verdict_event_carries_could_not_run_marker` and `test_rejected_verdict_event_has_no_could_not_run_marker` confirm.
- **Verdict**: PASS

### Requirement R10: Test-recovery success routes a review-qualifying feature through review, under the re-acquired lock
- **Expected**: Both recovery success branches dispatch review for `requires_review` features before `merged`; revert+defer on non-APPROVED/crash; the recovery RE-MERGE itself runs under the re-acquired lock.
- **Actual**: `_recovery_review_gate` (`outcome_router.py:994-1198`) is called from both flaky (`:2047`) and recovered (`:2085`) branches; non-`requires_review` features are logged as a deliberate skip (`:1026-1041`), never a blanket escape. The recovery re-merge (`recover_test_failure`, `:2020`) is inside the re-acquired `async with ctx.lock:` (`:2019`) that also wraps the review and revert. `test_recovery_remerge_runs_under_held_lock` instruments a real `asyncio.Lock` and asserts `ctx.lock.locked()` is True at the moment `recover_test_failure` runs. `test_recovery_qualifying_feature_not_merged_without_approved` and the flaky/recovered dispatch tests confirm review routing.
- **Verdict**: PASS
- **Notes**: The lock scope covers the re-merge itself, not just the post-merge steps — exactly the Technical Constraint the review flagged for verification.

### Requirement R11: Systemic review crashes trip the circuit breaker coherently
- **Expected**: A review-crash deferral increments `systemic_pauses_in_batch` AND records into the structure the threshold block reads to compute a non-empty `cause_class` attributable to the review crashes; at threshold, `global_abort_signal=True` and a `PIPELINE_SYSTEMIC_FAILURE` event with a non-empty cause.
- **Actual**: `_record_review_crash_systemic` (`:936-986`) increments `systemic_pauses_in_batch` and appends `REVIEW_DISPATCH_CRASH` to `cb_state.review_crash_classes` (new field, `types.py:50`). The threshold block derives `cause_class` from `paused_systemic + review_crash_classes` trailing window. `REVIEW_DISPATCH_CRASH` is a member of `_SYSTEMIC_ERROR_TYPES` (`constants.py:26`). Called on every review-crash path (ERROR verdict and raised exception); excluded for REJECTED/CHANGES_REQUESTED. `test_cause_class_not_derived_from_unrelated_paused_feature` seeds an unrelated NON-systemic paused feature and asserts the emitted cause_class equals `[REVIEW_DISPATCH_CRASH] * 3` and excludes "task paused".
- **Verdict**: PASS
- **Notes**: The cause_class is genuinely attributable to the review crashes (not an unrelated paused feature) — the specific concern flagged for this review.

### Requirement R12: Close the remaining unreviewed-merge paths (uniform review-or-revert at every merge-to-`merged` site)
- **Expected**: `repair_completed` ff-merge and sync `completed` branch route review-qualifying features through review-or-revert; live sites that argue unreachability install a runtime guard that RAISES (not a prose annotation).
- **Actual**: The `repair_completed` ff-merge is lifted into the async `_repair_completed_review_gate` (`:1246`), which dispatches review for qualifying features and rolls back the ff-merge with `git reset --hard <pre_ff_base>` on defer/crash. The two sync merge-success arms (`_apply_feature_result:568,700`) call `_guard_no_review_qualifying_sync_merge` (`:1230`), which `raise`s if `requires_review` is true. The exhaustiveness pin (`test_merge_to_merged_write_sites_are_exactly_the_known_set`) asserts the complete append-site set is `{_apply_feature_result: 2, _repair_completed_review_gate: 1, apply_feature_result: 3}` (six total), pins the `"merged"` write-back co-location, pins exactly two runtime guards on the sync arms, and pins the total at 6.
- **Verdict**: PASS
- **Notes**: Implementer deviation #1 (six sites: 4 review-gated + 2 runtime-guarded vs the plan's five) holds the state-invariant at every site and the exhaustiveness pin genuinely fails if a seventh un-gated site is added (it changes a per-function append count). Deviation #2 (`git reset --hard <pre_ff_base>` for the ff-merge, which leaves no merge commit) runs under the held `ctx.lock` — both the `pre_ff_base_sha` capture (`:1305`) and the reset (`_reset_ff_merge:1556`) are inside `_repair_completed_review_gate`, called from `apply_feature_result` under `async with ctx.lock`. Because the lock serializes all integration-worktree mutations, no sibling feature can advance HEAD between the base-tip capture and the reset, so the reset cannot discard concurrent sibling commits. Both deviations are sound against the spec's intent.

### Technical Constraints / Acceptance guarantees
- **State invariant (every path)**: PASS — all six merge-to-`merged` sites are review-gated or runtime-guarded; the exhaustiveness pin fails on a seventh un-gated site.
- **Physical-code revert guarantee (with documented dependent-conflict exception)**: PASS — real-git tests prove the revert leaves no feature code on the branch including the intervening-merge discriminator (distinguishing the SHA-anchored fix from the dead HEAD-anchored code); the dependent-conflict R-edge aborts (`git revert --abort`), surfaces a `SEVERITY_BLOCKING` deferral naming Y, retains "do NOT re-run", and keeps the feature in `deferred` state.
- **All reverts + the recovery re-merge run under `ctx.lock`**: PASS — verified at the primary, rework, recovery (re-merge included), and repair (reset) paths.
- **Events-registry drift gate**: PASS — `just check-events-registry` exits 0; producer-line rows updated for `dispatch_error`, `merge_revert_error`, `merge_reverted`, `pipeline_systemic_failure`.

## Requirements Drift
**State**: detected
**Findings**:
- `cortex/requirements/pipeline.md` "Post-Merge Review" acceptance (line 70) states only "review agent failure → feature status `deferred`; deferral file written" — it does not capture the new fail-safe behavior that a non-APPROVED/crashed/errored review now REVERTS the feature's live merge commit (SHA-anchored, under the lock) before deferring. The revert-on-failure containment is new behavior absent from the requirements.
- `cortex/requirements/pipeline.md` "Post-Merge Test Failure Recovery" acceptance (line 81) states the flaky guard marks the feature `merged` directly; the implementation now routes recovery success (flaky and recovered) through review-or-revert before `merged` for review-qualifying features. The requirement does not reflect this added gate.
- `cortex/requirements/pipeline.md` line 72 still describes the synthetic "morning review `review_verdict: APPROVED, cycle: 0`" event that is not emitted in code (the spec's documented requirement-vs-code drift). The implementation correctly builds no handling for it, but the requirement text remains stale.
- The systemic-failure circuit breaker now trips on `SYSTEMIC_FAILURE_THRESHOLD` review-dispatch crashes (a new `review_dispatch_crash` cause class). pipeline.md's circuit-breaker behavior (lines 57, 168) describes only worker-failure pauses feeding the breaker, not review crashes.
**Update needed**: `cortex/requirements/pipeline.md`

## Suggested Requirements Update
**File**: cortex/requirements/pipeline.md
**Section**: Post-Merge Review
**Content**:
```
- On any non-APPROVED outcome (REJECTED, CHANGES_REQUESTED after rework, or a could-not-run/crashed review with verdict ERROR), the feature's live merge commit is reverted SHA-anchored under `ctx.lock` before deferring, so no unreviewed code remains on the integration branch; the one exception is a dependent-conflict revert that aborts and surfaces as a blocking deferral naming the dependent feature. Review gating applies uniformly at every merge-to-`merged` site (primary, post-recovery re-merge, and the repair_completed ff-merge), and `SYSTEMIC_FAILURE_THRESHOLD` review-dispatch crashes in a batch trip the systemic circuit breaker with a `review_dispatch_crash` cause class.
```

## Stage 2: Code Quality
- **Naming conventions**: Consistent with project patterns. New helpers (`_recovery_review_gate`, `_repair_completed_review_gate`, `_repair_review_or_revert`, `_reset_ff_merge`, `_guard_no_review_qualifying_sync_merge`, `_record_review_crash_systemic`) follow the existing `_verb_noun` private-helper convention; `RevertResult` mirrors `MergeResult`/`MergeRecoveryResult`; `merge_sha` fields and `REVIEW_DISPATCH_CRASH` constant are descriptive and co-located with their dataclasses.
- **Error handling**: Appropriate for the context. Git subprocess calls are capture-not-check (`revert_merge`, `_reset_ff_merge`, ff-merge), inspecting `returncode`/`REVERT_HEAD` state rather than relying on exceptions. The abort-on-conflict path (`git revert --abort`) leaves no half-applied revert. `dispatch_review` crashes are caught and routed through the same revert+defer path as the substantive-defer path, never leaving merged code. The `_revert_in_progress` check resolves `REVERT_HEAD` via `git rev-parse --git-path` so it is correct for both plain repos and linked worktrees.
- **Test coverage**: Strong and meets the spec's fidelity mandate. Real-git harness tests (`tests/test_revert_merge_real_git.py`, `tests/test_revert_rework_remerge_real_git.py`) build genuine `--no-ff` merges, interpose an unrelated intervening merge before reverting by SHA (the discriminator against the dead HEAD-anchored code), and drive a real revert conflict to exercise the abort branch — these run production `revert_merge` against real git trees, not mocks. The lock-instrumented recovery test uses a real `asyncio.Lock` to prove the re-merge runs under the held lock. The unconditional exhaustiveness pin AST-enumerates every `features_merged.append` and `"merged"` write-back and fails on enumeration drift. Mock-spy tests cover the call contract at each gate. The only `just test` failure is `tests/test_mcp_subprocess_contract.py` (a `uv run --script` PyPI fetch blocked by the offline sandbox — DNS error, unrelated to this change); all 136 implementation-relevant tests pass directly.
- **Pattern consistency**: Follows existing conventions — `overnight_log_event` for batch-owned events, `write_deferral`/`DeferralQuestion` for deferral files, `_write_back_to_backlog` for status, `async with ctx.lock` for integration-worktree mutations, registered-event reuse (`merge_reverted`/`merge_revert_error`) with same-commit registry updates.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
