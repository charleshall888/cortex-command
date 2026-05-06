# Plan: apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites

## Overview
Centralize all sandbox-settings construction, tempfile lifecycle, deny-set/allow-set composition, and Linux warning emission inside a single new `cortex_command/overnight/sandbox_settings.py` module that every spawn site imports as a shared library. The orchestrator spawn (`runner.py`), per-feature dispatch (`pipeline/dispatch.py`), and feature-executor base-path resolution (`feature_executor.py`) each become thin call sites that consume well-typed builder outputs from this layer; tests, docs, and tooling key off the same module.

**Architectural Pattern**: layered — a single `sandbox_settings` library layer sits beneath all three call sites and exposes typed builders so each site only invokes the layer (no event bus, no pipeline stages, no shared mutable state, no plug-in registration).

## Tasks

### Task 1: Create `sandbox_settings.py` module skeleton with builder signatures and constants
- **Files**: `cortex_command/overnight/sandbox_settings.py` (new)
- **What**: Establish the layer's public surface — builder function signatures, named constants, and the env-var contract — before any caller wires in.
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
    - `build_sandbox_settings_dict(deny_paths: list[str], soft_fail: bool) -> dict`
    - `build_dispatch_allow_paths(worktree_path: Path, integration_base_path: Path | None) -> list[str]`
    - `read_soft_fail_env() -> bool` (reads `os.environ` at call time per Req 4)
    - `write_settings_tempfile(session_dir: Path, settings: dict) -> Path` (uses `cortex_command.common.atomic_write`, mode 0o600, prefix/suffix/dir per spec Req 1)
    - `cleanup_stale_tempfiles(session_dir: Path, runner_start_ts: float) -> None`
    - `register_atexit_cleanup(tempfile_path: Path) -> None`
    - `emit_linux_warning_if_needed(stream: TextIO = sys.stderr) -> None`
- **Verification**: `python -c "from cortex_command.overnight import sandbox_settings; assert all(hasattr(sandbox_settings, n) for n in ['build_orchestrator_deny_paths','build_sandbox_settings_dict','build_dispatch_allow_paths','read_soft_fail_env','write_settings_tempfile','cleanup_stale_tempfiles','register_atexit_cleanup','emit_linux_warning_if_needed','SOFT_FAIL_ENV_VAR','GIT_DENY_SUFFIXES','OUT_OF_WORKTREE_ALLOW_WRITERS','LINUX_WARNING'])"` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 2: Implement deny-path builder + JSON-shape builder + soft-fail reader
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implement the deny-set construction (per-repo enumeration over `home_repo` + `integration_worktrees.keys()` joined with each `GIT_DENY_SUFFIXES`) and the full JSON-settings dict shape (Req 2 keys), plus the `os.environ`-reading `read_soft_fail_env`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - `build_sandbox_settings_dict` returns a dict shaped:
    - `sandbox.enabled: True`
    - `sandbox.failIfUnavailable: not soft_fail`
    - `sandbox.allowUnsandboxedCommands: False`
    - `sandbox.enableWeakerNestedSandbox: False`
    - `sandbox.enableWeakerNetworkIsolation: False`
    - `sandbox.filesystem.denyWrite: deny_paths`
    - `sandbox.filesystem.allowWrite: []`
  - `build_orchestrator_deny_paths` iterates `[home_repo, *integration_worktrees.values()]` (worktree paths, not repo keys, per Req 3 — the deny applies at the worktree's `.git/` location which on a `git worktree add`-created worktree is a `.git` file pointer, but per session-1708 evidence the orchestrator's Bash runs `git commit` against the actual repo). Iterate over distinct repo absolute paths (use `state.integration_worktrees.keys()` which are repo absolute paths per `state.py:228-230`). Confirm with spec Req 3 wording: "For each repo (home repo + each cross-repo via `state.integration_worktrees.keys()`)".
- **Verification**: `pytest tests/test_runner_sandbox.py::test_denyset_specific_git_paths tests/test_runner_sandbox.py::test_orchestrator_settings_json_shape tests/test_runner_sandbox.py::test_soft_fail_killswitch_set tests/test_runner_sandbox.py::test_soft_fail_killswitch_unset -v` exits 0 (tests authored in Task 11) — pass if exit 0.
- **Status**: [ ] pending

### Task 3: Implement tempfile lifecycle, atexit registration, startup-scan, and Linux warning
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implement `write_settings_tempfile` (creates `<session_dir>/sandbox-settings/` directory, atomic-writes JSON via `cortex_command.common.atomic_write`, returns path), `register_atexit_cleanup` (uses `atexit.register` patterned on `dashboard/app.py:237`), `cleanup_stale_tempfiles` (scans the directory, removes `cortex-sandbox-*.json` older than `runner_start_ts`), and `emit_linux_warning_if_needed` (one-shot guard via module-level flag; checks `sys.platform != "darwin"`).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Tempfile path: `tempfile.mkstemp(prefix="cortex-sandbox-", suffix=".json", dir=<session_dir>/sandbox-settings/)`. Mode chmod to 0o600 after creation.
  - `atomic_write` pattern at `cortex_command/common.py:498-522`.
  - Linux-warning module-level guard prevents repeated emission across multiple builder invocations within a single process.
- **Verification**: `pytest tests/test_runner_sandbox.py::test_tempfile_atexit_cleanup tests/test_runner_sandbox.py::test_tempfile_startup_scan_removes_stale tests/test_runner_sandbox.py::test_linux_warning_emitted tests/test_runner_sandbox.py::test_macos_no_warning -v` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 4: Wire `_spawn_orchestrator` to consume the sandbox_settings layer
- **Files**: `cortex_command/overnight/runner.py`
- **What**: Modify `_spawn_orchestrator` (lines 930-974) to accept `state: OvernightState` and `session_dir: Path`, build the deny-set + settings dict + tempfile via the layer, register atexit cleanup, and append `--settings <tempfile-path>` to the argv. Update the single call site at `runner.py:2103`.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**:
  - New `_spawn_orchestrator` signature: `(filled_prompt: str, coord: RunnerCoordination, spawned_procs: list[tuple[subprocess.Popen, str]], stdout_path: Path, state: OvernightState, session_dir: Path) -> tuple[subprocess.Popen, WatchdogContext, WatchdogThread]`.
  - Inside body: call `emit_linux_warning_if_needed()`, `build_orchestrator_deny_paths(home_repo=..., integration_worktrees=state.integration_worktrees)`, `build_sandbox_settings_dict(deny_paths, soft_fail=read_soft_fail_env())`, `write_settings_tempfile(session_dir, settings)`, `register_atexit_cleanup(tempfile_path)`. Insert `"--settings", str(tempfile_path)` into the argv list between `filled_prompt` and `--dangerously-skip-permissions`.
  - Home-repo path: derive from `state.project_root` (per `state.py:225`) when set, else `Path.cwd()`.
  - Call site at `runner.py:2103` — pass `state=state, session_dir=session_dir`. Both are already in the surrounding scope per `runner.py:2034-2064`.
  - Add startup-scan call near runner-init: invoke `cleanup_stale_tempfiles(session_dir, runner_start_ts=time.time())` once at runner entry (e.g., near the `session_dir` derivation in the runner's main entry function around `runner.py:1825-1870`).
- **Verification**: `pytest tests/test_runner_sandbox.py::test_orchestrator_spawn_includes_settings_flag -v` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 5: Convert `dispatch.py` to typed `SandboxSettings` SDK field with TMPDIR locking
- **Files**: `cortex_command/pipeline/dispatch.py`
- **What**: Replace the stringly-typed `sandbox.write.allowOnly` shape (lines 536-549, 567) with `ClaudeAgentOptions(sandbox=SandboxSettings(filesystem=SandboxFilesystemSettings(allowWrite=...)))` typed field. Remove the project-settings blob injection (`_load_project_settings` no longer feeds `settings=`). Add `TMPDIR=$TMPDIR` to the `_env` dict.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - Imports needed (top of file): `from claude_agent_sdk import SandboxSettings, SandboxFilesystemSettings`. (Existing `ClaudeAgentOptions` import remains.)
  - `_write_allowlist` constructed via `build_dispatch_allow_paths(worktree_path, integration_base_path)` from sandbox_settings layer; the layer extends with the six `OUT_OF_WORKTREE_ALLOW_WRITERS` entries (expanded via `os.path.expanduser` and `$TMPDIR` resolution).
  - `_load_project_settings` retained on disk but no longer called from the dispatch builder; only natural multi-scope merge from project scope applies (Req 6).
  - `_env` dict gains `"TMPDIR": os.environ.get("TMPDIR", "/tmp")`.
  - `ClaudeAgentOptions(...)` call: drop `settings=_worktree_settings`; add `sandbox=SandboxSettings(filesystem=SandboxFilesystemSettings(allowWrite=_write_allowlist))`.
  - `read_soft_fail_env()` consulted at this call site too — when soft-fail is on, set `failIfUnavailable=False` on the `SandboxSettings` (or omit so defaults apply); spec Req 4 mandates per-dispatch re-read.
- **Verification**: `pytest tests/test_dispatch.py::test_typed_sandbox_field_used tests/test_dispatch.py::test_dispatched_env_locks_tmpdir tests/test_dispatch.py::test_no_blob_injection tests/test_dispatch.py::test_sdk_typed_sandbox_symbols_present -v` exits 0 AND `grep -c "SandboxSettings\|SandboxFilesystemSettings" cortex_command/pipeline/dispatch.py` returns ≥ 1 — pass if both pass.
- **Status**: [ ] pending

### Task 6: Fix cross-repo `integration_base_path` at `feature_executor.py:603`
- **Files**: `cortex_command/overnight/feature_executor.py`
- **What**: Replace unconditional `integration_base_path=Path.cwd()` with a conditional that consults `state.integration_worktrees` via the canonical `_normalize_repo_key` helper from `outcome_router.py:115-195` when `repo_path is not None`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Import `_normalize_repo_key` from `cortex_command.overnight.outcome_router`.
  - The line `integration_base_path=Path.cwd()` becomes a value derived from: `Path(state.integration_worktrees[_normalize_repo_key(str(repo_path))])` when `repo_path is not None`, else `Path.cwd()`.
  - `state` is available in the surrounding scope (the executor receives state through its config object); confirm by reading the caller signature in `feature_executor.py` around lines 580-610.
- **Verification**: `pytest tests/test_feature_executor.py::test_cross_repo_uses_integration_worktree tests/test_feature_executor.py::test_same_repo_uses_cwd -v` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 7: Migrate tool-failure-tracker hook + readers from `/tmp/` to `$TMPDIR/`
- **Files**: `claude/hooks/cortex-tool-failure-tracker.sh`, `cortex_command/overnight/report.py` (lines 246, 1094, 1159 per spec Req 19)
- **What**: Replace `/tmp/claude-tool-failures-${SESSION_KEY}` with `${TMPDIR:-/tmp}/claude-tool-failures-${SESSION_KEY}` in the hook (line 44); update the three reader sites in `report.py` to construct the path via `os.environ.get("TMPDIR", "/tmp")`.
- **Depends on**: none
- **Complexity**: trivial
- **Context**:
  - Hook line 44: shell parameter expansion `${TMPDIR:-/tmp}`.
  - `report.py:246` and `report.py:1094` both construct `Path(f"/tmp/claude-tool-failures-{session_id}")`; update both to read `TMPDIR` from env.
  - `report.py:1159` is in a docstring; update the docstring text to reflect new path.
- **Verification**: `grep -c "/tmp/claude-tool-failures" claude/hooks/cortex-tool-failure-tracker.sh` returns 0 AND `grep -c '\${TMPDIR:-/tmp}/claude-tool-failures' claude/hooks/cortex-tool-failure-tracker.sh` returns ≥ 1 AND `grep -c '"/tmp/claude-tool-failures"' cortex_command/overnight/report.py` returns 0 — pass if all three conditions hold.
- **Status**: [ ] pending

### Task 8: Add morning-report soft-fail header surfacing + events.log entry
- **Files**: `cortex_command/overnight/report.py`, `cortex_command/overnight/sandbox_settings.py` (event emission helper)
- **What**: When the soft-fail env var is read truthy at any builder invocation, the layer emits a `sandbox_soft_fail_active` event into `<session_dir>/events.log` (first activation only). The morning-report builder reads events.log and emits the unconditional header line per Req 20.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Layer adds: `record_soft_fail_event(session_dir: Path) -> None` — writes a single line `{"event": "sandbox_soft_fail_active", "ts": "<iso8601>"}` to `<session_dir>/events.log` (idempotent: skip if line already present).
  - Both `_spawn_orchestrator` (Task 4) and `dispatch.py` (Task 5) call `record_soft_fail_event(session_dir)` when `read_soft_fail_env()` returns True.
  - `report.py` morning-report builder gains a function that scans events.log for `sandbox_soft_fail_active`; if present, emit header `"CORTEX_SANDBOX_SOFT_FAIL=1 was active for this session; sandbox.failIfUnavailable was downgraded to false."` at top of report.
- **Verification**: `pytest tests/test_morning_report.py::test_soft_fail_header_emitted tests/test_morning_report.py::test_no_soft_fail_no_header -v` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 9: Author behavior-level test suite for sandbox_settings layer
- **Files**: `tests/test_runner_sandbox.py` (new)
- **What**: Write the test functions named in spec Reqs 1, 2, 3, 4, 8, 11, 18 plus the synthetic-EPERM (Req 9) and precedence-overlap (Req 16) tests (both `sandbox-exec` PRIMARY + `srt` SECONDARY variants).
- **Depends on**: [2, 3, 4]
- **Complexity**: complex
- **Context**:
  - Test functions to author (names per spec acceptance lines):
    - `test_orchestrator_spawn_includes_settings_flag` (mock `subprocess.Popen`, assert argv contains `--settings <existing-path>`)
    - `test_orchestrator_settings_json_shape` (assert exact dict shape from Req 2)
    - `test_denyset_specific_git_paths` (Req 3 — assert all entries match the four `.git/*` suffixes; no bare repo roots)
    - `test_soft_fail_killswitch_set` / `test_soft_fail_killswitch_unset` / `test_soft_fail_per_dispatch_re_read` (Req 4)
    - `test_denyset_recomputed_per_dispatch` (Req 8)
    - `test_tempfile_atexit_cleanup` (call `atexit._run_exitfuncs()`)
    - `test_tempfile_startup_scan_removes_stale`
    - `test_linux_warning_emitted` / `test_macos_no_warning` (mock `sys.platform`, capture stderr)
    - `test_synthetic_kernel_eperm_under_sandbox_exec` (PRIMARY, blocking on Darwin; invokes `/usr/bin/sandbox-exec` with a Seatbelt SBPL profile equivalent to a deny on a temp file; asserts non-zero exit + `"Operation not permitted"` in stderr + target untouched)
    - `test_synthetic_kernel_eperm_under_srt` (SECONDARY; `pytest.skip("sandbox-runtime CLI not installed; sandbox-exec test provides hard coverage")` when `srt` not on `PATH`)
    - `test_denywrite_overrides_allowwrite_under_sandbox_exec` (PRIMARY, blocking)
    - `test_denywrite_overrides_allowwrite_under_srt` (SECONDARY, skip-allowed)
  - Test pattern reference: existing `cortex_command/pipeline/tests/test_dispatch.py` for SDK-mock structure.
- **Verification**: `pytest tests/test_runner_sandbox.py -v` exits 0 (synthetic `srt` tests may report as `skipped` but no failures) — pass if exit 0 and `test_synthetic_kernel_eperm_under_sandbox_exec` + `test_denywrite_overrides_allowwrite_under_sandbox_exec` show as `passed` (not skipped) on Darwin.
- **Status**: [ ] pending

### Task 10: Author dispatch + feature-executor + morning-report tests
- **Files**: `tests/test_dispatch.py` (extend), `tests/test_feature_executor.py` (new or extend existing fixture), `tests/test_morning_report.py` (extend)
- **What**: Add the four `test_dispatch.py` test functions, the two `test_feature_executor.py` test functions, and the two `test_morning_report.py` test functions named in spec acceptance criteria.
- **Depends on**: [5, 6, 8]
- **Complexity**: simple
- **Context**:
  - `tests/test_dispatch.py`: add `test_typed_sandbox_field_used`, `test_dispatched_env_locks_tmpdir`, `test_no_blob_injection`, `test_sdk_typed_sandbox_symbols_present`. SDK-import test imports `SandboxSettings`, `SandboxFilesystemSettings` from real `claude_agent_sdk` (not mocked) and asserts class accepts the documented kwargs.
  - `tests/test_feature_executor.py`: add `test_cross_repo_uses_integration_worktree`, `test_same_repo_uses_cwd`. Construct `OvernightState` fixture with populated `integration_worktrees` mapping; mock `dispatch_task` to capture `integration_base_path`.
  - `tests/test_morning_report.py`: add `test_soft_fail_header_emitted` (events.log fixture with `sandbox_soft_fail_active`) and `test_no_soft_fail_no_header`.
- **Verification**: `pytest tests/test_dispatch.py tests/test_feature_executor.py tests/test_morning_report.py -v` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 11: Update three documentation surfaces
- **Files**: `docs/overnight-operations.md`, `docs/pipeline.md`, `docs/sdk.md`
- **What**: Apply the doc updates from spec Req 13: remove "no permissions sandbox" claim from overnight-operations:23; add "Per-spawn sandbox enforcement" section there; add "Sandbox shape" + "Allowed write paths" subsections in pipeline.md; corrective edit on sdk.md:199.
- **Depends on**: [4, 5]
- **Complexity**: simple
- **Context**:
  - `docs/overnight-operations.md:23`: remove the parenthetical "no permissions sandbox" string.
  - New `docs/overnight-operations.md` section "Per-spawn sandbox enforcement" describes: orchestrator deny-set (4 git-path suffixes per repo), dispatch allow-set (worktree + 6 OUT_OF_WORKTREE_ALLOW_WRITERS), `CORTEX_SANDBOX_SOFT_FAIL` kill-switch, threat-model boundary (Bash-only; Write/Edit/MCP bypass per Anthropic [#26616](https://github.com/anthropics/claude-code/issues/26616) and https://code.claude.com/docs/en/sandboxing).
  - `docs/pipeline.md` "Sandbox shape" subsection: documents `sandbox.filesystem.{allowWrite,denyWrite}` post-conversion. "Allowed write paths" subsection enumerates each of the 6 entries with one-sentence rationale per Req 10.
  - `docs/sdk.md:199`: replace the asymmetric-claim string ("does not constrain what a Bash subprocess can do") with the corrected text per #26616 inversion; cross-link to overnight-operations.md.
- **Verification**: All five grep conditions from spec Req 13 acceptance pass — `grep -c "Per-spawn sandbox enforcement" docs/overnight-operations.md` ≥ 1 AND `grep -c "no permissions sandbox" docs/overnight-operations.md` == 0 AND `grep -cE "Sandbox shape|Allowed write paths" docs/pipeline.md` ≥ 2 AND `grep -c "code.claude.com/docs/en/sandboxing" docs/overnight-operations.md` ≥ 1 AND `grep -c "does not constrain what a Bash subprocess" docs/sdk.md` == 0 — pass if all five.
- **Status**: [ ] pending

### Task 12: Extend `bin/cortex-check-parity` (or sibling hook) with SDK-pin + sandbox-source-file pre-flight gate
- **Files**: `bin/cortex-check-parity` (extend), `lifecycle/archive/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md` (new artifact)
- **What**: Add a pre-commit-level check that any change to `pyproject.toml` (specifically the `claude-agent-sdk` pin), `cortex_command/overnight/sandbox_settings.py`, `cortex_command/pipeline/dispatch.py:84-112`, or `cortex_command/overnight/runner.py` (specifically `_spawn_orchestrator`) must be accompanied by a `lifecycle/{feature}/preflight.md` containing a `PASS:` line dated within 24h of the commit timestamp. Author the initial preflight.md artifact with PASS line from the human pre-flight run.
- **Depends on**: [4, 5]
- **Complexity**: complex
- **Context**:
  - `bin/cortex-check-parity` currently does SKILL.md-to-bin parity. Add a new check function `_check_sandbox_preflight_gate()` that:
    - Inspects `git diff --cached --name-only` (when run as pre-commit) or `git diff <ref>...HEAD --name-only` (when invoked standalone).
    - If any of {`pyproject.toml`, the three sandbox-source files} changed AND no `lifecycle/*/preflight.md` contains a `PASS:` line dated within the last 24h, exit non-zero with a diagnostic message.
  - `preflight.md` schema: first line `# Pre-flight verification`; required line `^PASS: <ISO-8601 timestamp> <claude --version output> <stderr excerpt>`.
  - The initial human-run preflight (executing `claude -p "$PROMPT" --settings <denying-tempfile> --dangerously-skip-permissions --max-turns 3` per Req 12) recorded into the file.
- **Verification**: `bin/cortex-check-parity` exits non-zero against a fixture commit that bumps the SDK pin without a fresh `PASS:` line; exits 0 against the same diff with a fresh PASS line. Verify with: `cd $(mktemp -d) && git init && git commit --allow-empty -m init && (printf 'claude-agent-sdk>=0.1.47,<0.1.48\n' > pyproject.toml; git add pyproject.toml) && /Users/charlie.hall/Workspaces/cortex-command/bin/cortex-check-parity` returns non-zero — pass if non-zero exit code.
- **Status**: [ ] pending

### Task 13: Run full test suite + dry-run snapshot regression check
- **Files**: none modified; verification-only task
- **What**: Run `just test` end-to-end and verify the `tests/fixtures/dry_run_reference.txt` byte-identical snapshot does not regress (per `requirements/pipeline.md:27`). If sandbox-tempfile creation logging surfaces in dry-run output, suppress in dry-run mode rather than updating the snapshot.
- **Depends on**: [4, 5, 6, 7, 8, 9, 10, 11]
- **Complexity**: simple
- **Context**:
  - `just test` is the canonical test entry per `CLAUDE.md` Commands section.
  - Dry-run snapshot at `tests/fixtures/dry_run_reference.txt` per `requirements/pipeline.md:27`.
- **Verification**: `just test` exits 0 — pass if exit 0.
- **Status**: [ ] pending

### Task 14: CLAUDE.md 100-line cap check
- **Files**: `CLAUDE.md`, `docs/policies.md` (created only if cap crossed)
- **What**: Per spec Req 14, verify CLAUDE.md remains ≤ 100 lines after this work. If any documentation change in this feature added a policy entry that crosses the cap, extract OQ3 + OQ6 + the new entry into `docs/policies.md` and replace the entries in CLAUDE.md with `Policy entries: see docs/policies.md`. (Likely no-op for this feature since policy entries are not added — sandbox config is config, not prose escalation per spec line 175.)
- **Depends on**: [11]
- **Complexity**: trivial
- **Context**:
  - Current CLAUDE.md line count: 68 (per spec line 81).
  - Threshold check: line that crosses 100 triggers extraction.
- **Verification**: `[ $(wc -l < CLAUDE.md) -le 100 ]` exits 0 — pass if exit 0.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification proceeds in three layers:

1. **Unit + behavior tests via `just test`**: Tasks 9 + 10 cover all 20 spec Requirements at the unit-of-behavior level, including the dual-mechanism kernel-EPERM tests (Req 9) and precedence-overlap tests (Req 16) using `sandbox-exec` (PRIMARY, blocking) and `srt` (SECONDARY, skip-allowed). The synthetic kernel tests are the hard line of defense against shape regressions inside CI.
2. **Human pre-flight gate (Req 12)**: a clean non-sandboxed terminal runs `claude -p "$PROMPT" --settings <denying-tempfile> --dangerously-skip-permissions --max-turns 3` against an instructed-Bash-write-attempt prompt; expects non-zero exit, "Operation not permitted" in stderr, target file unchanged. Result recorded with `PASS:` line into `lifecycle/{feature}/preflight.md`. PR cannot merge without a `PASS:` line — verified by `grep -E '^PASS:' lifecycle/.../preflight.md` returning a match.
3. **Pre-commit gate (Req 17)**: `bin/cortex-check-parity` extension blocks future commits that touch sandbox source files or the SDK pin without a fresh PASS line, ensuring drift is caught at code-change time. Verified by Task 12's fixture-commit test.

## Sizing

14 tasks, target 5-15 minutes each; complex tasks (5, 9, 12) may approach 20 minutes due to SDK-typed-field migration, dual-mechanism Seatbelt test authoring, and pre-commit-gate logic. Each task touches ≤ 5 files. All tasks have explicit `Depends on` fields — Tasks 1, 6, 7 are independent; remainder chain through the layer module (1 → 2, 3 → 4 → 11 → 14; 2 → 5, 8 → 10; 4, 5 → 9, 12, 13).
