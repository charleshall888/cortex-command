# Plan: apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites

## Overview

This variant centers a single in-memory `SandboxPolicyStore` dataclass (in a new `cortex_command/overnight/sandbox_settings.py` module) that holds the canonical per-session sandbox state — soft-fail flag, runner-start timestamp, active deny-set repo list, allowWrite extensions, tempfile registry, and platform observability. All three spawn sites (`_spawn_orchestrator`, `dispatch_task` per-feature, retry-resolve) read from and mutate this single store rather than constructing settings independently. The store is the source-of-truth: tempfile-builder helpers, atexit cleanup, startup-scan, kill-switch reads, Linux warning emission, and morning-report `sandbox_soft_fail_active` event-log entries are all functions that operate on this store. Soft-fail re-read at each invocation works by store helpers re-checking `os.environ` rather than caching.

**Architectural Pattern**: shared-state — variants A and B distribute construction across pipeline stages or event hooks; this variant centralizes all sandbox-policy state into a single typed store object whose methods are the only entry points for tempfile creation, deny-set computation, allowWrite extension, and lifecycle cleanup, so spawn sites become thin readers of one shared object instead of independent constructors.

## Tasks

### Task 1: Create `SandboxPolicyStore` shared-state module skeleton
- **Files**: `cortex_command/overnight/sandbox_settings.py` (new)
- **What**: Establishes the new module with the central `SandboxPolicyStore` dataclass plus stub method signatures that all later tasks fill in. This single module owns all sandbox-policy state and helpers.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Module exposes one dataclass `SandboxPolicyStore` with fields `session_dir: Path`, `runner_start_ts: float`, `allowwrite_extensions: list[str]`, `tempfile_registry: list[Path]`, `soft_fail_event_recorded: bool`, `linux_warning_emitted: bool`. Public method stubs: `build_orchestrator_settings(state) -> Path`, `build_dispatch_sandbox(state, repo_root, worktree_path, integration_base_path) -> SandboxSettings`, `compute_denyset(state) -> list[str]`, `read_soft_fail_env() -> bool`, `emit_linux_warning_once() -> None`, `register_tempfile(path) -> None`, `cleanup_atexit() -> None`, `startup_scan(session_dir, runner_start_ts) -> int`. Atomic-write pattern reference: `cortex_command/common.py:482` `atomic_write`. Tempfile dir convention: `<session_dir>/sandbox-settings/` per spec Req 11.
- **Verification**: `python -c "from cortex_command.overnight.sandbox_settings import SandboxPolicyStore; s = SandboxPolicyStore.__dataclass_fields__; assert {'session_dir','runner_start_ts','allowwrite_extensions','tempfile_registry','soft_fail_event_recorded','linux_warning_emitted'} <= set(s)"` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 2: Implement deny-set computation and soft-fail env read
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implements `compute_denyset(state)` — enumerates `state.integration_worktrees.keys()` plus the home repo, emits four entries per repo (`<repo>/.git/refs/heads/main`, `<repo>/.git/refs/heads/master`, `<repo>/.git/HEAD`, `<repo>/.git/packed-refs`). Implements `read_soft_fail_env()` reading `os.environ.get("CORTEX_SANDBOX_SOFT_FAIL") == "1"` at each call (no caching).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Spec Reqs 3, 4, 8. State object is `OvernightState` from `cortex_command/overnight/state.py:192`; `integration_worktrees: dict[str, str]` per state.py:270. Home-repo path comes from `state.cwd` or runner's `Path.cwd()` at spawn time. Static enumeration only — no `git symbolic-ref` calls. Soft-fail re-read happens per dispatch (spec Req 4 acceptance test `test_soft_fail_per_dispatch_re_read`).
- **Verification**: `pytest tests/test_runner_sandbox.py::test_denyset_specific_git_paths tests/test_runner_sandbox.py::test_soft_fail_killswitch_set tests/test_runner_sandbox.py::test_soft_fail_killswitch_unset tests/test_runner_sandbox.py::test_soft_fail_per_dispatch_re_read tests/test_runner_sandbox.py::test_denyset_recomputed_per_dispatch -v` exits 0 — pass if exit 0 and all four tests pass.
- **Status**: [ ] pending

### Task 3: Implement orchestrator-spawn settings JSON builder + tempfile lifecycle
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implements `build_orchestrator_settings(state)` constructing the per-spawn JSON object per spec Req 2 (sandbox.enabled, failIfUnavailable, allowUnsandboxedCommands, enableWeakerNestedSandbox, enableWeakerNetworkIsolation, filesystem.denyWrite from Task 2, filesystem.allowWrite empty), writing via `cortex_command.common.atomic_write` to a `tempfile.mkstemp(prefix="cortex-sandbox-", suffix=".json", dir=<session_dir>/sandbox-settings/)` path with mode 0o600. Registers tempfile in store registry; registers `atexit.register(self.cleanup_atexit)` once on first call.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: Spec Reqs 2, 11. Settings JSON shape:
  - `sandbox.enabled: true`
  - `sandbox.failIfUnavailable: true | false` (read from `read_soft_fail_env()` at this invocation)
  - `sandbox.allowUnsandboxedCommands: false`
  - `sandbox.enableWeakerNestedSandbox: false`
  - `sandbox.enableWeakerNetworkIsolation: false`
  - `sandbox.filesystem.denyWrite: list[str]` (from Task 2)
  - `sandbox.filesystem.allowWrite: []`
  Tempfile path: ensure `<session_dir>/sandbox-settings/` exists before `mkstemp`. Cleanup pattern reference: `cortex_command/dashboard/app.py:237` `atexit.register(lambda: _pid_file.unlink(missing_ok=True))`.
- **Verification**: `pytest tests/test_runner_sandbox.py::test_orchestrator_settings_json_shape tests/test_runner_sandbox.py::test_tempfile_atexit_cleanup -v` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 4: Implement startup-scan crash-path cleanup + Linux platform warning
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implements `startup_scan(session_dir, runner_start_ts)` that finds `<session_dir>/sandbox-settings/cortex-sandbox-*.json` whose mtime is older than `runner_start_ts` and unlinks them. Implements `emit_linux_warning_once()` that checks `sys.platform != "darwin"` and emits the spec-mandated stderr warning string exactly once per store instance.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Spec Reqs 11, 18. Linux warning string: `"WARNING: cortex sandbox enforcement is macOS-Seatbelt-only; Linux/bwrap behavior is undefined per parent epic #162. Sandbox configuration may not enforce as documented."` Pattern reference: `cortex_command/dashboard/app.py:237` PID-file precedent. Glob via `pathlib.Path.glob("cortex-sandbox-*.json")`.
- **Verification**: `pytest tests/test_runner_sandbox.py::test_tempfile_startup_scan_removes_stale tests/test_runner_sandbox.py::test_linux_warning_emitted tests/test_runner_sandbox.py::test_macos_no_warning -v` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 5: Wire `_spawn_orchestrator` to read from `SandboxPolicyStore`
- **Files**: `cortex_command/overnight/runner.py`
- **What**: Modifies `_spawn_orchestrator` (line 930) to accept `state` and `session_dir` parameters, instantiate or fetch the per-session `SandboxPolicyStore`, call `store.startup_scan(...)` once at runner-init (callsite of first orchestrator spawn), call `store.emit_linux_warning_once()`, then call `store.build_orchestrator_settings(state)` to produce a tempfile path and append `["--settings", str(tempfile_path)]` to the existing argv.
- **Depends on**: [3, 4]
- **Complexity**: simple
- **Context**: Spec Req 1. Existing `subprocess.Popen` argv at runner.py:946-955 is the surgical site. Caller adds `state` and `session_dir` to existing call sites; `state` is already plumbed at the runner's main loop. `runner_start_ts` is captured at runner-init via `time.time()`. Store is held on `RunnerCoordination` (`coord`) or a new module-level singleton keyed by session_id; either works — pick coord for explicit lifetime.
- **Verification**: `pytest tests/test_runner_sandbox.py::test_orchestrator_spawn_includes_settings_flag -v` exits 0 AND `grep -c '"--settings"' cortex_command/overnight/runner.py` ≥ 1 — pass if both true.
- **Status**: [ ] pending

### Task 6: Convert `dispatch.py` sandbox shape to typed `SandboxSettings` field via store
- **Files**: `cortex_command/pipeline/dispatch.py`, `cortex_command/overnight/sandbox_settings.py`
- **What**: Implements `build_dispatch_sandbox(state, repo_root, worktree_path, integration_base_path) -> SandboxSettings` in the store, returning a typed `SandboxSettings(filesystem=SandboxFilesystemSettings(allowWrite=[...], denyWrite=[...]))` object. Replaces `dispatch.py:536-549` granular `sandbox.write.allowOnly` shape with a call to this helper, passing the result via `ClaudeAgentOptions(sandbox=...)` typed field. Removes sandbox keys from the stringly-typed `settings=` parameter. Adds `TMPDIR=<resolved-value>` to the dispatched-agent `env=` dict.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: Spec Reqs 5, 6, 8. Imports `SandboxSettings`, `SandboxFilesystemSettings` from `claude_agent_sdk` (typed field per research §A.3). The dispatch path no longer force-injects merged project settings (Req 6) — `_load_project_settings` keeps loading for callers that still need its return value, but the dispatch site no longer writes it into `options.settings`. Soft-fail flag does not appear on `SandboxSettings` directly (it's a top-level `sandbox.failIfUnavailable` key); for typed-field dispatch path, the typed `SandboxSettings` carries `failIfUnavailable` per SDK type def. allowWrite list = [worktree, realpath(worktree), integration_base_path?, realpath(integration_base_path)?] + Task 7 risk-targeted writers.
- **Verification**: `pytest tests/test_dispatch.py::test_typed_sandbox_field_used tests/test_dispatch.py::test_dispatched_env_locks_tmpdir tests/test_dispatch.py::test_no_blob_injection tests/test_dispatch.py::test_sdk_typed_sandbox_symbols_present -v` exits 0 AND `grep -c "SandboxSettings\|SandboxFilesystemSettings" cortex_command/pipeline/dispatch.py` ≥ 1 — pass if both true.
- **Status**: [ ] pending

### Task 7: Add risk-targeted allowWrite extensions list to store
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implements `allowwrite_extensions` field default factory returning the six documented out-of-worktree writers: `~/.cache/uv/`, `$TMPDIR/`, `~/.claude/sessions/`, `~/.cache/cortex/`, `~/.cache/cortex-command/`, `~/.local/share/overnight-sessions/`. `build_dispatch_sandbox` (Task 6) appends these onto the per-feature allowWrite list with home-dir and TMPDIR expansion via `os.path.expanduser` and `os.environ.get("TMPDIR", ...)`.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Spec Req 10. Each entry has a known cortex writer it serves. Expansion happens once at store-construction time so the resolved paths are stable across dispatches in a session.
- **Verification**: `grep -cE '\.cache/uv|TMPDIR|claude/sessions|\.cache/cortex|\.cache/cortex-command|local/share/overnight-sessions' cortex_command/overnight/sandbox_settings.py` ≥ 6 — pass if count ≥ 6.
- **Status**: [ ] pending

### Task 8: Fix cross-repo allowlist inversion in feature_executor
- **Files**: `cortex_command/overnight/feature_executor.py`
- **What**: Changes line 603 `integration_base_path=Path.cwd()` to a conditional that calls the canonical `_effective_merge_repo_path(repo_path, state.integration_worktrees, state.integration_branches, state.session_id)` from `cortex_command/overnight/outcome_router.py:115` when `repo_path is not None`, else `Path.cwd()`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec Req 7. `repo_path` is already in scope at the dispatch site (line 604). State plumbed in via existing args; if not, add `state` to the dispatch call. Helper signature: `_effective_merge_repo_path(repo_path: Path | None, integration_worktrees: dict[str, str], integration_branches: dict[str, str], session_id: str) -> Path | None` from outcome_router.py:115-195. Use directly — do not re-implement key normalization.
- **Verification**: `pytest tests/test_feature_executor.py::test_cross_repo_uses_integration_worktree tests/test_feature_executor.py::test_same_repo_uses_cwd -v` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 9: Add synthetic kernel-EPERM and precedence-overlap dual-mechanism tests
- **Files**: `tests/test_runner_sandbox.py` (new)
- **What**: Creates the test file with `test_synthetic_kernel_eperm_under_sandbox_exec` (PRIMARY, blocking on macOS) invoking `sandbox-exec` with a Seatbelt profile equivalent to the cortex deny-JSON, plus the secondary `test_synthetic_kernel_eperm_under_srt` (skip-allowed). Adds matching `test_denywrite_overrides_allowwrite_under_sandbox_exec` and `test_denywrite_overrides_allowwrite_under_srt` for precedence-overlap.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**: Spec Reqs 9, 16. `sandbox-exec` is universally available on Darwin; tests must NOT skip on macOS. `srt` (`@anthropic-ai/sandbox-runtime` CLI) tests skip with the documented message `"sandbox-runtime CLI not installed; sandbox-exec test provides hard coverage"` when `srt` is not on PATH. Assertion shape: child exits non-zero, stderr contains `"Operation not permitted"`, target file does not exist after the run. Precedence test: deny `<tmp>/repo/.git/refs/heads/main`, allow `<tmp>/repo/`, write to deny path → must EPERM.
- **Verification**: `pytest tests/test_runner_sandbox.py::test_synthetic_kernel_eperm_under_sandbox_exec tests/test_runner_sandbox.py::test_denywrite_overrides_allowwrite_under_sandbox_exec -v` exits 0 (passes, NOT skipped) on macOS — pass if exit 0 with no SKIP markers in output.
- **Status**: [ ] pending

### Task 10: Migrate tool-failure-tracker to `$TMPDIR` + update report.py readers
- **Files**: `claude/hooks/cortex-tool-failure-tracker.sh`, `cortex_command/overnight/report.py`
- **What**: Changes `TRACK_DIR="/tmp/claude-tool-failures-${SESSION_KEY}"` (line 44) to `TRACK_DIR="${TMPDIR:-/tmp}/claude-tool-failures-${SESSION_KEY}"`. Updates `report.py:246, 1094, 1159` to construct the same path via `os.environ.get("TMPDIR", "/tmp")`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec Req 19. Hook's `mkdir -p ... 2>/dev/null || true` silently swallows EPERM today; migration aligns with the `$TMPDIR` allowWrite entry from Task 7.
- **Verification**: `grep -c "/tmp/claude-tool-failures" claude/hooks/cortex-tool-failure-tracker.sh` == 0 AND `grep -c '\${TMPDIR:-/tmp}/claude-tool-failures' claude/hooks/cortex-tool-failure-tracker.sh` ≥ 1 AND `grep -c "/tmp/claude-tool-failures" cortex_command/overnight/report.py` == 0 — pass if all three conditions hold.
- **Status**: [ ] pending

### Task 11: Wire morning-report unconditional soft-fail header from event log
- **Files**: `cortex_command/overnight/sandbox_settings.py`, `cortex_command/overnight/report.py`
- **What**: In the store, when `read_soft_fail_env()` returns true at any settings build (orchestrator or dispatch), if `soft_fail_event_recorded` is false, emit a `sandbox_soft_fail_active` event to `lifecycle/sessions/<session_id>/events.log` via `cortex_command.overnight.events.log_event` and flip the flag. In `report.py` morning-report builder, scan events.log for any `sandbox_soft_fail_active` event; if present, prepend the spec-mandated header line.
- **Depends on**: [3, 6]
- **Complexity**: simple
- **Context**: Spec Req 20. Header string: `"CORTEX_SANDBOX_SOFT_FAIL=1 was active for this session; sandbox.failIfUnavailable was downgraded to false."` Event log helper: `cortex_command.overnight.events.log_event` (events.py:194). Read helper: `read_events(log_path)` (events.py:248).
- **Verification**: `pytest tests/test_morning_report.py::test_soft_fail_header_emitted tests/test_morning_report.py::test_no_soft_fail_no_header -v` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 12: Documentation updates across three doc surfaces
- **Files**: `docs/overnight-operations.md`, `docs/pipeline.md`, `docs/sdk.md`
- **What**: Edits `docs/overnight-operations.md:23` to remove "no permissions sandbox"; adds new "Per-spawn sandbox enforcement" section (orchestrator deny-set, dispatch allow-set, `CORTEX_SANDBOX_SOFT_FAIL` kill-switch, threat-model boundary referencing #26616 and https://code.claude.com/docs/en/sandboxing). Adds "Sandbox shape" + "Allowed write paths" subsections to `docs/pipeline.md`. Replaces `docs/sdk.md:199` with the inverted-asymmetry text per #26616.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec Req 13. Doc-source convention from CLAUDE.md:50 — owning doc gets full content, others cross-link. Six allowWrite entries from Task 7 each need a one-sentence rationale in pipeline.md.
- **Verification**: `grep -c "Per-spawn sandbox enforcement" docs/overnight-operations.md` ≥ 1 AND `grep -c "no permissions sandbox" docs/overnight-operations.md` == 0 AND `grep -c "Sandbox shape\|Allowed write paths" docs/pipeline.md` ≥ 2 AND `grep -c "code.claude.com/docs/en/sandboxing" docs/overnight-operations.md` ≥ 1 AND `grep -c "does not constrain what a Bash subprocess" docs/sdk.md` == 0 — pass if all five hold.
- **Status**: [ ] pending

### Task 13: Extend `bin/cortex-check-parity` for SDK-pin / sandbox-source-file gating
- **Files**: `bin/cortex-check-parity`
- **What**: Extends the script to detect commits that modify `pyproject.toml`'s `claude-agent-sdk` pin OR `cortex_command/overnight/sandbox_settings.py` OR `cortex_command/pipeline/dispatch.py` (lines covering `_load_project_settings`) OR `cortex_command/overnight/runner.py` (lines covering `_spawn_orchestrator`) without a fresh `PASS:` line in `lifecycle/<feature>/preflight.md` dated within 24h of the commit timestamp. Non-zero exit on violation.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Spec Req 17. Diff inspection via `git diff --cached --name-only` and content grep for the SDK pin string. Preflight file path discovered via lifecycle directory traversal. Date check via parsing `PASS:` line for ISO-8601 timestamp and comparing to `git log -1 --format=%ct`.
- **Verification**: Run script against a fixture commit that bumps the SDK pin without updating preflight.md; assert non-zero exit. `bash -c 'cd $(mktemp -d) && git init -q && cp /Users/charlie.hall/Workspaces/cortex-command/pyproject.toml . && sed -i "" "s/0.1.46/0.1.47/" pyproject.toml && git add . && /Users/charlie.hall/Workspaces/cortex-command/bin/cortex-check-parity; echo $?'` returns non-zero — pass if exit code != 0.
- **Status**: [ ] pending

### Task 14: Create preflight.md artifact + run pre-flight gate
- **Files**: `lifecycle/archive/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md`
- **What**: Human runs `claude -p "$PROMPT" --settings <denying-tempfile> --dangerously-skip-permissions --max-turns 3` with `$PROMPT` instructing Claude to attempt a denied write via Bash. Records pass/fail line, actual stderr excerpt, `claude --version`, and date in `preflight.md`. The `PASS:` line is required for PR merge.
- **Depends on**: [3, 5, 6]
- **Complexity**: simple
- **Context**: Spec Req 12. Interactive/manual gate — cannot run in CI. Output file format: a line beginning `PASS:` or `FAIL:` followed by the stderr excerpt and metadata. Re-run required on SDK pin bumps and sandbox-source-file changes (Task 13 enforces this).
- **Verification**: `grep -E '^PASS:' lifecycle/archive/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md` returns at least one match — pass if grep exit 0.
- **Status**: [ ] pending

### Task 15: Verify CLAUDE.md 100-line cap unchanged
- **Files**: `CLAUDE.md` (verify only)
- **What**: This work adds no new policy entries to CLAUDE.md (sandbox config-flag values are not prose escalations per spec Tech Constraints). Verifies the line-count cap is unaffected by this change.
- **Depends on**: [12]
- **Complexity**: trivial
- **Context**: Spec Req 14. CLAUDE.md is at 68 lines today; threshold is 100. No edit expected.
- **Verification**: `bash -c '[ "$(wc -l < /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md)" -le 100 ] && echo OK'` outputs `OK` — pass if output is `OK`.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification proceeds in three layers:

1. **Unit-layer (automated, runs in `just test`)**: All `tests/test_runner_sandbox.py`, `tests/test_dispatch.py`, `tests/test_feature_executor.py`, `tests/test_morning_report.py` tests pass. Includes the `SandboxPolicyStore` shape/behavior tests, soft-fail re-read tests, deny-set recompute tests, tempfile lifecycle tests, Linux platform-warning tests, and the SDK typed-symbol assertion test that catches pin-bump drift.

2. **Synthetic kernel-layer (automated, runs in `just test`)**: The `sandbox-exec` PRIMARY tests (`test_synthetic_kernel_eperm_under_sandbox_exec`, `test_denywrite_overrides_allowwrite_under_sandbox_exec`) prove the deny-set as constructed produces real EPERM at the macOS Seatbelt layer. The `srt` SECONDARY tests opportunistically validate the Anthropic wrapper layer when the CLI is installed.

3. **Empirical end-to-end gate (manual, blocking pre-merge)**: `lifecycle/archive/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md` contains a `PASS:` line from a real `claude -p --settings <denying-tempfile>` invocation that demonstrates kernel-EPERM blocks a Bash-tool write to a denied path. The `bin/cortex-check-parity` extension enforces re-running this gate on SDK pin bumps and sandbox-source-file changes.

Post-merge soak: monitor morning reports for unexpected EPERM events; tighten or migrate writers as observed. The `CORTEX_SANDBOX_SOFT_FAIL=1` kill-switch + Req 20 morning-report header provide the recovery path if Anthropic regressions #53085/#53683 fire.

## Sizing

15 tasks, each 1-5 files, sized 5-15 minutes per task except Tasks 3, 6, 9, 13 which are complex (~30-45 minutes). Every task has a `Depends on` field. The shared-state pattern keeps the `SandboxPolicyStore` module (Tasks 1-4, 7, 11) as a tightly-bound vertical, while spawn-site wiring (Tasks 5, 6, 8) and surface tasks (10, 12, 13, 14, 15) decompose cleanly along independent edges.
