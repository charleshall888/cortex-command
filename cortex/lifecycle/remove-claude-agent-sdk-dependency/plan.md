# Plan: remove-claude-agent-sdk-dependency

## Overview
A new leaf module, `cortex_command/claude_stream.py`, owns spawning the operator's `claude` (`-p --output-format stream-json --verbose`, prompt on stdin) and yielding parsed frames; `dispatch.py` and `discovery.py` consume it, and a frame-level test double replaces the `sys.modules` SDK stub. Phase 1 lands that behaviour change with the SDK still declared; Phase 2 deletes the dependency, folds the dashboard stack into the base install, and corrects every SDK-naming surface; Phase 3 adds the live-CLI and scheduled-resolve checks.

## Outline

### Phase 1: Spawn `claude` directly (tasks: 1, 2, 3, 4, 5, 6, 7, 8, 9)
**Goal**: both call sites run through one spawn-and-parse seam; no production module imports `claude_agent_sdk`.
**Checkpoint**: `grep -c claude_agent_sdk cortex_command/pipeline/dispatch.py cortex_command/discovery.py` is 0 for both, `just test` passes, and the live verification note records a real sandboxed dispatch through the seam.

### Phase 2: Delete the dependency and collapse the install (tasks: 10, 11, 12, 13, 14, 15, 16, 17, 18)
**Goal**: `claude-agent-sdk` is gone from metadata, tests and prose; the base install serves the dashboard; the sandbox gate watches the new spawn module.
**Checkpoint**: `grep -c claude-agent-sdk pyproject.toml uv.lock` is 0, the R21 `git grep` returns nothing, `uv run pytest -q` passes, and `uv run python3 -m cortex_command.sandbox_preflight` exits 0.

### Phase 3: Cover the drift the SDK used to absorb (tasks: 19, 20)
**Goal**: CLI-schema churn and published-install breakage each have a check that can see them.
**Checkpoint**: an opt-in `--run-slow` live test exists and passes on an authenticated machine; a scheduled workflow resolves the published install command.

## Tasks

### Task 1: Build the spawn-and-parse seam
- **Files**: `cortex_command/claude_stream.py` (new), `tests/test_claude_stream.py` (new), `tests/fixtures/fake_claude.py` (new, executable)
- **What**: A stdlib-only leaf module that builds the argv and environment, spawns `claude`, writes the prompt to stdin, and yields one parsed dict per stream-json line while draining stderr concurrently; plus the subprocess-level tests that pin R3–R8 and the spawn-failure half of R11.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Public surface (inter-task contract — Tasks 2, 3, 5, 19 bind to these names):
    - `build_env(overlay: Mapping[str, str]) -> dict[str, str]` — `{**os.environ}` minus `CLAUDECODE`, then `overlay` applied; an overlay value of `""` for `CLAUDECODE` must still result in the key being absent (R6; `dispatch.py:682-701` builds the overlay today).
    - `build_argv(cli_path: str, *, max_turns: int | None = None, max_budget_usd: float | None = None, permission_mode: str | None = None, allowed_tools: Sequence[str] | None = None, system_prompt: str | None = None, settings: str | None = None, effort: str | None = None) -> list[str]` — always `[cli_path, "-p", "--output-format", "stream-json", "--verbose"]`, then each flag only when its value is not None: `--max-turns N`, `--max-budget-usd X`, `--permission-mode M`, `--allowedTools a,b,c` (comma-joined), `--system-prompt S`, `--settings PATH`, `--effort E`. Never a positional prompt (R3). Never `--bare`, `--input-format`, or `--model` (ADR-0032).
    - `class ClaudeSpawnError(Exception)` carrying `.cli_path` and the underlying `OSError`; raised when the child cannot be started (`FileNotFoundError`, `PermissionError`, any `OSError` including `E2BIG`).
    - `class ClaudeRun` — async context manager `run_claude(argv, *, prompt: str, cwd: str | None, env: dict[str, str], on_stderr: Callable[[str], None] | None = None)`; `async for frame in run.frames()` yields dicts; after iteration completes, `run.exit_code: int` is set. The process ends the run, not any frame (R7): read stdout to EOF, then `await proc.wait()`.
  - Stream mechanics: `asyncio.create_subprocess_exec(..., stdin=PIPE, stdout=PIPE, stderr=PIPE, limit=<≥ 1 MiB>)` (R4; Python's 64 KiB default is the failure). Write the prompt from a separate task then close stdin, so a child that writes before it finishes reading cannot deadlock the writer. A stderr reader task calls `on_stderr` per decoded line, catching and swallowing exceptions from the callback (the SDK did the same); the reader must run for the life of the process (R5). An over-limit stdout line is discarded with a `logger.warning` and never raised.
  - Frame rules (R8): a line that is blank, not valid JSON, not a JSON object, or an object without a string `type` is skipped silently; every object with a `type` is yielded unchanged — the seam does not interpret types.
  - Cleanup: on an exception or cancellation inside the `async with`, terminate the child, wait up to 5 s, then kill — the ladder the SDK ran (`research.md` Adversarial 6). Do not pass `start_new_session` (keeps today's signal behaviour — Adversarial 7). No timeout is added (spec Non-Requirements).
  - Leaf rule: must not import `cortex_command.pipeline`, `overnight`, or `discovery`; same constraint `cli_resolver.py` documents in its module docstring.
  - Fake CLI: a Python script driven by env vars (e.g. `FAKE_CLAUDE_FRAMES` path to an NDJSON file to echo, `FAKE_CLAUDE_STDERR_BYTES`, `FAKE_CLAUDE_EXIT`, `FAKE_CLAUDE_ECHO_STDIN_TO` path) — tests point `cli_path` at it via `sys.executable`-prefixed argv or a shebang. Frames recorded in `cortex/lifecycle/sessions/*/orchestrator-round-*.stdout.json` show real field shapes.
  - Required tests: argv contains every flag in R2 order-independently and no positional prompt; a >128 KiB prompt arrives byte-identical on the child's stdin (R3); a single 256 KiB `assistant` line parses (R4); >128 KiB on both stderr and stdout completes (R5); env contains parent `PATH` and `HOME`, lacks `CLAUDECODE`, contains every overlay key (R6); a `system` frame after `result` is yielded and the run ends at exit (R7); unknown type, non-JSON line, and type-less object are skipped without raising (R8); a non-existent `cli_path` raises `ClaudeSpawnError` (R11 spawn half).
- **Verification**: `uv run pytest tests/test_claude_stream.py -q` — pass if all tests pass and the count collected is ≥ 8; `grep -c "claude_agent_sdk\|cortex_command.pipeline\|cortex_command.overnight" cortex_command/claude_stream.py` = 0.
- **Status**: [x] done (df88b8a2 2026-09-16T16:00:18-04:00)

### Task 2: Add the frame-level test double
- **Files**: `cortex_command/tests/_claude_double.py` (new)
- **What**: Frame builders and a fake `run_claude` that yields scripted frames, feeds scripted stderr lines to `on_stderr`, and sets a scripted `exit_code` — the in-process double that replaces patching `query` in unit tests.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Builders return plain dicts matching real frames: `assistant_frame(text: str | None = None, *, model: str = "claude-test", tool_uses: list[tuple[id, name, input]] = ())` → `{"type": "assistant", "message": {"model": ..., "content": [{"type": "text", "text": ...}, {"type": "tool_use", "id", "name", "input"}]}}`; `tool_result_frame(tool_use_id, is_error=False)` → `{"type": "user", "message": {"content": [{"type": "tool_result", ...}]}}`; `result_frame(*, is_error=False, subtype="success", num_turns=1, total_cost_usd=0.01, stop_reason="end_turn", duration_ms=10, terminal_reason=None, api_error_status=None, errors=None, result=None)`; `system_frame(subtype="init", **fields)`; `rate_limit_frame(**fields)` (copy the real `rate_limit_event` shape from a recorded session stdout). `fake_run_claude(frames, *, exit_code=0, stderr_lines=(), spawn_error: Exception | None = None, capture: dict | None = None)` returns a callable with `run_claude`'s signature that records `argv`, `prompt`, `cwd`, `env` into `capture`. Must not import `claude_agent_sdk`.
- **Verification**: `uv run python -c "from cortex_command.tests._claude_double import fake_run_claude, assistant_frame, result_frame, tool_result_frame, system_frame, rate_limit_frame"` exits 0; `grep -c claude_agent_sdk cortex_command/tests/_claude_double.py` = 0.
- **Status**: [x] done (6574186a 2026-09-16T16:02:46-04:00)

### Task 3: Move `dispatch_task` onto the seam and rebuild error classification
- **Files**: `cortex_command/pipeline/dispatch.py`
- **What**: Replace the `query()` loop and SDK types with `claude_stream.run_claude` over dict frames, and replace exception-type classification with a classifier over exit code, the last result frame, structured rate-limit fields, and the assistant-text-plus-stderr corpus — adding `api_unavailable` as a session-halting type.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Remove the `claude_agent_sdk` import block (`:25-41`), `_SDK_AVAILABLE`, and the `RuntimeError` at `:643-649`. Rewrite the module docstring (`:1-10`), the `ClaudeAgentOptions`/`AssistantMessage` wording in comments (`:159-162`, `:589-592`, `:607-611`, `:799-817`, `:852-856`), and the SDK-transport comment (`:708-711`).
  - **Sandbox gate**: `.githooks/pre-commit` runs `cortex_command.sandbox_preflight`, which fires on added lines in this file matching `sandbox`, `SandboxSettings`, `build_sandbox`, `write_settings_tempfile`, `_load_project_settings`. Keep added lines free of those words (reword comments; leave the `from cortex_command.overnight.sandbox_settings import …` block and `_settings_dict` construction untouched). If a firing line is unavoidable, record a fresh `preflight.md` per Task 18's procedure against current HEAD before committing; never bypass the hook.
  - Argv: `build_argv(cli, max_turns=tier["max_turns"], max_budget_usd=tier["max_budget_usd"], permission_mode="bypassPermissions", allowed_tools=_ALLOWED_TOOLS, system_prompt=system_prompt, settings=str(_settings_tempfile_path), effort=effort)`; `cwd=str(worktree_path)`; `env=build_env(_env)` — `_env` stays the overlay it is today.
  - Binary: `cli = resolve_claude_cli()`; if `None`, or `run_claude` raises `ClaudeSpawnError`, return `error_type="infrastructure_failure"` with an `error_detail` that names the path tried (or PATH plus `cli_resolver._SYSTEM_FALLBACKS` when none resolved) and says to install Claude Code (R11), log `dispatch_error`, and populate diagnostics.
  - Frame handling preserves every event today's loop emits, keyed on `frame["type"]`: `assistant` → `observed_model` from `message.model` (first non-empty, emits `dispatch_model_observed`), `text` blocks into `output_parts`, `dispatch_progress` preview, `tool_use` blocks → `tool_call` activity events; `user` → `tool_result` blocks → `tool_result` activity events; `result` → retain as last result (R7: keep the *last* one; emit `dispatch_truncation` / `dispatch_complete` / `turn_complete` from it once the stream ends, with the same fields as `:916-951`); `rate_limit_event` → retain its structured fields only. Every other frame type is ignored. Only assistant `text` enters `output_parts` (R9). Read fields with `.get` — never index an optional key.
  - Classifier (pure function, name it `classify_failure`; replaces `classify_error`; keep `_is_turn_limit_stop` — `cortex_command/pipeline/tests/test_turn_limit_classification.py` imports it). Inputs: `exit_code`, `result` (last result frame or None), `rate_limit` (last rate_limit frame or None), `corpus` (assistant text + captured stderr, lowercased), `max_turns`. Order:
    1. success = `exit_code == 0` and result present and `result.get("is_error")` is falsy → no error.
    2. `result.subtype == "error_max_budget_usd"` → `budget_exhausted`.
    3. `_is_turn_limit_stop(stop_reason, num_turns, max_turns)` or `subtype == "error_max_turns"` → `turn_limit_exhausted` (R13).
    4. `api_error_status == 429`, or the rate-limit frame reports a non-`allowed*` status, or a rate-limit pattern in the corpus → `api_rate_limit`.
    5. `terminal_reason == "api_error"`, or `api_error_status` in (401, 403) or ≥ 500 → `api_unavailable` (R12b).
    6. Keyword scans in today's order (`:521-530`) → `agent_timeout` / `agent_test_failure` / `agent_refusal` / `agent_confused`; effort hard-reject signature (`:538`) → `effort_unsupported`.
    7. Otherwise `task_failure` — including non-zero exit with no result frame (spec Edge Cases). `unknown` remains only for an unexpected exception inside cortex's own handling.
  - Callers of the removed `query` binding and `classify_error` are tests only — `cortex_command/pipeline/tests/test_dispatch.py`, `cortex_command/pipeline/tests/test_dispatch_instrumentation.py`, `tests/test_dispatch.py` — migrated by Tasks 6 and 8, which run in the next wave; the suite is red for those three files between this task and theirs.
  - `ERROR_RECOVERY` gains `"api_unavailable": "pause_session"`; the `DispatchResult.error_type` docstring lists it. `output_parts` keeps a bracketed marker naming the classified type on an `is_error` result (as `:914` does for budget today).
  - Diagnostics (R14): every failure return carries `DispatchDiagnostics(child_stderr, exit_code, cwd)` and logs `dispatch_error` with `num_turns`, `max_turns`, `stop_reason` — including the result-frame failure path that returns none today (`:961-968`).
  - Warn-ignore effort detection over `_stderr_lines` (`:976-987`) and `_on_stderr` redaction/caps (`:786-797`) are unchanged.
- **Verification**: `grep -c "claude_agent_sdk" cortex_command/pipeline/dispatch.py` = 0; `grep -cE "\bquery\(" cortex_command/pipeline/dispatch.py` = 0; `grep -c '"api_unavailable": *"pause_session"' cortex_command/pipeline/dispatch.py` = 1; `uv run python -c "import cortex_command.pipeline.dispatch as d; assert 'api_unavailable' in d.ERROR_RECOVERY and callable(d.classify_failure)"` exits 0. Behavioural coverage is Task 7.
- **Status**: [x] done (02ca8fe0 2026-09-16T16:52:27-04:00)

### Task 4: Make `api_unavailable` halt and name the session pause
- **Files**: `cortex_command/overnight/feature_executor.py`, `cortex_command/overnight/runner.py`, `cortex_command/overnight/report.py`, `cortex_command/pipeline/retry.py`
- **What**: Thread the new session-halting type through the halt chain so an API-wide fault stops the round loop, notifies, and renders a paused banner under its own name (R12).
- **Depends on**: none
- **Complexity**: moderate
- **Context**: The type string is `api_unavailable` (contract with Task 3). `feature_executor.py:76` `_SESSION_HALT_ERROR_TYPES` gains it (orchestrator.py imports that tuple at `:56` and needs no edit). `runner.py:3342` hardcodes `("budget_exhausted", "api_rate_limit")` — replace with the imported `_SESSION_HALT_ERROR_TYPES` so the lists cannot drift again; `runner.py:2704-2715` gains an `api_unavailable` notify branch ("Overnight session paused — the Claude API is unavailable (auth or provider error)…"). `report.py:598-609` gains a matching banner branch. `retry.py:401` comment names the three types. Check `runner.py` import graph before importing from `feature_executor` (lazy import inside the function if a cycle appears).
- **Verification**: `grep -c "api_unavailable" cortex_command/overnight/feature_executor.py cortex_command/overnight/runner.py cortex_command/overnight/report.py` each ≥ 1; `grep -c '("budget_exhausted", "api_rate_limit")' cortex_command/overnight/runner.py` = 0; `uv run pytest cortex_command/overnight/tests -q` passes. End-to-end halt coverage is Task 7.
- **Status**: [x] done (96f70afe 2026-09-16T15:59:11-04:00)

### Task 5: Move the gate-brief sub-dispatch onto the seam
- **Files**: `cortex_command/discovery.py`, `tests/test_discovery_gate_brief.py`
- **What**: `_run_brief_query` spawns through `run_claude` with `max_turns=3`, `permission_mode="bypassPermissions"`, the rubric as system prompt, and raises on a spawn failure, a missing binary, or a non-zero exit, so a dead CLI is reported as a dispatch failure rather than an empty brief (`research.md` Adversarial 20).
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Remove the import guard `:585-594`, `_BRIEF_SDK_AVAILABLE`, and the `RuntimeError` at `:642-646`; rewrite the docstring at `:621-640`. Env overlay `:649-656` passes through `build_env`. Collect `text` blocks from `assistant` frames only. `_cmd_generate_brief`'s `except RuntimeError` arms (`:772-775`, `:~800`) print "SDK not available" — reword to name the real cause (e.g. "claude unavailable"). Existing tests stub `_run_brief_query` wholesale (`tests/test_discovery_gate_brief.py:558`, `:676`) and stay valid; add one test using `cortex_command.tests._claude_double.fake_run_claude` patched onto `discovery` that asserts a non-zero exit raises and assistant text is joined on success.
- **Verification**: `grep -c "claude_agent_sdk" cortex_command/discovery.py` = 0; `grep -c "SDK not available" cortex_command/discovery.py` = 0; `uv run pytest tests/test_discovery_gate_brief.py -q` passes.
- **Status**: [x] done (4fc9f2b1 2026-09-16T16:05:44-04:00)

### Task 6: Port the existing pipeline dispatch tests to the frame double
- **Files**: `cortex_command/pipeline/tests/test_dispatch.py`
- **What**: Every test that builds SDK message objects or patches `_dispatch_module.query` drives `fake_run_claude` with dict frames instead; `TestClassifyError` targets `classify_failure`'s structured inputs.
- **Depends on**: [2, 3]
- **Complexity**: complex
- **Context**: 63 tests across `TestClassifyError` (`:61`), `TestErrorRecovery` (`:215`), `TestDispatchTaskSandboxSettings` (`:270`), `TestDispatchTaskBudgetExhausted` (`:514`), `TestDispatchTaskDiagnostics` (`:630`), `TestDispatchTaskStderrRedaction` (`:705`), `TestDispatchTaskValidation` (`:936`), `TestEffortWarnIgnore` (`:1292`); 13 `query` patch sites. Patch target is the name `dispatch.py` binds (`run_claude`). Leave `test_sdk_parser_extracts_stop_reason` (`:980`) and `test_effort_value_passthrough` (`:~1110`) and the module-level `_install_sdk_stub()` / `_sdk` reads (`:32-40`, `:261`) for Task 13 — they still pass while the SDK is installed. Budget-exhausted tests must now feed `subtype="error_max_budget_usd"`; a test that fed `is_error` with another subtype and expected `budget_exhausted` asserts the new classification instead. Do not weaken an assertion to make it pass — if behaviour changed by design, the new expectation must cite the spec requirement in the test docstring.
- **Verification**: `grep -c '"query"' cortex_command/pipeline/tests/test_dispatch.py` = 0; `grep -c 'classify_error' cortex_command/pipeline/tests/test_dispatch.py` = 0; `uv run pytest cortex_command/pipeline/tests/test_dispatch.py -q` passes.
- **Status**: [x] done (06c5528a 2026-09-16T16:09:52-04:00)

### Task 7: Pin the new classification, argv, and halt behaviour
- **Files**: `cortex_command/pipeline/tests/test_dispatch_spawn.py` (new)
- **What**: The dispatch-level tests for R2, R9, R10, R11 (message half), R12, R13, R14 — each driving `dispatch_task` through `fake_run_claude`, and for R10/R12 continuing into `retry.py` and the overnight halt chain.
- **Depends on**: [2, 3, 4]
- **Complexity**: complex
- **Context**:
  - R2: `capture["argv"]` contains `-p`, `--output-format stream-json`, `--verbose`, and `--max-turns`/`--max-budget-usd` with `TIER_CONFIG[complexity]` values, `--permission-mode bypassPermissions`, `--allowedTools Read,Write,Edit,Bash,Glob,Grep`, `--system-prompt`, `--settings <existing file>`, `--effort <resolve_effort value>`; the prompt is `capture["prompt"]` and appears nowhere in argv.
  - R9: a failing run whose `system_frame(subtype="init", cwd="/wt/fix-failing-tests")` precedes a non-zero exit classifies as anything but `agent_test_failure`; a `rate_limit_frame` with a rejected status plus a non-zero exit classifies `api_rate_limit` with no rate-limit words in any text.
  - R10: one test per `ERROR_RECOVERY` key reachable through a dispatch (`agent_timeout`, `agent_test_failure`, `agent_refusal`, `agent_confused`, `task_failure`, `infrastructure_failure`, `budget_exhausted`, `api_rate_limit`, `effort_unsupported`, `turn_limit_exhausted`, `api_unavailable`) — each drives `retry.retry_task` (`retry.py:178`; read `:178-444` for its signature and required fixtures; `cortex_command/pipeline/tests/test_retry.py` shows the fixture pattern) with the double patched, and asserts the action taken: a second dispatch attempt for retry keys, `paused=True` after one attempt for `pause_human`/`pause_session`, and `effort_override == "max"` on the second dispatch for `effort_unsupported` (`retry.py:321-340`). `unknown` is reached by making the double raise a non-spawn exception mid-stream. An `ERROR_RECOVERY[...]` dict lookup alone does not count.
  - R11: `CORTEX_CLAUDE_CLI_PATH=/nonexistent/claude` → `error_type == "infrastructure_failure"` and `error_detail` contains the path and "install Claude Code".
  - R12: (a) `result_frame(is_error=True, subtype="success", terminal_reason="api_error")` → not `budget_exhausted` and `in feature_executor._SESSION_HALT_ERROR_TYPES`; (b) `subtype="error_max_budget_usd"` → `budget_exhausted`; (c) end to end: follow the fixture pattern of an existing orchestrator halt test (grep `global_abort_signal` in `cortex_command/overnight/tests/`) to assert `state.paused_reason == "api_unavailable"` and that `runner.py`'s round-loop early-out fires (`:3340-3350`).
  - R13: `stop_reason="tool_use"`, `num_turns=max_turns + 1`, exit 1 → `turn_limit_exhausted`.
  - R14: result-frame failure and non-zero-exit failure both return non-None `diagnostics` with `exit_code` and `cwd` set.
  - Mutation check before marking done: revert one classifier branch (e.g. drop step 5) locally and confirm at least one test fails, then restore.
- **Verification**: `uv run pytest cortex_command/pipeline/tests/test_dispatch_spawn.py -q` passes with ≥ 18 tests collected; the mutation check above is recorded in the task's commit message body (which branch was removed and which test failed).
- **Status**: [x] done (7fa049f7 2026-09-16T16:08:46-04:00)

### Task 8: Port the remaining dispatch-coupled tests to the frame double
- **Files**: `cortex_command/pipeline/tests/test_dispatch_instrumentation.py`, `tests/test_dispatch.py`
- **What**: Replace SDK message construction and `query` patching with `fake_run_claude` frames in the instrumentation tests (18) and the root dispatch tests (9).
- **Depends on**: [2, 3]
- **Complexity**: moderate
- **Context**: `test_dispatch_instrumentation.py:20-33` imports stub types off `sys.modules["claude_agent_sdk"]`; `tests/test_dispatch.py` uses `ProcessError` for classification (`:83-95`) and SDK messages in `TestBudgetExhaustedDispatchPath` (`:45`), `TestStderrAccumulatorIntegration` (`:97`), `TestDispatchErrorCapturesStderrAndExitCode` (`:142`), `test_settings_tempfile_used` (`:295`), `test_dispatched_env_locks_tmpdir` (`:339`), `test_no_blob_injection` (`:362`). Settings/env tests now assert on `capture["argv"]` (`--settings <path>`) and `capture["env"]`. Leave `test_no_typed_sandbox_field_attempted` (`:408`), `test_sdk_settings_param_accepts_filepath` (`:439`), and the module-level `_install_sdk_stub()` / `_sdk` lines for Task 13.
- **Verification**: `uv run pytest cortex_command/pipeline/tests/test_dispatch_instrumentation.py tests/test_dispatch.py -q` passes; `grep -c '"query"' cortex_command/pipeline/tests/test_dispatch_instrumentation.py tests/test_dispatch.py` = 0 for both.
- **Status**: [x] done (72bbe174 2026-09-16T16:07:46-04:00)

### Task 9: Verify a real sandboxed dispatch through the seam
- **Files**: `cortex/lifecycle/remove-claude-agent-sdk-dependency/live-verification.md` (new)
- **What**: Run one real dispatch through `run_claude` + `dispatch.py`'s argv under a per-dispatch settings file that denies a write, and one tiny-budget run, and record the observed frames (R15); then run the full suite as the Phase 1 gate.
- **Depends on**: [3, 5, 6, 7, 8]
- **Complexity**: moderate
- **Context**: Build argv with `build_argv` and a settings file from `cortex_command.overnight.sandbox_settings.build_sandbox_settings_dict(deny_paths=[<target>], allow_paths=[<workdir>], …)` written to a temp file; prompt asks the agent to write to the denied target via Bash. Record: the `operation not permitted` tool-result frame, target byte-identical before/after, the final `result` frame (`is_error`, `subtype`, `num_turns`, `stop_reason`, `total_cost_usd`), `claude --version`, and the `message.model` value. Second run: `--max-budget-usd 0.01` — record the actual `subtype` and `is_error` so Task 3's step 2 is confirmed against the real CLI (`research.md` Open Question 3). If the subtype differs from `error_max_budget_usd`, fix `classify_failure` and Task 7's fixture before closing this task. Also record any `rate_limit_event` frame's exact field names and reconcile Task 2's `rate_limit_frame`. Cost ≈ $0.30–0.60.
- **Verification**: Interactive/session-dependent: needs an authenticated `claude` and a paid model call, so the implementer runs it and records the frames in `live-verification.md`; the automatable half is `just test` exiting 0 at the end of Phase 1.
- **Status**: [x] done (f8ed87ac 2026-09-16T16:17:36-04:00)

### Task 10: Remove the SDK and move the dashboard stack into the base install
- **Files**: `pyproject.toml`, `uv.lock`
- **What**: Drop `claude-agent-sdk`; move `fastapi<1.0`, `uvicorn<1.0`, `jinja2`, `markdown<4`, `starlette>=0.49.1,<2.0` into `dependencies`; keep `dashboard`, `overnight`, `all` declared as empty lists; rewrite the lean-base and extras comments (R16, R17, R23).
- **Depends on**: [9]
- **Complexity**: moderate
- **Context**: `pyproject.toml:9-50`. Keep the starlette cap rationale comment (it still applies); delete the SDK and "no-extra reinstall would silently strip" prose. `all = []` rather than a self-reference (`research.md` Adversarial 15: a self-referencing `all` emitted no `Requires-Dist`). Regenerate with `uv lock`. R23 is a regression guard: do not touch either `install_core.py` argv line.
- **Verification**: `grep -c "claude-agent-sdk" pyproject.toml uv.lock` = 0 for both; `uv build --wheel -o <scratch>` then, for each of `<wheel>`, `<wheel>[all]`, `<wheel>[dashboard]`, `<wheel>[overnight]` written to a requirements file, `uv pip compile <file> 2>&1` — pass if every output lists `fastapi`, `uvicorn`, `jinja2`, `markdown`, `starlette` and none contains `does not have an extra`; `uv run pytest tests/test_cortex_core_background_install.py tests/test_no_clone_install.py tests/test_mcp_auto_update_real_install.py -q` passes and `git diff HEAD -- plugins/cortex-core/install_core.py plugins/cortex-overnight/install_core.py | grep -c "cortex-command\[all\] @"` = 0.
- **Status**: [x] done (524342bc 2026-09-16T16:18:48-04:00)

### Task 11: Stop creating the macOS app at `cortex init` and delete dead extra guards
- **Files**: `cortex_command/init/handler.py`, `cortex_command/dashboard/macapp.py`, `cortex_command/cli.py`, `cortex_command/dashboard/tests/test_launcher.py`, `cortex_command/init/tests/test_init_creates_no_app.py` (new)
- **What**: Remove `ensure_app()` from init (the first `cortex dashboard` run already calls it at `cli.py:553`), remove the `uvicorn` `find_spec` guard in `ensure_app`, and remove the "optional 'dashboard' extra" import hint (R18).
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: `init/handler.py:397-408` — keep `projects.register_project(repo_root)`, drop the macapp import and call, reword the step comment. `macapp.py:146` guard and the module docstring line `:19` that justifies it; drop `importlib.util` if unused. `cli.py:489-499` — import `uvicorn` directly. `test_launcher.py:108` patches `find_spec`; delete that patch and any test asserting `None` when uvicorn is absent. Add `test_init_creates_no_app.py` (copy the tmp-repo handler fixture pattern from `cortex_command/init/tests/test_handler_ensure.py`) with a test that runs init with `HOME` pointed at a tmp dir on darwin (or with `macapp.app_path` monkeypatched to a tmp path) and asserts no bundle exists at `macapp.app_path()`.
- **Verification**: `grep -c "requires the optional 'dashboard' extra" cortex_command/cli.py` = 0; `grep -c 'find_spec("uvicorn")' cortex_command/dashboard/macapp.py` = 0; `grep -c "ensure_app" cortex_command/init/handler.py` = 0; `uv run pytest cortex_command/dashboard/tests/test_launcher.py cortex_command/init/tests -q` passes; temporarily restoring the init `ensure_app()` call makes the new test fail (mutation check).
- **Status**: [x] done (1f8e334e 2026-09-16T16:20:46-04:00)

### Task 12: Drop the SDK-bundled branch from the CLI resolver
- **Files**: `cortex_command/cli_resolver.py`, `cortex_command/pipeline/tests/test_cli_resolver.py`
- **What**: Delete `_find_bundled_cli_path` and collapse `_compute_best_cli` to "system path or None", keeping the env override, memoization, `_SYSTEM_FALLBACKS`, and version parsing (R19).
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: `cli_resolver.py:73-89` goes; `:126-160` collapses (the probe-flake non-memoize rule only existed to arbitrate against the bundle — memoize the found path). Rewrite the module docstring (`:1-26`) around "find the operator's claude"; `None` now means "no claude installed" and callers fail loudly (Task 3). `_probe_version` / `_parse_cli_version` stay only if a caller remains — grep before deleting. In the tests, delete the bundled comparisons (`:32-60`, `:108`), keep override/memoize/none/parse tests, and add one: `PATH` set to a tmp dir without `claude`, `HOME` set to a tmp dir containing an executable `.local/bin/claude` → resolves to that path.
- **Verification**: `grep -c "claude_agent_sdk\|bundled" cortex_command/cli_resolver.py` = 0; `uv run pytest cortex_command/pipeline/tests/test_cli_resolver.py cortex_command/overnight/tests/test_spawn_resolved_cli.py -q` passes and includes the `~/.local/bin/claude` fallback test.
- **Status**: [x] done (5e50c91a 2026-09-16T16:20:49-04:00)

### Task 13: Remove the SDK stub and the real-SDK tests
- **Files**: `cortex_command/tests/_stubs.py` (delete), `cortex_command/pipeline/tests/conftest.py`, `cortex_command/overnight/tests/conftest.py`, `cortex_command/overnight/tests/test_orchestrator.py`, `cortex_command/pipeline/tests/test_dispatch.py`, `cortex_command/pipeline/tests/test_dispatch_instrumentation.py`, `tests/test_dispatch.py`, `cortex_command/pipeline/tests/test_merge_sha_capture.py`, `cortex_command/pipeline/tests/test_recovery_paths.py`, `cortex_command/pipeline/tests/test_retry.py`, `cortex_command/pipeline/tests/test_review_dispatch.py`, `cortex_command/pipeline/tests/test_review_path_contract.py`
- **What**: Delete `_install_sdk_stub` and every call and import of it, the module-level `_sdk = sys.modules[...]` reads, and the tests that import the real package (R20).
- **Depends on**: [6, 8, 10] (write-serialization: test_dispatch.py)
- **Complexity**: moderate
- **Context**: `_stubs.py` holds nothing but the SDK stub — delete the file. Conftests: `pipeline/tests/conftest.py:1-11`, `overnight/tests/conftest.py:3,31-35` (keep its other stubs). `_install_sdk_stub()` call sites: `test_dispatch.py:32-34`, `test_dispatch_instrumentation.py:20-22`, `test_merge_sha_capture.py:31-32`, `test_recovery_paths.py:29-31`, `test_retry.py:31-34`, `test_review_dispatch.py:26-27`, `test_review_path_contract.py:25-26`, `tests/test_dispatch.py:21-22`. Delete tests: `test_sdk_parser_extracts_stop_reason` and `test_effort_value_passthrough` in `pipeline/tests/test_dispatch.py` (`~:980-1180`), `test_no_typed_sandbox_field_attempted` and `test_sdk_settings_param_accepts_filepath` in `tests/test_dispatch.py` (`:400-479`, with their section comments). `test_orchestrator.py:23` docstring names the SDK — reword. If a test file relied on the stub's eviction of `dispatch` from `sys.modules`, confirm it still imports cleanly.
- **Verification**: `git grep -c claude_agent_sdk -- 'cortex_command/**/tests/**' 'tests/**'` prints nothing; `test -e cortex_command/tests/_stubs.py` exits 1; `uv run pytest -q` passes.
- **Status**: [x] done (b4d3373c 2026-09-16T16:29:18-04:00)

### Task 14: Correct SDK prose in requirements, docs, and install guidance
- **Files**: `cortex/requirements/multi-agent.md`, `docs/internals/sdk.md`, `docs/internals/pipeline.md`, `docs/setup.md`, `docs/overnight-operations.md`, `install.sh`, `CLAUDE.md`
- **What**: Rewrite every statement that the SDK is the live spawn mechanism or that `[all]` supplies it (R21, docs half).
- **Depends on**: [9]
- **Complexity**: moderate
- **Context**: `multi-agent.md:15` (spawn mechanism → `claude -p --output-format stream-json --verbose`, prompt on stdin, via `cortex_command/claude_stream.py`) and `:82` (dependency → the operator's `claude` CLI). `docs/internals/sdk.md` is the policy-named owner of dispatch mechanics (`docs/policies.md:69`); keep the path, rewrite Path B (`:33-60`) around the seam and drop the claimed third call site in `conflict.py` (`:132` — `conflict.py` calls `dispatch_task`, not `query`). `docs/internals/pipeline.md:101,121` (settings passthrough is `--settings <path>`; the typed-field deviation paragraph becomes history — delete or reduce to one line). `docs/setup.md:73,78` (one install shape; extras are empty names kept for compatibility), `:202` (drop "Agent SDK"). `docs/overnight-operations.md:118,131,418,626,751,756` ("SDK level" / "SDK subprocesses" → the dispatched `claude` process). `install.sh:60-61`. `CLAUDE.md:5` — the `[all]` clause no longer pulls separate stacks; keep the install command. Docs policy: overnight docs link to `docs/internals/sdk.md` rather than restating. No test may pin this prose.
- **Verification**: `git grep -il "agent sdk" -- cortex/requirements docs install.sh CLAUDE.md` prints nothing; `git grep -n "claude_agent_sdk\|ClaudeAgentOptions" -- docs cortex/requirements` prints nothing.
- **Status**: [x] done (77f86e29 2026-09-16T16:20:45-04:00)

### Task 15: Correct SDK wording in code comments and operator strings
- **Files**: `plugins/cortex-core/install_core.py`, `plugins/cortex-overnight/install_core.py`, `cortex_command/pipeline/__init__.py`, `cortex_command/pipeline/review_dispatch.py`, `cortex_command/lifecycle/review_brief.py`, `cortex_command/pipeline/conflict.py`, `cortex_command/pipeline/tests/test_repair_agent.py`, `cortex_command/dashboard/tests/test_ticket_feed.py`
- **What**: Fix the remaining SDK mentions in comments and strings, and retarget the dashboard import guard at "imports with no `claude` on PATH" (R21, code half).
- **Depends on**: [9]
- **Complexity**: moderate
- **Context**: `install_core.py` rationale comments at `plugins/cortex-core/install_core.py:~366-370` and `plugins/cortex-overnight/install_core.py:528-532` — comment text only; the argv lines stay byte-identical (R23). `pipeline/__init__.py:4`. `review_dispatch.py:39` and `review_brief.py:22,156` — reword the "free of the Claude Agent SDK" rationale to say the duplication is historical and tracked separately; do not merge the parsers (spec Non-Requirements). `conflict.py:364,396,429` — "SDK exception" → "dispatch failure" wording (e.g. `"(dispatch failed during the first repair dispatch)"`); update `test_repair_agent.py:5,301` comments and any assertion on the old string. `test_ticket_feed.py:469-499` — replace the `claude_agent_sdk` import block with a subprocess probe run under `env={"PATH": <tmp dir with no claude>, "HOME": <tmp>}` that imports `cortex_command.dashboard.ticket_feed` and builds a snapshot; rename the test accordingly.
- **Verification**: `git grep -il "agent sdk" -- plugins/cortex-core/install_core.py plugins/cortex-overnight/install_core.py cortex_command/pipeline/__init__.py cortex_command/pipeline/review_dispatch.py cortex_command/lifecycle/review_brief.py cortex_command/dashboard/tests/test_ticket_feed.py` prints nothing; `git grep -n "SDK exception" -- cortex_command` prints nothing; `uv run pytest cortex_command/pipeline/tests/test_repair_agent.py cortex_command/dashboard/tests/test_ticket_feed.py -q` passes.
- **Status**: [x] done (43fb88ba 2026-09-16T16:53:14-04:00)

### Task 16: Record ADR-0038 and ADR-0039 and mark what they supersede
- **Files**: `cortex/adr/0038-cortex-spawns-the-operator-claude-directly.md` (new), `cortex/adr/0039-one-install-shape-with-the-dashboard-in-the-base.md` (new), `cortex/adr/0014-*.md`, `cortex/adr/0032-*.md`
- **What**: Write the two ADRs proposed in `spec.md` §Proposed ADR, and add a supersession/amendment note to ADR-0014 (bundled-vs-system half superseded; effort-by-outcome half kept) and ADR-0032 (model read from the `assistant` frame).
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: Follow `cortex/adr/README.md` for the three-criteria gate and frontmatter (`status: accepted`); header style of `cortex/adr/0037-*.md`. Re-check that 0038/0039 are still free (`ls cortex/adr`) before writing — renumber if another session took them. Context/Decision/Trade-off text comes from `spec.md:115-121`; do not restate the full spec.
- **Verification**: `ls cortex/adr/0038-*.md cortex/adr/0039-*.md` lists both; `grep -c "0038" cortex/adr/0014-*.md` ≥ 1; `grep -c "0038" cortex/adr/0032-*.md` ≥ 1.
- **Status**: [x] done (aebf8ab7 2026-09-16T16:19:07-04:00)

### Task 17: Point the CI fresh-resolve guard at the base install
- **Files**: `.github/workflows/validate.yml`
- **What**: The dashboard smoke step installs the package with no extras and still runs the route smoke test and the Starlette ≥ 1.0 assertion (R22).
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: `validate.yml:87-103`: `pip install ".[dashboard]" httpx packaging` → `pip install . httpx packaging`; rewrite the comment block so it says the step now proves the base install carries the web stack (the anti-revert guard named at `cortex/requirements/project.md:54`); remove the "Dashboard deps now live in the" sentence.
- **Verification**: `grep -c "Dashboard deps now live in the" .github/workflows/validate.yml` = 0; `grep -c 'pip install \. httpx packaging' .github/workflows/validate.yml` = 1; locally, `python -m venv <scratch>/v && <scratch>/v/bin/pip install . httpx packaging pytest && <scratch>/v/bin/pytest cortex_command/dashboard/tests/test_routes_smoke.py -q` passes.
- **Status**: [x] done (3b992f4a 2026-09-16T16:21:16-04:00)

### Task 18: Re-point the sandbox gate and record a fresh preflight
- **Files**: `cortex_command/sandbox_preflight.py`, `cortex/lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md`
- **What**: Replace the dead `pyproject.toml → claude-agent-sdk` and `dispatch.py → SandboxSettings` patterns with a `cortex_command/claude_stream.py` entry watching the settings passthrough, then re-run the kernel preflight against current HEAD and confirm the gate passes with Phase 2 staged (R24).
- **Depends on**: [10, 11, 12, 13, 14, 15, 16, 17]
- **Complexity**: moderate
- **Context**: `SANDBOX_WATCHED_FILES` (`sandbox_preflight.py:29-49`). New entry: `"cortex_command/claude_stream.py": (r"--settings", r"settings")`. Preflight procedure: the existing `preflight.md` body (`test_command`, EPERM excerpt, `target_unmodified`) is the template — rerun the same denying-settings probe, this time through `claude_stream.build_argv` + `run_claude`, and write `commit_hash` = `git rev-parse HEAD` at run time and `claude_version` = `claude --version`. Any commit landing after the run invalidates `commit_hash` (E102), so run it last, immediately before this task's commit, and redo it if a sibling session commits first.
- **Verification**: `grep -c "claude-agent-sdk\|SandboxSettings" cortex_command/sandbox_preflight.py` = 0; `grep -c "cortex_command/claude_stream.py" cortex_command/sandbox_preflight.py` = 1; with this task's changes staged, `uv run python3 -m cortex_command.sandbox_preflight; echo $?` prints `0`; the repo-wide R21 check `git grep -il "agent sdk" -- . ':!cortex/lifecycle' ':!cortex/backlog' ':!cortex/adr' ':!cortex/research' ':!CHANGELOG.md'` prints nothing; `uv run pytest -q` passes. The probe run itself is Interactive/session-dependent: it needs an authenticated `claude` and a paid call.
- **Status**: [x] done (657cb824 2026-09-16T16:30:40-04:00)

### Task 19: Add an opt-in live test of the real CLI's frames
- **Files**: `tests/test_claude_stream_live.py` (new)
- **What**: A `@pytest.mark.slow` test drives one real dispatch-shaped run through `run_claude` and asserts the keys cortex reads (R25).
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: Marker and `--run-slow` wiring already exist (`pyproject.toml:158`, `tests/conftest.py:13-19`). Use `build_argv` with `max_turns=2`, `permission_mode="bypassPermissions"`, `effort="low"`, a tiny prompt. Assert: at least one frame with `type == "assistant"` whose `message.content` is a list and `message.model` is a non-empty string; exactly one last `type == "result"` frame carrying `stop_reason`, `num_turns`, `total_cost_usd`, `is_error`; `run.exit_code == 0`. Skip (not fail) when `resolve_claude_cli()` is None.
- **Verification**: `uv run pytest tests/test_claude_stream_live.py -q -rs` reports 1 skipped with reason containing `--run-slow`; `uv run pytest tests/test_claude_stream_live.py --run-slow -q` passes on an authenticated machine (Interactive/session-dependent: paid model call).
- **Status**: [x] done (579542e4 2026-09-16T16:19:27-04:00)

### Task 20: Add a scheduled check that the published install still resolves
- **Files**: `.github/workflows/scheduled-resolve.yml` (new), `cortex/requirements/project.md`
- **What**: A daily scheduled workflow resolves `cortex-command[all] @ git+<repo>@<latest vX.Y.Z tag>` with `uv pip compile` and fails loudly when it cannot; the gate is registered in the enforcement-gate list with its generic named failure (R26).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Latest tag via `git ls-remote --tags` sorted by version, highest `vX.Y.Z` (the method `CLAUDE.md:5` describes). Triggers: `schedule:` (daily cron) plus `workflow_dispatch:`. Scope statement in the workflow comment: resolution only — no wheel build, no console scripts. Registry: add a "scheduled resolve" survivor to `cortex/requirements/project.md:41`'s gate list, evidence = the 2026-09-16 yank that broke every `v5.2.0` install, failure = any pinned or bounded dependency of a published tag stops resolving.
- **Verification**: `grep -c "schedule:" .github/workflows/scheduled-resolve.yml` ≥ 1; `grep -c "uv pip compile" .github/workflows/scheduled-resolve.yml` ≥ 1; `grep -c "scheduled resolve" cortex/requirements/project.md` ≥ 1; locally `echo 'cortex-command[all] @ git+https://github.com/charleshall888/cortex-command.git@<latest tag>' > <scratch>/r.txt && uv pip compile <scratch>/r.txt` exits 0, and the same against `@v5.2.0` exits non-zero.
- **Status**: [x] done (8a98e4c0 2026-09-16T15:59:53-04:00)

## Risks
- **`api_unavailable` is a new error-type name**, not a reuse of `api_rate_limit`. It adds a notify branch and a report banner. Folding auth and provider faults into `api_rate_limit` would be smaller but would name the wrong cause, which R12 forbids.
- **The classifier's API-fault rules rest on fields seen once live** (`terminal_reason: "api_error"`) plus documented but unobserved ones (`api_error_status`, `error_max_budget_usd`). Task 9 confirms the budget subtype against the real CLI before Phase 1 closes. Any other drift surfaces only through the Task 19 live test.
- **Orphan cleanup is ported, not dropped.** Task 1 keeps the SDK's terminate → wait → kill ladder on exception or cancellation. It does not add the SDK's `atexit` reaper, because the runner's SIGTERM path re-raises before `atexit` runs (`research.md` Adversarial 6). It also does not add `start_new_session`.
- **The sandbox pre-commit gate can block Phase 1 commits** that touch `dispatch.py` with sandbox-named lines. Task 3 avoids those lines. The fallback is a paid preflight re-run that is only valid until the next commit. Concurrent sessions committing to `main` can make that re-run stale again.
- **Phase 2 changes install shape for everyone at once.** A bare install now pulls about 17 MB of web stack (ADR-0039 trade-off). The extras stay as empty names, so every published install command keeps resolving.
- **Test migration is the largest body of work** (Tasks 6, 8, 13 touch about 90 tests). The in-process double was chosen over a fake binary for those tests to limit churn. The fake binary covers only the stream mechanics in Task 1.

## Acceptance
With the phases landed, `uv tool install "cortex-command @ git+…@<new tag>"` (no extras) resolves without `claude-agent-sdk` and `cortex dashboard` serves.
An overnight or `cortex-batch-runner` dispatch runs through `claude -p --output-format stream-json` with its per-dispatch `--settings`, and `live-verification.md` records a kernel-denied write.
A forced `is_error` API fault pauses the session as `api_unavailable`, and `uv run pytest -q` passes.
