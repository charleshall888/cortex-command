# Review: surface-built-but-merge-blocked-overnight

## Stage 1: Spec Compliance

### Requirement R1: Re-point the genuine-merge-conflict terminus from `paused` to recoverable
- **Expected**: In `_apply_feature_result`, the merge-failure handling routes a genuine conflict (`merge_result.conflict is True`) to `features_deferred` + recoverable write-back, NOT `features_paused`; non-conflict failures (`conflict is False`, including systemic) stay `paused` and still increment `consecutive_pauses`/`systemic_pauses_in_batch`. `recover_test_failure` untouched.
- **Actual**: `outcome_router.py:682-728` adds an `elif merge_result.conflict:` branch that appends to `features_deferred`, emits `FEATURE_DEFERRED`, calls the recoverable write-back, and does NOT touch the pause counters. The non-conflict `else` branch (`:729-746`) is unchanged: `features_paused.append`, `consecutive_pauses += 1`, `if error in _SYSTEMIC_ERROR_TYPES: systemic_pauses_in_batch += 1`. The `recover_test_failure` terminus is not modified.
- **Verdict**: PASS
- **Notes**: Tests `test_merge_conflict_recoverable` and `test_non_conflict_still_paused` pass. The latter uses `error="infrastructure_failure"`, verified to be a member of `_SYSTEMIC_ERROR_TYPES`, and asserts `systemic_pauses_in_batch == 1`. Both mock `merge_feature` rather than hand-building a result, so routing flows through the production `:581` merge call and no-commit guard.

### Requirement R2: Add `recoverable_branch` to the record AND thread it through the carrier
- **Expected**: (a) `recoverable_branch: Optional[str] = None` on `OvernightFeatureStatus`; (b) `recoverable_branch` key in the `features_deferred` entry dict; (c) `_map_results_to_state` sets `fs.recoverable_branch = entry.get("recoverable_branch")`. Round-trips via save/load; absent key loads `None`.
- **Actual**: (a) Field at `state.py:108` (alongside `repo_path: Optional[str] = None` at `:107`), with docstring at `:89-93`. (b) Entry dict carries `"recoverable_branch": recoverable_branch` at `outcome_router.py:710`. (c) `map_results.py:120` sets `fs.recoverable_branch = entry.get("recoverable_branch")` inside the `features_deferred` loop, below the `_TERMINAL_STATUSES` early-continue.
- **Verdict**: PASS
- **Notes**: `test_recoverable_branch_roundtrip` and `test_load_state_defaults_recoverable_branch_none` pass; persistence is automatic via `asdict`/`**fs_dict` splat, confirming backward compat.

### Requirement R3: Source `recoverable_branch` from the resolved branch, never a bare reconstruction
- **Expected**: `recoverable_branch` = the in-scope `actual_branch` (`ctx.worktree_branches.get(name)`) when non-empty, and `None` (NEVER `f"pipeline/{name}"`) when absent.
- **Actual**: `actual_branch = (ctx.worktree_branches or {}).get(name)` at `outcome_router.py:550`; the conflict branch sets `recoverable_branch = actual_branch or None` at `:695`. Never reconstructs `f"pipeline/{name}"`.
- **Verdict**: PASS
- **Notes**: `test_recoverable_branch_suffix` (`worktree_branches={"feat-a": "pipeline/feat-a-2"}` → persists `"pipeline/feat-a-2"`) and `test_recoverable_branch_absent` (`{}` → persists `None`) both pass and flow the routed entry through the real `_map_results_to_state` carrier. Spec/plan cited `:534`/`:832` for the local; the actual resolution site is `:550` (line drift only — source is the correct in-scope `ctx.worktree_branches`, not the outer async frame nor `merge_start.branch`).

### Requirement R4: The recoverable feature stops auto-retrying within the session
- **Expected**: Landing `deferred` excludes it from `_count_pending` (counts `pending/running/paused`) and from re-dispatch. Property assertion, no code change.
- **Actual**: `_count_pending` (runner) counts only `pending/running/paused`; a `deferred` feature is excluded for free. No code change needed.
- **Verdict**: PASS
- **Notes**: `test_recoverable_not_redispatched` invokes the real `_count_pending` against a recoverable `deferred` feature and asserts count 0.

### Requirement R5: The live status view does not mislabel a recoverable feature as failed
- **Expected**: A discriminator so a feature with `recoverable_branch` set is reported in a distinct recoverable group, not `failed`.
- **Actual**: `status.py:45-69` extracts a pure `bucket_features` helper returning a `FeatureBuckets` NamedTuple with a `recoverable` field; `recoverable_branch is not None` is checked FIRST (`:58-59`) before the `status in ("failed","deferred","paused")` arm. `render_status` calls it (`:367`) and prints a "Recoverable" section (`:479-484`).
- **Verdict**: PASS
- **Notes**: `test_recoverable_not_failed` asserts the recoverable feature is absent from `failed` and present in `recoverable`; `test_non_recoverable_buckets_unchanged` confirms non-recoverable bucketing is unchanged. The refactor to a testable helper avoids stdout-scraping as the plan intended.

### Requirement R6: The backlog write-back positively records a recoverable disposition
- **Expected**: Thread `recoverable_branch` into `_write_back_to_backlog`; for the recoverable sub-case write `status: in_progress` (NOT `backlog`, not nothing) AND record the branch; existing callers unaffected.
- **Actual**: Keyword-only `recoverable_branch: Optional[str] = None` added (`outcome_router.py:394-395`). When truthy, the `_OVERNIGHT_TO_BACKLOG` mapping is bypassed and `fields = {"status": "in_progress", "session_id": None, "recoverable_branch": <branch>}` (`:425-430`). The best-effort try/except envelope is preserved (`:414-451`). The early-return guard now also accounts for the recoverable case (`if mapping is None and not recoverable_branch: return`, `:411`).
- **Verdict**: PASS
- **Notes**: `test_recoverable_writeback_positive` passes — asserts `status: in_progress` and the branch string in the item text.

### Requirement R7: No spurious from-scratch-rebuild follow-up for the recoverable sub-case
- **Expected**: In `create_followup_backlog_items`, a feature with `recoverable_branch` set MUST NOT produce the `deferred`-branch "Retry deferred" rebuild item; question-deferrals unchanged.
- **Actual**: `report.py:271-272` adds `if fs.recoverable_branch is not None: continue` before the item is built, after the `status not in (...)` skip. Question-deferrals (`recoverable_branch is None`) fall through to the unchanged `Retry deferred` path.
- **Verdict**: PASS
- **Notes**: `test_recoverable_no_rebuild_followup` passes — no item for the recoverable feature; the question-deferral still produces its `Retry deferred` item.

### Requirement R8: The morning report surfaces recoverable features and excludes them from the deferred-question count
- **Expected**: A render section listing each recoverable feature naming its branch; exec-summary `deferred` count EXCLUDES recoverable; `render_deferred_questions` byte-identical for question-deferrals.
- **Actual**: New `render_built_merge_blocked` (`report.py:1218-1256`) selects `recoverable_branch is not None`, names the branch, returns `""` when none (omit-when-empty convention), wired into `generate_report` at `:2174` adjacent to `render_deferred_questions`. The exec-summary count at `:377-381` now requires `f.status == "deferred" and f.recoverable_branch is None`. `render_deferred_questions` body is untouched (only the section-list insertion appears in the diff).
- **Verdict**: PASS
- **Notes**: `test_recoverable_surface_positive` passes — (a) body contains the recoverable line + branch, (b) deferred count is 1 not 2, (c) `render_deferred_questions(data) == render_deferred_questions(baseline)` byte-identical.

### Requirement R9: A built-but-merge-blocked session is not labeled `[ZERO PROGRESS]`; empty-branch guard intact
- **Expected**: New `_count_built_merge_blocked_home_repo` helper (mirrors `_count_merged_home_repo`) counting `recoverable_branch is not None and repo_path is None`; inner `[ZERO PROGRESS]` gate excludes such sessions; outer `commit_count == 0` guard unchanged.
- **Actual**: Helper at `runner.py:1503-1515`. The inner label gate at `:1733` is now `if mc_merged_count == 0 and mc_recoverable_count == 0:`; the sibling metadata conditional at `:1887` mirrors the same exclusion. The outer `commit_count == 0` gate at `:1711` is unchanged (still skips PR creation entirely).
- **Verdict**: PASS
- **Notes**: `test_recoverable_not_zero_progress` (commits=5 → PR created, no `[ZERO PROGRESS]` title) and `test_zero_commits_still_skips_pr` (commits=0 → no PR) both pass, routing through the real `_post_loop` with only externals mocked.

### Requirement R10: The canonical `deferred` definition documents the recoverable sub-case
- **Expected**: Amend `pipeline.md` `deferred` definition so `grep -c "recoverable_branch"` ≥ 1.
- **Actual**: `pipeline.md:40` adds a bullet documenting that a `deferred` feature with `recoverable_branch` set is the built-but-merge-blocked recoverable sub-case, distinct from question-deferrals, surfaced positively keyed off `recoverable_branch`.
- **Verdict**: PASS
- **Notes**: `grep -c "recoverable_branch" cortex/requirements/pipeline.md` returns 1.

### Acceptance criteria (spec/plan)
- **Expected**: Conflict → persisted `deferred` + suffix-correct `recoverable_branch` (or `None`, never bare reconstruction); excluded from `_count_pending`; backlog `status: in_progress` + branch (no rebuild follow-up); morning report + live status surface it and exclude it from the deferred count; not `[ZERO PROGRESS]` with commits > 0; all question-deferral paths byte-for-byte unchanged. `just test` exits 0.
- **Actual**: All ten requirement tests pass. Full overnight suite: 519 passed, 1 skipped (unrelated `launchctl` environment skip), 0 failed. The systemic-breaker invariant, the `None`-not-reconstruction invariant, the `status: in_progress`-not-`backlog` invariant, the inner-vs-outer gate split, and the byte-identical `render_deferred_questions` are each independently asserted.
- **Verdict**: PASS
- **Notes**: The MVP-scoped 2-way discriminator soundness holds — no sibling-cascade sweep emits `deferred`+`recoverable_branch=None` for never-built dependents in this change (verified: no such producer added).

## Requirements Drift
**State**: detected
**Findings**:
- The Conflict Resolution acceptance criterion (`pipeline.md:56`, "If repair fails after escalation, feature is paused; in-progress merge is aborted before returning") still asserts `paused` as the terminal disposition for an exhausted-repair merge conflict. R1 changed that disposition for a genuine conflict to recoverable `deferred`. The Task 9 amendment widened the `deferred` *definition* (under Feature Execution) but did not reconcile this Conflict Resolution criterion — the doc's own statement of the behavior R1 altered. (The line 50 Outputs already say "feature paused/deferred", so the contradiction is localized to the line 56 criterion.)
**Update needed**: `cortex/requirements/pipeline.md`

## Suggested Requirements Update
**File**: `cortex/requirements/pipeline.md`
**Section**: Conflict Resolution → Acceptance criteria (the bullet at line 56)
**Content**:
```
  - If repair fails after escalation on a genuine merge conflict, the in-progress merge is aborted before returning and the feature is routed to recoverable `deferred` with its `recoverable_branch` set (built-but-merge-blocked: not re-queued, not auto-retried, surfaced positively); non-conflict / systemic merge failures remain `paused` and feed the systemic circuit breaker
```

## Stage 2: Code Quality
- **Naming conventions**: Consistent. `recoverable_branch` matches the existing optional-scalar naming (`repo_path`, `recovery_attempts`). `_count_built_merge_blocked_home_repo` mirrors `_count_merged_home_repo`. `render_built_merge_blocked` follows the `render_*` section convention. `bucket_features`/`FeatureBuckets` is a clean, documented extraction.
- **Error handling**: Appropriate. The `_write_back_to_backlog` best-effort try/except envelope is preserved on the recoverable path; the early-return guard correctly extends to `if mapping is None and not recoverable_branch`. `render_built_merge_blocked` guards `data.state is None`. The merge-conflict branch reuses the existing `FEATURE_DEFERRED` event (no new event) per spec.
- **Test coverage**: Strong. All ten plan verification commands pass. Test fidelity is high: Task 4 mocks `merge_feature` (not a hand-built result) so routing flows through the production no-commit guard and merge-failure handling; the suffix/absent tests flow the producer output through the real `_map_results_to_state` carrier (closing the fabricated-state gap); R9 drives the real `_post_loop`; R8's byte-identical assertion compares `render_deferred_questions` against a baseline; R4 uses the real `_count_pending`. Added regression tests (`test_non_recoverable_buckets_unchanged`, the question-deferral fall-through assertions) protect the unchanged paths.
- **Pattern consistency**: Follows established conventions — optional-scalar field on the shared record (mirrors `repo_path`/`recovery_attempts`), `**fs_dict` splat for automatic backward compat, render-section omit-when-empty (mirrors `render_complexity_normalized`), `_count_*_home_repo` helper mirror, and the carrier-not-routing-site state-write discipline the spec's "Correct carrier" constraint demands.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
