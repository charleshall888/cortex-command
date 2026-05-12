# Research: Morning Report — Surface Failure Root Cause Inline

## Clarified Intent

Build failure classification logic in the overnight runner so the morning report surfaces specific, actionable root causes inline instead of a generic "check log files" message.

## Current Data Flow

The failure data pipeline is:

```
batch_runner.py (FeatureResult.error)
  → _accumulate_result() → BatchResult dict
  → batch-{N}-results.json
  → map_results.py _map_results_to_state() (direct copy, no transformation)
  → overnight-state.json OvernightFeatureStatus.error
  → report.py render_failed_features() (displays as-is)
```

Key finding: `map_results.py` is a transparent passthrough — it copies error strings directly from batch results to state without any processing (`fs.error = entry.get("error")` at map_results.py:104 and :122).

## Current Error Sources

The `error` field in `OvernightFeatureStatus` is `Optional[str]` — a free-form string, not structured. Errors originate from these points in `batch_runner.py`:

| Source | Location | Current Error String |
|--------|----------|---------------------|
| No-commit guard | batch_runner.py:1279-1281 | `"completed with no new commits — check pipeline-events.log task_output and task_git_state events (branch: {branch_label})"` |
| Plan parse failure | batch_runner.py:806 | `"Plan parse error: {exc}"` |
| Dependency error | batch_runner.py:820 | `"Dependency error: {exc}"` |
| Repair merge failure | batch_runner.py:1254 | `"repair_ff_merge_failed: {stderr}"` |
| Merge failure | batch_runner.py:1377 | `merge_result.error or "merge failed"` |
| Task failure | batch_runner.py:961 | `"Task {task.number} failed after {attempts} attempts"` |
| Budget exhausted | batch_runner.py:944 | `"budget_exhausted"` |
| Unexpected exception | batch_runner.py:934 | `"Unexpected error: {item}"` |
| Circuit breaker | batch_runner.py:1475 | `"batch circuit breaker: 3 consecutive pauses"` |
| Generic pause | batch_runner.py:1445 | `result.error or "task paused"` |

Most error sources already produce somewhat descriptive strings. The major exception is the **no-commit guard**, which produces a single generic message regardless of the underlying reason. The backlog item's claim that `no_commit_guard` "already knows why" is incorrect — it checks a single condition (`not changed_files`) and produces one string.

## Existing Classification in report.py

`_suggest_next_step()` (report.py:1084-1093) already does rudimentary pattern matching:

- `"merge conflict"` or `"conflict"` → "Resolve conflict manually, then retry"
- `"test fail"` → "Investigate test failure, fix, retry"
- `"circuit breaker"` → "Review learnings, consider spec revision"
- Default → "Review learnings, retry or investigate"

The no-commit guard error triggers the default suggestion because it doesn't match any pattern.

## Structured Data Available at Failure Points

At the task dispatch level (`dispatch.py`, `retry.py`), rich classification already exists:

- `error_type`: agent_timeout, agent_test_failure, agent_refusal, agent_confused, task_failure, infrastructure_failure, budget_exhausted, api_rate_limit, unknown
- `error_detail`: Human-readable detail
- `attempts`: Retry count
- `final_output`: Last agent output

At the merge level (`merge.py`):

- `merge_result.conflict`: Boolean
- `merge_result.classification.conflicted_files`: File list
- `merge_result.classification.conflict_summary`: Summary
- `merge_result.test_result.output`: Test output

This structured data is available at the point where `FeatureResult` is constructed, but is flattened to a single error string before reaching the state file.

## Approach A: Improve Error Strings at Source (Minimal)

Improve the error strings produced at each failure point in `batch_runner.py`, particularly the no-commit guard. Since `fs.error` is already a free-form string and `report.py` displays it as-is, no schema changes are needed.

For the no-commit guard specifically, the classification logic would need to inspect available context to determine WHY no commits were produced:

1. Check if the branch already has prior commits matching main (stale feature)
2. Check if the agent ran but produced no changes (possible already-complete or agent confusion)
3. Check pipeline-events.log for task_output events to extract agent reasoning

Then produce a descriptive string instead of the generic message.

**Pros**: Minimal changes (only batch_runner.py and maybe report.py's `_suggest_next_step`). No schema changes. No intermediary file changes.

**Cons**: Classification logic is string-based — harder to test, parse, or extend. Report.py still pattern-matches on strings, which is brittle.

## Approach B: Add Structured Failure Classification Field

Add a `failure_class` field to `FeatureResult` and `OvernightFeatureStatus` that categorizes the failure type. Report.py uses the classification to produce template-driven inline explanations.

Classification values: `stale_feature`, `no_changes`, `agent_no_commit`, `plan_parse_error`, `dependency_error`, `merge_conflict`, `test_failure`, `budget_exhausted`, `circuit_breaker`, `agent_timeout`, `repair_failed`, `unknown`

The error string still exists for details, but `failure_class` drives the report's inline explanation template.

**Pros**: Clean separation of classification and detail. Report templates are testable. Easy to extend with new failure classes. `_suggest_next_step` becomes a lookup table.

**Cons**: Adds a field to the state schema. Requires changes to `batch_runner.py`, `state.py`, `map_results.py`, and `report.py`. More files touched. Existing overnight-state.json files lack the field (needs backward compat handling — default to `None`/`unknown`).

## Analysis

Approach A is sufficient for the stated problem. The backlog item asks for better error messages, not a classification system. Most error sources already produce reasonable strings — only the no-commit guard needs significant improvement. Enhancing `_suggest_next_step` patterns is low-risk.

Approach B is cleaner long-term but introduces schema changes and multi-file coordination beyond what the problem requires. The overnight runner already has extensive structured data in `pipeline-events.log` — adding another classification layer to the state file may be redundant.

**Recommendation**: Approach A (improve error strings at source) with one element borrowed from Approach B: extract the no-commit guard's classification logic into a helper function that returns both a `reason` string and a `suggested_action` string, making it testable without a full schema change.

## Codebase Analysis

### Files to Modify

| File | Change | Lines |
|------|--------|-------|
| `claude/overnight/batch_runner.py` | Replace no-commit guard's generic message with classified messages; add classification helper | 1276-1297 |
| `claude/overnight/report.py` | Enhance `_suggest_next_step()` patterns to match new error strings | 1084-1093 |

### Files to Read (No Changes)

| File | Purpose |
|------|---------|
| `claude/overnight/map_results.py` | Verify passthrough behavior (no changes needed) |
| `claude/overnight/state.py` | Verify `error` field is free-form string (no schema change) |
| `claude/overnight/merge.py` | Understand merge error strings |
| `claude/overnight/dispatch.py` | Reference for error_type classification |

## Open Questions

- What git operations can reliably determine "stale feature" (branch already has prior commits matching main) at no-commit guard time? The guard has access to the feature branch and base branch — `git log {base}..{branch}` could reveal if commits exist but produce no diff against main. Deferred: will be resolved during Plan phase by inspecting git commands available in the batch_runner execution context.
