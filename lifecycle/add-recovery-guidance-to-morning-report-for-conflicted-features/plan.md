# Plan: add-recovery-guidance-to-morning-report-for-conflicted-features

## Overview

Add one line inside the existing conflict block in `render_failed_features` to display the recovery branch name. All data is already in scope — the branch is `pipeline/{name}` where `name` is the loop variable. A companion test task covers the positive case, the empty-files edge case, and the non-conflict regression.

## Tasks

### Task 1: Add recovery branch line to render_failed_features

- **Files**: `claude/overnight/report.py`
- **What**: Add `lines.append(f"- **Recovery branch**: \`pipeline/{name}\`")` inside the `if conflict is not None:` block, after the `if conflicted_files:` sub-block closes, before the `- Learnings:` line.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The target location in `render_failed_features` (line 748) is in the section that builds per-feature lines. The current conflict block structure is:

  ```
  conflict = conflict_info.get(name)          # line 796
  if conflict is not None:                    # line 797 — outer guard
      conflict_summary = conflict.get(...)    # line 798
      lines.append("- **Conflict summary**:") # line 799
      conflicted_files = conflict.get(...)    # line 800
      if conflicted_files:                    # line 801 — inner guard
          files_str = ...                     # line 802
          lines.append("- **Conflicted files**:") # line 803
      # ← INSERT HERE: outside if conflicted_files: but still inside if conflict is not None:
  lines.append("- Learnings: ...")            # line 804 — already outside if conflict is not None:
  ```

  The new line goes at the position marked `# ← INSERT HERE`. It must be at the same indentation level as `conflict_summary = conflict.get(...)` (line 798) — NOT inside `if conflicted_files:` (line 801). This ensures the recovery branch appears for every conflict, including when `conflicted_files` is empty.

  The `name` variable is the outer loop variable from `for name, fs in sorted(failed.items()):` (line 789) — it is in scope at the insertion point.

- **Verification**: Run `just test`. The three new tests added in Task 2 must all pass. The positive-case test confirms the line appears when `conflicted_files` is non-empty; the empty-files test confirms it appears when `conflicted_files` is empty; the non-conflict test confirms it does not appear for non-conflicted failures.
- **Status**: [x] complete

### Task 2: Add tests for recovery branch line

- **Files**: `claude/overnight/tests/test_report.py`
- **What**: Add two new tests and extend one existing test to fully cover the recovery branch requirement.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Test file is `claude/overnight/tests/test_report.py`. Existing helpers: `_pytest_make_state(features: dict[str, str])` and `_pytest_make_data(state, events: list[dict])`. Pattern: inject a `merge_conflict_classified` event as `{"event": "merge_conflict_classified", "round": 1, "feature": "feature-name", "details": {"conflicted_files": [...], "conflict_summary": "..."}}` into `ReportData.events`, call `render_failed_features(data)`, assert the output string.

  Three changes are required:

  1. **New test `test_render_failed_features_shows_recovery_branch`**: fixture has `"conflicted_files": ["src/foo.py"]`. Assert `"- **Recovery branch**: \`pipeline/feature-name\`"` appears in output.

  2. **New test `test_render_failed_features_recovery_branch_shown_when_no_conflicted_files`**: fixture has `"conflicted_files": []` (empty list). Assert `"- **Recovery branch**: \`pipeline/feature-name\`"` appears in output. This test distinguishes correct placement (outside `if conflicted_files:`) from incorrect placement (inside it).

  3. **Extend existing test `test_non_conflicted_paused_feature_renders_no_conflict_lines`**: add an assertion `assert "**Recovery branch**" not in output` alongside the existing assertions for `**Conflict summary**` and `**Conflicted files**`. This guards against the recovery branch leaking outside the `if conflict is not None:` guard.

- **Verification**: `just test` passes with no new failures. All three changes are visible in the test output: two new test names plus the extended existing test still passing.
- **Status**: [x] complete

## Verification Strategy

Run `just test` after both tasks are complete. All existing tests pass; the two new tests pass; the extended non-conflict test still passes. Non-conflict feature output is unaffected (verified by the extended existing test).
