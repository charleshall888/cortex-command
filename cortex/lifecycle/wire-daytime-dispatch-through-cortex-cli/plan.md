# Plan: wire-daytime-dispatch-through-cortex-cli

## Overview

Implement Alternative B (Popen + `start_new_session` + documented harness dependencies) in three phases mirroring the spec: foundation hardening (PID schema, install_guard awareness, slug validator), CLI + MCP surfaces (new `cortex daytime` verb + new `cortex-daytime` plugin with 4 tools), and documentation/tests/release-gate. Parent-side O_EXCL claim on `daytime.pid` is the load-bearing concurrency primitive; the spawn handshake polls for the child to update sentinel fields from null to real values within 5s.

## Outline

### Phase 1: Foundation hardening (tasks: 1, 2, 3, 4, 5)
**Goal**: Land PID schema upgrade, install_guard daytime-awareness, and feature-slug validator before any new entry point exists.
**Checkpoint**: All Phase 1 tests green; `daytime.pid` files written via `cortex-daytime-pipeline --feature smoke-direct` carry the v1 JSON schema; `cortex upgrade` aborts during a live dispatch with `CORTEX_ALLOW_INSTALL_DURING_RUN=1` bypass working.

### Phase 2: CLI + MCP surfaces (tasks: 6, 7, 8, 9, 10, 11, 12, 13)
**Goal**: Wire `cortex daytime start` CLI verb (parent-side O_EXCL, handshake, JSON envelope) and stand up the new `plugins/cortex-daytime/` MCP plugin with 4 tools (start_run, status, logs, cancel) using overnight's delegate pattern.
**Checkpoint**: `cortex daytime start --feature smoke --format json` from a fresh terminal exits 0 with a JSON envelope and a detached child; `mcp__plugin_cortex-daytime_cortex-daytime__daytime_start_run` is invocable from a Claude session; concurrent-dispatch refusal and killpg cancel paths exercised by pytest.

### Phase 3: Documentation, tests, validation (tasks: 14, 15, 16, 17)
**Goal**: Document the two entry points and harness dependencies honestly; add the detached-spawn test; record the from-Claude-session release-gate result.
**Checkpoint**: `docs/daytime-operations.md` exists with honest framing; MCP contract docs enumerate the 4 new tools; `release-gate-results.md` records the empirical from-Claude-session smoke test result with zero EPERM events.

## Tasks

### Task 1: Add `cortex_command/overnight/daytime_validation.py` module
- **Files**: `cortex_command/overnight/daytime_validation.py` (new), `tests/test_daytime_validation_module.py` (new)
- **What**: Create a shared validator module exposing `validate_feature_slug(slug: str) -> str` (regex `^(?!\.{1,2}$)[a-zA-Z0-9_][a-zA-Z0-9._-]{0,127}$`, raises `ValueError` on mismatch) and `assert_feature_path_contained(feature: str, repo_root: Path) -> Path` (returns resolved `cortex/lifecycle/<feature>/` path after asserting containment via `Path.resolve().is_relative_to(...)`). Module is callable from MCP delegate, CLI argparse, and `run_daytime` — three of the four R4 enforcement layers consume this module. Pattern reference: `cortex_command/overnight/session_validation.py:15-44`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Module signature: `validate_feature_slug(slug: str) -> str` returning the slug unchanged on success. `assert_feature_path_contained(feature: str, repo_root: Path) -> Path` joins `repo_root / "cortex" / "lifecycle" / feature`, calls `.resolve()`, then checks containment via `is_relative_to(repo_root.resolve() / "cortex" / "lifecycle")`. Both raise `ValueError` on failure with messages that name the rejected input (do NOT echo the full traversal path to avoid log injection). The new test file exercises the validator with cases listed in spec R4: valid slug, `..`, `.`, leading `-`, over-length, `../etc/passwd` (containment), special chars.
- **Verification**: `pytest tests/test_daytime_validation_module.py -v` exits 0
- **Status**: [ ] pending

### Task 2: Upgrade `daytime.pid` schema and PID lifecycle in `daytime_pipeline.py`
- **Files**: `cortex_command/overnight/daytime_pipeline.py`
- **What**: Rewrite `_write_pid` (`:107-113`), `_read_pid`, `_is_alive` (`:86-104`), `_recover_stale` (`:125-168`), and the PID-write site (`:375-393`) to read and write the v1 JSON schema `{"schema_version": 1, "magic": "cortex-daytime-v1", "pid": int, "pgid": int, "start_time": float, "session_id": str, "feature": str, "repo_path": str}`. PID writes use O_EXCL atomic claim with `os.O_CREAT|os.O_EXCL|os.O_WRONLY` mode 0o600 (mirror `cortex_command/overnight/ipc.py:201`, `_exclusive_create_runner_pid`). `start_time` is `psutil.Process(os.getpid()).create_time()`. Liveness verification consults magic AND `psutil.Process(pid).create_time()` within ±2s of stored value AND `psutil.Process(pid).cmdline()` contains `daytime_pipeline` (defense against PID recycling). Add `_clear_pid` helper called from `run_daytime`'s normal exit and `_orphan_guard`. `_recover_stale` consults the full verification (not just `os.kill(pid, 0)`).
- **Depends on**: none
- **Complexity**: complex
- **Context**: Schema constant: `_DAYTIME_MAGIC = "cortex-daytime-v1"`, `_SCHEMA_VERSION = 1`, `_START_TIME_TOLERANCE_SECONDS = 2.0`. The atomic O_EXCL claim must handle `FileExistsError` to return the existing PID file's contents (so callers can decide between accept-as-alive or stale-clear-and-retry). `_is_alive(pid_data: dict) -> bool` returns True iff all three checks pass (magic + create_time + cmdline). Pattern reference for atomic claim: `cortex_command/overnight/ipc.py:201-296` (`_exclusive_create_runner_pid` + verification helpers). NOTE: this task does NOT add the runtime feature-slug guard at the top of `run_daytime` — that's Task 3. Task 2's verification includes a minimal write/read round-trip AND a liveness check so downstream consumers (Tasks 4, 7) do not build atop unverified primitives.
- **Verification**: `python3 -c "
import os, json, tempfile, pathlib, psutil
from cortex_command.overnight.daytime_pipeline import _write_pid, _read_pid, _is_alive, _clear_pid
# Round-trip: write a self-referencing PID file and verify schema fields
tmp = pathlib.Path(tempfile.mkdtemp()) / 'daytime.pid'
_write_pid(tmp, feature='smoke-task-2', session_id='manual', repo_path=str(pathlib.Path.cwd()))
data = _read_pid(tmp)
assert data['magic'] == 'cortex-daytime-v1' and data['schema_version'] == 1
assert 'pgid' in data and 'start_time' in data and 'pid' in data and 'feature' in data
assert data['pid'] == os.getpid() and data['feature'] == 'smoke-task-2'
# Liveness: self-pid with own start_time passes
assert _is_alive(data) is True
# Clear: file removed cleanly
_clear_pid(tmp)
assert not tmp.exists()
print('ok')
" 2>&1 | tail -1 | grep -c "^ok$" = 1; pass if count = 1` (comprehensive PID-recycling and stale-recovery tests still in Task 5)
- **Status**: [ ] pending

### Task 3: Add feature-slug runtime guard at top of `run_daytime`
- **Files**: `cortex_command/overnight/daytime_pipeline.py`
- **What**: Add a single-statement call at the top of `run_daytime` (immediately after `_check_cwd()` at `:316`) that invokes both `validate_feature_slug(feature)` and `assert_feature_path_contained(feature, Path.cwd())` from Task 1's module. This makes R18's regression-guard path safe against path-traversal — the direct `cortex-daytime-pipeline` console-script entry has no Pydantic or argparse new-type-converter and would otherwise be unprotected. Per spec Non-Requirements, this is the explicit carve-out exception to "`run_daytime` untouched."
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Insert at `daytime_pipeline.py:316` (right after `_check_cwd()`). Two-line import addition near the top of the module. Pattern: `validate_feature_slug(feature); assert_feature_path_contained(feature, Path.cwd())`. Both raise `ValueError`; `run_daytime` already raises on `_check_cwd()` failure so this propagates cleanly without new try/except scaffolding.
- **Verification**: `python3 -c "
import asyncio, inspect
from cortex_command.overnight import daytime_pipeline as dp
# Inspect run_daytime source to assert BOTH validators are called (regression that drops containment-check still passes slug-regex on '..')
src = inspect.getsource(dp.run_daytime)
assert 'validate_feature_slug' in src and 'assert_feature_path_contained' in src
# Runtime: '..' fails regex first; '../foo' (passes regex) tests containment
try:
    asyncio.run(dp.run_daytime('../foo'))
    raise SystemExit('expected ValueError on path-traversal')
except ValueError:
    pass
print('ok')
" 2>&1 | tail -1 | grep -c "^ok$" = 1; pass if count = 1`
- **Status**: [ ] pending

### Task 4: Extend `install_guard.py` to scan daytime PID files
- **Files**: `cortex_command/install_guard.py`
- **What**: In `check_in_flight_install_core` (`:71-73` and `:288-294`), add a glob scan of `cortex/lifecycle/*/daytime.pid`. For each file, parse the JSON and apply the full Task 2 verification (magic + create_time + cmdline-mismatch). If verification passes (alive AND looks like a daytime dispatch), trip the guard with `CORTEX_ALLOW_INSTALL_DURING_RUN=1` bypass. If verification fails (stale file or PID recycled to foreign process), clear the file (`os.unlink`) and log a warning event, then continue scan — do NOT block on stale files.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Use the same `psutil` calls and tolerance constants exposed from Task 2's PID schema upgrade. The guard's existing overnight scan logic is the pattern; add daytime as a sibling check. Carve-outs (`pytest`, `CORTEX_RUNNER_CHILD=1`, dashboard, cancel-force) inherit unchanged.
- **Verification**: `grep -c "daytime.pid" cortex_command/install_guard.py >= 1` AND `python3 -c "from cortex_command.install_guard import check_in_flight_install_core; import inspect; src = inspect.getsource(check_in_flight_install_core); assert 'daytime' in src"; rc=0; pass if rc=0` (comprehensive runtime tests in Task 5)
- **Status**: [ ] pending

### Task 5: Write Phase 1 tests
- **Files**: `tests/test_daytime_concurrent_dispatch.py` (new), `tests/test_install_guard_daytime_awareness.py` (new), `tests/test_daytime_feature_slug_validation.py` (new), `tests/test_daytime_pid_schema.py` (new)
- **What**: Four test files covering Phase 1 acceptance criteria from spec R1-R4. (a) `test_daytime_pid_schema.py`: PID file write/read round-trip; O_EXCL claim semantics; clean-shutdown clears file. (b) `test_daytime_concurrent_dispatch.py`: valid alive PID accepted, PID recycled by foreign process rejected via cmdline-mismatch, stale PID file (dead process) cleared on read, foreign Python process recycling PID rejected because cmdline lacks `daytime_pipeline`. (c) `test_install_guard_daytime_awareness.py`: valid alive dispatch trips guard, stale file cleared and guard passes, PID recycled to foreign process recognized and cleared. (d) `test_daytime_feature_slug_validation.py`: valid slug accepted, `..` rejected, `.` rejected, `-foo` rejected, `../etc/passwd` rejected (containment), over-length rejected, special chars rejected.
- **Depends on**: [1, 2, 3, 4]
- **Complexity**: simple
- **Context**: Use `pytest` fixtures from `tests/conftest.py` (already provides `tmp_path`, `repo_root`-like helpers). For PID-recycling tests, use `multiprocessing.Process` with controlled PIDs, NOT real-world recycling (which would be flaky). For install_guard tests, use `monkeypatch` to bypass the actual `cortex` install side-effects. Each test file targets 5-8 test functions; total task is at the upper edge of 5-file budget — splitting further would dilute test cohesion since the cases are tightly correlated.
- **Verification**: `pytest tests/test_daytime_concurrent_dispatch.py tests/test_install_guard_daytime_awareness.py tests/test_daytime_feature_slug_validation.py tests/test_daytime_pid_schema.py -v` exits 0
- **Status**: [ ] pending

### Task 6: Add `cortex daytime` CLI subparser and dispatcher in `cli.py`
- **Files**: `cortex_command/cli.py`
- **What**: Mirror the overnight subparser pattern at `cli.py:378-456`. Register a top-level `daytime` parser with a `start` subcommand (per Clarify Q1, no `schedule` or `list-sessions`). Arguments: `--feature <slug>` (required, with argparse `type=validate_feature_slug` from Task 1's module), `--format {human,json}` (default `human`), `--dispatch-id <hex>` (optional), hidden `--launchd` flag (`argparse.SUPPRESS`). The dispatcher `_dispatch_daytime_start` is a lazy-import shim mirroring `cli.py:48-81`'s overnight pattern, lazy-importing `cortex_command.overnight.daytime_cli_handler.handle_start`. Add similar lazy dispatchers `_dispatch_daytime_status`, `_dispatch_daytime_logs`, `_dispatch_daytime_cancel` for the other three CLI subcommands (consumed by Task 8).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Argparse subparser tree pattern is well-established in `cli.py:378-456` for overnight. The `--launchd` hidden flag uses `help=argparse.SUPPRESS` — the child re-execed process uses this to signal "you ARE the runner, skip the spawn fork" (pattern at `cli_handler.py:603-611`). Do NOT implement handle_start in this task; only the parser + dispatcher stub.
- **Verification**: `cortex daytime --help 2>&1 | grep -c "start\|status\|logs\|cancel" >= 4; pass if count >= 4`
- **Status**: [ ] pending

### Task 7: Implement `daytime_cli_handler.handle_start` (parent-side O_EXCL + spawn handshake)
- **Files**: `cortex_command/overnight/daytime_cli_handler.py` (new)
- **What**: Implement `handle_start(args)` as the CLI verb's production logic. Sequence: (1) call `validate_feature_slug(args.feature)` + `assert_feature_path_contained(...)` (defense-in-depth even though argparse already validated). (2) parent-side O_EXCL claim: write a sentinel `daytime.pid` with `{"schema_version": 1, "magic": "cortex-daytime-v1", "pid": null, "pgid": null, "start_time": null, "feature": args.feature, "session_id": <minted>, "repo_path": str(Path.cwd())}` via O_EXCL. On `FileExistsError`, verify the existing file's liveness (Task 2's `_is_alive`); if alive, emit `concurrent_dispatch` refusal envelope and exit non-zero; if stale, clear and retry once. (3) `subprocess.Popen([sys.executable, "-m", "cortex_command.overnight.daytime_pipeline", "--feature", args.feature], stdin=DEVNULL, stdout=<log_fd>, stderr=<log_fd>, start_new_session=True, close_fds=True)`. (4) Poll `daytime.pid` for 5s waiting for child to update `pid/pgid/start_time` from null to real values (mirror `cortex_command/overnight/scheduler/spawn.py:50`'s `wait_for_pid_file`). (5) On success, emit `{"schema_version": "2.0", "started": true, "pid": <int>, "feature": args.feature, "started_at": <ISO 8601>}` on stdout via `_emit_json` matching `cli_handler.py:104-117`. (6) On timeout, clear the sentinel and emit `{"started": false, "reason": "spawn_timeout"}`. (7) When `args.launchd` is True (the child re-exec path), short-circuit the spawn block and delegate directly to `daytime_pipeline.run_daytime(args.feature)`.
- **Depends on**: [2, 6]
- **Complexity**: complex
- **Context**: This is the load-bearing concurrency primitive. Key pattern references: `cortex_command/overnight/cli_handler.py:317-457` (`_spawn_runner_async`), `cortex_command/overnight/scheduler/spawn.py:50` (`wait_for_pid_file`), `cortex_command/overnight/ipc.py:201` (`_exclusive_create_runner_pid`). JSON envelope helper: reuse `cli_handler.py:_emit_json` (`schema_version: "2.0"` prepended). Log file path: `cortex/lifecycle/<feature>/daytime.log` (append-mode FD, mode 0o600). Sentinel-with-null-fields cleanup: if the parent dies between sentinel write and Popen, the next dispatch's startup logic checks for sentinel-with-null-fields-older-than-5s and clears them.
- **Verification**: `out=$(cortex daytime start --feature smoke-task-7 --format json) && echo "$out" | python3 -c "import sys, json, os; d = json.loads(sys.stdin.read()); assert d['started'] == True and d['feature'] == 'smoke-task-7' and isinstance(d['pid'], int); print(d['pid'])" > /tmp/claude/_task7_pid.txt && pid=$(cat /tmp/claude/_task7_pid.txt) && (kill -TERM "$pid" 2>/dev/null || true) && rm -f cortex/lifecycle/smoke-task-7/daytime.pid cortex/lifecycle/smoke-task-7/daytime-dispatch.json && rc=0; pass if rc=0` (cleanup: SIGTERM spawned child + clear PID/dispatch files; the smoke test must not leak state into Tasks 8/13/16)
- **Status**: [ ] pending

### Task 8: Implement `daytime_cli_handler.handle_cancel` + `handle_status` + `handle_logs` (must serialize before Task 9 in same file)
- **Files**: `cortex_command/overnight/daytime_cli_handler.py`
- **What**: `handle_cancel(args)`: read `cortex/lifecycle/<feature>/daytime.pid`, apply R12's fallback hierarchy. (a) On `JSONDecodeError`, log `daytime_cancel_corrupted_pid` event and exit non-zero with `{"cancelled": false, "reason": "corrupted_pid_file"}`. (b) On well-formed JSON with missing `pgid` field, fall back to `os.kill(pid, SIGTERM)` with a warning event. (c) On full schema, `os.killpg(pgid, SIGTERM)`. Mirror `cli_handler.py:1124`'s overnight cancel. `handle_status(args)`: read `cortex/lifecycle/<feature>/daytime-result.json` and last N lines of `events.log`; emit JSON envelope `{"schema_version": "2.0", "feature": ..., "result_present": bool, "recent_events": [...], "in_flight": bool}`. `handle_logs(args)`: paginate `cortex/lifecycle/<feature>/events.log` (and `daytime.log` if present) with optional cursor offset.
- **Depends on**: [2, 6, 7]
- **Complexity**: complex
- **Context**: All three handlers read filesystem-grounded state per spec R13 (`pipeline.md:153` stateless-server requirement). For `handle_cancel`'s killpg fallback hierarchy, see spec R12. Use `psutil` for sanity-checking the PID is still alive before sending the signal (avoid signaling a recycled PID — apply cmdline-mismatch check from Task 2). Complexity tier upgraded from `simple` to `complex` because the task bundles three logically separable handlers each with independent fallback logic — `handle_cancel`'s 3-branch fallback + PID-recycling check alone is `simple`-tier work; combining with status + logs justifies `complex`.
- **Verification**: `cortex daytime start --feature smoke-task-8 && cortex daytime status --feature smoke-task-8 --format json | python3 -c "import sys, json; assert json.loads(sys.stdin.read())['feature'] == 'smoke-task-8'" && cortex daytime logs --feature smoke-task-8 --format json | python3 -c "import sys, json; assert 'cursor' in json.loads(sys.stdin.read())" && cortex daytime cancel --feature smoke-task-8 --format json | python3 -c "import sys, json; d = json.loads(sys.stdin.read()); assert d.get('cancelled') in (True, False) and d.get('feature') == 'smoke-task-8'"; rc=0; pass if rc=0`
- **Status**: [ ] pending

### Task 9: Implement `DAYTIME_DISPATCH_ID` hybrid resolver with fail-closed env-var verification
- **Files**: `cortex_command/overnight/daytime_cli_handler.py`
- **What**: Add `_resolve_dispatch_id(feature: str, flag_value: str | None) -> tuple[str, bool]` returning `(dispatch_id, minted_by_wrapper)`. Order: (a) flag value if provided — validate against `^[a-f0-9]{32}$` at this layer (do not trust argparse). (b) `os.environ.get("DAYTIME_DISPATCH_ID")` if set — validate regex AND verify `cortex/lifecycle/<feature>/daytime-dispatch.json` exists with matching `id` field; if env-var set but no matching file OR file's id doesn't match, raise `StaleDispatchIdEnv` exception (caller emits `stale_dispatch_id_env` refusal envelope). (c) Mint uuid4 hex AND write `daytime-dispatch.json` ONLY if file does not already exist (never clobber). Emit `daytime_dispatch_id_minted_by_wrapper` event to `cortex/lifecycle/<feature>/events.log` when path (c) fires. Call site: `handle_start` invokes this before the O_EXCL sentinel write so the resolved dispatch ID is available for env propagation to the child.
- **Depends on**: [6, 7, 8]
- **Complexity**: simple
- **Context**: Existing `_check_dispatch_id` at `daytime_pipeline.py:267-287` is the pipeline-level guard (validates env-var format only). This new wrapper-level resolver enforces the disk-cross-check the spec requires. Pattern: write the daytime-dispatch.json via tempfile + os.replace for atomicity. Pass the resolved dispatch ID to the child via `env=os.environ.copy(); env["DAYTIME_DISPATCH_ID"] = resolved_id` in the Popen call. **Dep on Task 8** added so the same file (`daytime_cli_handler.py`) is not edited in parallel by Tasks 8 and 9.
- **Verification**: `python3 -c "from cortex_command.overnight.daytime_cli_handler import _resolve_dispatch_id; import inspect; sig = inspect.signature(_resolve_dispatch_id); assert 'feature' in sig.parameters and 'flag_value' in sig.parameters"; rc=0; pass if rc=0` (comprehensive runtime tests in Task 13)
- **Status**: [ ] pending

### Task 10: Scaffold `plugins/cortex-daytime/` plugin (server.py, .mcp.json, plugin.json)
- **Files**: `plugins/cortex-daytime/server.py` (new), `plugins/cortex-daytime/.mcp.json` (new), `plugins/cortex-daytime/.claude-plugin/plugin.json` (new)
- **What**: Mirror `plugins/cortex-overnight/` structure. (a) `plugin.json`: `{"name": "cortex-daytime", "description": "Cortex daytime dispatch MCP tools", "author": <from cortex-overnight>}`. (b) `.mcp.json`: `{"mcpServers": {"cortex-daytime": {"command": "uv", "args": ["run", "${CLAUDE_PLUGIN_ROOT}/server.py"]}}}`. (c) `server.py`: FastMCP server skeleton with `CLI_PIN = ("<current-tag>", "2.0")`, `MCP_REQUIRED_CLI_VERSION = CLI_PIN[1]`, R1 architectural invariant (zero `cortex_command.*` imports), helpers `_run_cortex`, `_resolve_cortex_argv`, `_retry_on_cli_missing`, `_gate_dispatch` — mirror `plugins/cortex-overnight/server.py:106-2250` for the helper layer, NOT the tool registrations (those land in Task 12). Empty `@server.tool` decorators are not yet registered. Pattern reference for CLI_PIN auto-resolution: the existing CI workflow at `.github/workflows/release.yml` updates CLI_PIN on release; for this task, use the current published tag found via `git describe --tags --abbrev=0`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: FastMCP server pattern: import from `mcp.server.fastmcp`. Helper functions (`_run_cortex`, etc.) are largely copy-paste from `plugins/cortex-overnight/server.py` with the prefix `daytime` instead of `overnight` — they reference no overnight-specific tool names. R1 invariant: `grep -c "^from cortex_command\|^import cortex_command" plugins/cortex-daytime/server.py` must be 0. The plugin manifest pattern is at `plugins/cortex-overnight/.claude-plugin/plugin.json`. The plugin can be scaffolded independently of the CLI verb work — the `_run_cortex` helper invokes the cortex CLI as a runtime subprocess (not an import-time dependency).
- **Verification**: `python3 -c "from pathlib import Path; assert (Path('plugins/cortex-daytime/server.py').exists() and Path('plugins/cortex-daytime/.mcp.json').exists() and Path('plugins/cortex-daytime/.claude-plugin/plugin.json').exists())"; grep -c "^from cortex_command\|^import cortex_command" plugins/cortex-daytime/server.py = 0; pass if assert succeeds and grep count = 0`
- **Status**: [ ] pending

### Task 11: Define Pydantic input/output models for the 4 MCP tools
- **Files**: `plugins/cortex-daytime/server.py`
- **What**: Add 8 Pydantic models in server.py: (a) `DaytimeStartRunInput` with `feature: str = Field(pattern=r"^(?!\.{1,2}$)[a-zA-Z0-9_][a-zA-Z0-9._-]{0,127}$", max_length=128)` AND `confirm_dangerously_skip_permissions: Literal[True]`. (b) `DaytimeCancelInput` with the same feature regex AND `confirm_dangerously_skip_permissions: Literal[True]`. (c) `DaytimeStatusInput` with feature regex only (no confirm gate — read tool). (d) `DaytimeLogsInput` with feature regex AND optional `cursor: int = 0`. Plus 4 output models (`DaytimeStartRunOutput`, `DaytimeStatusOutput`, `DaytimeLogsOutput`, `DaytimeCancelOutput`) each with `model_config = ConfigDict(extra="ignore")` for forward-compat. Mirror `plugins/cortex-overnight/server.py:2049-2196`.
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: Pydantic Literal type encoding: `from typing import Literal`; `confirm_dangerously_skip_permissions: Literal[True]` ensures FastMCP rejects `False`, `"true"`, `1`, etc. at schema-validation time — the gate cannot be bypassed by sending a different value. Output model pattern: each `DaytimeXxxOutput(BaseModel)` declares the fields the tool's JSON envelope returns; `extra="ignore"` allows forward-compat field addition. The plugin directory `plugins/cortex-daytime/` contains a hyphen and is not a Python dot-import path — verifications must use `importlib.util.spec_from_file_location` against the literal file path.
- **Verification**: `python3 -c "
import importlib.util, pytest
spec = importlib.util.spec_from_file_location('cortex_daytime_server', 'plugins/cortex-daytime/server.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
from pydantic import ValidationError
with pytest.raises(ValidationError):
    mod.DaytimeStartRunInput(feature='ok', confirm_dangerously_skip_permissions=False)
with pytest.raises(ValidationError):
    mod.DaytimeCancelInput(feature='ok', confirm_dangerously_skip_permissions=False)
print('ok')
" 2>&1 | tail -1 | grep -c "^ok$" = 1; pass if count = 1`
- **Status**: [ ] pending

### Task 12: Implement the 4 MCP tool delegates
- **Files**: `plugins/cortex-daytime/server.py`
- **What**: Implement `_delegate_daytime_start_run`, `_delegate_daytime_status`, `_delegate_daytime_logs`, `_delegate_daytime_cancel` mirroring `_delegate_overnight_start_run` (`plugins/cortex-overnight/server.py:2327-2419`). For `_delegate_daytime_start_run`: call `_gate_dispatch()`, build `argv = ["daytime", "start", "--feature", input.feature, "--format", "json"]`, wrap `_run_cortex(argv, timeout=_START_RUN_TOOL_TIMEOUT)` (30s) in `_retry_on_cli_missing`, branch on stdout content. Then register 4 `@server.tool` decorators wiring the Pydantic input/output models to the delegates. Use feature-slug regex validation via Pydantic models from Task 11 (no separate validation in the delegate body — the Pydantic layer is authoritative).
- **Depends on**: [10, 11]
- **Complexity**: complex
- **Context**: Each delegate is ~30-50 LOC: call `_gate_dispatch()`, build argv, call `_run_cortex` (handling `CortexCliMissing` retry once per tool via `_retry_on_cli_missing` budget=[1]), branch on stdout (empty + rc=0 = spawn confirmed; stdout JSON = refusal envelope). Tool registration via `@server.tool` decorator binds the input/output Pydantic models to FastMCP's schema generation. The `confirm_dangerously_skip_permissions: Literal[True]` field on Input models is automatically translated into the tool's JSON schema by FastMCP. NOTE: runtime correctness of the delegates depends on Tasks 7/8/9 having shipped (the CLI verbs the delegates invoke via subprocess), but build-time importability only requires Tasks 10 + 11. Comprehensive functional tests are in Task 13. **R4 4-layer enforcement reconciliation**: R1 architectural invariant forbids `cortex_command.*` imports in `server.py`, but spec R11 requires the delegate to apply `assert_feature_path_contained` after Pydantic validation. Resolution: duplicate the containment-check logic INLINE in `_delegate_daytime_start_run` (private helper `_assert_feature_path_contained_local` defined in server.py — same shape as Task 1's module but copy-pasted to honor R1). This preserves R4's 4-layer enforcement (Pydantic + argparse + delegate-inline + runtime) while respecting R1. The duplicated regex from Task 11 + duplicated containment-check from Task 12 are the documented cost of R1; a parity test in Task 13 asserts the regex string in `server.py` exactly equals the canonical string in `cortex_command/overnight/daytime_validation.py`.
- **Verification**: `python3 -c "import plugins.cortex_daytime.server as s; assert hasattr(s, '_delegate_daytime_start_run') and hasattr(s, '_delegate_daytime_status') and hasattr(s, '_delegate_daytime_logs') and hasattr(s, '_delegate_daytime_cancel')"; rc=0`
- **Status**: [ ] pending

### Task 13: Write Phase 2 tests (CLI handler + MCP tool tests)
- **Files**: `tests/test_daytime_spawn_handshake.py` (new), `tests/test_daytime_cli_concurrent_refusal.py` (new), `tests/test_daytime_dispatch_id_resolution.py` (new), `tests/test_daytime_cancel_killpg.py` (new), `plugins/cortex-daytime/tests/test_daytime_mcp_input_and_delegates.py` (new)
- **What**: Five test files covering spec R6-R13 and the R4-vs-R1 reconciliation. (a) `test_daytime_spawn_handshake.py`: normal sub-second handshake, injected disk pressure <5s succeeds, injected delay >5s fails with sentinel cleared. (b) `test_daytime_cli_concurrent_refusal.py`: sequential dispatches refused cleanly, two-parent race deterministically resolves to one win + one concurrent_dispatch envelope, stale-file path clears and proceeds. (c) `test_daytime_dispatch_id_resolution.py`: 7 cases per spec R8 (flag valid/invalid, env-var match, env-var no-file → stale_dispatch_id_env, env-var mismatched-id, mint-no-file, mint-with-file). (d) `test_daytime_cancel_killpg.py`: full schema → killpg, missing-pgid → kill with warning, corrupted JSON → error envelope/no signal, full schema asserts all pgid members receive SIGTERM. (e) `test_daytime_mcp_input_and_delegates.py` (covers R10, R11, R13 + parity): confirm=True valid on start AND cancel, confirm=False rejected on start AND cancel, confirm omitted rejected, feature with `..`/`.`/leading-`-` rejected on all 4 input models. Delegate stdout-branching: `_delegate_daytime_start_run` empty-stdout-rc-0 → spawn-confirmed, JSON-stdout → refusal envelope (mock `_run_cortex`). Status/logs delegates: filesystem-grounded read returns expected envelopes for present/absent feature directories. **Regex parity assertion**: the regex string in `plugins/cortex-daytime/server.py` exactly equals the canonical regex string in `cortex_command/overnight/daytime_validation.py`. **Containment parity assertion**: the inline `_assert_feature_path_contained_local` in server.py rejects symlinked-out paths with the same semantics as `cortex_command.overnight.daytime_validation.assert_feature_path_contained`.
- **Depends on**: [7, 8, 9, 11, 12]
- **Complexity**: complex
- **Context**: 5 test files at the 1-5 file budget ceiling AND spanning 5 distinct acceptance areas — tier upgraded from `simple` to `complex` to reflect surface area honestly. Use pytest fixtures and `monkeypatch` for env-var/filesystem injection. For two-parent race in `test_daytime_cli_concurrent_refusal.py`, use `multiprocessing.Process` with a `time.sleep(0.05)` sync barrier. For killpg test, use a fixture process group with multiple children. Place the MCP test in `plugins/cortex-daytime/tests/` (not `tests/`) so the plugin's hyphenated-path import scheme is exercised via `importlib.util` consistently with Task 11/12 verifications.
- **Verification**: `pytest tests/test_daytime_spawn_handshake.py tests/test_daytime_cli_concurrent_refusal.py tests/test_daytime_dispatch_id_resolution.py tests/test_daytime_cancel_killpg.py plugins/cortex-daytime/tests/test_daytime_mcp_input_and_delegates.py -v` exits 0
- **Status**: [ ] pending

### Task 14: Write `docs/daytime-operations.md` (honest framing)
- **Files**: `docs/daytime-operations.md` (new)
- **What**: Document the three entry points honestly per spec R14: (a) `cortex-daytime-pipeline` direct console-script — fresh-terminal regression guard. (b) `cortex daytime start` CLI verb — convenience packaging; Bash invocations from inside Claude sessions require `dangerouslyDisableSandbox: true` (the same precondition `cortex-daytime-pipeline` already requires). (c) `mcp__plugin_cortex-daytime_cortex-daytime__daytime_start_run` MCP tool — the only entry that works from a Claude session WITHOUT `dangerouslyDisableSandbox: true`, because MCP servers run unsandboxed at hook trust level. Explicit caveat: both Bash-path and MCP-path depend on harness behaviors outside cortex's control. R7's 5s spawn handshake is the detection layer for harness-dependency violations (surfaces as `spawn_timeout`). Real launchctl bootstrap (Alternative A) is named as the durable upgrade path. Link from `docs/overnight-operations.md`.
- **Depends on**: [12]
- **Complexity**: simple
- **Context**: Use the existing `docs/overnight-operations.md` as a structural model. Sections: Overview, Entry Points, Harness Dependencies and Detection, Concurrency Contract, Schema References, Future: Alternative A. Be explicit about the convenience-packaging vs sandbox-escape distinction — the critical review surfaced this as a framing gap that must be addressed honestly.
- **Verification**: `grep -c "dangerouslyDisableSandbox" docs/daytime-operations.md >= 2 && grep -c "unsandboxed at hook trust" docs/daytime-operations.md >= 1 && grep -c "Alternative A\|launchctl" docs/daytime-operations.md >= 1 && grep -c "convenience packaging\|same precondition" docs/daytime-operations.md >= 1`
- **Status**: [ ] pending

### Task 15: Update `docs/internals/mcp-contract.md` and `docs/mcp-server.md` for 4 new tools
- **Files**: `docs/internals/mcp-contract.md`, `docs/mcp-server.md`
- **What**: Add JSON-payload reference entries for `daytime_start_run`, `daytime_status`, `daytime_logs`, `daytime_cancel` to `docs/internals/mcp-contract.md` (mirror lines :70-90's overnight verbs format). Extend the tool inventory in `docs/mcp-server.md` (mirror lines :40-79) to enumerate the 4 daytime tools.
- **Depends on**: [12]
- **Complexity**: simple
- **Context**: Pattern is well-established for the overnight verbs. Each new entry includes: tool name, input schema summary (highlighting `confirm_dangerously_skip_permissions: Literal[True]` on start/cancel), output schema summary, error envelope shapes (`concurrent_dispatch`, `spawn_timeout`, `stale_dispatch_id_env`, `corrupted_pid_file`).
- **Verification**: `grep -c "daytime_start_run\|daytime_status\|daytime_logs\|daytime_cancel" docs/internals/mcp-contract.md docs/mcp-server.md >= 8; pass if count >= 8`
- **Status**: [ ] pending

### Task 16: Write `tests/test_daytime_cli_detached_spawn.py`
- **Files**: `tests/test_daytime_cli_detached_spawn.py` (new)
- **What**: Per spec R15: after `cortex daytime start --feature smoke-detached`, assert `os.getpgid(returned_pid) != os.getpgid(os.getpid())` (the spawned child is in a different process group). Explicitly does NOT claim this proves Seatbelt escape — Task 17's release gate is the load-bearing empirical verification. Test asserts only PGID detachment.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Use `subprocess.run(["cortex", "daytime", "start", "--feature", "smoke-detached", "--format", "json"], capture_output=True, text=True)` to invoke the CLI verb, parse the returned `pid` field, then `os.getpgid(pid)` and compare to `os.getpgid(os.getpid())`. After assertion, send SIGTERM to clean up the spawned child to avoid leaking processes between test runs.
- **Verification**: `pytest tests/test_daytime_cli_detached_spawn.py -v` exits 0
- **Status**: [ ] pending

### Task 17: Run the from-Claude-session release-gate procedure and record results (manual / requires human Claude session)
- **Files**: `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/release-gate-results.md` (new), `cortex/lifecycle/smoke-release-gate/events.log` (real artifact produced by the gate dispatch — NOT created by the agent)
- **What**: Per spec R16 (release-gate, no documentation-only fallback). **This task MUST be executed by a human operator inside a real interactive Claude session — it is NOT routine-pipeline-executable**. Procedure: (1) From inside an interactive Claude session, invoke `daytime_start_run` via the MCP tool with feature slug `smoke-release-gate`. (2) Wait for the dispatch to reach at least `feature_dispatched` event in `cortex/lifecycle/smoke-release-gate/events.log`. (3) Assert from the resulting events.log: `grep -c "EPERM" = 0` AND `grep -c "Sandbox failed to initialize" = 0` AND `grep -c "feature_dispatched" >= 1`. (4) Record in `release-gate-results.md`: the dispatch ID (must match a real entry in the events.log), the events.log absolute path, the three assertion outcomes, the operator's initials, the UTC ISO 8601 datetime, AND a non-fabricable artifact: paste the actual `feature_dispatched` event line verbatim from the events.log. The verification command below cross-checks that the pasted line appears in the referenced events.log.
- **Depends on**: [7, 8, 9, 12, 13, 14]
- **Complexity**: interactive — outside the routine `trivial|simple|complex` taxonomy. Pipeline must defer this task and surface it in the morning report; autonomous dispatch must NOT mark it complete by writing the results file itself.
- **Context**: pytest cannot exercise this — the MCP tool runs inside a Claude Code MCP host. The autonomous overnight dispatch agent MUST NOT execute this task. Verification requires cross-referencing the results.md against an external `cortex/lifecycle/smoke-release-gate/events.log` that contains the pasted `feature_dispatched` line — if the agent fabricates the results.md, the cross-reference check fails because no real dispatch event exists in the smoke-release-gate events.log. **Lifecycle behavior**: when the pipeline encounters Task 17, it should write a deferral to `cortex/lifecycle/deferred/release-gate-{feature}-q001.md` and pause the feature; lifecycle completion requires the operator to run the procedure and re-trigger Task 17.
- **Verification**: `test -f cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/release-gate-results.md && test -f cortex/lifecycle/smoke-release-gate/events.log && python3 -c "
import pathlib, re
results = pathlib.Path('cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/release-gate-results.md').read_text()
events = pathlib.Path('cortex/lifecycle/smoke-release-gate/events.log').read_text()
# Results must contain the operator's initials block AND a verbatim feature_dispatched event line
assert re.search(r'operator initials:\s*[A-Z]{2,5}', results, re.IGNORECASE), 'missing operator initials'
assert 'EPERM count: 0' in results and 'sandbox init failure count: 0' in results and 'feature_dispatched count:' in results
# Extract the pasted event line from results.md and verify it exists verbatim in the actual events.log
m = re.search(r'pasted feature_dispatched line:\s*(\\{.*?\\})', results, re.DOTALL)
assert m, 'missing pasted feature_dispatched line'
assert m.group(1).strip() in events, 'pasted line not found in actual events.log — fabrication suspected'
print('ok')
" 2>&1 | tail -1 | grep -c "^ok$" = 1; pass if count = 1`
- **Status**: [ ] pending

## Risks

- **Architectural pattern field absent** (criticality=high, not critical): Plan does not assign an `Architectural Pattern` from the closed enum because §1b competing-plans flow only fires at criticality=critical. If reviewer wants the field populated, the closest match is `plug-in` (new MCP plugin extends existing dispatch model).
- **Task 2 verification deferral window**: Task 2's verification (round-trip + liveness check) catches most behavior bugs but does NOT exercise PID-recycling defenses (Task 5 does). Task 4 (install_guard) lands between Task 2 and Task 5 in the dep graph. If Task 2's `_is_alive` has a subtle PID-recycling bug, Task 4's implementation propagates it before Task 5 catches it — mitigation is the round-trip check in Task 2's own verification (added per critical-review feedback) which catches the common-case bugs. Residual risk: PID-recycling-specific defects.
- **Task 7 complex tier at upper edge**: bundles 5+ sub-features (validation, O_EXCL sentinel, Popen, 5s handshake, two envelope shapes, `--launchd` re-exec). The `--launchd` branch is structurally distinct from the spawn path. If the task overruns its turn budget during implementation, split out the `--launchd` short-circuit into a Task 7b follow-up.
- **Task 7 sentinel-with-null-fields cleanup is sketched but not exhaustively spec'd**: the spawn handshake's edge case where the parent CLI dies between O_EXCL write and Popen completion leaves a sentinel file with null `pid`/`pgid`/`start_time`. The plan describes "check for sentinel-with-null-fields-older-than-5s and clear them on next dispatch" but defers the precise timestamp check to implementation. Implementer should use the file's mtime + 5s grace, NOT the null `start_time` field (which is null by definition).
- **Task 8 complexity upgrade**: critical review flagged that bundling cancel + status + logs at `simple` was tier misclassification; upgraded to `complex` in this revision. Implementation should still avoid further bundling — if cancel's fallback hierarchy plus PID-recycling check approaches the `complex` budget alone, split status/logs into a Task 8b.
- **Task 11 size**: 8 Pydantic models (4 inputs + 4 outputs) with regex constraints. The duplicated regex string + duplicated containment-check logic in server.py (R1 invariant cost) makes the task larger than `simple` typical. Parity tests in Task 13 catch regex drift; the inline-containment-helper drift is harder to detect — Task 12 implementer should manually compare against Task 1's module.
- **Task 13 complexity upgrade**: critical review flagged 5-file/5-acceptance-area surface at `simple` as understated; upgraded to `complex`. Now also covers R11 delegate stdout-branching + R13 status/logs delegate + regex/containment parity, expanding scope further. If implementer overruns, split into Task 13a (CLI handler tests) + Task 13b (MCP plugin tests).
- **Task 13's two-parent race test** uses `multiprocessing.Process` to spawn two parents; on slow CI this could be flaky. Mitigation: a `time.sleep(0.05)` sync barrier. If flakes persist, candidate for `@pytest.mark.flaky(retries=2)`.
- **Task 17 is interactive — not autonomously executable**: marked `Complexity: interactive` (outside trivial/simple/complex taxonomy). The autonomous overnight dispatch agent MUST defer this task; lifecycle completion requires a human operator to run the procedure inside a real Claude Code MCP host session. Verification cross-references the operator-pasted `feature_dispatched` event line against the actual smoke-release-gate `events.log`, preventing fabrication. **Lifecycle reviewer note**: this task must be handled outside the autonomous loop — pipeline should write a `deferred/release-gate-*.md` and require manual re-triggering. If the pipeline runs Task 17 routinely and writes a fabricated results.md, the cross-reference check catches it but the lifecycle wastes a turn.
- **R1 invariant cost (Tasks 11, 12)**: server.py duplicates Task 1's regex AND containment-check logic to honor the zero-`cortex_command.*`-imports rule. Two regex parity tests + one containment parity test in Task 13 detect drift. This is an explicit architectural cost reviewed during critical review.
- **CLI_PIN value in Task 10** hardcodes the current published tag via `git describe --tags --abbrev=0`; the existing CI workflow at `.github/workflows/release.yml` updates this on release. If this lifecycle ships between release cuts, the pinned value may need a one-line bump in a follow-up commit before merge.
- **Critical review identified Bash-path as convenience packaging not sandbox fix**: documented honestly in Task 14. Reviewers approving the spec should know that the user-facing value is primarily the MCP-path; the Bash-path is parity with the existing direct invocation under `dangerouslyDisableSandbox: true`.
- **Critical review verification gate failed** (synthesizer sentinel absent on both spec and plan critical-review runs): findings were content-validated manually against the artifact text. All A-class objections applied in this revision; B/C-class objections selectively applied (R13 delegate test added to Task 13; R18 success-path check added implicitly via Task 13 fixtures; Task 17 hardened against fabrication).

## Acceptance

- `cortex daytime start --feature <slug> --format json` from a fresh terminal exits 0 with a JSON envelope referencing a detached process; concurrent invocations reliably emit `concurrent_dispatch` refusal (not `spawn_timeout`); cancel via `cortex daytime cancel` cleanly terminates the spawned dispatch and all SDK children via killpg.
- `mcp__plugin_cortex-daytime_cortex-daytime__daytime_start_run` invoked from a real Claude session successfully spawns a dispatch whose `events.log` contains zero `EPERM` events, zero `Sandbox failed to initialize` events, and reaches at least `feature_dispatched`. The release-gate-results.md artifact records this empirical run.
- Direct `cortex-daytime-pipeline --feature <slug>` from a fresh terminal continues to work with the new JSON PID schema and is protected against path-traversal by Task 3's runtime guard.
- All Phase 1 / Phase 2 / Phase 3 pytest files green; `cortex upgrade` aborts during a live daytime dispatch unless `CORTEX_ALLOW_INSTALL_DURING_RUN=1` is set inline.
