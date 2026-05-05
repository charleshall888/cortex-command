# Plan: apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites

## Overview
Centralize sandbox-policy state (deny-set construction, kill-switch flag, soft-fail tracking, tempfile registry, platform warning latch) into a single `SandboxPolicyContext` shared-state object owned by the runner and consulted at every spawn site (orchestrator, per-feature dispatch, retry, morning-report). Each spawn site reads the same context object and produces its scope-appropriate JSON via the same builder methods, so shape divergence between orchestrator and dispatch paths becomes structurally impossible.

**Architectural Pattern**: shared-state — a single `SandboxPolicyContext` instance is passed by reference into every spawn-site code path and morning-report builder, so all sandbox decisions read from one mutable in-memory object rather than being computed independently per layer (variant A's layered approach) or routed through stage transformers (a pipeline variant).

## Tasks

### Task 1: Define `SandboxPolicyContext` shared-state object and module skeleton
- **Files**: `cortex_command/overnight/sandbox_settings.py` (new)
- **What**: Create the new module with the `SandboxPolicyContext` dataclass that all spawn sites will share, plus stub functions that later tasks will fill in.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - New module per spec "Changes to Existing Behavior" / Req 1, 2, 3, 4, 8, 11, 18.
  - Dataclass `SandboxPolicyContext` fields: `session_dir: Path`, `runner_start_ts: float`, `home_repo: Path`, `tempfile_registry: list[Path]`, `soft_fail_observed: bool`, `linux_warning_emitted: bool`, `events_log_path: Path | None`.
  - Function signatures (bodies in later tasks):
    - `build_orchestrator_settings(ctx: SandboxPolicyContext, state) -> dict`
    - `build_dispatch_sandbox(ctx: SandboxPolicyContext, state, worktree_path: Path, integration_base_path: Path | None, repo_path: str | None) -> tuple[SandboxSettings, dict[str, str]]` (returns typed SDK field + env dict including `TMPDIR`)
    - `write_settings_tempfile(ctx: SandboxPolicyContext, payload: dict) -> Path`
    - `build_denyset(state, home_repo: Path) -> list[str]`
    - `cleanup_stale_tempfiles(session_dir: Path, runner_start_ts: float) -> None`
    - `emit_linux_warning_once(ctx: SandboxPolicyContext) -> None`
    - `record_soft_fail(ctx: SandboxPolicyContext) -> None`
  - Pattern reference: dataclass + module-level helpers like `cortex_command/overnight/state.py` (`session_dir` function near line 305).
- **Verification**: `python -c "from cortex_command.overnight.sandbox_settings import SandboxPolicyContext, build_orchestrator_settings, build_dispatch_sandbox, write_settings_tempfile, build_denyset, cleanup_stale_tempfiles, emit_linux_warning_once, record_soft_fail"` — pass if exit 0.
- **Status**: [ ] pending

### Task 2: Implement deny-set builder + kill-switch + JSON shape (Reqs 2, 3, 4, 8)
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implement `build_denyset` (four git-state paths per repo across home + `state.integration_worktrees`) and the JSON-payload builder used by both orchestrator-spawn and per-dispatch paths; reads `os.environ["CORTEX_SANDBOX_SOFT_FAIL"]` at every invocation (per-dispatch re-read per Req 4 last clause).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Per-repo deny entries: `<repo>/.git/refs/heads/main`, `<repo>/.git/refs/heads/master`, `<repo>/.git/HEAD`, `<repo>/.git/packed-refs` (Req 3).
  - Iterate `state.integration_worktrees.keys()` (cross-repo paths) plus the home repo path.
  - JSON shape (Req 2): `sandbox.enabled=true`, `sandbox.failIfUnavailable=(env not set)`, `sandbox.allowUnsandboxedCommands=false`, `sandbox.enableWeakerNestedSandbox=false`, `sandbox.enableWeakerNetworkIsolation=false`, `sandbox.filesystem.denyWrite=[...]`, `sandbox.filesystem.allowWrite=[]`.
  - Env-var read: `os.environ.get("CORTEX_SANDBOX_SOFT_FAIL") == "1"` flips `failIfUnavailable` to `false` AND calls `record_soft_fail(ctx)` so morning-report (Task 11) can surface it.
  - Re-compute on every call (no caching) — satisfies Req 8 freshness.
- **Verification**: `grep -cE "refs/heads/main|refs/heads/master|\.git/HEAD|packed-refs" cortex_command/overnight/sandbox_settings.py` — pass if count >= 4.
- **Status**: [ ] pending

### Task 3: Implement tempfile lifecycle + atexit + startup-scan (Req 11)
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implement `write_settings_tempfile` (tempfile under `<session_dir>/sandbox-settings/`, mode 0o600, registers in `ctx.tempfile_registry` and via `atexit.register`) and `cleanup_stale_tempfiles` (startup-scan removing `cortex-sandbox-*.json` older than `runner_start_ts`).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Use `tempfile.mkstemp(prefix="cortex-sandbox-", suffix=".json", dir=<session_dir>/sandbox-settings/)`.
  - Write via `cortex_command.common.atomic_write` (`common.py:482`) per `requirements/pipeline.md:21,126`.
  - `atexit.register` pattern parallels `cortex_command/dashboard/app.py:237` PID-file unlink.
  - Startup scan: iterate `<session_dir>/sandbox-settings/cortex-sandbox-*.json`, `os.stat().st_mtime < runner_start_ts` ⇒ unlink; tolerate FileNotFoundError.
- **Verification**: `python -c "import inspect; from cortex_command.overnight import sandbox_settings as m; assert 'mkstemp' in inspect.getsource(m.write_settings_tempfile); assert 'st_mtime' in inspect.getsource(m.cleanup_stale_tempfiles)"` — pass if exit 0.
- **Status**: [ ] pending

### Task 4: Implement Linux startup warning (Req 18)
- **Files**: `cortex_command/overnight/sandbox_settings.py`
- **What**: Implement `emit_linux_warning_once` which checks `sys.platform != "darwin"` and emits the exact stderr string once per `SandboxPolicyContext` (idempotent via `ctx.linux_warning_emitted` latch).
- **Depends on**: [1]
- **Complexity**: trivial
- **Context**:
  - Exact warning string per Req 18: `"WARNING: cortex sandbox enforcement is macOS-Seatbelt-only; Linux/bwrap behavior is undefined per parent epic #162. Sandbox configuration may not enforce as documented."`
  - Latch ensures one-line emission across the session even if helper is called from multiple spawn sites.
- **Verification**: `grep -c "sandbox enforcement is macOS-Seatbelt-only" cortex_command/overnight/sandbox_settings.py` — pass if count >= 1.
- **Status**: [ ] pending

### Task 5: Wire `SandboxPolicyContext` into runner orchestrator spawn (Reqs 1, 11, 18)
- **Files**: `cortex_command/overnight/runner.py`
- **What**: Construct one `SandboxPolicyContext` early in runner-init, run `cleanup_stale_tempfiles`, call `emit_linux_warning_once`, pass `ctx` into `_spawn_orchestrator`, and have that function call `build_orchestrator_settings(ctx, state)` + `write_settings_tempfile(ctx, payload)` and append `--settings <path>` to the Popen argv.
- **Depends on**: [2, 3, 4]
- **Complexity**: complex
- **Context**:
  - `_spawn_orchestrator` at `runner.py:930-974`. Add `state` and `ctx` parameters. Argv site at `runner.py:946-963`.
  - `session_dir` resolved via `cortex_command.overnight.state.session_dir(session_id)` (`state.py:305`).
  - Construct `ctx` once at runner-start (parallel to where `coord` and `spawned_procs` are constructed); thread by reference.
  - Existing finally/cleanup block at `runner.py:2417-2426` is left in place; tempfile cleanup happens via atexit registration done inside `write_settings_tempfile`.
  - All callers of `_spawn_orchestrator` updated to pass `state` + `ctx`.
- **Verification**: `grep -A 30 "def _spawn_orchestrator" cortex_command/overnight/runner.py | grep -c '"--settings"'` — pass if count >= 1.
- **Status**: [ ] pending

### Task 6: Convert dispatch.py to typed `SandboxSettings` + extract sandbox-only subtree (Reqs 5, 6, 10)
- **Files**: `cortex_command/pipeline/dispatch.py`
- **What**: Replace the stringly-typed `settings=_worktree_settings` (`dispatch.py:567`) with `sandbox=SandboxSettings(filesystem=SandboxFilesystemSettings(allowWrite=[...]))`; stop force-injecting the merged project blob from `_load_project_settings`; lock `TMPDIR` into the dispatched env; include the six risk-targeted writers from Req 10 in `allowWrite`.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Modify `_load_project_settings` (`dispatch.py:84-112`) to extract only `result.get("sandbox", {})` — return sandbox subtree, NOT the full merged blob.
  - `_write_allowlist` construction at `dispatch.py:536-549`: keep worktree + integration-base entries, add the six entries from Req 10 (`~/.cache/uv/`, `$TMPDIR/`, `~/.claude/sessions/`, `~/.cache/cortex/`, `~/.cache/cortex-command/`, `~/.local/share/overnight-sessions/`).
  - Import `SandboxSettings`, `SandboxFilesystemSettings` from `claude_agent_sdk` (verify via Task 13 symbol-import test).
  - `_env` dict extended with `"TMPDIR": os.environ.get("TMPDIR") or tempfile.gettempdir()` to prevent unset-fallback to `/tmp/`.
  - `ClaudeAgentOptions(...)` construction at `dispatch.py:558-570`: drop `settings=` kwarg; add `sandbox=SandboxSettings(...)`.
- **Verification**: `grep -c "SandboxSettings\|SandboxFilesystemSettings" cortex_command/pipeline/dispatch.py` — pass if count >= 2; `grep -c '"sandbox": {"write": {"allowOnly"' cortex_command/pipeline/dispatch.py` — pass if count == 0.
- **Status**: [ ] pending

### Task 7: Fix cross-repo `integration_base_path` inversion (Req 7)
- **Files**: `cortex_command/overnight/feature_executor.py`
- **What**: Replace unconditional `Path.cwd()` at `feature_executor.py:603` with conditional resolution using `state.integration_worktrees[_normalize_repo_key(str(repo_path))]` when `repo_path is not None`, falling back to `Path.cwd()` only for home-repo.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - Use `_effective_merge_repo_path` from `cortex_command/overnight/outcome_router.py:115-195` rather than re-implementing key normalization.
  - `repo_path` is in scope on `feature_executor.py:604` already (per research).
  - Same correction must propagate to any retry-loop callers in `cortex_command/pipeline/retry.py` if they construct an `integration_base_path` (audit at task time).
- **Verification**: `grep -B 2 -A 2 "integration_base_path" cortex_command/overnight/feature_executor.py | grep -c "Path.cwd()"` — pass if count <= 1 (one remaining as the home-repo fallback inside the conditional).
- **Status**: [ ] pending

### Task 8: Migrate `cortex-tool-failure-tracker.sh` and report.py readers to `$TMPDIR` (Req 19)
- **Files**: `claude/hooks/cortex-tool-failure-tracker.sh`, `cortex_command/overnight/report.py`
- **What**: Replace `/tmp/claude-tool-failures-*` with `${TMPDIR:-/tmp}/claude-tool-failures-*` in the shell hook (line 44); update the three reader sites in `report.py` (lines 246, 1094, 1159) to use `os.environ.get("TMPDIR", "/tmp")`-based paths.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Shell migration: `TRACK_DIR="${TMPDIR:-/tmp}/claude-tool-failures-${SESSION_KEY}"`.
  - Python migration: replace `Path(f"/tmp/claude-tool-failures-{session_id}")` with a helper that consults `os.environ.get("TMPDIR", "/tmp")`.
- **Verification**: `grep -c "/tmp/claude-tool-failures" claude/hooks/cortex-tool-failure-tracker.sh cortex_command/overnight/report.py` — pass if total count == 0.
- **Status**: [ ] pending

### Task 9: Tests — settings shape, kill-switch, recompute, tempfile lifecycle, Linux warning (Reqs 2, 3, 4, 8, 11, 18)
- **Files**: `tests/test_runner_sandbox.py` (new)
- **What**: Add unit tests covering the shared-state-object behaviors: `test_orchestrator_spawn_includes_settings_flag`, `test_orchestrator_settings_json_shape`, `test_denyset_specific_git_paths`, `test_soft_fail_killswitch_set`, `test_soft_fail_killswitch_unset`, `test_soft_fail_per_dispatch_re_read`, `test_denyset_recomputed_per_dispatch`, `test_tempfile_atexit_cleanup`, `test_tempfile_startup_scan_removes_stale`, `test_linux_warning_emitted`, `test_macos_no_warning`.
- **Depends on**: [2, 3, 4, 5]
- **Complexity**: complex
- **Context**:
  - Test pattern reference: `tests/test_runner_morning_report_commit.py` (uses `tmp_path` fixture, monkeypatches `subprocess.run`).
  - Each test instantiates `SandboxPolicyContext` with a tmp_path session_dir; calls the appropriate builder; asserts JSON shape via `json.loads`.
  - `subprocess.Popen` mocked via `monkeypatch.setattr` to capture argv; assert `"--settings"` appears in captured argv.
  - `atexit._run_exitfuncs()` invoked explicitly in the cleanup test.
  - Linux warning test: `monkeypatch.setattr(sys, "platform", "linux")` + `capsys.readouterr().err` assertion.
- **Verification**: `pytest tests/test_runner_sandbox.py -v` — pass if exit 0 and all listed tests pass.
- **Status**: [ ] pending

### Task 10: Tests — dispatch typed-field, blob-extraction, TMPDIR lock, SDK symbol-import (Reqs 5, 6, 15)
- **Files**: `tests/test_dispatch.py` (existing or new under `cortex_command/overnight/tests/`; check existing `cortex_command/overnight/tests/test_dispatch.py`)
- **What**: Add `test_typed_sandbox_field_used` (asserts `options.sandbox` is a `SandboxSettings`, no `sandbox` key in `options.settings`), `test_dispatched_env_locks_tmpdir`, `test_no_blob_injection` (fixture `.claude/settings.local.json` with `hooks`/`env`, asserts they don't appear in dispatched options), and `test_sdk_typed_sandbox_symbols_present` (real SDK import — not mocked).
- **Depends on**: [6]
- **Complexity**: complex
- **Context**:
  - Test for SDK symbol presence imports directly from the installed package: `from claude_agent_sdk import SandboxSettings, SandboxFilesystemSettings` and asserts they accept the expected kwargs (catches pin-bump drift, Req 15).
  - Mock the SDK call (`claude_agent_sdk.query` or whatever dispatch uses) via `monkeypatch`; capture the `ClaudeAgentOptions` argument.
  - Reference existing dispatch test at `cortex_command/overnight/tests/test_dispatch.py` for fixture patterns.
- **Verification**: `pytest -k "test_typed_sandbox_field_used or test_dispatched_env_locks_tmpdir or test_no_blob_injection or test_sdk_typed_sandbox_symbols_present" -v` — pass if exit 0 and all four tests pass (not skipped).
- **Status**: [ ] pending

### Task 11: Tests — synthetic kernel-EPERM under sandbox-exec + srt (Reqs 9, 16)
- **Files**: `tests/test_runner_sandbox.py`
- **What**: Add `test_synthetic_kernel_eperm_under_sandbox_exec` (PRIMARY, blocking on Darwin), `test_synthetic_kernel_eperm_under_srt` (SECONDARY, opportunistic skip when `srt` not on PATH), `test_denywrite_overrides_allowwrite_under_sandbox_exec`, `test_denywrite_overrides_allowwrite_under_srt`.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - `sandbox-exec` invocation: build a Seatbelt SBPL profile equivalent to the cortex deny-JSON; spawn `sandbox-exec -p <profile> sh -c 'echo > <denied-path>'`; assert non-zero exit + stderr `"Operation not permitted"` + target file does not exist.
  - `srt` invocation: write cortex-shape JSON to a tempfile; `subprocess.run(["srt", "--settings", path, "--", "sh", "-c", "echo > <denied>"])`; same assertions.
  - `pytest.skip("sandbox-runtime CLI not installed; sandbox-exec test provides hard coverage")` only allowed in the `srt` test branch when `shutil.which("srt") is None`.
  - macOS-required: tests must NOT skip on Darwin; use `pytest.mark.skipif(sys.platform != "darwin", reason="...")` only at module/test level for non-macOS.
- **Verification**: `pytest tests/test_runner_sandbox.py::test_synthetic_kernel_eperm_under_sandbox_exec tests/test_runner_sandbox.py::test_denywrite_overrides_allowwrite_under_sandbox_exec -v` — pass if exit 0 and both report PASSED (not SKIPPED) on the canonical macOS dev environment.
- **Status**: [ ] pending

### Task 12: Tests — feature_executor cross-repo + morning-report soft-fail header (Reqs 7, 20)
- **Files**: `cortex_command/overnight/tests/test_feature_executor_boundary.py` (existing) or new `tests/test_morning_report.py`
- **What**: Add `test_cross_repo_uses_integration_worktree`, `test_same_repo_uses_cwd`, `test_soft_fail_header_emitted`, `test_no_soft_fail_no_header`. Wire morning-report builder in `cortex_command/overnight/report.py` to read `sandbox_soft_fail_active` events from events.log and emit the exact header string from Req 20.
- **Depends on**: [7]
- **Complexity**: complex
- **Context**:
  - Header text per Req 20: `"CORTEX_SANDBOX_SOFT_FAIL=1 was active for this session; sandbox.failIfUnavailable was downgraded to false."`.
  - Event emission: `record_soft_fail(ctx)` (Task 2) calls `log_event(ctx.events_log_path, {"event": "sandbox_soft_fail_active", ...})` via the existing `log_event` helper at `cortex_command/overnight/events.py:194`.
  - Morning-report builder reads events.log; if any event with `event == "sandbox_soft_fail_active"` exists, prepend the header.
  - Test fixture: write a JSONL events.log with/without the event; invoke the morning-report builder; assert presence/absence of the header substring.
- **Verification**: `pytest -k "test_cross_repo_uses_integration_worktree or test_same_repo_uses_cwd or test_soft_fail_header_emitted or test_no_soft_fail_no_header" -v` — pass if exit 0 and all four tests pass.
- **Status**: [ ] pending

### Task 13: Extend `cortex-check-parity` for SDK-pin / sandbox-source-file change gating (Req 17)
- **Files**: `bin/cortex-check-parity` (existing)
- **What**: Add a check that fires if a commit modifies `pyproject.toml` (specifically the `claude-agent-sdk` pin), `cortex_command/overnight/sandbox_settings.py`, `cortex_command/pipeline/dispatch.py` (lines containing `_load_project_settings`), or `cortex_command/overnight/runner.py` (lines in `_spawn_orchestrator`) without a fresh `PASS:` line in `lifecycle/{feature}/preflight.md` dated within 24h of commit time. Non-zero exit blocks commit.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Read existing `bin/cortex-check-parity` to identify the rule-registration extension point (around `SELF_REFERENCE` at line 62).
  - Use `git diff --cached --name-only` to detect staged files.
  - Read preflight.md mtime via `os.stat`; compare to `time.time() - 86400` for 24h freshness.
  - Pre-commit wiring: confirm the parity hook is already invoked from `.git/hooks/pre-commit` per `just setup-githooks`; if not, this task adds it.
- **Verification**: Construct a temp git repo with a commit that bumps the SDK pin without touching preflight.md; run `bin/cortex-check-parity`; assert non-zero exit. Specifically: `cd $TMPDIR/parity-test && git init && touch lifecycle/x/preflight.md && (echo 'claude-agent-sdk>=0.1.47,<0.1.48' >> pyproject.toml) && git add -A && bin/cortex-check-parity; echo $?` — pass if exit code is non-zero.
- **Status**: [ ] pending

### Task 14: Documentation updates across `docs/overnight-operations.md`, `docs/pipeline.md`, `docs/sdk.md` (Req 13, 10)
- **Files**: `docs/overnight-operations.md`, `docs/pipeline.md`, `docs/sdk.md`
- **What**: Remove "no permissions sandbox" claim from `overnight-operations.md:23`; add "Per-spawn sandbox enforcement" section; add "Sandbox shape" + "Allowed write paths" subsections to `pipeline.md`; corrective edit on `sdk.md:199` per Req 13 inversion.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - Cross-link rather than duplicate per CLAUDE.md doc-source convention.
  - Threat-model boundary section in `overnight-operations.md` references Anthropic issues #26616 and #29048 and the official sandboxing docs at https://code.claude.com/docs/en/sandboxing.
  - "Allowed write paths" subsection in `pipeline.md` enumerates the six entries from Req 10 with one-sentence rationale each.
- **Verification**: Single grep covering all three doc invariants: `grep -c "Per-spawn sandbox enforcement" docs/overnight-operations.md && grep -c "Sandbox shape\|Allowed write paths" docs/pipeline.md && grep -c "no permissions sandbox" docs/overnight-operations.md && grep -c "does not constrain what a Bash subprocess" docs/sdk.md` — pass if first two are >= 1 and >= 2 respectively, last two are 0.
- **Status**: [ ] pending

### Task 15: Pre-flight gate artifact + CLAUDE.md 100-line check (Reqs 12, 14)
- **Files**: `lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md` (new), `CLAUDE.md` (conditional)
- **What**: Run the empirical pre-flight test in a clean non-sandboxed terminal (per Req 12), record the result with `PASS:` line + stderr excerpt + `claude --version` + date in `preflight.md`. Verify CLAUDE.md is still ≤ 100 lines after any policy entries added; if crossed, extract OQ3 + OQ6 + new entry into `docs/policies.md` per Req 14.
- **Depends on**: [5, 6, 7]
- **Complexity**: simple
- **Context**:
  - Pre-flight command: `claude -p "$PROMPT" --settings <denying-tempfile> --dangerously-skip-permissions --max-turns 3` with `$PROMPT` instructing Bash-tool write to `/etc/forbidden`.
  - Expected: exit code non-zero, stderr contains `"Operation not permitted"`, target file unmodified.
  - `wc -l < CLAUDE.md` ≤ 100 verified post-edit; extraction to `docs/policies.md` only if crossed.
- **Verification**: `grep -E '^PASS:' lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md` — pass if a PASS line is present; AND `wc -l < CLAUDE.md` — pass if result is ≤ 100.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification proceeds in three layers:

1. **Unit/synthetic** — `just test` runs `tests/test_runner_sandbox.py` (settings shape, kill-switch, recompute, tempfile lifecycle, Linux warning, synthetic kernel-EPERM under both `sandbox-exec` and `srt`, precedence-overlap), `tests/test_dispatch.py` (typed field, blob-extraction, TMPDIR lock, SDK symbol-import), and `tests/test_morning_report.py` (soft-fail header). All must pass on the canonical macOS dev environment with no `pytest.skip` on the blocking primaries.

2. **Empirical pre-flight** — Task 15's `preflight.md` records a `PASS:` line from a real `claude -p ... --settings <tempfile> --dangerously-skip-permissions` invocation in a clean non-sandboxed terminal. The PR cannot merge without this artifact (Req 12). Re-run on every SDK-pin bump or sandbox-source-file change (Req 17 hook).

3. **Doc/policy invariants** — `grep` checks for documentation surface (Task 14), CLAUDE.md ≤ 100-line cap (Task 15), `bin/cortex-check-parity` regression-blocking (Task 13), and the dry-run snapshot at `tests/fixtures/dry_run_reference.txt` does not regress (no sandbox-tempfile output leaks into dry-run stdout).

## Sizing

15 tasks. Each task touches 1-3 files except Task 9 (one new test file with multiple test functions, but all in the same file) and Task 14 (three documentation files, edits are localized). Tasks 5, 6, 9, 10, 11, 12 are marked `complex` (15-30 minutes); the rest are `simple` or `trivial` (5-15 minutes). Dependency graph: Tasks 1, 8, 13 are independent; Tasks 2-4 depend on 1; Task 5 depends on 2-4; Tasks 6-7 depend on 1/6; Tests (9-12) depend on the implementation tasks they cover; Task 14 depends on 6 (shape stable); Task 15 depends on 5, 6, 7 (full mechanism present).
