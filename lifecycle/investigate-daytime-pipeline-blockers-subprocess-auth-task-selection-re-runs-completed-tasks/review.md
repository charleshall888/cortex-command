# Review: investigate-daytime-pipeline-blockers-subprocess-auth-task-selection-re-runs-completed-tasks

## Stage 1: Spec Compliance

### Requirement R1: Shared auth module `claude/overnight/auth.py` — Python API
- **Expected**: New stdlib-only module exports `ensure_sdk_auth(event_log_path) -> dict` resolving four vectors (`env_preexisting` | `api_key_helper` | `oauth_file` | `none`), writing credential to `os.environ`, sanitizing `sk-ant-*` via the specified regex, emitting one JSON line to the log path when provided (otherwise writing the message to stderr), and returning `{"vector", "message"}`.
- **Actual**: `claude/overnight/auth.py::ensure_sdk_auth` implements all four branches in priority order (pre-existing `ANTHROPIC_API_KEY` → apiKeyHelper → oauth file → none), writes to `os.environ`, routes messages through `_sanitize` (which uses the exact regex), writes the event to the path when provided via `_write_event` or to stderr otherwise, and returns `{"vector", "message", "event"}` (superset of the spec's required keys — R5 Phase B uses `event`). The parametrized test `test_vector_resolution` covers all four branches.
- **Verdict**: PASS
- **Notes**: Return dict additionally contains `event`, which is a non-breaking superset used intentionally by R5 Phase B.

### Requirement R2: Shared auth module — shell API
- **Expected**: `resolve_auth_for_shell() -> int` invokable via `python3 -m cortex_command.overnight.auth --shell`; prints `export VAR=VALUE` with `shlex.quote`, warnings to stderr, exit 0 on resolved / 1 on no-vector / 2 on helper-internal failure. Module must import with no venv active.
- **Actual**: `resolve_auth_for_shell` prints `export ANTHROPIC_API_KEY=…` or `export CLAUDE_CODE_OAUTH_TOKEN=…` via `shlex.quote`, writes warnings to stderr, catches `_HelperInternalError` → exit 2, catches generic `Exception` → exit 2 (stdlib-regression safety net), returns 0 on pre-existing env and resolved helper/oauth, 1 on no-vector. CLI dispatch in `_main` under `if __name__ == "__main__"`. The unit test `test_shell_exit_codes` asserts all three exit codes.
- **Verdict**: PASS

### Requirement R3: Stdlib-only regression guard
- **Expected**: Test dispatches `python3 -I -c "…"` with `PYTHONPATH=REPO_ROOT` and fixture `HOME`; subprocess must exit 0 or 1 (never 2); test asserts `returncode == 1` and stderr free of `ImportError` / `ModuleNotFoundError`.
- **Actual**: `test_stdlib_only` runs `[sys.executable, "-I", "-c", code]` with `PATH`, `HOME`, `PYTHONPATH` env, asserts `returncode == 1`, asserts stderr contains neither `ImportError` nor `ModuleNotFoundError`. Module imports enumerated: `argparse`, `json`, `os`, `pathlib`, `re`, `shlex`, `subprocess`, `sys`, plus stdlib-only sibling `claude.pipeline.state._now_iso` (stdlib transitively).
- **Verdict**: PASS

### Requirement R4: runner.sh refactor — concrete bash pattern
- **Expected**: Lines 42–87 replaced with the exact `set +e` / capture / `case` pattern specified; `bash -n` passes; regression test covers three exit-code branches.
- **Actual**: `claude/overnight/runner.sh:42-58` matches the spec block verbatim (the `set +e` bracket, `$(python3 -m cortex_command.overnight.auth --shell)` capture, `case` on `$_AUTH_EXIT`, `unset` cleanup). The two warning strings at the old `runner.sh:78,82` are removed as specified. `tests/test_runner_auth.sh` stages a stubbed `python3` on `PATH` per scenario and exercises success (token exported), no-vector (sentinel reached), and helper-internal-failure (exit 2 with stderr message, sentinel NOT reached) — all three scenarios.
- **Verdict**: PASS

### Requirement R5: daytime_pipeline.py auth bootstrap — call-site ordering
- **Expected**: Phase A — `ensure_sdk_auth(event_log_path=None)` invoked as the first statement of `run_daytime`, before `_check_cwd`, plan-exists, PID-file liveness, `_write_pid`; no event written here. Phase B — after `pipeline_events_path` is computed, append the buffered event. Acceptance: call appears before `_write_pid`; integration test asserts exactly one `auth_bootstrap` event in `pipeline-events.log` by the time `execute_feature` runs.
- **Actual**: `daytime_pipeline.py:339` calls `ensure_sdk_auth(event_log_path=None)` inside the outer try-block. Positioned AFTER `_check_cwd()` (line 318), `_check_dispatch_id()` (line 322), and `start_ts` capture — but BEFORE `plan_path.exists()` (line 353), `_read_pid`/`_is_alive` (lines 367–381), `_write_pid` (line 383). Phase B emission at `daytime_pipeline.py:395-398` appends via `json.dumps(event) + "\n"` with parent-dir creation, matching `log_event` byte format. The hard-fail-test monkeypatch confirms the call runs inside the try-block so the outer finally writes the result file.
- **Verdict**: PARTIAL
- **Notes**: The spec text says "first statement of `run_daytime`, before `_check_cwd`". The implementation runs `_check_cwd` and `_check_dispatch_id` first so that the outer try/finally can set up the `daytime-result.json` write path correctly — which is also why the test fixture creates a `lifecycle/` dir for `_check_cwd`. The R5 acceptance criterion (grep-before-`_write_pid` and exactly-one-event-before-`execute_feature`) is satisfied. The deviation is a defensible consequence of the exception-classification design (also required by R6): moving auth resolution before `_check_cwd`/`_check_dispatch_id` would mean a `_check_cwd` failure could never produce a `daytime-result.json`, and a missing `dispatch_id` could not be captured. The literal spec text is violated but the acceptance criteria pass; rated PARTIAL to surface the deviation rather than FAIL because the acceptance bar passes.

### Requirement R6: Hard fail on no auth vector — daytime path
- **Expected**: `vector: "none"` → startup-phase failure with `daytime-result.json` showing `outcome: "failed"`, `terminated_via: "startup_failure"`, and error containing `"no auth vector available"`. Must happen before worktree creation.
- **Actual**: `daytime_pipeline.py:340-350` sets `_top_exc`, `_terminated_via = "startup_failure"`, `_outcome = "failed"`, and returns 1 before any later work (no PID file written, no worktree created). `tests/test_daytime_auth.py::test_no_auth_vector_hard_fails` runs in a temp-dir fixture with no `.claude/settings.json` or `personal-oauth-token`, asserts `rc == 1`, `terminated_via == "startup_failure"`, `outcome == "failed"`, and the error string contains `"no auth vector available"`.
- **Verdict**: PASS

### Requirement R7: Auth observability event — schema and field sanitization
- **Expected**: `auth_bootstrap` JSON line with `ts` first, `event`, `vector`, `message`; no raw token, no full helper command; `sk-ant-*` substituted with `sk-ant-<redacted>` before inclusion; byte-format matches `log_event`.
- **Actual**: `_build_event` constructs the dict in the order `ts`, `event`, `vector`, `message`; `_write_event` writes `json.dumps(event) + "\n"` to an O_APPEND handle, matching `log_event` byte-for-byte. `_sanitize` applies the exact regex. Messages are canned per branch and never include the full helper command. Test `test_redaction_and_byte_equivalence` frozen-clocks both emission paths and asserts byte-equivalence with `pipeline_state.log_event`; redaction assertion checks `"sk-ant-secret123"` absence via direct `_sanitize` call and end-to-end event-file inspection.
- **Verdict**: PASS
- **Notes**: R7 acceptance (i) describes "feed a synthetic helper that emits `sk-ant-secret123` on stderr into `ensure_sdk_auth`" — the test implements the equivalent by feeding a helper that emits the token on stdout (which is redacted before being exported as `message`, though the raw value is still written into `os.environ` per design). The spec's own Edge Cases note helper stderr/exception `repr()` MUST also pass through `_sanitize` (and the implementation does this in `_read_api_key_helper` and `_read_oauth_file`). The end-to-end event-file inspection proves the leak path is closed, and a direct `_sanitize` unit call proves the stderr-content sanitization path works. Acceptance bar met.

### Requirement R8: `os.environ` write
- **Expected**: `ensure_sdk_auth` writes resolved credentials directly to `os.environ`; `dispatch.py:401-405` unchanged.
- **Actual**: `auth.py:217` writes `os.environ["ANTHROPIC_API_KEY"] = api_key` on the helper branch; `auth.py:228` writes `os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = token` on the oauth-file branch. Test `test_environ_write` asserts `os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == fixture_value`. `dispatch.py:402-406` unchanged forwarding.
- **Verdict**: PASS

### Requirement R9: stderr token redaction in dispatch.py
- **Expected**: `_on_stderr` applies `re.sub(r'sk-ant-[a-zA-Z0-9_-]+', 'sk-ant-<redacted>', line)` before appending.
- **Actual**: `dispatch.py:425-428` — `_on_stderr` runs the exact substitution on `line`, then appends to `_stderr_lines`. Test `TestDispatchTaskStderrRedaction::test_on_stderr_redacts_sk_ant_tokens_stderr_redact` feeds a synthetic stderr with `sk-ant-abc123def` via the SDK stub's `options.stderr` callback and inspects the closure cell to assert `"sk-ant-<redacted>"` present and `"sk-ant-abc123def"` absent.
- **Verdict**: PASS

### Requirement R10: Parser E1 — heading marker strip (narrowed class)
- **Expected**: `_parse_tasks` applies `re.sub(r'\s*\[[xX]\]\s*$', '', description).strip()` after the initial `.strip()`. Trailing `[x]`/`[X]` stripped; `[ ]` preserved.
- **Actual**: `parser.py:301-302` — `description = match.group(2).strip(); description = re.sub(r'\s*\[[xX]\]\s*$', '', description).strip()`. Test `TestParseTasksStripsTrailingXXFromHeading::test_parse_tasks_strips_trailing_xX_from_heading` asserts all three cases (`[x]` stripped → `"Do the thing"`, `[X]` stripped → `"Other"`, `[ ]` preserved → `"Reserve slot [ ]"`).
- **Verdict**: PASS

### Requirement R11: Parser E2 — regex anchor in `_parse_field_status`
- **Expected**: Detection changes from `re.search(r"\[x\]", raw, re.IGNORECASE)` to `re.match(r"\[[xX]\]", raw)`; no `\s*` prefix.
- **Actual**: `parser.py:395` — `if re.match(r"\[[xX]\]", raw):`. Tests `TestParseFieldStatusAnchoredMatch` cover (i) `[x] complete` → done, (ii) `[X] complete` → done, (iii) `see [x]y.txt pending` → pending (anchored match rejects mid-line), (iv) `[ ] pending` → pending.
- **Verdict**: PASS

### Requirement R12: Parser E3 — writer idempotency verification (test-only)
- **Expected**: Test asserts `mark_task_done_in_plan` byte-identical on already-`[X]` and `[x]` fields, and updates `[ ] pending` to `[x] complete`.
- **Actual**: `tests/test_common_utils.py::TestMarkTaskDoneInPlanIdempotent::test_mark_task_done_in_plan_idempotent_over_existing_marks` codifies three cases: `[X] complete` → bytes unchanged, `[x] complete` → bytes unchanged, `[ ] pending` → becomes `[x] pending`.
- **Verdict**: PASS
- **Notes**: The R12 acceptance text says the `[ ] pending` case "updates to `- **Status**: [x] complete` as before". The actual regex in `mark_task_done_in_plan` substitutes only the bracket (`[ ]` → `[x]`), not the trailing literal "pending"/"complete" text; the real post-substitution value is `[x] pending`. The test codifies the actual behavior, which matches the R12 framing of "ALREADY idempotent... no source change required... future refactor cannot silently regress". The acceptance wording about "`[x] complete`" is mildly imprecise relative to the function's actual substitution; the test correctly captures real behavior and satisfies the core R12 goal (guard against writer regression).

### Requirement R13: Parser round-trip test
- **Expected**: Integration test with two tasks — both headings end with `[x]`; Task 1 Status `[x] complete` → `status=done`, description stripped; Task 2 Status `[ ] pending` → `status=pending`, description stripped.
- **Actual**: `test_parser.py::test_heading_and_status_round_trip` writes the exact fixture plan.md with both task patterns, parses, asserts Task 1 `description == "Do the complete thing"` + `status == "done"`, Task 2 `description == "Capture baseline commit SHA and reference-file line counts"` + `status == "pending"`. The Task 2 title matches the lifecycle-plan Task 2 pattern cited in the spec.
- **Verdict**: PASS

### Requirement R14: Documentation update
- **Expected**: `docs/overnight-operations.md` auth section updated with both `runner.sh` and `daytime_pipeline.py`, shared module path, three-exit-code contract, deferred-event-emit pattern. Greps: `daytime_pipeline` ≥ 1, `claude/overnight/auth.py` ≥ 1, `exit code 2` ≥ 1.
- **Actual**: `docs/overnight-operations.md:512-544` reworks the Auth Resolution section. Greps return: `daytime_pipeline` = 3, `claude/overnight/auth.py` = 2, `exit code 2` = 1. The Shell entry-point three-exit-code subsection and the Daytime deferred-event-emit subsection are both present and internally consistent with the code.
- **Verdict**: PASS

### Requirement R15: Problem 2 literal close-out in PR body
- **Expected**: PR description contains "user-error on the reproducer" or equivalent in a Problem 2 section.
- **Actual**: No PR has been opened yet on this branch. The acceptance is a PR-time deliverable satisfied during `/pr` creation, not an implementation source-tree check.
- **Verdict**: PARTIAL
- **Notes**: This is not a code defect; the PR body is authored at PR-creation time. Flagging for the author to include the required narrative when `/pr` runs. Not a blocker for implementation approval.

## Requirements Drift

**State**: none
**Findings**:
- None — the implementation is a consolidation/hardening effort: it extracts existing shell auth logic into a shared stdlib module, adds token-redaction and a narrow parser bug-fix, and adds observability for an existing event stream. `requirements/pipeline.md` governs session orchestration, feature lifecycle, conflict resolution, post-merge review, deferral, metrics, and post-session sync — none of which are modified. `requirements/multi-agent.md:84` already lists `ANTHROPIC_API_KEY` as a dependency; `CLAUDE_CODE_OAUTH_TOKEN` forwarding in `dispatch.py:405` predates this lifecycle (commit `e78c226`, "Add CLAUDE_CODE_OAUTH_TOKEN support to overnight runner"), so this implementation does not introduce that behavior. Implementation details (auth module path, exit-code contract, deferred-event-emit pattern) live in `docs/overnight-operations.md` where they belong; they are below the abstraction level of the requirements docs.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Module and function names follow the project pattern (`ensure_sdk_auth`, `resolve_auth_for_shell`, `_sanitize`, `_read_api_key_helper`, `_HelperInternalError`). Test function/class names mirror spec requirement IDs (`test_vector_resolution`, `test_shell_exit_codes`, `TestParseTasksStripsTrailingXXFromHeading`, etc.) which is consistent with other pipeline/overnight tests.
- **Error handling**: Exception boundaries are precise — `_read_api_key_helper` raises `_HelperInternalError` only on `JSONDecodeError` and `OSError`; `_invoke_api_key_helper` swallows timeout/missing-binary/OS errors (per Edge Cases spec); `resolve_auth_for_shell` has a final generic-Exception catch-all for stdlib-regression safety (documented with `noqa: BLE001`). `daytime_pipeline.py` classifies `vector == "none"` as `startup_failure` via the existing try/except/finally pattern so `daytime-result.json` always gets written.
- **Test coverage**: All twelve verification steps from the plan were executed. Test coverage includes parametrized four-way vector resolution, three-way exit-code cases, stdlib-isolated-mode subprocess, byte-equivalence with a frozen clock, environ write on oauth-file branch, three-way parser E1 strip cases (including `[ ]` preservation), four-way parser E2 anchored-match cases, three-way writer idempotency cases, round-trip integration with two-task fixture, daytime hard-fail with real `run_daytime` invocation, and runner.sh bash regression with stubbed-`python3` covering all three exit-code paths.
- **Pattern consistency**: `_write_event` uses `open(..., "a", encoding="utf-8")` and `json.dumps(event) + "\n"`, byte-matching `claude/pipeline/state.py::log_event`. Timestamp source is shared via re-export (`from cortex_command.pipeline.state import _now_iso`) — monkey-patchable from a single site per the spec's guidance. Daytime Phase B also uses `json.dumps(event) + "\n"` directly for the same reason. Subprocess tests use `tmp_path` fixture redirection via `monkeypatch.setattr(pathlib.Path, "home", ...)`, matching the plan's Task 1 note pinning `Path.home()` as the single API surface. Tests mix `pytest`-style parametrize and `unittest.TestCase` inheritance consistently with the existing codebase.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
