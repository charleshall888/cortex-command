# Review: fix-morning-report-accuracy-when-post-merge-steps-fail

## Stage 1: Spec Compliance

### Requirement 1: FEATURE_MERGED constant registered
- **Expected**: Add `FEATURE_MERGED = "feature_merged"` to `claude/overnight/events.py` and add the constant to the `EVENT_TYPES` tuple.
- **Actual**: Line 78 defines `FEATURE_MERGED = "feature_merged"` and line 127 adds it to the `EVENT_TYPES` tuple. `grep -c 'FEATURE_MERGED = "feature_merged"' claude/overnight/events.py` returns 1.
- **Verdict**: PASS

### Requirement 2: Event written before post-merge steps in `_accumulate_result`
- **Expected**: Immediately after `merge_result.success` is True — before `read_tier()`, `requires_review()`, or `dispatch_review()` — write `overnight_log_event(FEATURE_MERGED, config.batch_id, feature=name, details={"integration_branch": effective_branch}, log_path=config.overnight_events_path)`. Must use the `effective_branch` local variable.
- **Actual**: `claude/overnight/batch_runner.py:1685-1686` places the call as the first statement inside `if merge_result.success:`, preceding the `read_tier(name)` call on line 1688. Uses `effective_branch` (computed on line 1675 via `_effective_base_branch(...)`), not `config.base_branch`. `FEATURE_MERGED` is imported on line 70.
- **Verdict**: PASS

### Requirement 3: `render_failed_features()` annotates merged features
- **Expected**: Features with `status in ("failed", "paused")` having a `feature_merged` event get a warning line and an overridden suggested-next-step string containing the phrases "Feature is on the integration branch", "Do NOT re-run the feature", and "overnight-events.log".
- **Actual**: `claude/overnight/report.py:925-977`. The `merged_to_integration` set is built from `data.events` before the main render loop. When a failed/paused feature is in that set, the warning line `"- ⚠️ Feature is on the integration branch — merge succeeded but a post-merge step failed after the commit landed."` is appended (lines 961-965) and the suggestion is fully overridden to the spec text containing all three required substrings (lines 967-974). Tests in `tests/test_report.py::test_render_failed_features_annotates_merged_feature` verify all three string assertions pass.
- **Verdict**: PASS

### Requirement 4: `render_deferred_questions()` annotates merged features
- **Expected**: SEVERITY_BLOCKING deferred features with a `feature_merged` event get the `To unblock` line replaced with text that contains "Feature is on the integration branch" and "overnight-events.log" and does NOT contain "re-run the feature".
- **Actual**: `claude/overnight/report.py:834-881`. A `merged_to_integration` set is built from `data.events` before the deferral iteration loop (lines 852-857). For `SEVERITY_BLOCKING` deferrals whose feature is in that set, the `action` variable is overridden to `"Feature is on the integration branch — do NOT re-run. Investigate the post-merge failure (see error details above and overnight-events.log). Address missed post-merge steps manually (review dispatch, backlog write-back)."` The phrase "re-run the feature" is not present in this override (only "do NOT re-run."). Tests in `tests/test_report.py::test_render_deferred_questions_annotates_merged_blocking_deferral` verify all three assertions.
- **Verdict**: PASS

### Requirement 5: Annotation wording elements (all four required elements)
- **Expected**: Annotations must include (a) integration-branch statement, (b) "do NOT re-run" guidance, (c) reference to overnight-events.log, (d) actionable next steps.
- **Actual**: Both renderers include all four elements. `render_failed_features` suggestion: (a) "already on the integration branch", (b) "Do NOT re-run the feature", (c) "check overnight-events.log for the feature_deferred event details", (d) "Address any missed post-merge steps manually (e.g., trigger review, update backlog item)". `render_deferred_questions` action: (a) "Feature is on the integration branch", (b) "do NOT re-run", (c) "and overnight-events.log", (d) "Address missed post-merge steps manually (review dispatch, backlog write-back)".
- **Verdict**: PASS

### Requirement 6: Walkthrough Section 4 updated
- **Expected**: Section 4 of `skills/morning-review/references/walkthrough.md` handles features annotated with the integration-branch warning: states the feature is on the integration branch, does not suggest creating an investigation/re-run ticket, instructs verifying presence, identifying the failed post-merge step, fixing it manually, and advancing the lifecycle manually.
- **Actual**: `skills/morning-review/references/walkthrough.md:268-285` adds step 4 to check for the integration-branch annotation. Instructs stating the feature is already on the integration branch, explicitly does not ask about investigation/re-run tickets, and lists the four required follow-ups (verify presence, identify failed step, address manually, advance lifecycle). `grep -c 'integration branch'` returns 7 (≥ 1).
- **Verdict**: PASS

### Requirement 7: Regression — happy path unaffected
- **Expected**: Features failing pre-merge (no `feature_merged` event) receive no annotation from either renderer. A test asserts `render_failed_features` output for such a feature does NOT contain "integration branch".
- **Actual**: `tests/test_report.py::test_render_failed_features_no_annotation_without_merged_event` constructs a failed feature with `data.events = []` and asserts `"integration branch" not in output`. Additional test `test_render_deferred_questions_no_annotation_without_merged_event` verifies the original "Answer this question and re-run the feature" text is preserved when no merged event is present. All 4 report tests pass (`uv run pytest tests/test_report.py -v` → 4 passed).
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with existing project patterns. `FEATURE_MERGED` follows the SCREAMING_SNAKE event-constant convention (like `FEATURE_COMPLETE`, `FEATURE_PAUSED`). The `merged_to_integration` local set name is descriptive and consistent with how other `render_*` functions build lookup sets (e.g., `cb_features`, `retry_counts`, `conflict_info`). Test class `TestMergedFeatureAnnotations` uses the same pytest class pattern as other test files in this repo.
- **Error handling**: Appropriate. The `overnight_log_event(FEATURE_MERGED, ...)` call is intentionally not wrapped in try/except per the spec's Technical Constraints (absence of the event must unambiguously mean "never merged"). Event read paths rely on `read_events()` which already handles corrupted JSONL lines with a warning. The renderers degrade gracefully if `data.events` is empty — `merged_to_integration` becomes an empty set and no annotation fires, preserving existing behavior.
- **Test coverage**: Four test methods cover all four required scenarios: failed feature with event (annotation fires), failed feature without event (no annotation — regression check), blocking deferral with event (override fires and excludes "re-run the feature"), blocking deferral without event (original text preserved). `just test` exits 0 and `uv run pytest tests/test_report.py -v` shows 4 passed. All acceptance criteria from Requirements 3, 4, and 7 are exercised by direct string assertions.
- **Pattern consistency**: The `render_deferred_questions` change mirrors the set-building pattern already used in `render_failed_features` for retry counts, conflict info, and circuit-breaker features (build a lookup set from `data.events` before the main loop, then check membership per item). The warning line uses the same `- ⚠️` prefix convention seen elsewhere in the renderer. The suggestion-override approach (replace `_suggest_next_step()` return value when the feature is in the merged set) keeps the code path local to the iteration loop without new helper functions.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
