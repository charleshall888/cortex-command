# Plan: surface-conflict-details-inline-in-morning-report

## Overview

Two-task implementation: add a `conflict_info` pre-pass loop to `render_failed_features` in `report.py` that mirrors the existing `retry_counts` pattern, then add corresponding tests to `test_report.py`. Changes are isolated to these two files.

## Tasks

### Task 1: Add conflict-info extraction and render lines to `render_failed_features`

- **Status**: [x] complete
- **Files**: `claude/overnight/report.py`
- **What**: Add a second event-scan loop after the `retry_counts` loop (line 774–778) to build `conflict_info: dict[str, dict]` keyed by feature name. In the per-feature render block, use `conflict_info.get(name)` to conditionally append the conflict summary and files bullet lines after the circuit-breaker line and before the learnings line.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `render_failed_features(data: ReportData) -> str` at `report.py:748`
  - Pattern to follow: `retry_counts` loop at `report.py:774–778` — identical structure, different event type string (`"merge_conflict_classified"`) and dict value (the `"details"` sub-dict instead of a count)
  - Insertion point for the new loop: immediately after line 778 (end of retry_counts loop), before line 780 (start of `for name, fs in sorted(failed.items())`)
  - Insertion point for the render lines: after the circuit-breaker line append (`lines.append(f"- Circuit breaker: {cb_status}")` at line 786), before the learnings line append (`lines.append(f"- Learnings: ...")` at line 787)
  - `ReportData.events` is `list[dict[str, Any]]` with each event carrying optional `"feature"` (string) and `"details"` (dict) fields
  - `MERGE_CONFLICT_CLASSIFIED = "merge_conflict_classified"` is defined at `events.py:60` — use the string literal to match the existing pattern in the function (which uses `"retry_attempt"` as a string literal)
  - Conflict detail lines format:
    - `- **Conflict summary**: {conflict_summary text}` — always shown when `conflict_info` entry exists
    - `- **Conflicted files**: `file1`, `file2`` — shown only when `conflicted_files` is non-empty; omit entirely when empty
  - Graceful degradation: `conflict_info.get(name)` returns `None` for non-conflict features — no lines appended, existing output unchanged
- **Verification**: Run `just test` — all existing tests pass. Manually confirm the function returns the circuit-breaker line before the conflict lines before the learnings line by calling `render_failed_features` with a hand-crafted `ReportData` in a Python REPL or via the test added in Task 2. Confirm a feature without a `merge_conflict_classified` event produces byte-for-byte identical output to the current behavior.
---

### Task 2: Write automated tests for `render_failed_features` conflict rendering

- **Files**: `claude/overnight/tests/test_report.py`
- **What**: Add three test functions to `test_report.py` covering: (a) a conflicted feature renders conflict summary and files inline, (b) a conflicted feature with an empty `conflicted_files` list renders summary only (no files line), and (c) a non-conflicted paused feature renders no conflict lines. These tests satisfy the spec's blocking requirement (R5).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Import `render_failed_features` from `claude.overnight.report` alongside the existing `render_completed_features` import at `test_report.py:7`
  - `_pytest_make_data(features: dict, ...) -> ReportData` at `test_report.py:23` — creates a `ReportData` with a populated `state`. Set `data.events = [...]` after calling the helper to inject synthetic events (the helper leaves `events` as the empty-list default)
  - `OvernightFeatureStatus(status="paused", error="merge conflict in src/foo.py")` — the `status` field must be `"paused"` (or `"failed"`) for the feature to appear in the failed section
  - Synthetic `merge_conflict_classified` event shape: `{"event": "merge_conflict_classified", "feature": "<name>", "details": {"conflicted_files": [...], "conflict_summary": "..."}}`
  - The feature name in the event must match the key in `data.state.features` exactly (this is the blocking join-correctness requirement from spec R5a)
  - Test function names should follow the existing `test_` prefix convention
- **Verification**: `just test` passes with all three new tests green and no regressions. Confirm the test for non-empty conflicted files asserts both the summary line and at least one filename appear in the output. Confirm the test for empty conflicted files asserts the summary line appears and no `"Conflicted files"` line appears.
- **Status**: [x] complete

---

## Verification Strategy

After both tasks complete: run `just test`. All tests pass. Grep `render_failed_features` output for `"Conflict summary"` and `"Conflicted files"` to confirm the new lines appear when the event is present. Confirm the insertion order in the output string: `Circuit breaker:` appears before `Conflict summary:` appears before `Learnings:`. Confirm a paused feature without a `merge_conflict_classified` event produces the same output as before this change.
