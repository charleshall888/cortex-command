# Plan: apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites

## Overview
Centralize all sandbox-settings construction, tempfile lifecycle, deny-set/allow-set composition, and Linux warning emission inside a single new `cortex_command/overnight/sandbox_settings.py` module that every spawn site imports as a shared library. Both the orchestrator spawn (`runner.py`) and per-feature dispatch (`pipeline/dispatch.py`) use the **same `--settings <tempfile>` JSON-shape mechanism** — the SDK's `ClaudeAgentOptions(settings=...)` parameter accepts a JSON-string-or-filepath and converts to `claude --settings <value>` on the CLI argv (verified at `claude_agent_sdk/_internal/transport/subprocess_cli.py:111-163`). The feature-executor cross-repo fix is a parallel correction.

**Architectural Pattern**: layered — a single `sandbox_settings` library layer sits beneath both spawn sites and exposes builder functions producing the documented `sandbox.filesystem.{denyWrite,allowWrite}` JSON shape. The dispatch path does NOT migrate to a typed `SandboxSettings`/`SandboxFilesystemSettings` SDK field — that path was specced against shapes that do not exist in the pinned SDK (verified empirically against `claude_agent_sdk@0.1.46` — `__init__.py` exports `SandboxSettings`, `SandboxNetworkConfig`, `SandboxIgnoreViolations` only; `SandboxSettings` TypedDict has no `filesystem` key). See Veto Surface for the spec deviation.

## Tasks

### Task 1: Create `sandbox_settings.py` module skeleton with builder signatures and constants
- **Files**: `cortex_command/overnight/sandbox_settings.py` (new)
- **What**: Establish the layer's public surface — builder function signatures, named constants, and the env-var contract — before any caller wires in. The dispatch and orchestrator paths both consume this layer's outputs as JSON dicts that are then written to per-spawn tempfiles.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Module exposes:
    - `SOFT_FAIL_ENV_VAR = "CORTEX_SANDBOX_SOFT_FAIL"`
    - `SETTINGS_TEMPFILE_PREFIX = "cortex-sandbox-"`
    - `SETTINGS_TEMPFILE_SUFFIX = ".json"`
    - `SETTINGS_DIRNAME = "sandbox-settings"`
    - `GIT_DENY_SUFFIXES = (".git/refs/heads/main", ".git/refs/heads/master", ".git/HEAD", ".git/packed-refs")`
    - `OUT_OF_WORKTREE_ALLOW_WRITERS: tuple[str, ...]` containing the six entries from spec Req 10 (`~/.cache/uv/`, `$TMPDIR/`, `~/.claude/sessions/`, `~/.cache/cortex/`, `~/.cache/cortex-command/`, `~/.local/share/overnight-sessions/`)
    - `LINUX_WARNING = "WARNING: cortex sandbox enforcement is macOS-Seatbelt-only; Linux/bwrap behavior is undefined per parent epic #162. Sandbox configuration may not enforce as documented."`
  - Builder signatures:
    - `build_orchestrator_deny_paths(home_repo: Path, integration_worktrees: dict[str, str]) -> list[str]`
    - `build_dispatch_allow_paths(worktree_path: Path, integration_base_path: Path | None) -> list[str]`
    - `build_sandbox_settings_dict(deny_paths: list[str], allow_paths: list[str], soft_fail: bool) -> dict` (single canonical builder used by both orchestrator and dispatch; emits the spec Req 2 / Req 5 documented shape)
    - `read_soft_fail_env() -> bool` (reads `os.environ` at call time per Req 4)
    - `write_settings_tempfile(session_dir: Path, settings: dict) -> Path` (uses `cortex_command.common.atomic_write`, mode 0o600, prefix/suffix/dir per spec Req 1)
    - `cleanup_stale_tempfiles(session_dir: Path, runner_start_ts: float) -> None`
    - `register_atexit_cleanup(tempfile_path: Path) -> Callable[[], None]` — **returns the registered callback** so tests can invoke it directly without calling `atexit._run_exitfuncs()` (which would drain all process-level handlers).
    - `reset_linux_warning_latch() -> None` — test-only helper that resets the module-level Linux-warning flag; lets `test_linux_warning_emitted` and `test_macos_no_warning` run in any order.
    - `emit_linux_warning_if_needed(stream: TextIO = sys.stderr) -> None`
    - `record_soft_fail_event(session_dir: Path) -> None` — writes `sandbox_soft_fail_active` to `<session_dir>/events.log` under `fcntl.LOCK_EX` to prevent the read-then-conditional-write TOCTOU race under concurrent dispatch.
- **Verification**: `python -c "from cortex_command.overnight import sandbox_settings; assert all(hasattr(sandbox_settings, n) for n in ['build_orchestrator_deny_paths','build_dispatch_allow_paths','build_sandbox_settings_dict','read_soft_fail_env','write_settings_tempfile','cleanup_stale_tempfiles','register_atexit_cleanup','reset_linux_warning_latch','emit_linux_warning_if_needed','record_soft_fail_event','SOFT_FAIL_ENV_VAR','GIT_DENY_SUFFIXES','OUT_OF_WORKTREE_ALLOW_WRITERS','LINUX_WARNING'])"` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 2: Implement deny-path / allow-path builders + JSON-shape builder + soft-fail reader
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implement the deny-set construction (per-repo enumeration over `home_repo` + `integration_worktrees.keys()` joined with each `GIT_DENY_SUFFIXES`), the allow-list construction (worktree path + integration_base_path + the six `OUT_OF_WORKTREE_ALLOW_WRITERS` with `os.path.expanduser` and `$TMPDIR` resolution), the JSON-shape dict builder, and the `os.environ`-reading `read_soft_fail_env`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - `build_sandbox_settings_dict(deny_paths, allow_paths, soft_fail)` returns a dict shaped per spec Req 2 + Req 5 documented schema:
    - `sandbox.enabled: True`
    - `sandbox.failIfUnavailable: not soft_fail`
    - `sandbox.allowUnsandboxedCommands: False`
    - `sandbox.enableWeakerNestedSandbox: False`
    - `sandbox.enableWeakerNetworkIsolation: False`
    - `sandbox.filesystem.denyWrite: deny_paths`
    - `sandbox.filesystem.allowWrite: allow_paths`
  - This dict is the canonical shape consumed by both orchestrator (Task 4) and dispatch (Task 5) paths via `--settings <tempfile>`.
  - `build_orchestrator_deny_paths` iterates over distinct repo absolute paths (`[home_repo, *integration_worktrees.keys()]` — keys are repo absolute paths per `state.py:228-230`, values are worktree paths).
  - `build_dispatch_allow_paths` returns `[str(worktree_path), str(worktree_path.resolve()), ...integration_base_path entries..., *expanded_out_of_worktree_writers]`.
- **Verification** (deferred-pytest pattern — full pytest assertions live in Task 9): `grep -cE "refs/heads/main|refs/heads/master|\\.git/HEAD|packed-refs" cortex_command/overnight/sandbox_settings.py` returns ≥ 4 AND `grep -c "filesystem.*denyWrite\|filesystem.*allowWrite" cortex_command/overnight/sandbox_settings.py` returns ≥ 2 AND `grep -c "CORTEX_SANDBOX_SOFT_FAIL" cortex_command/overnight/sandbox_settings.py` returns ≥ 1 — pass if all three counts hold.
- **Status**: [ ] pending

### Task 3: Implement tempfile lifecycle, atexit registration, startup-scan, Linux warning, and locked soft-fail event emission
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implement `write_settings_tempfile`, `register_atexit_cleanup` (returns the callback), `cleanup_stale_tempfiles`, `emit_linux_warning_if_needed` + `reset_linux_warning_latch`, and `record_soft_fail_event` with `fcntl.LOCK_EX` around the read-then-conditional-write.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Tempfile path: `tempfile.mkstemp(prefix="cortex-sandbox-", suffix=".json", dir=<session_dir>/sandbox-settings/)`. Mode chmod to 0o600 after creation.
  - `atomic_write` pattern at `cortex_command/common.py:498-522`.
  - `register_atexit_cleanup`: registers an unlink callback via `atexit.register` AND returns the callback so tests can invoke it directly. Tests MUST NOT call `atexit._run_exitfuncs()` (drains all process-level handlers including pytest-cov coverage finalizer + dashboard PID-file cleanup at `dashboard/app.py:237`).
  - Linux-warning module-level guard prevents repeated emission across multiple builder invocations within a single process; `reset_linux_warning_latch` is a test-only helper that flips the flag back to its initial state.
  - `record_soft_fail_event` opens `<session_dir>/events.log` with `fcntl.flock(fd, fcntl.LOCK_EX)`, reads to check for existing `sandbox_soft_fail_active` entry, and conditionally appends — atomic under concurrent per-dispatch invocations. Uses the existing `cortex_command.overnight.events.log_event` helper if it already takes a lock; otherwise implements the lock locally.
- **Verification** (deferred-pytest pattern — full pytest assertions live in Task 9): `grep -c "fcntl.LOCK_EX\|fcntl.flock" cortex_command/overnight/sandbox_settings.py` returns ≥ 1 AND `grep -c "atexit.register" cortex_command/overnight/sandbox_settings.py` returns ≥ 1 AND `grep -c "reset_linux_warning_latch\|def reset_linux_warning_latch" cortex_command/overnight/sandbox_settings.py` returns ≥ 1 — pass if all three counts hold.
- **Status**: [ ] pending

### Task 4: Wire `_spawn_orchestrator` to consume the sandbox_settings layer
- **Files**: `cortex_command/overnight/runner.py`
- **What**: Modify `_spawn_orchestrator` (lines 930-974) to accept `state: OvernightState` and `session_dir: Path`, build the deny-set + allow-set + settings dict + tempfile via the layer, register atexit cleanup, and append `--settings <tempfile-path>` to the argv. Update the call site at `runner.py:2103`.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**:
  - New `_spawn_orchestrator` signature: `(filled_prompt: str, coord: RunnerCoordination, spawned_procs: list[tuple[subprocess.Popen, str]], stdout_path: Path, state: OvernightState, session_dir: Path) -> tuple[subprocess.Popen, WatchdogContext, WatchdogThread]`.
  - Inside body: call `emit_linux_warning_if_needed()`, `build_orchestrator_deny_paths(home_repo=..., integration_worktrees=state.integration_worktrees)`, `build_sandbox_settings_dict(deny_paths, allow_paths=[], soft_fail=read_soft_fail_env())`, `write_settings_tempfile(session_dir, settings)`, `register_atexit_cleanup(tempfile_path)`. If soft-fail reads truthy, also call `record_soft_fail_event(session_dir)`. Insert `"--settings", str(tempfile_path)` into the argv list between `filled_prompt` and `--dangerously-skip-permissions`.
  - Home-repo path: derive from `state.project_root` (per `state.py:225`) when set, else `Path.cwd()`.
  - Call site at `runner.py:2103` — pass `state=state, session_dir=session_dir`. Both are already in the surrounding scope per `runner.py:2034-2064`.
  - Add startup-scan call near runner-init: invoke `cleanup_stale_tempfiles(session_dir, runner_start_ts=time.time())` once at runner entry around `runner.py:1825-1870`.
- **Verification** (deferred-pytest — full assertions in Task 9): `grep -A 30 "def _spawn_orchestrator" cortex_command/overnight/runner.py | grep -c '"--settings"'` returns ≥ 1 AND `grep -A 30 "def _spawn_orchestrator" cortex_command/overnight/runner.py | grep -c "build_sandbox_settings_dict\|write_settings_tempfile"` returns ≥ 2 — pass if both hold.
- **Status**: [ ] pending

### Task 5: Convert `dispatch.py` to JSON-shape `--settings <tempfile>` (mirrors orchestrator path)
- **Files**: `cortex_command/pipeline/dispatch.py`
- **What**: Replace the stringly-typed `sandbox.write.allowOnly` shape (lines 536-549, 567) with a per-dispatch tempfile carrying the documented `sandbox.filesystem.{denyWrite,allowWrite}` shape, passed via `ClaudeAgentOptions(settings=str(tempfile_path))`. The SDK transport at `claude_agent_sdk/_internal/transport/subprocess_cli.py:111-163` accepts the `settings=` parameter as JSON-string-or-filepath (heuristic: `startswith("{") and endswith("}")`); a tempfile path falls into the filepath branch and is forwarded as `claude --settings <value>` on the CLI argv. Add `TMPDIR` to the `_env` dict using `tempfile.gettempdir()` as fallback.
- **Depends on**: [2, 3]
- **Complexity**: complex
- **Context**:
  - **Spec basis**: spec Req 5 (revised 2026-05-05) mandates `--settings <tempfile>` JSON-shape mechanism, mirroring orchestrator path. The originally-specced typed-field migration was dropped — verified that `SandboxFilesystemSettings` does not exist in `claude_agent_sdk@0.1.46` and `SandboxSettings` TypedDict has no `filesystem` key (per SDK docstring at `types.py:683-727`: "Filesystem and network restrictions are configured via permission rules, not via these sandbox settings"). The `--settings <tempfile>` mechanism is the documented Claude Code CLI mechanism per https://code.claude.com/docs/en/sandboxing.
  - **Imports**: `from cortex_command.overnight.sandbox_settings import build_dispatch_allow_paths, build_sandbox_settings_dict, write_settings_tempfile, register_atexit_cleanup, read_soft_fail_env, record_soft_fail_event`. Existing `ClaudeAgentOptions` import retained. **Do NOT** import `SandboxSettings` or `SandboxFilesystemSettings` from `claude_agent_sdk` — those symbols either don't exist or don't carry filesystem nesting.
  - `_write_allowlist` constructed via `build_dispatch_allow_paths(worktree_path, integration_base_path)`. Per-feature deny-set is empty for dispatch (the per-feature allow-list narrowly bounds writes; dispatch agents don't need to be denied from the home-repo `.git/` paths because they don't operate on the home repo).
  - Per-dispatch JSON dict: `build_sandbox_settings_dict(deny_paths=[], allow_paths=allowlist, soft_fail=read_soft_fail_env())`.
  - Per-dispatch tempfile: `write_settings_tempfile(session_dir, settings)`. `session_dir` threaded into the dispatch context — verify the dispatch site has `session_id` or `session_dir` in scope; if only `session_id`, derive `session_dir` via `cortex_command.overnight.state.session_dir(session_id)`.
  - `register_atexit_cleanup(tempfile_path)` to clean per-dispatch tempfiles on runner exit.
  - `_load_project_settings` retained on disk but no longer feeds `settings=` (Req 6 — only sandbox subtree is consumed via the layer's tempfile).
  - `_env` dict gains `"TMPDIR": os.environ.get("TMPDIR") or tempfile.gettempdir()`.
  - `ClaudeAgentOptions(...)` call: drop `settings=_worktree_settings`; add `settings=str(tempfile_path)`. The SDK transport detects this is a filepath (does not start with `{`) and forwards as `claude --settings <path>`.
  - If soft-fail reads truthy, call `record_soft_fail_event(session_dir)`.
- **Verification** (deferred-pytest — full assertions in Task 10): `grep -c "sandbox.write.allowOnly\|\"write\":" cortex_command/pipeline/dispatch.py` returns 0 (legacy shape removed) AND `grep -c "build_sandbox_settings_dict\|write_settings_tempfile" cortex_command/pipeline/dispatch.py` returns ≥ 2 (layer consumed) AND `grep -c "SandboxSettings\|SandboxFilesystemSettings" cortex_command/pipeline/dispatch.py` returns 0 (no typed-field dependency) AND `grep -c '"TMPDIR"' cortex_command/pipeline/dispatch.py` returns ≥ 1 — pass if all four hold.
- **Status**: [ ] pending

### Task 6: Fix cross-repo `integration_base_path` at `feature_executor.py:603` (and audit `retry.py` callers)
- **Files**: `cortex_command/overnight/feature_executor.py`, `cortex_command/pipeline/retry.py` (audit; modify only if a parallel inversion exists)
- **What**: Replace unconditional `integration_base_path=Path.cwd()` with a conditional that consults `state.integration_worktrees` via the canonical `_effective_merge_repo_path` helper from `outcome_router.py:115-195` when `repo_path is not None`. Audit `cortex_command/pipeline/retry.py` for any retry-loop caller that constructs an `integration_base_path` and apply the same correction if found.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Use `_effective_merge_repo_path(repo_path, state.integration_worktrees, state.integration_branches, state.session_id)` from `cortex_command/overnight/outcome_router.py:115-195` directly. Spec Req 7 mandates this helper, not a re-implementation of key normalization.
  - The line `integration_base_path=Path.cwd()` becomes a value derived from: `_effective_merge_repo_path(repo_path, state.integration_worktrees, state.integration_branches, state.session_id) or Path.cwd()` when `repo_path is not None`, else `Path.cwd()`.
  - Retry-path audit: `cortex_command/pipeline/retry.py` is a wrapper around `dispatch_task`. If it constructs its own `integration_base_path` argument, the same conditional applies. If retry simply forwards executor-provided values, no change needed — document outcome in commit message.
- **Verification** (deferred-pytest — full assertions in Task 10): `grep -A 3 "integration_base_path" cortex_command/overnight/feature_executor.py | grep -c "_effective_merge_repo_path"` returns ≥ 1 AND `grep -c "integration_base_path=Path.cwd()" cortex_command/overnight/feature_executor.py` returns 0 (unconditional inversion removed) — pass if both hold.
- **Status**: [ ] pending

### Task 7: Migrate tool-failure-tracker hook + readers from `/tmp/` to `$TMPDIR/`
- **Files**: `claude/hooks/cortex-tool-failure-tracker.sh`, `cortex_command/overnight/report.py` (lines 246, 1094, 1159 per spec Req 19)
- **What**: Replace `/tmp/claude-tool-failures-${SESSION_KEY}` with `${TMPDIR:-/tmp}/claude-tool-failures-${SESSION_KEY}` in the hook (line 44); update the three reader sites in `report.py` to construct the path via `os.environ.get("TMPDIR", "/tmp")`.
- **Depends on**: none
- **Complexity**: trivial
- **Context**:
  - Hook line 44: shell parameter expansion `${TMPDIR:-/tmp}`.
  - `report.py:246` and `report.py:1094` both construct `Path(f"/tmp/claude-tool-failures-{session_id}")`; update both to read `TMPDIR` from env.
  - `report.py:1159` is in a docstring; update text to reflect new path.
- **Verification**: `grep -c "/tmp/claude-tool-failures" claude/hooks/cortex-tool-failure-tracker.sh` returns 0 AND `grep -c '\${TMPDIR:-/tmp}/claude-tool-failures' claude/hooks/cortex-tool-failure-tracker.sh` returns ≥ 1 AND `grep -c '"/tmp/claude-tool-failures"' cortex_command/overnight/report.py` returns 0 — pass if all three conditions hold.
- **Status**: [ ] pending

### Task 8: Add morning-report soft-fail header surfacing
- **Files**: `cortex_command/overnight/report.py`
- **What**: The morning-report builder reads events.log and emits the unconditional header line per Req 20 when any `sandbox_soft_fail_active` event is present. (Event emission with TOCTOU-safe fcntl locking is implemented in Task 3 and called from Tasks 4 + 5.)
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - `report.py` morning-report builder gains a function that scans events.log for `sandbox_soft_fail_active`; if present, emit header `"CORTEX_SANDBOX_SOFT_FAIL=1 was active for this session; sandbox.failIfUnavailable was downgraded to false."` at top of report.
  - Reader pattern: existing events.log readers in `cortex_command.overnight.events`.
- **Verification** (deferred-pytest — full assertions in Task 10): `grep -c "CORTEX_SANDBOX_SOFT_FAIL=1 was active for this session" cortex_command/overnight/report.py` returns ≥ 1 AND `grep -c "sandbox_soft_fail_active" cortex_command/overnight/report.py` returns ≥ 1 — pass if both hold.
- **Status**: [ ] pending

### Task 9: Author behavior-level test suite for sandbox_settings layer
- **Files**: `tests/test_runner_sandbox.py` (new)
- **What**: Write the test functions named in spec Reqs 1, 2, 3, 4, 8, 11, 18 plus the synthetic-EPERM (Req 9) and precedence-overlap (Req 16) tests (both `sandbox-exec` PRIMARY + `srt` SECONDARY variants). Use the **direct-callback test pattern** for atexit (do NOT call `atexit._run_exitfuncs()`); use a **module-flag-reset fixture** for Linux-warning order independence.
- **Depends on**: [2, 3, 4]
- **Complexity**: complex
- **Context**:
  - Test functions to author (names per spec acceptance lines):
    - `test_orchestrator_spawn_includes_settings_flag` (mock `subprocess.Popen`, assert argv contains `--settings <existing-path>`)
    - `test_orchestrator_settings_json_shape` (assert exact dict shape from Req 2 — including `sandbox.enableWeakerNetworkIsolation: False`)
    - `test_denyset_specific_git_paths` (Req 3 — assert all entries match the four `.git/*` suffixes; no bare repo roots)
    - `test_soft_fail_killswitch_set` / `test_soft_fail_killswitch_unset` / `test_soft_fail_per_dispatch_re_read` (Req 4)
    - `test_denyset_recomputed_per_dispatch` (Req 8)
    - `test_tempfile_atexit_cleanup` — **uses the callback returned by `register_atexit_cleanup`** and invokes it directly (does NOT call `atexit._run_exitfuncs()` which would drain pytest-cov + dashboard handlers)
    - `test_tempfile_startup_scan_removes_stale`
    - `test_record_soft_fail_event_concurrent_idempotent` (NEW, addresses critical-review A3) — spawns two threads that both call `record_soft_fail_event` against an empty events.log; asserts exactly ONE `sandbox_soft_fail_active` line in the file after both return; relies on `fcntl.LOCK_EX` from Task 3.
    - `test_linux_warning_emitted` / `test_macos_no_warning` — **fixture-isolated**: each test calls `reset_linux_warning_latch()` in a `setup_function` (or `autouse=True` fixture) so the module-level flag is reset between tests; then mocks `sys.platform` and captures stderr.
    - `test_synthetic_kernel_eperm_under_sandbox_exec` (PRIMARY, blocking on Darwin)
    - `test_synthetic_kernel_eperm_under_srt` (SECONDARY; pytest.skip when `srt` not on PATH)
    - `test_denywrite_overrides_allowwrite_under_sandbox_exec` (PRIMARY, blocking)
    - `test_denywrite_overrides_allowwrite_under_srt` (SECONDARY, skip-allowed)
  - Test pattern reference: existing `cortex_command/pipeline/tests/test_dispatch.py` for SDK-mock structure.
- **Verification**: `pytest tests/test_runner_sandbox.py -v` exits 0 (synthetic `srt` tests may report as `skipped` but no failures) — pass if exit 0 and `test_synthetic_kernel_eperm_under_sandbox_exec` + `test_denywrite_overrides_allowwrite_under_sandbox_exec` show as `passed` (not skipped) on Darwin.
- **Status**: [ ] pending

### Task 10: Author dispatch + feature-executor + morning-report tests
- **Files**: `tests/test_dispatch.py` (extend), `tests/test_feature_executor.py` (new or extend existing fixture), `tests/test_morning_report.py` (extend)
- **What**: Add the dispatch test functions, the two `test_feature_executor.py` test functions, and the two `test_morning_report.py` test functions named in spec acceptance criteria.
- **Depends on**: [5, 6, 8]
- **Complexity**: simple
- **Context**:
  - `tests/test_dispatch.py`: add `test_settings_tempfile_used` (assert dispatched `ClaudeAgentOptions.settings` is a filepath that exists, JSON content matches expected shape with `sandbox.filesystem.{denyWrite,allowWrite}`), `test_dispatched_env_locks_tmpdir`, `test_no_blob_injection`, `test_no_typed_sandbox_field_attempted` (assert `SandboxSettings`/`SandboxFilesystemSettings` are NOT imported from `claude_agent_sdk` — guards against accidental re-introduction of the broken typed-field path). NB: spec Req 15 named `test_sdk_typed_sandbox_symbols_present` but that test cannot exist because the symbols don't exist; replaced with the inverse assertion. Document the substitution in commit message.
  - `tests/test_feature_executor.py`: add `test_cross_repo_uses_integration_worktree`, `test_same_repo_uses_cwd`. Construct `OvernightState` fixture with populated `integration_worktrees` mapping; mock `dispatch_task` to capture `integration_base_path`.
  - `tests/test_morning_report.py`: add `test_soft_fail_header_emitted` (events.log fixture with `sandbox_soft_fail_active`) and `test_no_soft_fail_no_header`.
- **Verification**: `pytest tests/test_dispatch.py tests/test_feature_executor.py tests/test_morning_report.py -v` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 11: Update three documentation surfaces
- **Files**: `docs/overnight-operations.md`, `docs/pipeline.md`, `docs/sdk.md`
- **What**: Apply the doc updates from spec Req 13: remove "no permissions sandbox" claim from overnight-operations:23; add "Per-spawn sandbox enforcement" section there; add "Sandbox shape" + "Allowed write paths" subsections in pipeline.md; corrective edit on sdk.md:199. Also document the spec Req 5 deviation (typed-field path doesn't exist; both spawn sites use `--settings <tempfile>` mechanism).
- **Depends on**: [4, 5]
- **Complexity**: simple
- **Context**:
  - `docs/overnight-operations.md:23`: remove the parenthetical "no permissions sandbox" string.
  - New `docs/overnight-operations.md` section "Per-spawn sandbox enforcement" describes: orchestrator deny-set (4 git-path suffixes per repo), dispatch allow-set (worktree + 6 OUT_OF_WORKTREE_ALLOW_WRITERS), `CORTEX_SANDBOX_SOFT_FAIL` kill-switch, threat-model boundary (Bash-only; Write/Edit/MCP bypass per Anthropic [#26616](https://github.com/anthropics/claude-code/issues/26616) and https://code.claude.com/docs/en/sandboxing).
  - `docs/pipeline.md` "Sandbox shape" subsection: documents the unified `sandbox.filesystem.{allowWrite,denyWrite}` JSON shape, written by `build_sandbox_settings_dict` and consumed via `--settings <tempfile>` by both orchestrator and dispatch. Note that the typed `SandboxSettings`/`SandboxFilesystemSettings` SDK field path was specced but found to be non-existent in `claude_agent_sdk@0.1.46`; the documented shape is preserved via the JSON-string mechanism instead.
  - `docs/pipeline.md` "Allowed write paths" subsection enumerates each of the 6 entries with one-sentence rationale per Req 10.
  - `docs/sdk.md:199`: replace the asymmetric-claim string with the corrected text per #26616 inversion; cross-link to overnight-operations.md.
- **Verification**: `grep -c "Per-spawn sandbox enforcement" docs/overnight-operations.md` ≥ 1 AND `grep -c "no permissions sandbox" docs/overnight-operations.md` == 0 AND `grep -cE "Sandbox shape|Allowed write paths" docs/pipeline.md` ≥ 2 AND `grep -c "code.claude.com/docs/en/sandboxing" docs/overnight-operations.md` ≥ 1 AND `grep -c "does not constrain what a Bash subprocess" docs/sdk.md` == 0 — pass if all five.
- **Status**: [ ] pending

### Task 12: Extend `bin/cortex-check-parity` with structured pre-flight gate (diff-hunk grep + commit-hash binding + claude-version re-check)
- **Files**: `bin/cortex-check-parity` (extend), `lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md` (new artifact)
- **What**: Add a pre-commit-level check using **diff-hunk grep** + **structured preflight schema with commit-hash binding** + **`claude --version` drift detection** per spec Req 17 (revised 2026-05-05). Eliminates calendar-time false positives on multi-day branches.
- **Depends on**: [4, 5]
- **Complexity**: complex
- **Context**:
  - `bin/cortex-check-parity` currently does SKILL.md-to-bin parity. Add a new check function `_check_sandbox_preflight_gate()`:
    1. Run `git diff --cached -U0 <each-watched-file>` to extract the actual changed-line hunks.
    2. For `cortex_command/pipeline/dispatch.py`: grep the hunk lines for `_load_project_settings\|sandbox\|SandboxSettings\|build_sandbox\|write_settings_tempfile`. If any match, the gate fires.
    3. For `cortex_command/overnight/runner.py`: grep the hunk lines for `_spawn_orchestrator\|--settings\|sandbox`. If any match, the gate fires. (Diff-hunk-content based, so a refactor that renames `_spawn_orchestrator` still matches via the `--settings` or `sandbox` keyword — addresses critical-review A4 finding 3.)
    4. For `cortex_command/overnight/sandbox_settings.py`: any change to this file fires the gate (entire file is sandbox-source).
    5. For `pyproject.toml`: grep the hunk lines for `claude-agent-sdk`. If any match, the gate fires.
    6. If any gate fires, validate `lifecycle/<feature>/preflight.md` against the structured YAML schema below. If missing or invalid, exit non-zero.
  - **Structured preflight.md schema** (replaces freeform PASS line):
    ```
    # Pre-flight verification

    ```yaml
    pass: true
    timestamp: <ISO-8601>
    commit_hash: "<full sha of the cortex-command HEAD at preflight-run time>"
    claude_version: "<exact output of `claude --version`>"
    test_command: "<exact command invoked>"
    exit_code: <int>
    stderr_contains_eperm: true|false
    stderr_excerpt: |
      <captured stderr>
    target_path: "<the denied-write target>"
    target_unmodified: true|false
    ```
    ```
  - **Gate validation logic** (commit-hash binding model — supersedes the rejected 24h-calendar-time approach):
    - Parse the YAML block (use `python3 -c "import yaml; ..."` — Python is already a hook dependency; `yaml` is in the project's runtime deps via PyYAML).
    - Assert `pass == true`, `exit_code != 0`, `stderr_contains_eperm == true`, `target_unmodified == true`.
    - **Commit-hash freshness check**: read `commit_hash` field; resolve `git rev-parse HEAD~` (HEAD's parent at gate time, since the gate runs pre-commit so HEAD~ is the commit before the staged change); if `commit_hash != HEAD~`, fail with "preflight evidence is stale relative to current sandbox-source state — re-run pre-flight against HEAD". This catches multi-day-branch drift without calendar-time false positives.
    - **`claude --version` drift check**: capture current `claude --version` output; compare against recorded `claude_version`; if drift, fail with "claude binary drift between preflight and current install — re-run preflight". Catches `brew upgrade claude` between preflight and merge.
  - The structured schema + commit-hash binding makes manual spoofing detectable: a developer typing the YAML block would have to fabricate `exit_code`, `stderr_excerpt`, `target_unmodified`, AND a `commit_hash` that matches HEAD~ at commit time. The hash binding is also self-invalidating — once any sandbox-source commit lands, the recorded hash no longer matches and a new preflight is required.
  - Author the initial preflight.md from a real human pre-flight run with all schema fields populated, including `commit_hash` set to whatever HEAD is at preflight time.
- **Verification**: Three fixture-commit tests, each exiting non-zero on misuse and zero on correct usage:
  1. `bin/cortex-check-parity` exits non-zero against a fixture commit that bumps the SDK pin (`pyproject.toml` grep match) without a fresh schema-valid PASS preflight whose `commit_hash` matches HEAD's parent.
  2. `bin/cortex-check-parity` exits non-zero when `claude --version` differs from the recorded `claude_version` field, even if `commit_hash` matches.
  3. `bin/cortex-check-parity` exits non-zero against a fixture commit that renames `_spawn_orchestrator` to `_build_orchestrator_argv` (diff-hunk pattern match still triggers via `sandbox` or `--settings` keyword).
  Verify with: `cd $(mktemp -d) && git init && git commit --allow-empty -m init && (printf 'claude-agent-sdk>=0.1.47,<0.1.48\n' > pyproject.toml; git add pyproject.toml) && /Users/charlie.hall/Workspaces/cortex-command/bin/cortex-check-parity` returns non-zero — pass if non-zero exit on each of the three fixtures.
- **Status**: [ ] pending

### Task 13: Run full test suite + dry-run snapshot regression check
- **Files**: none modified; verification-only task
- **What**: Run `just test` end-to-end and verify the `tests/fixtures/dry_run_reference.txt` byte-identical snapshot does not regress. If sandbox-tempfile creation logging surfaces in dry-run output, suppress in dry-run mode rather than updating the snapshot.
- **Depends on**: [4, 5, 6, 7, 8, 9, 10, 11]
- **Complexity**: simple
- **Context**:
  - `just test` is the canonical test entry per `CLAUDE.md` Commands section.
  - Dry-run snapshot at `tests/fixtures/dry_run_reference.txt` per `requirements/pipeline.md:27`.
- **Verification**: `just test` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 14: CLAUDE.md 100-line cap check
- **Files**: `CLAUDE.md`, `docs/policies.md` (created only if cap crossed)
- **What**: Per spec Req 14, verify CLAUDE.md remains ≤ 100 lines. (Likely no-op for this feature since policy entries are not added — sandbox config is config, not prose escalation per spec line 175.)
- **Depends on**: [11]
- **Complexity**: trivial
- **Context**:
  - Current CLAUDE.md line count: 68.
  - Threshold check: line that crosses 100 triggers extraction.
- **Verification**: `[ $(wc -l < CLAUDE.md) -le 100 ]` exits 0 — pass if exit 0.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification proceeds in three layers, with **deferred-pytest** for upstream-task verifications (each upstream task has a static-shape Verification that passes at task-completion time; the full pytest assertion suite runs at Task 13 once tests are authored in Tasks 9-10):

1. **Static-shape verifications (per-task)**: Tasks 2, 3, 4, 5, 6, 8 each have grep-count and code-shape verifications that pass at task-completion time. These confirm the implementation has the structural hooks the tests will assert against in Task 13.
2. **Behavior tests via `just test` (Task 13)**: Tasks 9 + 10 author the full pytest suite covering all 20 spec Requirements at the unit-of-behavior level, including the dual-mechanism kernel-EPERM tests (Req 9) and precedence-overlap tests (Req 16) using `sandbox-exec` (PRIMARY, blocking) and `srt` (SECONDARY, skip-allowed). The synthetic kernel tests are the hard line of defense against shape regressions inside CI. Task 13 runs the full suite and asserts byte-identical dry-run snapshot.
3. **Human pre-flight gate (Req 12 + Task 12)**: a clean non-sandboxed terminal runs `claude -p "$PROMPT" --settings <denying-tempfile> --dangerously-skip-permissions --max-turns 3`; result recorded to `lifecycle/{feature}/preflight.md` using the **structured YAML schema** introduced in Task 12 (timestamp, commit_hash, claude_version, exit_code, stderr_contains_eperm, target_unmodified). PR cannot merge without a schema-valid PASS preflight — verified by `bin/cortex-check-parity` schema-validation, not freeform grep.
4. **Pre-commit gate (Req 17 + Task 12)**: `bin/cortex-check-parity` extension uses `git diff --cached -U0` for diff-hunk grep (catches sandbox-source-file changes regardless of function name or line number — addresses critical-review A4 finding 3), validates `commit_hash` matches HEAD's parent at gate time (eliminates calendar-time false positives on multi-day branches), and re-checks `claude --version` (catches `brew upgrade claude` drift between preflight and merge).

## Veto Surface

Items requiring user attention before implementation begins. Q1 (spec Req 5 deviation) and Q2 (freshness window) from critical review have been resolved by spec.md revision (logged as `spec_revision` in events.log 2026-05-05); plan now matches the corrected spec.

**§1 — `_load_project_settings` retention vs deletion**: spec Req 6 says only the sandbox subtree is consumed; this plan retains the function on disk but removes the call site from dispatch. Aggressive variant: delete the function entirely. Retention is conservative; deletion is cleaner. Confirm at implementation time.

**§2 — Architectural choice (layered vs shared-state)**: layered free-functions chosen over shared-state context for smaller blast radius. If the implementer prefers shared-state for explicit per-session lifetime, switch the layer's free functions into methods on a `SandboxPolicyContext` dataclass without changing task structure.

## Scope Boundaries

Per spec Non-Requirements (lines 109-124), this feature explicitly does NOT cover:
- Write-tool / Edit-tool / MCP-server / plumbing-level ref-mutation escapes (Anthropic #26616 carve-out)
- Migrating non-sandbox SDK settings (hooks, env, statusLine) to typed fields
- Linux/bwrap support — Seatbelt-only, Linux observable via Req 18 stderr warning
- Sandbox-violation telemetry tracker (deferred to epic #162's child #164)
- Exhaustive enumeration of all out-of-worktree writers (six risk-targeted entries only)
- Spawning a real `claude -p` subprocess in CI tests (synthetic + human pre-flight only)
- Managed-settings install at `~/Library/Application Support/ClaudeCode/managed-settings.json` (Alt A rejected)
- Deny-set install into `~/.claude/settings.local.json` user-scope (Alt E rejected)
- `sandbox-exec` wrapper as primary enforcement (Alt D — kept as fallback contingency only)
- Repos with custom default branches (`develop`, `trunk`) under V1 — only `main` and `master`
- Cross-repo dispatched agents inheriting home cortex repo's project hooks (intentional isolation)
- **Migrating dispatch path to typed `SandboxSettings`/`SandboxFilesystemSettings` SDK field** — verified non-existent in `claude_agent_sdk@0.1.46` (see Veto Surface §1)

## Sizing

14 tasks, target 5-15 minutes each; complex tasks (5, 9, 12) may approach 25 minutes due to spec-deviation note + dispatch tempfile lifecycle (5), dual-mechanism Seatbelt test authoring + concurrent-event-log test (9), and structured preflight schema + hunk-grep parity logic (12). Each task touches ≤ 5 files. Tasks 1, 6, 7 are independent; remainder chain through the layer module (1 → 2, 3 → 4, 5; 5, 6, 8 → 10; 4, 5 → 11, 12, 13; 11 → 14). Tasks 2/3/4/5/6/8 use **deferred-pytest verifications** — static shape checks pass at task completion, full pytest assertions run at Task 13 once Tasks 9/10 author the test files.
