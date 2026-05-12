# Specification: Morning Report — Surface Failure Root Cause Inline

## Problem Statement

When a feature fails overnight, the morning report displays a generic error message ("completed with no new commits — check pipeline-events.log task_output and task_git_state events") that requires the user to manually trace through event logs, branch history, and git log to find the root cause. This violates the project's "morning is strategic review — not debugging sessions" philosophy. The no-commit guard in `batch_runner.py` produces a single message for all failure modes, even though enough context is available at that point to classify common failure patterns.

## Requirements

1. **No-commit guard classification**: When a feature completes with no new commits, the no-commit guard must classify the failure into one of these categories and produce a descriptive error string for each:
   - **Stale feature**: Branch already has commits that are ancestors of main (feature was implemented in a prior session). Acceptance: error string contains the substring `"already implemented"` or `"already merged"`.
   - **No changes produced**: Agent ran but produced no diff. Acceptance: error string contains the substring `"no changes produced"`.
   - **Fallback**: If classification cannot be determined, or if any exception occurs during classification. Acceptance: error string says "completed with no new commits" with the branch name but does not tell the user to check log files.

2. **Classification helper contract**: The classification logic must be a standalone function with the following properties:
   - **Inputs**: feature name, branch name, base branch name. The function runs its own git queries — it does not receive pre-computed `_get_changed_files()` output (which conflates "zero diff" with "git command failed").
   - **Error handling**: The function must catch all exceptions (subprocess failures, timeouts, invalid refs) and return the fallback classification. The no-commit guard must never raise an exception or produce an empty/None error string as a result of classification logic. Any git subprocess calls should use a reasonable timeout (consistent with existing `_get_changed_files()` pattern).
   - **Return value**: A human-readable error string. The function always returns a non-empty string.

3. **Enhanced `_suggest_next_step()` patterns**: The report's suggestion function must produce specific next-step suggestions for the new no-commit guard classifications, in addition to the existing patterns (merge conflict, test failure, circuit breaker). Acceptance: the substrings `"already implemented"`, `"already merged"`, and `"no changes produced"` each trigger a distinct, actionable suggestion rather than the default.

4. **Coupling test**: A test must verify that the error strings produced by the classification helper for each named category (stale feature, no changes produced) match the substring patterns expected by `_suggest_next_step()`. This catches silent drift between the two modules.

5. **Preserve existing error strings**: Error strings from other failure sources (plan parse error, merge failure, task failure, budget exhausted, circuit breaker) must not be modified. Acceptance: only the no-commit guard error string and `_suggest_next_step()` are changed.

6. **No schema changes**: The `OvernightFeatureStatus.error` field remains `Optional[str]`. No new fields are added to `state.py`, `map_results.py`, or the batch results JSON format. Acceptance: `state.py` and `map_results.py` are unchanged.

## Non-Requirements

- Building a general-purpose failure classification system or adding a `failure_class` field to the state schema — the free-form error string is sufficient for this problem.
- Classifying failures that already have descriptive error strings (merge conflicts, test failures, plan parse errors).
- Modifying `map_results.py` or the batch results JSON format.
- Changing the rendering structure of `render_failed_features()` — only the input error strings and the suggestion function change.
- Parsing `pipeline-events.log` at no-commit guard time — classification should use git state available in-process, not event log archaeology.
- Classifying every possible no-commit scenario (e.g., net-zero-diff from agent reverts, idempotency-skipped tasks) — the fallback handles uncommon cases.

## Edge Cases

- **Branch does not exist**: If the feature branch was never created (agent failed before first commit), git queries will fail. Expected: caught by the classification helper's error handling, falls through to the fallback classification (not "no changes produced," since the agent may not have run at all).
- **Branch exists with commits but none that differ from main**: Feature branch has commits that are merge-commits or empty commits. Expected: classify as "stale feature" if all commits are ancestors of main, otherwise "no changes produced."
- **Multiple prior sessions worked on the same feature**: Branch may have commits from multiple sessions. Expected: stale-feature detection still works — the check is whether the branch content matches main, not whether commits came from this session.
- **Feature on a non-default base branch**: The no-commit guard already receives `config.base_branch`. Expected: classification uses the configured base branch, not hardcoded `main`.
- **Git operation timeout during classification**: Expected: classification helper catches the timeout and returns the fallback classification. The batch run is not stalled.
- **Classifier returns unexpected value**: The no-commit guard validates the return value is a non-empty string before using it. If somehow empty or None, it substitutes the fallback message.

## Technical Constraints

- Classification logic runs inside `_apply_feature_result()` in `batch_runner.py`, which is async. Git operations must be subprocess calls (consistent with existing `_get_changed_files()` pattern).
- The classification helper must be a standalone function (not inline in the guard) so it is unit-testable.
- Error strings must remain human-readable plain text — they are displayed directly in the morning report markdown.
