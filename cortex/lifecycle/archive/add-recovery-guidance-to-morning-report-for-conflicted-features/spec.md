# Specification: Add recovery guidance to morning report for conflicted features

## Problem Statement

When an overnight feature is paused due to a merge conflict, the morning report (after ticket 015) shows the conflict summary and conflicted files inline, but does not show the branch name. The user must independently recall the `pipeline/{feature}` naming convention before they can check out the branch and act on the "Suggested next step: Resolve conflict manually, then retry" message. This ticket adds a `- **Recovery branch**:` line inside the existing conflict block so the user sees the full set of recovery information in one place.

## Requirements

1. **Recovery branch displayed inline**: For each feature in the `## Failed Features` section where a `merge_conflict_classified` event exists in `data.events` (i.e., `conflict_info.get(name)` is not None), display `- **Recovery branch**: \`pipeline/{name}\`` within the feature's conflict block. Acceptance criteria: a morning report generated from a session with a conflict shows the recovery branch line for that feature.

2. **Insertion point**: The recovery branch line appears after the `- **Conflicted files**:` line (or after `- **Conflict summary**:` when `conflicted_files` is empty) and before the `- Learnings:` line. Acceptance criteria: the rendered block order is: Conflict summary → Conflicted files (if non-empty) → Recovery branch → Learnings.

3. **Non-conflict features unaffected**: Features paused or failed for reasons other than merge conflicts show no recovery branch line. Acceptance criteria: existing `render_failed_features` output for non-conflict pauses is byte-for-byte identical before and after this change.

4. **Automated test**: A test in `claude/overnight/tests/test_report.py` verifies that the rendered output for a conflicted feature contains `- **Recovery branch**: \`pipeline/feature-name\``. Acceptance criteria: the test passes in `just test` with no new failures.

## Non-Requirements

- No changes to `_suggest_next_step()` — "Resolve conflict manually, then retry" is already correct.
- No changes to `OvernightFeatureStatus` schema or any file other than `report.py` and the test file.
- No conflict classification type/category logic — `ConflictClassification` has no type field and the ticket's "contextually appropriate guidance" is not feasible with existing data.
- No changes to the report's other sections.

## Edge Cases

- **`conflicted_files` empty list**: Recovery branch line still appears (it is always shown when `conflict is not None`, regardless of whether the files list is non-empty).
- **Non-conflict pause**: `conflict_info.get(name)` returns `None` → recovery branch line not rendered.
- **Multiple `merge_conflict_classified` events for the same feature**: Last-wins semantics (inherited from 015's implementation). Recovery branch name is derived from `name`, not the event, so it is unaffected.

## Technical Constraints

- Implementation is one line inside the `if conflict is not None:` block in `render_failed_features` (after the `conflicted_files` rendering, before `lines.append(f"- Learnings: ...")`).
- Branch name: `f"pipeline/{name}"` — no lookup required.
- New test uses existing helpers `_pytest_make_state` and `_pytest_make_data` from `test_report.py`, following the pattern of 015's conflict tests.
