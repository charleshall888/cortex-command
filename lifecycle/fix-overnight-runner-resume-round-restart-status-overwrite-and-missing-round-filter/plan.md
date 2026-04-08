# Plan: fix-overnight-runner-resume-round-restart-status-overwrite-and-missing-round-filter

## Overview

Surgical fixes across three files (`runner.sh`, `orchestrator-round.md`, `map_results.py`) and two new test files. All changes are isolated to the resume path and status-update guards; no new modules, no schema changes, no architectural redesign. Tasks are sequenced to avoid conflicting edits within `runner.sh`.

## Tasks

### [x] Task 1: Fix `count_pending()` and `REMAINING_PENDING` to include `paused`
- **Files**: `claude/overnight/runner.sh`
- **What**: Two-part change to ensure sessions with only `paused` features don't exit prematurely. (a) `count_pending()` at lines 355–363 adds `'paused'` to the status filter tuple. (b) The inline `REMAINING_PENDING` query at ~line 769 (stall exit block) changes from `status == 'pending'` to `status in ('pending', 'paused')`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `count_pending()` at line 360: `f.get('status') in ('pending', 'running')` → `('pending', 'running', 'paused')`. Inline REMAINING_PENDING at line 769: the one-liner `sum(1 for f in features.values() if f.get('status') == 'pending')` → `f.get('status') in ('pending', 'paused')`. These are in completely separate line ranges and do not conflict with Tasks 2–4.
- **Verification**: `grep -n 'pending.*running.*paused\|paused.*pending.*running' claude/overnight/runner.sh` returns ≥ 1 match — pass if match count ≥ 1, fail if 0

### [x] Task 2: Fix `ROUND` initialization from `state.current_round` on resume
- **Files**: `claude/overnight/runner.sh`
- **What**: Replace the hardcoded `ROUND=1` at line 519 with a Python one-liner that reads `current_round` from the state JSON, so resumed sessions start at the correct round instead of always restarting from Round 1.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Line 519 is the only assignment `ROUND=1` before the main loop. Replace it with the inline Python pattern used elsewhere in runner.sh (e.g., the `PAUSED_REASON` read at ~line 729): `ROUND=$(STATE_PATH="$STATE_PATH" python3 -c "import json, os; print(json.load(open(os.environ['STATE_PATH']))['current_round'])")`. For new sessions `current_round = 1`, so behavior is unchanged. `STATE_PATH` is already set by this point in the script.
- **Verification**: `grep -c '^ROUND=1$' claude/overnight/runner.sh` = 0 — pass if count is 0, fail otherwise

### [x] Task 3: Add `batch-N-results.json` existence check in round loop
- **Files**: `claude/overnight/runner.sh`
- **What**: Inside the `while [[ $ROUND -le $MAX_ROUNDS ]]` loop, after the `count_pending` exit check and before `fill_prompt`, add a block that detects already-completed rounds by checking for `${SESSION_DIR}/batch-${ROUND}-results.json`. If the file exists, the runner skips orchestrator spawn for that round and advances to ROUND+1.
- **Depends on**: [2] — the skip uses `ROUND` which must come from state on resume
- **Complexity**: simple
- **Context**: Insertion point is after line 598 (`break` for pending=0) and before line 601 (`echo "--- Round $ROUND ---"`). Skip block: print a message ("Round $ROUND: results file already exists — skipping"), run the same `state.current_round = ROUND + 1` Python update used at line 797, increment `ROUND=$(( ROUND + 1 ))`, then `continue`. `SESSION_DIR` is already in scope. The results file path is `${SESSION_DIR}/batch-${ROUND}-results.json`.
- **Verification**: `grep -c 'batch-.*results.json' claude/overnight/runner.sh` ≥ 1 — pass if ≥ 1, fail if 0

### [x] Task 4: Fix `MERGED_BEFORE` capture to per-round + stall check to `-le 0`
- **Files**: `claude/overnight/runner.sh`
- **What**: Remove the pre-loop `MERGED_BEFORE` initialization block (lines 522–530, which incorrectly counts merged features before the loop runs on resume), add a per-round capture at the top of the loop body, and tighten the stall circuit breaker to catch negative values.
- **Depends on**: [3] — `MERGED_BEFORE` capture must be placed after the batch-file skip block from Task 3 and before `fill_prompt`
- **Complexity**: simple
- **Context**: Remove lines 522–530 (`MERGED_BEFORE=0` declaration and the pre-loop Python block). Insert a new `MERGED_BEFORE` capture at the top of the loop body (after the Task 3 batch-file check, before line 601 `echo "--- Round $ROUND ---"`); use the same Python snippet template already at lines 749–754 (count merged features from state). The existing `MERGED_BEFORE=$MERGED_AFTER` at line 780 is retained (now redundant but harmless per spec). At line 763: `if [[ $MERGED_THIS_ROUND -eq 0 ]]; then` → `-le 0`.
- **Verification**: `grep -c 'MERGED_BEFORE=0' claude/overnight/runner.sh` = 0 (pre-loop init gone); `grep -c 'MERGED_THIS_ROUND -le 0' claude/overnight/runner.sh` ≥ 1 — both must pass

### [x] Task 5: Add round filter code block to `orchestrator-round.md` §1 and update §2a
- **Files**: `claude/overnight/prompts/orchestrator-round.md`
- **What**: Extend §1 ("Read Current State", line 152) to filter the feature list by round, producing `features_to_run`. Also update §2a's dependency gate to operate on `features_to_run` (not raw state) and change its `== current_round` predicate to `<= current_round`. Update the §1 exit sentence to distinguish "no features for this round" from "session truly complete."
- **Depends on**: none
- **Complexity**: simple
- **Context**: §1 currently reads state and identifies `pending`/`running` features but applies no round filter. After the existing state-read prose (line 154 "identify features with status `pending` or `running`"), add a Python code block (fenced with ```python, same style as the §0 escalation blocks). The block must use `current_round = {round_number}` — runner.sh substitutes `{round_number}` via `fill_prompt()` at line 376 area. Filter logic: `features_to_run = [f for f in features if f.get('status') == 'paused' or (f.get('round_assigned') or 0) <= current_round]`. The null-guard `(f.get('round_assigned') or 0)` handles legacy state.
  - **Exit condition (critical)**: Replace "If no features are pending or running, exit — the session is complete" with two distinct exit cases: (a) if the raw state has no features in `pending`/`running`/`paused` status → exit, session is complete; (b) if `features_to_run` is empty but there ARE pending/running features in the raw state → exit this round with no batch plan (the runner will advance ROUND and retry next iteration). Do NOT declare "session complete" in case (b). The runner's existing `orchestrator_no_plan` path handles this correctly on the bash side.
  - **§2a update (required)**: §2a's dependency gate at line 207 currently reads "For each feature F with `round_assigned == current_round`". This is a separate, stricter filter that would silently exclude paused features from prior rounds that ARE in `features_to_run`. Update §2a to: (1) iterate over `features_to_run` (not raw state) and (2) change `== current_round` to `<= current_round`. §1b already states paused features "will be included in this round's batch automatically" — §2a must not contradict this.
  - §3 and §4 naturally receive the filtered list via §2a.
- **Verification**: `grep -c 'round_assigned' claude/overnight/prompts/orchestrator-round.md` ≥ 2 (one in new §1 filter, one in updated §2a) — pass if ≥ 2

### [x] Task 6: Add terminal-status guard to `_map_results_to_state()` in `map_results.py`
- **Files**: `claude/overnight/map_results.py`
- **What**: In `_map_results_to_state()`, add `if fs.status in _TERMINAL_STATUSES: continue` before the `fs.status = ...` assignment in all three loops that can overwrite terminal status: `features_paused` (lines 97–104), `features_deferred` (lines 106–113), and `features_failed` (lines 115–122).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Guard placement: after `fs = state.features[name]` and before `fs.status = ...` in each of the three loops. Mirror exactly the pattern in `_handle_missing_results()` at lines 162–164: `if fs.status in _TERMINAL_STATUSES: continue`. `_TERMINAL_STATUSES = frozenset({"merged", "failed", "deferred"})` at line 32 — use the constant, not hardcoded strings. The `features_merged` loop (lines 89–95) must NOT receive the guard — overwriting `failed→merged` on a successful retry is correct behavior. Do not modify `features_merged`.
- **Verification**: `grep -c '_TERMINAL_STATUSES' claude/overnight/map_results.py` ≥ 4 (1 constant definition + 1 in `_handle_missing_results` + 3 new guards) — pass if ≥ 4

### [x] Task 7: Create `tests/test_map_results.py` with terminal-status guard unit tests
- **Files**: `tests/test_map_results.py` (new file)
- **What**: Unit tests that verify the three new guards in `_map_results_to_state()` and a regression test confirming retry-success still updates status correctly. Four test functions: `test_paused_result_does_not_overwrite_merged`, `test_failed_result_does_not_overwrite_merged`, `test_deferred_result_does_not_overwrite_merged`, `test_merged_result_overwrites_failed`.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Import `_map_results_to_state` from `claude.overnight.map_results` (it's a module-level function). Use `tmp_path` pytest fixture for state files. Minimal state dict structure that `load_state()` accepts: `{"session_id": "t", "phase": "executing", "plan_ref": "", "current_round": 1, "started_at": "<iso>", "updated_at": "<iso>", "features": {"feat": {"status": "<initial>"}}, "integration_branch": "main"}`. Write to `tmp_path / "overnight-state.json"` via `json.dumps`. After calling `_map_results_to_state(results, state_path, batch_id=1)`, load `overnight-state.json` from disk and assert `data["features"]["feat"]["status"]`. For guard tests: `results = {"features_paused": [{"name": "feat", "error": None}]}` etc., initial status `"merged"`, assert status is still `"merged"`. For the regression test: initial status `"failed"`, `results = {"features_merged": ["feat"]}`, assert status becomes `"merged"`. Follow import style in existing test files (e.g., `tests/test_dispatch.py`).
- **Verification**: `just test` exits 0 and `tests/test_map_results.py` exists — pass if both conditions hold

### [x] Task 8: Create `tests/test_runner_resume.py` with `count_pending()` paused coverage
- **Files**: `tests/test_runner_resume.py` (new file)
- **What**: Tests for runner.sh resume behavior. Two tests: (a) `count_pending()` returns non-zero for paused-only state; (b) `count_pending()` returns 0 for merged-only state. A structural assertion verifies runner.sh actually contains `'paused'` in the `count_pending` function body.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: The `count_pending()` function in runner.sh is a shell function containing a Python one-liner; it cannot be called directly from Python tests without running the full runner.sh. Approach: (1) write a state JSON to `tmp_path`; (2) use `subprocess.run(['python3', '-c', snippet], env={..., 'STATE_PATH': str(state_path)})` where `snippet` is the Python logic; (3) additionally assert that `runner.sh` itself contains the string `"'paused'"` inside the `count_pending` function — use `subprocess.run(['bash', '-c', "grep -A10 'count_pending()' claude/overnight/runner.sh | grep -c 'paused'"])` and assert the count ≥ 1. This structural assertion is the guard that catches "implementer forgot to update runner.sh but test still passes" — without it, the logic test validates only the test author's Python, not the production code. `REAL_REPO_ROOT` follows the pattern from `tests/test_runner_signal.py` (line 21). Follow that file's conventions for `tmp_path` usage and state structure.
- **Verification**: `just test` exits 0 and `tests/test_runner_resume.py` exists with the structural assertion — pass if both hold

## Verification Strategy

After all tasks complete, run `just test` — exit 0 with no failures is the gate. Then run these grep checks to confirm structural ACs:
- `grep -c '^ROUND=1$' claude/overnight/runner.sh` = 0
- `grep -c 'MERGED_BEFORE=0' claude/overnight/runner.sh` = 0
- `grep -c 'MERGED_THIS_ROUND -le 0' claude/overnight/runner.sh` ≥ 1
- `grep -c 'batch-.*results.json' claude/overnight/runner.sh` ≥ 1
- `grep -n 'pending.*running.*paused\|paused.*pending.*running' claude/overnight/runner.sh` ≥ 1 match
- `grep -c '_TERMINAL_STATUSES' claude/overnight/map_results.py` ≥ 4
- `grep -c 'round_assigned' claude/overnight/prompts/orchestrator-round.md` ≥ 2

End-to-end behavioral verification of the orchestrator round filter (R3 AC) and the full resume path (R1+R2 integrated) is Interactive/session-dependent — requires running an actual overnight session against a state file with mixed-round features.
