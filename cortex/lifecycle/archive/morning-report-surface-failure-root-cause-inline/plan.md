# Plan: morning-report-surface-failure-root-cause-inline

## Overview

Add a `_classify_no_commit()` helper function to `batch_runner.py` that inspects git state to determine why a feature completed with no new commits, then wire it into the existing no-commit guard. Uses `git rev-list {branch}..{base} --count` to distinguish stale features (base moved past branch) from fresh branches with no agent commits. Enhance `_suggest_next_step()` in `report.py` to match the new error string patterns. Add a coupling test to prevent silent drift between producer and consumer.

## Tasks

### Task 1: Add `_classify_no_commit()` helper function
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Create a standalone classification function near `_get_changed_files()` (~line 408) that determines why a feature completed with no new commits. Uses `git rev-list` to detect whether the base branch has moved past the feature branch (stale) or the branch is at the same point as base (no commits produced).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Insert after `_get_changed_files()` (line 408) in the same utility section
  - Function signature: `def _classify_no_commit(feature: str, branch: str, base_branch: str) -> str`
  - Uses `subprocess.run()` with `capture_output=True, text=True, timeout=30` (same pattern as `_get_changed_files()` at line 398-403)
  - Stale detection: `git rev-list {branch}..{base_branch} --count` — counts commits on base not reachable from branch
    - returncode != 0 → fallback (branch or base ref invalid, git error)
    - returncode 0, count > 0 → base moved past branch → string containing `"already merged"`
    - returncode 0, count = 0 → branch at base HEAD, no agent commits → string containing `"no changes produced"`
  - Outer try/except catching `subprocess.TimeoutExpired`, `OSError`, and `Exception` → fallback string `f"completed with no new commits (branch: {branch})"`
  - Must always return a non-empty string — no code path returns None or empty
- **Verification**: `grep -c 'def _classify_no_commit' claude/overnight/batch_runner.py` = 1 — pass if count is 1
- **Status**: [x] done

### Task 2: Wire classifier into no-commit guard
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Replace the hardcoded generic error string at lines 1279-1281 with a call to `_classify_no_commit()`. The `_accumulate_result` path at lines 1604-1616 already delegates to `_apply_feature_result`, so only one call site needs updating.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Current code at lines 1276-1282: checks `if not changed_files:` then builds a hardcoded f-string with "check pipeline-events.log"
  - Replace lines 1279-1281 (the `error = (...)` assignment) with a call to `_classify_no_commit(name, branch_label, config.base_branch)` where `branch_label = actual_branch or f"pipeline/{name}"` (already computed at line 1278)
  - After the call, validate the return is truthy — if somehow empty, substitute the fallback string `f"completed with no new commits (branch: {branch_label})"`
  - The rest of the guard (lines 1283-1297: appending to features_paused, logging, write-back) stays unchanged
- **Verification**: `grep -c 'check pipeline-events.log' claude/overnight/batch_runner.py` = 0 — pass if count is 0 (old generic string removed)
- **Status**: [x] done

### Task 3: Enhance `_suggest_next_step()` patterns
- **Files**: `claude/overnight/report.py`
- **What**: Add pattern matches for the new no-commit guard error strings so each classification gets a distinct, actionable suggestion.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current function at lines 1084-1093 uses `error.lower()` substring matching
  - Add before the default return (line 1093):
    - Pattern `"already implemented"` or `"already merged"` → suggestion like "Verify prior merge on main, close backlog item if complete"
    - Pattern `"no changes produced"` → suggestion like "Check agent output — agent ran but produced no diff"
  - Keep existing patterns (merge conflict, test fail, circuit breaker) unchanged
- **Verification**: `grep -c 'already merged\|already implemented\|no changes produced' claude/overnight/report.py` ≥ 2 — pass if count is at least 2
- **Status**: [x] done

### Task 4: Write coupling test
- **Files**: `tests/test_no_commit_classification.py`
- **What**: Create a test that verifies the error strings returned by `_classify_no_commit()` for each named category match the substring patterns expected by `_suggest_next_step()`, and that the fallback path explicitly hits the default suggestion.
- **Depends on**: [1, 3]
- **Complexity**: simple
- **Context**:
  - Import `_classify_no_commit` from `claude.overnight.batch_runner` and `_suggest_next_step` from `claude.overnight.report`
  - Mock `subprocess.run` to simulate three scenarios:
    - (a) Stale branch: returncode 0, stdout = "5\n" (base has 5 commits past branch) → verify result contains "already merged" AND `_suggest_next_step(result)` != default
    - (b) Fresh branch no commits: returncode 0, stdout = "0\n" (branch at base HEAD) → verify result contains "no changes produced" AND `_suggest_next_step(result)` != default
    - (c) Invalid branch ref: returncode 128, stderr = "fatal: Not a valid object name" → verify fallback returned (non-empty, contains branch name) AND `_suggest_next_step(result)` == default (fallback intentionally hits default — assert this explicitly)
    - (d) Subprocess timeout: `subprocess.TimeoutExpired` raised → verify fallback returned
  - The default suggestion string is `"Review learnings, retry or investigate"` — use this as the comparison value
  - Follow existing test patterns in `tests/` (pytest, standard assertions)
- **Verification**: `just test` — pass if exit 0, all tests pass
- **Status**: [x] done

## Verification Strategy

Run `just test` to verify all existing tests still pass and the new coupling test passes. Then manually inspect the error strings by reading `_classify_no_commit()` and confirming each return path produces a non-empty, human-readable message containing the required substrings per the spec.
