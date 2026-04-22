# Plan: route-python-layer-backlog-writes-through-worktree-checkout

## Overview

Thread an explicit `backlog_dir` argument through the Python-layer backlog-write surface (`backlog/update_item.py`, `backlog/create_item.py`, `claude/overnight/report.py::create_followup_backlog_items`, `claude/overnight/outcome_router.py::_write_back_to_backlog` and `_find_backlog_item_path`) so session-internal writers always route through `state.worktree_path`, add two `git add backlog/; git commit` blocks to `runner.sh` (nominal flow + SIGINT trap) to capture followup items on the integration branch, and fix two orchestrator defects (`set_backlog_dir` sourcing + state-load telemetry). Internal-API callers raise on `backlog_dir=None`; cwd-relative resolution is isolated to the `update-item` / `create-item` CLI `main()` layer so an accidentally-defaulted internal call fails loudly instead of silently writing to the home repo. **Scope note**: on orchestrator state-load corruption (any exception in `orchestrator.py:137-149`), `_backlog_dir` remains unset and `outcome_router._write_back_to_backlog` / `_find_backlog_item_path` silently fall back to `_PROJECT_ROOT / "backlog"` via the pre-existing `:360` pattern — the routing fix is inactive on that path per spec R6's explicit log-only decision. Task 5 telemetry surfaces this to operators via the `subsequent_writes_target` event field.

## Tasks

### Task 1: Refactor `backlog/update_item.py` internal API to thread `backlog_dir` explicitly
- **Files**: `backlog/update_item.py`
- **What**: Change `_find_item`, `_remove_uuid_from_blocked_by`, `_check_and_close_parent`, and `update_item` to accept a required `backlog_dir: Path` parameter (no default). Inside each, raise `TypeError("backlog_dir is required")` if called with `None`. Cascade helpers receive `backlog_dir` from `update_item`. CLI `main()` (at `update_item.py:458`-area) resolves `Path.cwd() / "backlog"` from argv once and passes it explicitly into `update_item()`. The module-level `BACKLOG_DIR` constant may survive as a local resolution inside `main()` only.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Signatures to change: `_find_item(slug_or_uuid: str) -> Path | None` at `backlog/update_item.py:127` becomes `_find_item(slug_or_uuid: str, backlog_dir: Path) -> Path | None`. `_remove_uuid_from_blocked_by` at `:201`, `_check_and_close_parent` at `:254`, `update_item` at `:336` all gain a required `backlog_dir: Path` parameter placed after the existing first positional arg (item_path or similar) and before optional kwargs.
  - The self-call at `update_item.py:458` (inside `main()` flow) must be updated to pass `backlog_dir`.
  - `BACKLOG_DIR = Path.cwd() / "backlog"` at module-top (`:38`) and `ARCHIVE_DIR = BACKLOG_DIR / "archive"` at `:39` are retained only as locals inside `main()` — remove the module-level bindings.
  - Every module-level use of `BACKLOG_DIR` inside `_find_item`, `_remove_uuid_from_blocked_by`, `_check_and_close_parent`, and the cascade helpers (grep found uses at `:135, :139, :148, :153, :158, :212, :222, :272, :277, :298`) must be replaced with the `backlog_dir` parameter now threaded through.
  - Caller-audit result: `grep -n "BACKLOG_DIR" backlog/update_item.py backlog/create_item.py backlog/generate_index.py claude/overnight/backlog.py` confirmed NO external importer uses `backlog.update_item.BACKLOG_DIR`; `generate_index.py` has its own independent `BACKLOG_DIR` constant at `:26`, and `claude/overnight/backlog.py` uses `DEFAULT_BACKLOG_DIR` (different symbol). Removing the module-level binding is safe.
  - Atomic-write discipline: all writes go through `claude/common.py:382`'s `atomic_write()` — no direct `Path.write_text` calls.
- **Verification**: `grep -n "BACKLOG_DIR" backlog/update_item.py` — pass if the only remaining match is inside the `main()` function body (run `grep -n "def main\|BACKLOG_DIR" backlog/update_item.py` and confirm every `BACKLOG_DIR` line number is strictly greater than the `def main` line number).
- **Status**: [ ] pending

### Task 2: Refactor `backlog/create_item.py` internal API to thread `backlog_dir` explicitly
- **Files**: `backlog/create_item.py`
- **What**: Change `create_item` at `:96` to accept a required `backlog_dir: Path` parameter (no default). Raise `TypeError("backlog_dir is required")` if called with `None`. Update the self-call at `create_item.py:167` (inside `main()` flow) to pass `backlog_dir` resolved from `Path.cwd() / "backlog"`. Remove the module-level `BACKLOG_DIR` constant at `:37`; keep cwd resolution local to `main()`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Follow the exact same pattern as Task 1 — mirror structure so the two CLI entry points are consistent.
  - `create_item` takes a dict-of-fields as its primary payload today; `backlog_dir` is an additional required kwarg positional-or-keyword.
  - Caller-audit: confirmed no external importer uses `backlog.create_item.BACKLOG_DIR` (see Task 1's audit). The `BACKLOG_DIR` usages at `:37, :40, :53, :110` are all internal to `create_item.py`.
- **Verification**: `grep -n "BACKLOG_DIR" backlog/create_item.py` — pass if the only remaining match is inside the `main()` function body (strictly after `def main`).
- **Status**: [ ] pending

### Task 3: Refactor `create_followup_backlog_items()` signature, session_id attribution, and in-file callers in `report.py`
- **Files**: `claude/overnight/report.py`
- **What**: Change `create_followup_backlog_items` signature at `report.py:272` to take `backlog_dir: Path` as a required parameter (remove any default). Replace the hardcoded `session_id: null` at `report.py:345` with `os.environ.get("LIFECYCLE_SESSION_ID", "manual")`. Update the two internal callers at `report.py:1435` and `report.py:1525` to pass `backlog_dir=Path(state.worktree_path) / "backlog"` — where `state` is already in scope at both call sites (these are inside functions that receive a `data` or state object). Inside `create_followup_backlog_items`, pass the new `backlog_dir` parameter through to `create_item()` (Task 2 makes this a required kwarg).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Signature (from grep): `def create_followup_backlog_items(` begins at `:272`; the function uses `create_item` internally and must pass `backlog_dir` to it per Task 2.
  - Pattern reference: `claude/overnight/outcome_router.py:409` and `backlog/update_item.py:358` already use `os.environ.get("LIFECYCLE_SESSION_ID", "manual")`; match that exact form for consistency.
  - The two call sites at `:1435` and `:1525` are inside different outer functions — inspect each to find the state variable name in scope. They differ in context (home-repo session vs target-project session paths in report generation).
- **Verification**: `grep -cn 'create_followup_backlog_items(' claude/overnight/report.py` equals 3 (one def + two calls); AND `grep -n "LIFECYCLE_SESSION_ID" claude/overnight/report.py` returns at least one match inside `create_followup_backlog_items`; AND `sed -n '272,360p' claude/overnight/report.py | grep -c 'session_id.*null'` equals 0.
- **Status**: [ ] pending

### Task 4: Fix `orchestrator.py:143` to source `set_backlog_dir` from `worktree_path`
- **Files**: `claude/overnight/orchestrator.py`
- **What**: Replace `outcome_router.set_backlog_dir(Path(next(iter(integration_branches))) / "backlog")` at `orchestrator.py:143` with a call that uses `overnight_state.worktree_path`: `outcome_router.set_backlog_dir(overnight_state.worktree_path / "backlog")`. Drop the `if integration_branches:` gate if the new expression is safe unconditionally; if `worktree_path` can be missing, gate the call on `if overnight_state.worktree_path:` — verify by reading `claude/overnight/state.py:244` to see the field's declared type (scalar `Path` vs `Path | None`).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current code at `orchestrator.py:140-143`: loads `integration_branches` then derives backlog dir from the first repo key. This is wrong because the first key isn't necessarily the worktree for the current session (and for pure wild-light sessions the home-repo key doesn't exist at all).
  - `OvernightState.worktree_path` is populated for every session by `plan.py:bootstrap_session`; trust that invariant for successful load paths.
  - Scope boundary: this call lives INSIDE the `try:` block at `:137`. On any exception in lines 139-149 (not just `load_state` failures), `set_backlog_dir` is bypassed and `_backlog_dir` remains None, activating the `:360` silent-fallback per spec R6 scope. Closing this structural bypass is NOT in scope for this task — see the Ask item in the Veto Surface.
  - `outcome_router.set_backlog_dir()` is declared at `outcome_router.py:316` — takes a single `Path`.
- **Verification**: `grep -n "set_backlog_dir" claude/overnight/orchestrator.py` shows the line references `worktree_path` (not `integration_branches`) — pass if the single match includes the substring `worktree_path`.
- **Status**: [ ] pending

### Task 5: Add `state_load_failed` telemetry to the `orchestrator.py` state-load exception handler
- **Files**: `claude/overnight/orchestrator.py`
- **What**: In the `except Exception:` block at `orchestrator.py:150-156`, emit a `state_load_failed` event to `lifecycle/pipeline-events.log` BEFORE setting the five empty-dict defaults (`spec_paths`, `backlog_ids`, `recovery_attempts_map`, `repo_path_map`, `integration_branches`). The event carries: `exception_type` (the exception's class name), `exception_message` (the str of the exception), `state_path` (the STATE_PATH being loaded), and `subsequent_writes_target` (the absolute path string `str(outcome_router._PROJECT_ROOT / "backlog")` — this field surfaces to operators WHERE subsequent backlog writes will silently route since `_backlog_dir` was not set). Control flow is unchanged: the fallback values are still set and the session continues.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - NDJSON schema in `lifecycle/pipeline-events.log`: existing events follow `{"ts": "<ISO 8601>", "event": "<name>", ...}`. Look at one existing event in that file for exact structure, and check `claude/overnight/orchestrator.py` (or `claude/overnight/events.py` if it exists) for an existing event-emit helper — prefer reusing it over hand-rolling the write.
  - Event fields: `event: "state_load_failed"`, `exception_type: <str>`, `exception_message: <str>`, `state_path: <str>`, `subsequent_writes_target: <str>`.
  - The `subsequent_writes_target` field is the observability connection that spec R6 requires: it tells an operator reading the event log exactly where backlog writes will land during this session — closing the gap where `state_load_failed` alone would not signal write misdirection.
  - Do NOT change the `except Exception:` clause's fallthrough behavior — the event emission is purely additive.
- **Verification**: `grep -n 'state_load_failed' claude/overnight/orchestrator.py` returns exactly one match inside the except-block (between the line containing `except Exception` and the next `def`/`class` after `:156`); AND `grep -n 'subsequent_writes_target' claude/overnight/orchestrator.py` returns exactly one match inside the same block.
- **Status**: [ ] pending

### Task 6: Thread `backlog_dir` through `_write_back_to_backlog` and `_find_backlog_item_path` call sites in `outcome_router.py`
- **Files**: `claude/overnight/outcome_router.py`
- **What**: Update both call sites of the imported `_backlog_*` aliases to pass `backlog_dir` as a kwarg (needed after Task 1 makes `backlog_dir` required).
  - Call site 1 — `_backlog_find_item(feature)` at `outcome_router.py:378` inside `_find_backlog_item_path`: update to `_backlog_find_item(feature, backlog_dir=backlog_dir)` where `backlog_dir` is the local variable already resolved at `:360` (`_backlog_dir if _backlog_dir is not None else _PROJECT_ROOT / "backlog"`).
  - Call site 2 — `_backlog_update_item(item_path, fields, session_id=session_id)` at `outcome_router.py:417` inside `_write_back_to_backlog`: add a new local `backlog_dir = _backlog_dir if _backlog_dir is not None else _PROJECT_ROOT / "backlog"` in `_write_back_to_backlog` (mirroring the `:360` pattern), then update the call to pass `backlog_dir=backlog_dir` as an additional kwarg.
  - The `:360` fallback itself is NOT modified — it is the spec-sanctioned silent-misdirection path per spec R6.
  - The local-fallback pattern (`_backlog_dir if _backlog_dir is not None else _PROJECT_ROOT / "backlog"`) is the spec R6 silent-misdirection path: on state-corruption (`_backlog_dir is None`), the caller resolves a concrete path (`_PROJECT_ROOT / "backlog"`) and passes it to Task 1's internal API. Task 1's raise-on-None is exercised only when a caller explicitly passes `None` — which Task 6 never does. This preserves spec R6's deliberate behavior (silent-misdirection on corruption, no crash) while still failing loudly on internal-API abuse.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Imports for reference: `from backlog.update_item import update_item as _backlog_update_item` at `:322`, `from backlog.update_item import _find_item as _backlog_find_item` at `:323`.
  - Grep-confirmed call sites in `outcome_router.py`: `_backlog_find_item` at `:378` (inside `_find_backlog_item_path`); `_backlog_update_item` at `:417` (inside `_write_back_to_backlog`). The verification grep spans both call sites.
  - `_find_backlog_item_path` already has the local `backlog_dir` variable at `:360` — reuse it for the `:378` call (no new resolution needed). `_write_back_to_backlog` does NOT have a local `backlog_dir` today — add one mirroring the `:360` pattern.
  - The existing `_PROJECT_ROOT / "backlog"` silent fallback at `:360` is NOT changed — that is the spec R6 accepted latent path and must survive this ticket.
- **Verification**: `grep -n "_backlog_update_item\|_backlog_find_item" claude/overnight/outcome_router.py` — every matching call-site (excluding the imports at `:322-323`) includes `backlog_dir=backlog_dir` in its argument list. Additionally, `grep -c 'if _backlog_dir is not None else _PROJECT_ROOT / "backlog"' claude/overnight/outcome_router.py` returns 2 (one at `:360`, one newly added inside `_write_back_to_backlog`) — confirms the local-fallback expression exists in both surrounding functions.
- **Status**: [ ] pending

### Task 7: Update the SIGINT trap in `runner.sh` to pass `backlog_dir` to `create_followup_backlog_items` and add the trap-path second-commit block
- **Files**: `claude/overnight/runner.sh`
- **What**: In the SIGINT trap at `runner.sh:507-521`:
  1. Add `WORKTREE_PATH="$WORKTREE_PATH"` to the trap's explicit env prefix at `:507`. The trap's current prefix (`STATE_PATH="$STATE_PATH" EVENTS_PATH="$EVENTS_PATH" TARGET_PROJECT_ROOT="$TARGET_PROJECT_ROOT" REPO_ROOT="$REPO_ROOT" SESSION_ID="$SESSION_ID"`) does NOT include `WORKTREE_PATH` — it is a non-exported shell variable (no `export` statement in `runner.sh`). Without this prefix addition, `os.environ["WORKTREE_PATH"]` inside the python snippet raises `KeyError` silently (swallowed by the trap's `|| true` at `:521`).
  2. Update the `create_followup_backlog_items(data)` call at `:513` to pass `backlog_dir` as a keyword argument, resolving it from `Path(os.environ["WORKTREE_PATH"]) / "backlog"`.
  3. Immediately after the `create_followup_backlog_items` call and before the trap's `exit 130`, add a commit block that: changes directory into `$WORKTREE_PATH`, stages the `backlog/` directory with `git add`, checks whether the index has staged changes (using `git diff --cached --quiet` — exits zero when nothing is staged, nonzero when there are changes), and only runs `git commit` when changes are staged. The commit message template is `"Overnight session ${SESSION_ID}: record followup backlog items"`. Wrap the entire commit block in a subshell, and follow with `|| true` so a commit failure cannot mask the original interrupt. Follow the pattern at `runner.sh:1001-1014` for the subshell structure. Per spec R4, this satisfies the trap-path commit requirement.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Current trap at `runner.sh:507-521` is an inline `python3 -c "..."` block. The call at `:513` sits inside that Python snippet. The existing env prefix (confirmed via `sed -n '505,525p' runner.sh`) lists only `STATE_PATH, EVENTS_PATH, TARGET_PROJECT_ROOT, REPO_ROOT, SESSION_ID` — `WORKTREE_PATH` must be added explicitly.
  - `$WORKTREE_PATH` is set at `runner.sh:243-247` as a non-exported shell variable. It is accessible at the trap level (shell scope) but not to subprocesses unless passed via the env prefix (`VAR="$VAR" command`) or exported.
  - Pattern reference for commit block: nominal-flow artifact commit at `runner.sh:1001-1014` shows the subshell + `git diff --cached --quiet || git commit` pattern.
  - The `|| true` after the subshell ensures the trap itself exits cleanly even if the commit fails — we don't want a trap-time commit failure to mask the original interrupt.
- **Verification**: `awk '/^trap_sigint\(\)/,/^}/' claude/overnight/runner.sh | grep -c "record followup"` equals 1 (the commit block exists inside the trap function). AND `awk '/^trap_sigint\(\)/,/^}/' claude/overnight/runner.sh | grep -c 'WORKTREE_PATH="$WORKTREE_PATH"'` equals 1 (env prefix includes WORKTREE_PATH). AND `awk '/^trap_sigint\(\)/,/^}/' claude/overnight/runner.sh | grep -c "backlog_dir="` equals 1 (trap's python call passes backlog_dir).
- **Status**: [ ] pending

### Task 8: Add the nominal-flow second-commit block and `followup_commit_skipped` event to `runner.sh` (set-e-safe)
- **Files**: `claude/overnight/runner.sh`
- **What**: After the if/else block that calls `generate_and_write_report` (the block at `runner.sh:1181-1283`), capture the report-generation exit code in a **set-e-safe** manner and conditionally emit a second commit block.
  1. **Exit-code capture under `set -euo pipefail`** (active at `runner.sh:18`): the current pattern at each branch is `python3 -c "..." 2>"$MR_STDERR" || { MR_DETAILS=...; log_event "morning_report_generate_result" "$ROUND" "$MR_DETAILS" || true; true }` — the trailing `true` inside the `|| { ... }` compound is what keeps errexit happy. Do NOT remove the compound or its trailing `true`. Inside the compound, ADD a line `report_gen_rc=$?` as the FIRST statement (so `$?` captures the python3 exit code before `MR_DETAILS=...` runs any command that would overwrite it). Outside the compound — i.e., on the success branch — add `report_gen_rc=0` (so the variable is always set regardless of which path ran). Do NOT use the bare pattern `python3 -c "..."; report_gen_rc=$?` — under errexit, a non-zero exit from python3 would terminate the script before `report_gen_rc=$?` is reached.
  2. After the closing `fi` at `:1283`, add a conditional block:
     - When `report_gen_rc` equals 0: run the same subshell commit structure as Task 7's trap block (cd to `$WORKTREE_PATH`, `git add backlog/`, check staged changes with `git diff --cached --quiet`, commit with message template `"Overnight session ${SESSION_ID}: record followup backlog items"`, wrap in `|| true`).
     - When `report_gen_rc` is nonzero: call the existing `log_event` shell helper with event name `followup_commit_skipped`, the current `$ROUND`, and a JSON payload containing `session_id` (value `"$SESSION_ID"`) and `reason` (value `"report_gen_failed"`).
  3. Per spec R4, the nominal-flow commit must be success-guarded so the commit does not fire over a partial followup set.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - **Existing pattern verified by `sed -n '1178,1240p' runner.sh`**: the real code uses `python3 -c "..." 2>"$MR_STDERR" || { MR_DETAILS=$(python3 -c "...") 2>/dev/null || echo '{...}'; log_event "morning_report_generate_result" "$ROUND" "$MR_DETAILS" || true; true }` — NOT the `|| echo "Warning: ..."` pattern earlier drafts referenced. The trailing `true` at the end of the `{ ... }` compound block is load-bearing for `set -e` compatibility; preserve it.
  - **`set -euo pipefail` at `runner.sh:18`** (confirmed) makes the script abort on any uncaught non-zero exit. The `|| true` guard on non-success paths is mandatory.
  - **rc-capture idiom under errexit**: the only portable set-e-safe form is to capture `$?` INSIDE the `||` compound (where errexit is already suppressed) — e.g., `python3 -c "..." || { report_gen_rc=$?; ... ; true }`. Placing `report_gen_rc=$?` on its own line after a bare failure-prone command terminates the script before capture.
  - Mutually exclusive if/else: only one of the two branches runs per session, so a single conditional block after the closing `fi` covers both.
  - `log_event` function: exists at `runner.sh:355` as a shell function — takes event name, round number, and JSON payload.
  - Pattern reference for session-id-qualified commit message: nominal-flow artifact commit at `runner.sh:1001-1014`.
- **Verification**: `grep -cn 'Overnight session.*record followup' claude/overnight/runner.sh` equals 2 (one nominal + one trap from Task 7). AND `grep -cn 'followup_commit_skipped' claude/overnight/runner.sh` equals 1. AND `grep -cn '|| report_gen_rc=\$?\|report_gen_rc=$?' claude/overnight/runner.sh` returns at least 2 matches (one per branch's `||` compound).
- **Status**: [ ] pending

### Task 9: Integration test — simulated failed session routes backlog writes through worktree
- **Files**: `tests/test_runner_signal.py` (existing — extend) or `tests/test_worktree.py` (existing — extend); add `tests/fixtures/failed-session/` if new fixtures are needed
- **What**: Write a test that simulates an overnight session, exercises `_write_back_to_backlog` (via orchestrator.py state-setup or a direct call through `outcome_router`) to mutate `session_id` on a backlog item, then triggers a session failure (either by faking SIGINT or by letting the test fixture harness exit non-zero). After the simulated failure, assert: (a) `git status --porcelain backlog/` run from the home repo (fixture repo) returns empty output; (b) the integration branch has a commit whose message matches the `Overnight session .* record followup` pattern; (c) the followup item's `session_id` frontmatter equals the fixture session id (not `null`, not `"manual"`).
- **Depends on**: [1, 3, 6, 7, 8]
- **Complexity**: complex
- **Context**:
  - Pattern reference: `tests/test_worktree.py` and `tests/test_runner_signal.py` already exercise the overnight runner's worktree + SIGINT paths — extend rather than creating a new test file if the fixtures align.
  - Test-harness helpers: `tests/conftest.py` at top-level may have fixture setup; `claude/overnight/tests/conftest.py:24-28` stubs `backlog.update_item` — the stub's lambda signature already accepts `*args, **kwargs` so the Task 1 signature change does NOT require conftest changes.
  - **Harness fidelity warning**: the test harness must run the REAL `runner.sh` (not a mocked version) to exercise Task 7's env-prefix fix and Task 8's set-e-safe rc-capture. Mocking the shell script would mask both defect classes. If the existing harness does not run the real script, prefer a subprocess-based harness that invokes `runner.sh` with `set -x` for trace observability.
  - Fixture isolation: use a tmpdir-backed fake home-repo + worktree so the test can `git status` against the fixture without affecting the real repo. Pattern: `tests/fixtures/` already contains pre-built scenarios.
  - Two cases to exercise inside this single test task: (1) nominal flow path where `generate_and_write_report` succeeds and the second-commit block fires; (2) trap path where SIGINT interrupts the round loop and the trap's commit block fires. Use parametrize or two test functions in the same file.
- **Verification**: Run `just test` (or the narrower `uv run pytest tests/test_worktree.py tests/test_runner_signal.py -v`) — pass if exit 0 and the newly-added test function(s) are listed as PASSED.
- **Status**: [ ] pending

### Task 10: Integration test — `state_load_failed` event logged on state corruption
- **Files**: `tests/test_events_contract.py` (existing — extend) or `tests/test_events.py` (existing — extend)
- **What**: Write a test that deliberately corrupts `lifecycle/overnight-state.json` (write invalid JSON or a truncated file), invokes `orchestrator.py`'s state-load path (either by calling the function directly or via a minimal harness that triggers it), and asserts that `lifecycle/pipeline-events.log` contains a `state_load_failed` event with the expected fields (`event`, `exception_type`, `exception_message`, `state_path`, `subsequent_writes_target`). Also assert control flow continues — the five empty-dict defaults are set and the session does not crash.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - Pattern reference: `tests/test_events_contract.py` asserts NDJSON event schemas; `tests/test_events.py` tests event emission behavior. Extend the most closely-matching file.
  - Fixture: write the corrupted state to a tmpdir path and pass it via `STATE_PATH` env or equivalent — do NOT mutate the real `lifecycle/overnight-state.json`.
  - Assertion on `subsequent_writes_target`: must equal `str(outcome_router._PROJECT_ROOT / "backlog")` — the spec R6 silent-misdirection target that the telemetry surfaces.
- **Verification**: Run `uv run pytest tests/test_events_contract.py tests/test_events.py -v` — pass if exit 0 and the new test function is listed as PASSED.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification runs `just test` at the repo root. For a feature-scoped verification, run `uv run pytest tests/ -v -k "worktree or runner_signal or events"` which exercises the integration tests added in Tasks 9 and 10 plus adjacent regression tests (existing tests like `test_plan_worktree_routing.py` already cover plan.py's worktree-path resolution; they should continue to pass unchanged).

Concrete end-to-end assertions (all covered by Tasks 9 and 10):

1. After a simulated failed home-repo session: `git status --porcelain backlog/` from the home repo returns empty (R7).
2. After a simulated failed session, `git log <integration-branch> -- backlog/` shows a commit whose message matches `Overnight session .* record followup` and whose diff includes the newly-created followup file (R4 nominal + R4 trap).
3. Followup items land with `session_id: <session-uuid>` or `session_id: manual`, not `session_id: null` (R5).
4. With a corrupted state.json, `lifecycle/pipeline-events.log` contains a `state_load_failed` event with `subsequent_writes_target` field set to the home-repo backlog path, and the session's round loop continues (R6).
5. Static verification: `grep -cn 'Overnight session.*record followup' claude/overnight/runner.sh` equals 2 (R4 count).
6. Static verification: `grep -n "BACKLOG_DIR" backlog/update_item.py backlog/create_item.py` returns matches only inside `main()` function bodies (R3 no-silent-fallback at internal-API level).
7. Regression: morning-report rendering on an existing fixture produces byte-identical output modulo the R5 session_id attribution fix — verified indirectly by existing `test_report.py` tests continuing to pass (update fixtures as part of Task 3 if needed).
8. Shell-set-e: the nominal flow's rc-capture pattern does not cause script termination on `python3 -c` non-zero exit — verified by Task 9's integration test exercising the success-guard skip path.

## Veto Surface

1. **Raise-on-None vs silent-cwd-fallback at the internal API** (Tasks 1, 2). Spec R3 locks the "raise on None at internal API; cwd fallback only at CLI main()" discipline to prevent silent regression to home-repo writes. Alternative considered and rejected in spec: keep `backlog_dir` optional with a cwd default. If the user wants to revisit, the plan becomes smaller (Tasks 1, 2 can keep current signatures and only add optional args), but the silent-misdirection failure mode survives at the internal-API level.

2. **Single post-if/else commit block** (Task 8) rather than one block inside each of the two `generate_and_write_report` branches. The branches at `runner.sh:1181-1283` are mutually exclusive (home-repo vs target-project session), so one block after the `fi` covers both cases. The alternative is two blocks (one per branch), which is more code and more places for drift.

3. **Success-guarded nominal commit block** (Task 8). Spec R4 specifies the nominal-flow second-commit block SKIPS when `generate_and_write_report` exited non-zero, emitting a `followup_commit_skipped` event instead. Alternative considered and rejected: commit a partial followup set anyway. The skip is safer against data corruption but means a failed report-gen loses any followups written before the failure. This is the deliberate trade-off.

4. **Telemetry-only fix for state-load corruption** (Task 5, spec R6) — **strengthened risk classification**:
   - **Frequency**: Spec Non-Requirements names three routine triggers: filesystem hiccup, concurrent dashboard read, truncated JSON from crashed concurrent save. State is saved multiple times per session (`orchestrator.py:239, :370, :381`), creating real windows for transient events. A millisecond-scale transient permanently disables the routing fix for the remainder of orchestrator.py's invocation.
   - **Scope of bypass**: `set_backlog_dir` at `orchestrator.py:143` lives inside the `try:` block at `:137`. ANY exception in lines 139-149 (not just `load_state` failures — also dataclass-construction errors, schema-mismatch errors, or any attribute access on `overnight_state`) activates the bypass. The ticket does not classify whether this broader exception surface is considered part of the accepted R6 deferral.
   - **Observability**: Task 5's `subsequent_writes_target` field closes part of the gap by surfacing WHERE writes will route during a state-corrupted session. It does NOT generate a separate warning-level event or notification; operators must proactively read the event log.
   - **Residual**: `_write_back_to_backlog` and `_find_backlog_item_path` silently fall back to `_PROJECT_ROOT / "backlog"` (home repo) per the `:360` pattern. Control flow is unchanged from pre-fix behavior on this path. Spec R6 explicitly accepts this as log-only; a separate hardening ticket will add a true session-pause primitive. **This is an Ask item for the user** (see "Open Questions" below) in case they want to revisit scope.

5. **Cross-repo followup routing is deferred** (spec non-requirement). Followups for pure wild-light sessions land on the cross-repo integration branch, not home-repo. Consistent with spec scope; flagged here because it is a visible behavior difference from "all followups go to home repo".

6. **Inline exit-code capture refactor for `generate_and_write_report`** (Task 8) — **strengthened blast radius note**:
   - The current pattern (`python3 -c "..." 2>"$MR_STDERR" || { ...; log_event ...; true }`) relies on the trailing `true` inside the `||`-compound to satisfy `set -euo pipefail` (active at `runner.sh:18`).
   - A naive rc-capture replacement (`python3 -c "..."; report_gen_rc=$?`) would cause the script to terminate at the `python3` line on non-zero exit — a full session availability regression, NOT merely a change in error-reporting surface.
   - Task 8's specified pattern (capture `$?` INSIDE the `||` compound as the first statement) preserves set-e compatibility. The `report_gen_rc=0` on the success branch ensures the variable is always set.
   - If the user wants the existing behavior preserved verbatim, Task 8 can be redesigned to use a sentinel file instead of an rc variable — more complex but further away from the error-reporting change.

## Scope Boundaries

Mirrors spec Non-Requirements:

- Cross-repo followup routing (per-feature to per-repo worktree) is out of scope.
- Session-pause primitive on state-corruption is out of scope (R6 is telemetry only).
- Auto-deleting integration branches on session failure is out of scope.
- The runner's orchestrator-prompt disambiguation is out of scope (sibling ticket in epic 126).
- The git pre-commit hook rejecting commits to main during a session is out of scope (sibling ticket).
- Morning-report commit un-silence is out of scope (sibling ticket).
- PR-creation gating is out of scope.
- Retroactive recovery of session 1708's lost followup content (IDs 101/102/103) is out of scope — permanently lost.
- Dashboard, statusline, and other read-only observability code are not modified.
- No new env vars introduced for worktree-path signaling — the fix is argument-based. The Task 7 addition of `WORKTREE_PATH="$WORKTREE_PATH"` to the trap's env prefix does NOT introduce a new env var; it propagates an existing shell variable into a subprocess.
- No transient-vs-persistent classification on state-load failures.
- Closing the structural state-load-exception bypass (moving `set_backlog_dir` out of the try block, or adding a fallback in the except path) is out of scope per spec R6 — see Ask item below.
