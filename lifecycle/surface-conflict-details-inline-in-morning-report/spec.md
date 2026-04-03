# Specification: Surface conflict details inline in morning report

## Problem Statement

When an overnight feature is paused due to a merge conflict, the morning report shows a generic error string (`merge conflict in src/foo.py`) and a pointer to a learnings file. The user must manually trace `overnight-events.log` to find which files conflicted and why. The data needed — `conflicted_files` (list) and `conflict_summary` (human-readable string) — is already present in `data.events` as a `merge_conflict_classified` event, loaded by `collect_report_data()`. This ticket adds two lines to the failed-feature block: the list of conflicted files and the conflict summary string. Result: reviewers see the full conflict context inline without opening any additional files.

## Requirements

1. **Conflict summary displayed inline**: For each feature in the `## Failed Features` section where a `merge_conflict_classified` event exists in `data.events`, display `details.conflict_summary` as a bullet line (`- **Conflict summary**: {text}`) within the feature's block. Acceptance criteria: a morning report generated from a session with a conflict shows the conflict summary text within the feature's block, visible without reading any other file.

2. **Conflicted files displayed inline**: For the same features, display `details.conflicted_files` as a bullet line (`- **Conflicted files**: {comma-separated backtick-wrapped filenames}`) within the feature's block. If `conflicted_files` is an empty list (classification failed), omit the files line entirely — do not render `- **Conflicted files**: ` with no content. Acceptance criteria: a report with a conflict shows at least one conflicted filename when the list is non-empty; no files line appears when the list is empty.

3. **Insertion point**: Conflict details lines appear after the `- Circuit breaker:` line and before the `- Learnings:` line in the feature block. Acceptance criteria: the rendered block order matches this sequence.

4. **Non-conflict features unaffected**: Features paused or failed for reasons other than merge conflicts show no conflict detail lines. Acceptance criteria: existing `render_failed_features` output for non-conflict pauses is byte-for-byte identical before and after this change (excluding conflict-specific features).

5. **Automated test**: A test in `claude/overnight/tests/test_report.py` verifies that: (a) the feature name in a `merge_conflict_classified` event keyed by `evt["feature"]` is found as a key in `data.state.features` for a representative conflict scenario, and (b) the rendered output contains both the conflict summary and the conflicted files. Acceptance criteria: the test passes in `just test` with no new test failures.

## Non-Requirements

- No changes to `OvernightFeatureStatus` schema or `overnight-state.json` state format.
- No changes to `batch_runner.py`, `events.py`, `state.py`, or any file other than `report.py` (and the test file).
- No normalization of feature name keys — both sources originate from the same master plan table cell and are identical by construction. If a future normalization is needed, it is a separate ticket.
- No recovery guidance (branch name, suggested next action) — that is ticket 016, which depends on this work.
- No changes to the report's other sections (completed, deferred questions, executive summary).

## Edge Cases

- **Non-conflict pause**: `merge_conflict_classified` event absent → `conflict_info.get(name)` returns `None` → conflict block not rendered → no change to existing output.
- **`conflicted_files` empty list**: `classify_conflict()` caught an exception and returned `ConflictClassification(conflicted_files=[], conflict_summary="classification failed")` → show `- **Conflict summary**: classification failed` but omit the `- **Conflicted files**:` line.
- **Multiple `merge_conflict_classified` events for the same feature** (feature attempted across multiple rounds): last-wins semantics — the final event's details are used.
- **Feature paused by circuit breaker, not conflict**: `circuit_breaker: fired` line renders; no conflict detail block appears.

## Technical Constraints

- Implementation uses Approach A from the research: add a second `for evt in data.events` loop immediately after the existing `retry_counts` loop in `render_failed_features`, building `conflict_info: dict[str, dict]`. The main render loop uses `conflict_info.get(name)`.
- The event constant `MERGE_CONFLICT_CLASSIFIED` is defined at `events.py:60` — use it by importing or by the string `"merge_conflict_classified"` (following the existing pattern in the function which uses string literals for `"retry_attempt"`).
- `data.events` is `list[dict[str, Any]]`; `details` is accessed as `evt.get("details", {})`.
- New test uses existing test helpers `_pytest_make_state` and `_pytest_make_data` from `test_report.py`.
