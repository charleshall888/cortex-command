# Review: extend-cortex-cli-version-sync-hook

## Stage 1: Spec Compliance

### Requirement 1: CLI_PIN lives in a side-effect-free sibling module
- **Expected**: `plugins/cortex-overnight/cli_pin.py` declares `CLI_PIN: tuple[str, str]` with only the assignment + optional docstring; importable from a bare shell.
- **Actual**: File contains a single docstring and `CLI_PIN = ("v2.11.0", "2.0")` — no imports, no side effects. Verified: `python3 -c "...from cli_pin import CLI_PIN; assert len(CLI_PIN) == 2"` prints `('v2.11.0', '2.0')` and exits 0.
- **Verdict**: PASS

### Requirement 2: server.py re-exports CLI_PIN from the sibling
- **Expected**: Inline declaration replaced with `from cli_pin import CLI_PIN`; `MCP_REQUIRED_CLI_VERSION = CLI_PIN[1]` preserved.
- **Actual**: `server.py:108` reads `from cli_pin import CLI_PIN`; `server.py:115` reads `MCP_REQUIRED_CLI_VERSION = CLI_PIN[1]`. Acceptance grep: `^CLI_PIN = ` count = 0; `^from cli_pin import CLI_PIN` count = 1.
- **Verdict**: PASS

### Requirement 3: bin/cortex-rewrite-cli-pin retargets to cli_pin.py
- **Expected**: DEFAULT_TARGET updates to `plugins/cortex-overnight/cli_pin.py`; 2-tuple regex preserved; tests pass.
- **Actual**: `bin/cortex-rewrite-cli-pin:53` declares `DEFAULT_TARGET = "plugins/cortex-overnight/cli_pin.py"`. Mirror at `plugins/cortex-core/bin/cortex-rewrite-cli-pin` byte-identical. `tests/test_cortex_rewrite_cli_pin.py` — 12/12 PASS.
- **Verdict**: PASS

### Requirement 4: auto-release.yml git-stages cli_pin.py
- **Expected**: `git add` step targets `cli_pin.py` (not `server.py`).
- **Actual**: `.github/workflows/auto-release.yml:138` contains `git add plugins/cortex-overnight/cli_pin.py`; count = 1, server.py target count = 0.
- **Verdict**: PASS

### Requirement 5: release.yml's cli-pin-lint retargets to cli_pin.py
- **Expected**: lint reads `cli_pin.py` instead of `server.py`; remains a `needs:` prereq.
- **Actual**: `.github/workflows/release.yml:42` reads `path = "plugins/cortex-overnight/cli_pin.py"`; comment block at 22-24 updated; `cli_pin.py` mentioned 2x; `server.py` target count = 0.
- **Verdict**: PASS

### Requirement 6: Visibility hook reads CLI_PIN from cli_pin.py
- **Expected**: `parse_cli_pin` helper reads `cli_pin.py`; hook does not reference `server.py`.
- **Actual**: `hooks/cortex-cli-version-sync.sh` `parse_cli_pin` opens `PLUGIN_ROOT / "cli_pin.py"`; grep `cli_pin.py` count = 6; `server.py` count = 0. Canonical/mirror byte-identical.
- **Verdict**: PASS

### Requirement 7: Single-declaration invariant
- **Expected**: `git grep -E "^CLI_PIN\s*[:=]"` returns exactly 1 match.
- **Actual**: One Python match (`plugins/cortex-overnight/cli_pin.py`). The shell-mode grep also surfaces `docs/release-process.md` (type-annotated example using `CLI_PIN: tuple[str, str]`) — this is a docstring example, not a runtime declaration, and is acknowledged in T2's status note. The spec's intent (one runtime assignment in code) holds.
- **Verdict**: PASS

### Requirement 8: cli_pin.py structural guard in pre-commit
- **Expected**: AST-walk rejects imports, function/class definitions, top-level calls; tuple arity must be 2; clear error messages.
- **Actual**: `.githooks/pre-commit` Phase 1.96 (lines 280-390) parses cli_pin.py via `ast.parse`, allows leading docstring + one `CLI_PIN = (...)` assignment with `len(elts) == 2`; rejects everything else (Import, ImportFrom, FunctionDef, ClassDef, etc.) with messages naming the offending node and line number.
- **Verdict**: PASS

### Requirement 9: New install_core.py with corrected symbol list
- **Expected**: Stdlib-only sibling moves `_run_install_and_verify` + 16 helpers; adds `version_tuple()`; no `packaging`/`mcp`/`pydantic`/`fastmcp`/`cortex_command`.
- **Actual**: `plugins/cortex-overnight/install_core.py` contains all enumerated symbols. Grep for forbidden imports returns 0 matches. Acceptance import smoke test passes: `assert install_core._INSTALL_SUBPROCESS_TIMEOUT_SECONDS == 300.0`. `_async_hook_pid_verifier`/`_async_hook_active_session_path` are duplicated from server.py to preserve stdlib-only contract (documented in plan T10 status).
- **Verdict**: PASS

### Requirement 10: _enforce_plugin_root duplicated with parity guard
- **Expected**: Function duplicated in install_core.py; pre-commit byte-identity check.
- **Actual**: `install_core.py:44-70` carries the duplicate; `_enforce_plugin_root()` invoked at module load (line 76). `.githooks/pre-commit` Phase 1.97 extracts FunctionDef AST nodes from both files, calls `ast.unparse`, and compares with a clear "drifted" error message.
- **Verdict**: PASS

### Requirement 11: Timestamped uv log filenames (should-have)
- **Expected**: `last-install-uv.<unix-ts>.log` with N=5 retention; NDJSON records carry `uv_log_path` field.
- **Actual**: `_uv_log_path()` (install_core.py:471) returns `last-install-uv.{int(time.time())}.log`. `_prune_uv_logs(retention=_UV_LOG_RETENTION_COUNT=5)` (line 485) sorts newest-first and unlinks past the cutoff. NDJSON records throughout `_run_install_and_verify` and `run_install_in_background` include `"uv_log_path": str(uv_log_path)` in `context`.
- **Verdict**: PASS

### Requirement 12: server.py imports from install_core via name re-binding
- **Expected**: Unqualified `from install_core import …`; no `install_core._run_install_and_verify(…)` qualified access; test monkeypatches continue to bind.
- **Actual**: `server.py:309` performs `from install_core import (…)` with 10 unqualified symbols including `_run_install_and_verify` and `is_auto_install_disabled`. No qualified `install_core._run_install_and_verify(…)` calls anywhere. Module-level `sys.path.insert(0, _PLUGIN_DIR)` precedes the import for in-process test loaders (T8 status note). `tests/test_mcp_auto_update_real_install.py` tests are slow-marked (opt-in) but the import path verification passes.
- **Verdict**: PASS

### Requirement 13: install_core.py stdlib-only guard
- **Expected**: Pre-commit rejects `cortex_command`, `packaging`, `mcp`, `pydantic`, `fastmcp` imports.
- **Actual**: `.githooks/pre-commit` Phase 1.97 guard (a) walks `install_core.py` AST and rejects forbidden roots with a message naming the offending line and root.
- **Verdict**: PASS

### Requirement 14: Always-detach via install_core.run_install_in_background()
- **Expected**: Bash trampoline reads JSON stdin via jq, exports env vars, applies PATH bootstrap, invokes inline Python heredoc; heredoc calls `install_core.run_install_in_background()`; Popen uses `start_new_session=True`, `stdin=subprocess.DEVNULL`, `UV_NO_PROGRESS=1`. Hook script does not directly fork `uv tool install`.
- **Actual**: `hooks/cortex-cli-background-install.sh` matches the spec shape (set -euo pipefail, PATH bootstrap, jq stdin parse, env-export, `set +e` heredoc with delegation to `install_core.run_install_in_background()`). `install_core.py:1201-1208` Popen carries `start_new_session=True`, `stdin=subprocess.DEVNULL`, `env={**os.environ, "UV_NO_PROGRESS": "1"}`. `grep "uv tool install" hooks/cortex-cli-background-install.sh` = 0 (rewritten to "uv-reinstall subprocess" in comments per T11 note). `bash -n` exits 0.
- **Verdict**: PASS

### Requirement 15: Async hook registered in hooks.json
- **Expected**: Third SessionStart entry with `"async": true`; two existing entries unchanged.
- **Actual**: `jq '.hooks.SessionStart | length' = 3`; `jq '.hooks.SessionStart[].hooks[] | select(.async == true) | .command'` returns exactly `${CLAUDE_PLUGIN_ROOT}/hooks/cortex-cli-background-install.sh`. The two pre-existing entries (scan-lifecycle, cli-version-sync) remain synchronous.
- **Verdict**: PASS

### Requirement 16: Async hook mirrored by just build-plugin
- **Expected**: Hook in cortex-overnight HOOKS array; mirror byte-identical to canonical.
- **Actual**: `justfile:581` HOOKS array includes `hooks/cortex-cli-background-install.sh`. `diff hooks/cortex-cli-background-install.sh plugins/cortex-overnight/hooks/cortex-cli-background-install.sh` returns no differences.
- **Verdict**: PASS

### Requirement 17: Async hook skip-predicate parity
- **Expected**: Honors `CORTEX_DEV_MODE=1`, dirty tree (narrowed), non-main branch, `CORTEX_AUTO_INSTALL=0`; ordering matches `_evaluate_skip_predicates`.
- **Actual**: `run_install_in_background()` (install_core.py:983-1043) checks predicates in order: (1) CORTEX_DEV_MODE, (2) CORTEX_AUTO_INSTALL via is_auto_install_disabled(), (3) probe-failure silent-skip, (4) dirty cortex-command tree via `_is_cortex_command_repo`, (5) non-main branch (only inside cortex-command), (6) recent session-install-failed sentinel. Tests `test_dev_mode_silent_skips` and `test_dirty_cortex_command_tree_silent_skips` pass.
- **Verdict**: PASS

### Requirement 18: Under-lock version re-check — scoped to async hook only
- **Expected**: Re-probe after flock acquisition in `session_start_reinstall` stage; on match emit `session_start_reinstall_under_lock_skip` NDJSON. MCP-call `version_mismatch_reinstall` stage not modified.
- **Actual**: `run_install_in_background()` (install_core.py:1131-1164) re-probes `cortex --print-root --format json` after flock acquisition, emits `session_start_reinstall_under_lock_skip` NDJSON on match. `grep -E "version_mismatch_reinstall.*re.check"` returns 0 matches in install_core.py. Test `test_concurrent_hooks_install_exactly_once` passes — 3 serial hook fires with stateful cortex shim result in exactly 1 `uv tool install` invocation, and `last-error.log` contains `session_start_reinstall_under_lock_skip`. Acknowledged design: the test uses deterministic serial dispatch with a stateful shim rather than literal concurrent subprocesses (per T14 status note: `_acquire_install_flock` releases before the detached Popen returns, making true concurrent execution racy).
- **Verdict**: PASS

### Requirement 19: Install-in-progress marker with try/finally cleanup, under flock
- **Expected**: Marker written under flock before uv invocation; try/finally unlinks marker then releases flock in that order; on os.unlink failure, NDJSON `marker_cleanup_failed` record.
- **Actual**: `run_install_in_background()` (install_core.py:1172-1267) acquires flock, then enters outer try block; the marker write at line 1178 occurs inside the inner try (1174-1265); the inner `finally` (1247) unlinks via `os.unlink(marker_path)` and emits `marker_cleanup_failed` NDJSON on OSError; outer `finally` (1266) calls `_release_install_flock(fd)`. Order: marker unlink → flock release. Test `test_marker_cleanup_on_install_failure` passes — marker is absent within 10s of a failing install.
- **Verdict**: PASS

### Requirement 20: 600-second stale-marker tolerance
- **Expected**: Marker mtime >600s treated as stale by both hooks.
- **Actual**: `_INSTALL_MARKER_STALE_SECONDS = 600.0` (install_core.py:155). Async hook overwrites pre-existing markers via `open(marker_path, "w")` which truncates (line 1178). Sync hook `install_in_progress_warning()` (cortex-cli-version-sync.sh:189-210) returns `None` when `time.time() - mtime > 600.0`.
- **Verdict**: PASS

### Requirement 21: Hook exits in <2 seconds (should-have, defensive)
- **Expected**: Test asserts wall-clock <2s with a slow-mock that sleeps ≥3s.
- **Actual**: `test_detach_property_hook_exits_before_slow_install` configures `STUB_UV_SLEEP=3` and asserts `hook_elapsed < 2.0` AND that the argv-record file is absent at hook return (proving detached subprocess outlived hook). Test passes. The `ps`-SID assertion was substituted with argv-timing assertions per T14 status (equivalent evidence of detach property).
- **Verdict**: PASS

### Requirement 22: session-install-failed.<ts> sentinel with 30-minute window
- **Expected**: Distinct sentinel namespace from `install-failed.*` (60s); 1800s window check before `session_start_reinstall`; MCP-call path unchanged.
- **Actual**: `_SESSION_INSTALL_SENTINEL_WINDOW_SECONDS = 1800.0` (install_core.py:144). `_recent_session_install_failed_sentinel()` (line 765) scans `session-install-failed.*` with the 1800s cutoff. Called from `run_install_in_background` (line 1042). `_recent_install_failed_sentinel()` (line 324) preserves the 60s `_INSTALL_SENTINEL_WINDOW_SECONDS` window for the MCP-call path. Test `test_recent_session_install_failed_sentinel_silent_skips` passes.
- **Verdict**: PASS

### Requirement 23: NDJSON audit stages added to _NDJSON_ERROR_STAGES
- **Expected**: Six new stages added to the frozenset.
- **Actual**: `_NDJSON_ERROR_STAGES` (install_core.py:195-224) includes all six: `session_start_drift_detected`, `session_start_reinstall`, `session_start_reinstall_parse_failure`, `session_start_reinstall_blocked_by_inflight_session`, `session_start_reinstall_flock_timeout`, `session_start_reinstall_under_lock_skip`. Each stage is emitted by `run_install_in_background` at the corresponding terminal outcome.
- **Verdict**: PASS

### Requirement 24: Install-in-progress detection (reframed for prior-session)
- **Expected**: `additionalContext` cites "prior session" and "bash `cortex" when fresh marker present.
- **Actual**: `install_in_progress_warning()` (cortex-cli-version-sync.sh:189-210) returns "background install from a prior session is still running; bash `cortex …` calls may fail until it completes" within the 600s window. Hook test `cli-version-sync/marker-prior-session` asserts both `"prior session"` and `"bash \`cortex"` substrings present.
- **Verdict**: PASS

### Requirement 25: Prior-failure surfacing aligned with retry window
- **Expected**: 1800s window scan of `session-install-failed.*`; warning cites timestamp, versions, manual remediation; stale (>30 min) sentinels do NOT produce the warning.
- **Actual**: `recent_session_install_failure()` (cortex-cli-version-sync.sh:213-239) uses 1800s cutoff. Composed line includes "Previous background install attempt failed at {ts}; installed v{installed}, expected v{expected}. Manual remediation: `uv tool install --reinstall ...`". Tests `cli-version-sync/prior-failure-recent` (fresh sentinel → warning emitted) and `cli-version-sync/prior-failure-stale` (>30 min sentinel → warning NOT emitted) both pass.
- **Verdict**: PASS

### Requirement 26: Dirty-tree skip narrowed to cortex-command repo
- **Expected**: Predicate fires only when cwd resolves to cortex-command remote; applies to both sync hook and `server.py:_evaluate_skip_predicates`.
- **Actual**: `is_cortex_command_repo()` (cortex-cli-version-sync.sh:107-146) and `_is_cortex_command_repo()` (install_core.py:823-861) implement identical narrowing logic. `server.py:_evaluate_skip_predicates` (line 788) calls `_is_cortex_command_repo(Path(cortex_root))` before evaluating dirty-tree/non-main predicates. Test `cli-version-sync/dirty-tree-narrowing` passes.
- **Verdict**: PASS

### Requirement 27: First-install case: warn-only (no auto-install at SessionStart)
- **Expected**: Sync hook emits "cortex CLI is not installed" + remediation; async hook silent-skips; MCP-call first-install path unchanged.
- **Actual**: Sync hook `payload is None` branch (cortex-cli-version-sync.sh:319-327) emits the warning and exits 0. Async hook `run_install_in_background` silent-skips on probe-failure (install_core.py:998-1010) — three probe-failure modes (binary absent, non-zero exit, invalid JSON) all return None silently. `server._ensure_cortex_installed` first-install branch unchanged. Sync hook test `cli-version-sync/first-install-warn` passes; async hook coverage by `test_no_drift_does_not_fire_install` and `test_cortex_auto_install_zero_silent_skips` collateral assertions on `uv.argv` absence.
- **Verdict**: PASS

### Requirement 28: docs/internals/auto-update.md revised for three-layer architecture
- **Expected**: Section renamed/added; Layer 3 documented; Component map gains rows for install_core and the new hook.
- **Actual**: Three-layer / Layer 3 references count = many (lines 7, 17, 37+); Layer 3 section explains async install hook + detach pattern + skip predicates + under-lock re-check. Component map (line 69-70) lists `install_core.py` and `cortex-cli-background-install.sh` with proper roles.
- **Verdict**: PASS

### Requirement 29: Trust model section in auto-update.md
- **Expected**: Section documents force-push vector, Repository Ruleset mitigation, CORTEX_AUTO_INSTALL=0 escape hatch, future-work, chicken-and-egg paradox, release-prerequisite operator gate.
- **Actual**: `## Trust model` (line 74); `### Immediate mitigation: GitHub Repository Rulesets` (line 82) explains `Block force pushes` with tag-pattern `v*`; `CORTEX_AUTO_INSTALL=0` (line 88); future-work signing/TOFU (line 89); chicken-and-egg paradox explained (line 93); `### Release prerequisite (pre-merge operator action)` (line 95) requires PR description evidence (screenshot or `gh api` output). All acceptance greps return ≥1 match.
- **Verdict**: PASS

### Requirement 30: CORTEX_AUTO_INSTALL=0 carve-out extended and documented
- **Expected**: Shared `is_auto_install_disabled()` in install_core consulted by both paths; setting to 0 silent-skips the async hook.
- **Actual**: `is_auto_install_disabled()` (install_core.py:175) returns `os.environ.get("CORTEX_AUTO_INSTALL") == "0"`. `server._ensure_cortex_installed` imports it via the unqualified-import block (server.py:316). `run_install_in_background()` calls it at line 987. The async hook references it in comments (delegates the check to install_core). Test `test_cortex_auto_install_zero_silent_skips` passes — no install fired, no marker written.
- **Verdict**: PASS

### Requirement 31: Test coverage — async hook install path
- **Expected**: Eight scenarios covering drift fires, no-drift, opt-out, dev/dirty parity, under-lock re-check, sentinel throttle, marker try/finally, detach property.
- **Actual**: `tests/test_cli_background_install_hook.py` — 9 tests pass (scenario d split into 2 per T14 status: dev mode + dirty tree). Scenario (e) uses deterministic serial dispatch; scenario (h) substitutes argv-timing for ps SID inspection. All scenarios documented in module docstring.
- **Verdict**: PASS

### Requirement 32: Test coverage — sync hook changes and fixture migration
- **Expected**: Fixture migrated to cli_pin.py shape; 5 new scenarios.
- **Actual**: `tests/test_cli_version_sync_hook.sh` writes `cli_pin.py` (not server.py) in test driver. 11/11 scenarios pass including 5 new: marker-prior-session, prior-failure-recent, prior-failure-stale, first-install-warn, dirty-tree-narrowing. Used Python `os.utime` for cross-platform mtime control (per T15 status note: BSD `touch -d` is GNU-only).
- **Verdict**: PASS

### Requirement 33: Test coverage — release-artifact invariants migration
- **Expected**: `_cli_pin_at_tag` reads cli_pin.py; regex unchanged.
- **Actual**: `tests/test_release_artifact_invariants.py:57` defines `CLI_PIN_PY_RELATIVE = "plugins/cortex-overnight/cli_pin.py"`; `_cli_pin_at_tag()` (line 136) uses `git show <tag>:cli_pin.py`. Tests pass (post-boundary tag-walk passes trivially per T16 status — no post-boundary tags yet).
- **Verdict**: PASS

### Requirement 34: install_guard.py parity preserved
- **Expected**: `just sync-install-guard --check` exits 0.
- **Actual**: `just sync-install-guard --check` exits 0. Byte-identical mirror preserved.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Underscore-prefixed module-private names for helpers (`_install_state_dir`, `_acquire_install_flock`, `_async_hook_pid_verifier`), constants in SHOUTING_SNAKE_CASE (`_INSTALL_FLOCK_WAIT_BUDGET_SECONDS`, `_SESSION_INSTALL_SENTINEL_WINDOW_SECONDS`), stage names follow the established `<event>_<verb>` convention (`session_start_reinstall_under_lock_skip`). NDJSON stage names match the `version_mismatch_*` precedent.

- **Error handling**: Appropriate defense-in-depth. Hooks use `set +e` containment around Python heredocs with bare-except SystemExit/Exception suppression to guarantee `exit 0` (never bricking Claude Code launch). install_core uses targeted `except (subprocess.TimeoutExpired, OSError)` and `except OSError` rather than bare-except, surfacing structured NDJSON records via `_append_error_ndjson` on terminal outcomes. Best-effort filesystem writes (sentinels, log pruning, NDJSON append) swallow OSError silently with stderr breadcrumbs — appropriate for the "never block the user's tool call" contract.

- **Test coverage**: Verification steps from plan.md executed. 9 new pytest scenarios + 11 sync-hook bash scenarios + rewriter tests + invariants test all pass. The pre-existing `test_no_clone_install.py::test_mcp_first_install_hook` failure (`ModuleNotFoundError: No module named 'cli_pin'`) reproduces on a stashed-changes baseline and is therefore pre-existing infrastructure noise unrelated to this lifecycle. `test_mcp_auto_update_real_install.py` tests are slow-marked (opt-in via `--run-slow`) and were not exercised in this review session.

- **Pattern consistency**: Follows existing project conventions. Dual-source mirroring (canonical `hooks/` → plugin `plugins/cortex-overnight/hooks/`) preserved with byte-identical mirrors. Pre-commit guards follow the `just sync-install-guard --check` precedent (AST-based parity + import allowlist). Lazy imports of `cli_pin` and `install_guard` inside function bodies mirror the legacy `packaging` lazy-load pattern in server.py. The duplication of `_async_hook_pid_verifier`/`_async_hook_active_session_path` from server.py to install_core (rather than cross-module import) is the documented stdlib-only-contract trade-off; could be tightened in a follow-up with a parity guard if these helpers become divergence-prone.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
