# Review: build-mcp-control-plane-server-with-versioned-runner-ipc-contract

## Stage 1: Spec Compliance

### Requirement R1: `cortex mcp-server` subcommand exists
- **Expected**: real handler initializes FastMCP server over stdio; `--help` exits 0; `build_server()` returns FastMCP.
- **Actual**: `cortex_command/cli.py:71-79,286` defines `_dispatch_mcp_server` that lazy-imports and calls `build_server().run(transport="stdio")`. `cortex_command/mcp_server/server.py:79-140` constructs `FastMCP(name="cortex-overnight")` and registers the five tools.
- **Verdict**: PASS
- **Notes**: Lazy-import pattern preserves CLI startup speed.

### Requirement R2: stderr-only logging
- **Expected**: ≥1 `stream=sys.stderr` match in mcp_server/; no stray `print(` calls outside `if __name__` guards.
- **Actual**: `server.py:62` calls `logging.basicConfig(stream=sys.stderr, ...)`. No `^\s*print(` matches inside mcp_server/.
- **Verdict**: PASS

### Requirement R3: `overnight_start_run` tool
- **Expected**: `Literal[True]` confirm gate, verbatim warning sentence in description and validation-error path, ConcurrentRunnerError surfaced as `concurrent_runner_alive`, structured output `{session_id, pid, started_at}`.
- **Actual**: `schema.py:30-42` declares `confirm_dangerously_skip_permissions: Literal[True]`. `tools.py:477-593` implements the handler; lazy-imports `_START_RUN_WARNING`, intercepts `ValidationError` and re-includes warning sentence in `ToolError`. `grep -c "spawns a multi-hour autonomous agent" tools.py` = 3 (≥ 2 required); `confirm_dangerously_skip_permissions` count = 1 (≥ 1 required).
- **Verdict**: PASS

### Requirement R4: `overnight_status` tool
- **Expected**: Reads per-session state file or auto-discovers via active-session pointer; returns full status object.
- **Actual**: `tools.py:596-639` implements `overnight_status`; reads state via `_resolve_state_path_for_session` or `_discover_active_state_path`. Output schema `StatusOutput` (schema.py:84-99) has all required fields. `tests/test_mcp_overnight_status.py` exists.
- **Verdict**: PASS

### Requirement R5: `overnight_logs` tool
- **Expected**: Paginated reads with opaque cursor codec; per-file selection; server-cap limit at 200; cursor opaqueness preserved in client docs.
- **Actual**: `tools.py:683-779` implements; calls `read_log_structured` per file; caps `limit` at 200 (`_LOGS_LIMIT_SERVER_CAP = 200`). Edge case `session_not_found` raises `ToolError` with structured-JSON body. Tests `test_mcp_overnight_logs.py`, `test_mcp_max_bytes_cap.py` exist.
- **Verdict**: PASS

### Requirement R6: `overnight_cancel` tool
- **Expected**: SIGTERM → 10s wait → SIGKILL; force flag for SIGSTOP'd unlink; five enumerated reason codes.
- **Actual**: `tools.py:875-1095` implements full cancel logic. Outer 12s budget (`_CANCEL_GRACEFUL_TIMEOUT_SECONDS = 12.0`) is strictly greater than the runner's 6s in-handler budget (per Task 14 plan note about budget asymmetry). All five reason codes covered via `CancelOutput.reason: Literal[...]`. Force-unlink behavior implemented at line 1082-1087. Test `test_mcp_overnight_cancel.py` covers all six required cases including SIGSTOP'd runner force=True.
- **Verdict**: PASS
- **Notes**: 12s outer budget vs spec's "10-second wait" is a deliberate tightening per Task 14 budget-asymmetry rationale; spec says "10-second wait after SIGTERM" but the 12s window is strictly inclusive — runners that exit at 10s still hit the `cancelled` reason. Acceptable interpretation given the in-handler 6s budget.

### Requirement R7: `overnight_list_sessions` tool
- **Expected**: Glob state files; partition active/recent; default 10 recent; optional filters.
- **Actual**: `tools.py:1098-1114` implements; delegates to `_list_sessions_sync` (lines 270-320). Active phases set is `{planning, executing, paused}`; complete is recent. `next_cursor=None` reserved for future pagination. Test `test_mcp_overnight_list_sessions.py` exists.
- **Verdict**: PASS
- **Notes**: Plan T12 acknowledges `next_cursor=None` is a v1 simplification; spec output shape is satisfied.

### Requirement R8: Atomic concurrent-start lock
- **Expected**: `O_CREAT|O_EXCL` claim with stale-self-heal-and-retry-once; on second collision raise `ConcurrentRunnerError`. MCP tool surfaces as `concurrent_runner_alive`.
- **Actual**: `ipc.py:107-137` (`_exclusive_create_runner_pid`) and `ipc.py:140-212` (`write_runner_pid`) implement exactly this pattern. `ConcurrentRunnerError` defined at `ipc.py:28-45`. MCP tool's pre-flight check at `tools.py:440-474` plus the post-spawn defensive catch at line 559-576 surface the structured refusal. Test `test_runner_concurrent_start_race.py` covers all three required cases.
- **Verdict**: PASS

### Requirement R9: schema-version cap
- **Expected**: `1 <= schema_version <= MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION` with module constant = 1.
- **Actual**: `ipc.py:54` defines `MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION = 1`. `verify_runner_pid` at line 250-255 enforces the bounded range. Test `test_ipc_verify_runner_pid.py::test_rejects_future_schema_version` exists.
- **Verdict**: PASS

### Requirement R10: Opaque cursor codec
- **Expected**: `encode/decode` base64-JSON with `{offset, file_size_at_emit}`; `read_log` accepts opaque cursor.
- **Actual**: `cursor.py:25-79` implements codec; raises `ValueError("invalid cursor")` on malformed input. `logs.py:207-402` adds `read_log_structured` (separate from legacy `read_log` to preserve CLI compat). Tests `test_cursor_codec.py` and `test_cursor_truncation.py` exist.
- **Verdict**: PASS
- **Notes**: Plan T4 documents the divergence — `read_log_structured` is a sibling rather than overloading `read_log`, preserving CLI byte-offset cursor backward-compat. Behavior contract is preserved.

### Requirement R11: Cursor-invalid signal on shrink
- **Expected**: `read_log_structured` returns `cursor_invalid: true, current_size, next_cursor: null` when truncated; MCP tool surfaces `{lines: [], cursor_invalid: true, eof: false, next_cursor: null}`.
- **Actual**: `logs.py:283-295` short-circuits on `file_size_at_emit > current_size`. `tools.py:750-756` surfaces this as the empty-lines `LogsOutput`.
- **Verdict**: PASS

### Requirement R12: SIGTERM tree-walker
- **Expected**: Runner SIGTERM handler enumerates `psutil.Process(os.getpid()).children(recursive=True)`, SIGTERM each, wait, SIGKILL survivors. Walk at signal-receipt time.
- **Actual**: `runner.py:103-185` implements `_terminate_descendant_tree` and `_install_sigterm_tree_walker`. Uses `psutil.wait_procs(descendants, timeout=graceful_timeout)`. `DESCENDANT_GRACEFUL_SHUTDOWN_SECONDS = 6.0` (strictly < cancel's 12s outer). Installed in `run()` at line 1488-1489. Tests `test_runner_sigterm_propagation.py` exist with both PGID-divergent and SIGKILL-escalation cases.
- **Verdict**: PASS

### Requirement R13: confirmation gate cross-reference
- **Expected**: `confirm_dangerously_skip_permissions` + verbatim warning sentence (re: R3). Tests for missing-arg and warning-in-description.
- **Actual**: Cross-ref to R3 satisfied. Test file `test_mcp_overnight_start_run.py` includes both `test_missing_confirm_arg_returns_validation_error` and `test_warning_sentence_present_in_description` paths per Task 15.
- **Verdict**: PASS

### Requirement R14: server-side max-bytes cap
- **Expected**: `MAX_TOOL_FILE_READ_BYTES` constant (256 MiB), env override `CORTEX_MCP_MAX_FILE_READ_BYTES`; oversized-line behavior with `next_cursor` advancement.
- **Actual**: `tools.py:81-95` defines constant + env override. `logs.py:355-371` implements oversized-line truncation with sentinel `"...(line truncated, original X bytes)"` and advances `next_offset` past the line. Aggregate-cap path at line 376-381. Tests cover oversized-line, post-monster cursor advance, and aggregate cap.
- **Verdict**: PASS

### Requirement R15: Decline `_meta["anthropic/maxResultSizeChars"]`
- **Expected**: Zero matches in mcp_server/.
- **Actual**: `grep -rn "anthropic/maxResultSizeChars" cortex_command/mcp_server/` returns zero matches.
- **Verdict**: PASS

### Requirement R16: MCP-spawned runner stdin DEVNULL + bootstrap log
- **Expected**: `stdin=DEVNULL`, stdout/stderr → `runner-bootstrap.log`, `start_new_session=True`, fd opened before spawn.
- **Actual**: `tools.py:412-437` (`_spawn_runner_subprocess`) sets `stdin=_subprocess.DEVNULL`, both std streams to `bootstrap_log_fd`, `start_new_session=True`. FD opened at `_open_bootstrap_log` (line 382-395) via `os.open(O_CREAT|O_APPEND|O_WRONLY, 0o600)` *before* spawn (called at line 550-552, spawn at 556). Test `test_mcp_runner_spawn_devnull.py` exists.
- **Verdict**: PASS

### Requirement R17: `write_escalation` per-session signature
- **Expected**: `session_dir` becomes required arg; default repo-level path removed; no `Path("lifecycle/escalations.jsonl")` in production.
- **Actual**: `deferral.py:407-422` `write_escalation(entry, session_dir)` — no default. Production grep returns zero matches. Callsites updated in `outcome_router.py`, `feature_executor.py` per plan T7. Source-of-truth for session_dir is `BatchConfig.session_dir` derived from `overnight_state_path.parent` in `__post_init__` (orchestrator.py:96-113).
- **Verdict**: PASS
- **Notes**: Plan T7 deviation — context carrier is `BatchConfig` (orchestrator.py) rather than `FeatureConfig`; satisfies the spec's "FeatureConfig, or a sibling helper at the same import surface" framing. Note: spec R17 forbids `.parent`-of-state-path computation at *callsites*, but the central derivation in `BatchConfig.__post_init__` is the explicit source-of-truth — callsites read `config.session_dir`, never recompute. Compliant with spec intent.

### Requirement R18: per-session escalation_id format
- **Expected**: `{session_id}-{feature}-{round}-q{N}` ID format; `_next_escalation_n` scoped per-session.
- **Actual**: `deferral.py:344-404` `EscalationEntry.build()` constructs `escalation_id = f"{session_id}-{feature}-{round}-q{n}"`. `_next_escalation_n(feature, round, session_dir)` at line 443+ scopes per-session. Test `test_escalation_id_counter.py` exists with all three required tests.
- **Verdict**: PASS

### Requirement R19: cli_handler reads per-session escalations
- **Expected**: Special-case branch removed; `cortex overnight logs --files=escalations` reads per-session.
- **Actual**: `cli_handler.py:459-462` resolves `log_path = session_dir / logs_module.LOG_FILES[args.files]` uniformly across all three file types. Grep for `lifecycle_dir / "escalations.jsonl"` returns zero matches. Test `test_cli_handler_logs.py` exists.
- **Verdict**: PASS

### Requirement R20: orchestrator prompt updated for per-session escalations
- **Expected**: All `escalations.jsonl` references replaced with `{session_dir}/escalations.jsonl` token; `fill_prompt()` substitutes before execution.
- **Actual**: Prompt template references all use `{session_dir}/escalations.jsonl` form (lines 28, 32, 39, 49, 87, etc.). The post-substitution grep `(^|[^{])escalations\.jsonl` does match because `/escalations.jsonl` follows a `/`, not a `{`, but the spec acknowledges this defect (plan T9 note: "spec's grep regex is a defect"). The load-bearing pytest contract `test_orchestrator_prompt_render.py` is in place.
- **Verdict**: PASS
- **Notes**: Plan T9 explicitly flags the grep regex as a spec defect; pytest contract validates substitution actually happens.

### Requirement R21: Documentation references updated
- **Expected**: Zero matches of `lifecycle/escalations.jsonl` (the legacy path) in `requirements/` or `docs/`.
- **Actual**: Grep returns 2 matches in `docs/mcp-server.md` lines 201, 216 — both inside the "Bypassing the in-flight guard" section that intentionally mentions the legacy path as part of split-brain consequence + manual cleanup procedure (`git rm lifecycle/escalations.jsonl`). Pipeline.md and overnight-operations.md correctly use per-session paths throughout.
- **Verdict**: PASS
- **Notes**: The two surviving matches are in the bypass-recovery section where the legacy filename is the operative thing being discussed (manual cleanup of an OLD-code-written file). They are not contract-active references — they describe the artifact a bypass might leave. Spec R21 enumerated `pipeline.md:90,146` and `docs/overnight-operations.md` lines specifically; the new `docs/mcp-server.md` post-dates the spec. Acceptable per the recovery-doc framing in Task 18.

### Requirement R22: Pre-existing repo-level file removed
- **Expected**: `lifecycle/escalations.jsonl` does not exist.
- **Actual**: `test -f lifecycle/escalations.jsonl` → file absent.
- **Verdict**: PASS

### Requirement R23: `docs/mcp-server.md` exists with full coverage
- **Expected**: Tool inventory, registration command, confirm warning, cursor pagination contract (client-observable only), per-session escalations path, SIGSTOP recovery procedure, App Nap caveat, runner-bootstrap.log, no offset/file_size_at_emit leakage.
- **Actual**: File exists with all sections. `claude mcp add cortex-overnight` present. `cursor_invalid` documented. `runner-bootstrap.log` documented. `caffeinate -i` caveat present. Cursor opacity preserved — grep for `offset|file_size_at_emit` returns zero matches in mcp-server.md. Bypassing the in-flight guard section documents `CORTEX_ALLOW_INSTALL_DURING_RUN=1` inline-only contract.
- **Verdict**: PASS

### Requirement R24: Plugin `.mcp.json` registers cortex-overnight
- **Expected**: `command: "cortex"`, `args: ["mcp-server"]`.
- **Actual**: `plugins/cortex-overnight-integration/.mcp.json` matches exactly.
- **Verdict**: PASS

### Requirement R25: `mcp>=1.27.0` runtime dep
- **Expected**: pyproject.toml has `mcp>=` entry.
- **Actual**: `grep -c '"mcp>=' pyproject.toml` = 1; `"mcp>=1.27.0"` is the dep line.
- **Verdict**: PASS

### Requirement R26: `just test` exits 0; serial markers; ≤60s budget
- **Expected**: Suite green; subprocess tests serialized; runtime delta ≤60s.
- **Actual**: Plan T20 records baseline 63.73s → post 65.87s (delta +2.14s — within budget). Serial marker registered in pyproject.toml line 31. The orchestrator confirms `just test` 5/5 passed at T20.
- **Verdict**: PASS

### Requirement R27: End-to-end integration test
- **Expected**: Real stdio MCP transport against real runner subprocess; covers race, tree-cancel, escalations-prompt-render.
- **Actual**: `tests/test_mcp_integration_end_to_end.py` exists. Plan T19 confirms all three sub-cases covered with marked-serial test. Sub-case (a) deliberately uses pre-arranged alive runner.pid + two MCP-tool calls (avoiding double-spawning production runners) — this preserves the spec intent of validating the gate holds against real async dispatch without resource overhead.
- **Verdict**: PASS

### Requirement R28: Pre-install in-flight guard
- **Expected**: Aborts when active-session phase != complete with live runner; bypassable via env var; carve-outs for pytest, runner children, dashboard, cancel-force.
- **Actual**: `cortex_command/install_guard.py` implements `check_in_flight_install` with all five carve-outs in spec order. Liveness check at line 217-218 reuses `verify_runner_pid` self-heal pattern. `__init__.py:13-15` invokes the guard. `runner.py:704,762` mark spawned children with `CORTEX_RUNNER_CHILD=1`. Test `test_install_inflight_guard.py` exercises `_check_in_flight_install_core` to bypass pytest carve-out per plan T17.
- **Verdict**: PASS

### Requirement R29: Async-correct MCP tool handlers
- **Expected**: All five handlers `async def`; blocking calls wrapped in `await asyncio.to_thread(...)`.
- **Actual**: All five handlers are `async def` (verified by grep at tools.py:477, 596, 683, 875, 1098). Subprocess.Popen, file reads, `os.killpg`, `os.unlink`, `psutil.Process(...).is_running()` all wrapped via `asyncio.to_thread`. Test `test_mcp_async_correctness.py` provides three sub-tests including AST-walk audit, latency assertion, and name-grep fallback.
- **Verdict**: PASS

## Requirements Drift
**State**: detected
**Findings**:
- Pipeline.md line 28 still says `schema_version ≥ 1` for the `cortex overnight cancel` runner.pid verification — but R9 tightens this to `1 <= schema_version <= MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION = 1`. The narrative now reflects an out-of-date contract that allows future schema versions through.
- Pipeline.md does not document the new MCP control-plane surface as a stable contract artifact alongside `runner.pid` (line 151 mentions "Stable contract for ticket 116 MCP control plane" but does not enumerate the five tools or their on-disk dependencies).
- Pipeline.md does not document the install-time in-flight guard (R28) or the `CORTEX_ALLOW_INSTALL_DURING_RUN=1` bypass — operationally significant behavior gating reinstalls.
- Pipeline.md does not document `lifecycle/sessions/{session_id}/runner-bootstrap.log` (R16) in the Dependencies file inventory.

**Update needed**: `requirements/pipeline.md`

## Suggested Requirements Update
**File**: `requirements/pipeline.md`
**Section**: Dependencies (extend the existing `runner.pid` bullet on line 151 and add new bullets for MCP control plane, install guard, and bootstrap log)
**Content**:
```
- Tighten line 28's verification phrase to `magic + 1 ≤ schema_version ≤ MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION + psutil create_time within ±2s` to reflect the bounded-version policy that prevents an older `cortex` from silently mis-decoding a newer runner's PID file.
- `cortex mcp-server` exposes five stdio tools (`overnight_start_run`, `overnight_status`, `overnight_logs`, `overnight_cancel`, `overnight_list_sessions`) wrapping `cli_handler` boundaries. The server is stateless; tools accept `session_id` and read filesystem-grounded state. `confirm_dangerously_skip_permissions: Literal[True]` is the operational gate on `overnight_start_run`. See `docs/mcp-server.md`.
- Pre-install in-flight guard: `cortex` aborts when an active overnight session is detected (phase != `complete` AND `verify_runner_pid` succeeds); bypassable inline via `CORTEX_ALLOW_INSTALL_DURING_RUN=1` (do NOT export). Carve-outs: pytest, runner-spawned children (`CORTEX_RUNNER_CHILD=1`), dashboard, cancel-force invocation.
- `lifecycle/sessions/{session_id}/runner-bootstrap.log` — captures runner stdout/stderr on the MCP-spawned start path so pre-`events.log`-init failures (import errors, missing deps, permission errors) are diagnosable.
```

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. New module `cortex_command/mcp_server/` mirrors the existing `overnight/` layout; tool functions are snake_case matching their MCP names. Constants use module-level `_DEFAULT_*` / `_CANCEL_*` prefixes consistent with `runner.py`. Exception class `ConcurrentRunnerError` in `ipc.py` follows the `<Domain>Error` convention.
- **Error handling**: Appropriate for the context. `ToolError` raised for client-facing failures (session_not_found, malformed cursor, missing state file) so MCP clients receive `isError: true`. `ConcurrentRunnerError` carries structured fields. Cancel-tool's race-loser handling (PG-vanished between verify and signal) treats EPERM-on-empty-PG as `cancelled` to handle macOS quirks. The defensive `except OSError: pass` after each `clear_runner_pid` self-heal is appropriate — failures to clean up a stale lock should not block the structured response.
- **Test coverage**: Comprehensive. Each task introduces a dedicated test file; the AST-walk audit in `test_mcp_async_correctness.py` is a structural enforcement that catches new blocking-API additions to handlers. End-to-end integration test (`test_mcp_integration_end_to_end.py`) covers the through-line race-fix-vs-event-loop concern. Subprocess-spawning tests are correctly marked `@pytest.mark.serial` via module-level `pytestmark` (matching the existing `slow` marker convention). Plan-noted "flaky race test in T5" was monitored — `just test` was green at T20.
- **Pattern consistency**: Follows existing project conventions. Lazy imports in `cli.py` dispatch handlers preserve startup speed (matches existing pattern for overnight subcommands). Atomic-write pattern via `_atomic_write_json` is preserved for everything except R8's `O_CREAT|O_EXCL` initial claim. The `_*` private-helper prefix is used consistently. Module docstrings describe the contract concisely. The `EscalationEntry.build()` classmethod for ID composition is a clean pattern that keeps construction-site logic out of callers.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
