# Specification: fix-overnight-runner-resume-round-restart-status-overwrite-and-missing-round-filter

## Problem Statement

When the overnight runner resumes a partially-completed session, it corrupts execution state in four ways: it always restarts at Round 1 regardless of progress already recorded in state; it dispatches features from all rounds, not just the current one; it overwrites the terminal `merged` status on re-dispatched features that pause with a no-commit guard; and it computes a negative "merged this round" count from a stale pre-run baseline. A fifth related issue causes the runner to exit prematurely if only `paused` features remain (the pending-feature count check omits `paused`). Together, these bugs make the resume path unusable: a resumed session starts over from Round 1, re-dispatches already-merged features, corrupts their status from `merged` to `paused`, and logs a `merged_this_round: -2` event. This PR restores correct resume behavior.

## Requirements

### Must-Have

1. **ROUND initialized from state on resume**: `runner.sh` must initialize `ROUND` from `state.current_round` (not hardcode `ROUND=1`) when a session is resumed with existing state. For new sessions where `current_round = 1`, the behavior is unchanged.
   - Acceptance criteria: `grep -c '^ROUND=1$' claude/overnight/runner.sh` = 0

2. **Skip already-mapped rounds on resume**: Before executing round N, the runner must check whether `$SESSION_DIR/batch-N-results.json` already exists. If it does, the runner skips straight to round N+1 without re-spawning the orchestrator for round N.
   - Acceptance criteria: `grep -c 'batch-.*results.json' claude/overnight/runner.sh` ≥ 1 (existence check present in runner loop)

3. **Round filter in orchestrator dispatch**: `orchestrator-round.md` §1 must contain a Python code block that filters the feature list to exclude features with `round_assigned > current_round` and status `pending` or `running`. Features with status `paused` are always included regardless of `round_assigned` (they are in recovery and must be retried). The filter must use Python code-block style identical to the existing §2a dependency gate.
   - Acceptance criteria (structural): `grep -c 'round_assigned' claude/overnight/prompts/orchestrator-round.md` ≥ 2 (one in the new §1 filter, one already in §2a)
   - Acceptance criteria (behavioral): Interactive/session-dependent — the filter is a prompt code block executed by the orchestrator LLM agent at runtime; correct filtering behavior can only be verified by running an actual orchestrator session against a state file with mixed-round features.

4. **Terminal-status guard in `_map_results_to_state()`**: The `features_paused`, `features_deferred`, and `features_failed` loops in `map_results.py`'s `_map_results_to_state()` must each check `if fs.status in _TERMINAL_STATUSES: continue` before overwriting feature status. This mirrors the guard already present in `_handle_missing_results()` and uses the existing `_TERMINAL_STATUSES` constant. All three loops exhibit the same unconditional overwrite pattern; all three require the guard.
   - Acceptance criteria: `grep -c '_TERMINAL_STATUSES' claude/overnight/map_results.py` ≥ 4 (one constant definition + one in `_handle_missing_results` already + three new guards in `_map_results_to_state`)

5. **Unit tests for terminal-status guard** (moved to must-have — semantic verification that grep-count ACs cannot provide): Create `tests/test_map_results.py` with at minimum three tests:
   - `test_paused_result_does_not_overwrite_merged`: construct a state dict with feature in `merged` status, call `_map_results_to_state` with `features_paused=[{name}]`, assert status remains `merged`
   - `test_failed_result_does_not_overwrite_merged`: same with `features_failed`
   - `test_deferred_result_does_not_overwrite_merged`: same with `features_deferred`
   - `test_merged_result_overwrites_failed`: construct state with feature in `failed`, pass `features_merged=[{name}]`, assert status becomes `merged` (regression: verify retry-success still works)
   - Acceptance criteria: `just test` exits 0 and `tests/test_map_results.py` exists with the above test names

6. **MERGED_THIS_ROUND arithmetic non-negative**: The pre-loop `MERGED_BEFORE` initialization (runner.sh lines 522–530) must be removed and replaced with a per-round capture inside the loop, before the orchestrator spawns each round. The existing end-of-round `MERGED_BEFORE=$MERGED_AFTER` reset continues to serve for round-to-round transitions.
   - Acceptance criteria: `grep -c 'MERGED_BEFORE=0' claude/overnight/runner.sh` = 0

7. **Stall check handles negative values**: The stall circuit breaker at runner.sh:763 must use `-le 0` instead of `-eq 0`, so that a negative `MERGED_THIS_ROUND` correctly triggers the stall counter rather than passing silently.
   - Acceptance criteria: `grep -c 'MERGED_THIS_ROUND -le 0' claude/overnight/runner.sh` ≥ 1

8. **`count_pending()` includes paused features and consistent exit notification**: The `count_pending()` function (runner.sh:355–363) must include `paused` in its status filter so that sessions where only paused features remain do not exit the dispatch loop prematurely. Additionally, the inline `REMAINING_PENDING` check in the stall circuit-breaker exit block (runner.sh ~line 769) must also include `paused`, to avoid reporting "0 features remaining" when paused features are present.
   - Acceptance criteria: `grep -n 'pending.*running.*paused\|paused.*pending.*running' claude/overnight/runner.sh` returns at least one match (the count_pending function)

### Should-Have

9. **Tests for runner.sh resume changes**: Add tests covering `ROUND` initialization from state and `count_pending()` paused inclusion. May be placed in `tests/test_runner_signal.py` or a new `tests/test_runner_resume.py` following the existing integration-test pattern (spawn runner.sh in a tmp dir, write a pre-populated state file, verify behavior).
   - Acceptance criteria: `just test` exits 0 and at least one test verifies that `count_pending()` returns non-zero when state contains only a `paused` feature

## Non-Requirements

- **Not redesigning round management**: The round-based dispatch model, `round_assigned` schema, and `current_round` tracking are unchanged. This is a bug fix in the resume path, not a refactor.
- **Not changing the state schema**: `overnight-state.json` already has `round_assigned` per feature and `current_round` at session level. No schema migration needed.
- **Not adding a pre-dispatch server-side round filter**: The round filter lives in the orchestrator prompt (Approach A from research), not in a Python pre-pass that injects a constrained feature list.
- **Not fixing crash-during-orchestrator recovery**: Crashes and SIGHUP handling were addressed in #039. This PR only covers the four resume-path bugs.
- **Not protecting `features_merged` with the terminal-status guard**: Overwriting `failed`→`merged` on a successful retry is correct behavior. The guard applies only to `features_paused`, `features_deferred`, and `features_failed`.
- **Not handling `round_assigned: null` in the round filter**: `round_assigned` is populated by `plan.py` during session creation and is assumed present on all features. The null-guard `(f.round_assigned or 0) <= current_round` may be included as a safety measure but is not a primary concern.

## Edge Cases

- **Crash during map_results (after batch completes, before `current_round` increment)**: `state.current_round` still equals N, but `batch-N-results.json` already exists in SESSION_DIR. On resume, the runner detects the file, skips spawning the orchestrator for round N, and advances to N+1. Round N's features remain in whatever status map_results last wrote before the crash.
- **Paused features from prior rounds**: A feature paused in round 1 retains `round_assigned=1` in state. After the runner advances to round 2 (`current_round=2`), the feature must still be dispatched (it is in recovery). The round filter exempts all `paused` features regardless of `round_assigned`.
- **Interrupted features (reset to `pending` by interrupt handler)**: `interrupt.py` resets interrupted features to `pending` but preserves `round_assigned`. A feature interrupted in round 1 and reset to `pending` retains `round_assigned=1`. The `round_assigned <= current_round` semantics correctly include it when `current_round ≥ 1`.
- **`running` features on resume (unclean crash before interrupt.py)**: If a crash occurs during the orchestrator itself (out of scope for this PR per Non-Requirements) and leaves features in `running` state, those features retain their original `round_assigned`. The round filter applies to `running` features the same as `pending` — `running` features with `round_assigned > current_round` are excluded; those with `round_assigned <= current_round` are included.
- **Session with only paused features**: With the `count_pending()` fix, the runner continues dispatching when only paused features remain. Permanently-paused features (all recovery exhausted) still produce `MERGED_THIS_ROUND = 0` each round, and the stall circuit breaker fires after 2 consecutive rounds — terminating the session.
- **Feature appears in both `features_merged` and `features_paused` in a malformed results file**: `_map_results_to_state` processes `features_merged` first. The guard on `features_paused` then fires (`merged` is in `_TERMINAL_STATUSES`) and the paused entry is skipped. Final status: `merged`.
- **Feature appears in both `features_merged` and `features_deferred` in a malformed results file**: `features_merged` runs before `features_deferred` in `_map_results_to_state()`. The guard on `features_deferred` fires (`merged` is in `_TERMINAL_STATUSES`) and the deferred entry is skipped. Final status: `merged`.
- **Round N is the last round and the runner advances to N+1**: After `batch-N-results.json` check, the runner sets `ROUND=N+1`. The `count_pending()` check at the next loop iteration finds 0 features in pending/running/paused state and exits normally.

## Changes to Existing Behavior

- **MODIFIED: `ROUND` initialization** — was hardcoded `ROUND=1`, now reads from `state.current_round`. For fresh sessions, `state.current_round = 1` so behavior is unchanged. For resumed sessions, the runner starts at the correct round.
- **MODIFIED: `count_pending()` status filter** — was `('pending', 'running')`, now `('pending', 'running', 'paused')`. Sessions with only paused features no longer exit the dispatch loop prematurely.
- **MODIFIED: stall circuit-breaker `REMAINING_PENDING` query** — was `status == 'pending'` only, now includes `paused`, for consistency with count_pending() change.
- **MODIFIED: `_map_results_to_state()` feature status update** — `features_paused`, `features_deferred`, and `features_failed` loops now skip features whose current status is in `_TERMINAL_STATUSES`. Previously, these loops unconditionally overwrote status for any feature named in the results.
- **MODIFIED: `MERGED_THIS_ROUND` arithmetic** — `MERGED_BEFORE` is now captured at the start of each round iteration (before the orchestrator runs), not once before the loop. For the first round of a fresh session, the value is the same (0 features merged). For resumed sessions, this prevents the negative-count bug.
- **MODIFIED: Stall circuit breaker** — changed from `MERGED_THIS_ROUND -eq 0` to `MERGED_THIS_ROUND -le 0`. Negative counts now correctly increment the stall counter.
- **ADDED: Batch-results-file existence check in round loop** — runner skips to N+1 if `batch-N-results.json` already exists for the current round.
- **ADDED: Round filter code block in `orchestrator-round.md` §1** — features with `round_assigned > current_round` and status `pending` or `running` are now excluded from the dispatch list. `paused` features are always included regardless of `round_assigned`.

## Technical Constraints

- **Atomic state writes preserved**: The round filter fix is prompt-only (no new state writes); the `_map_results_to_state` guard only skips writes. All state saves that do run continue to use `save_state()` with atomic `os.replace()`.
- **`_TERMINAL_STATUSES` constant must be reused**: New guards in `_map_results_to_state()` must use the existing `_TERMINAL_STATUSES = frozenset({"merged", "failed", "deferred"})` constant at line 32 — not hardcoded status strings.
- **Round filter must use Python code-block style**: The §1 filter in `orchestrator-round.md` must be structured as a Python code block (like §2a), not prose. Code blocks in this prompt are executed by the orchestrator agent and are more reliable than prose instructions.
- **`{round_number}` substitution**: `orchestrator-round.md` uses `{round_number}` as a template variable substituted by runner.sh at line 376. The round filter code block must reference this template literal (e.g., `current_round = {round_number}`) so it resolves to the actual round number at fill time.
- **No new modules**: All fixes are surgical changes to existing files. No new Python modules or shell utilities.
- **`round_assigned` assumed present**: The fix assumes all features in active sessions have `round_assigned` set (populated by `plan.py` at session creation). The null-guard pattern `(f.round_assigned or 0) <= current_round` handles legacy state gracefully.
