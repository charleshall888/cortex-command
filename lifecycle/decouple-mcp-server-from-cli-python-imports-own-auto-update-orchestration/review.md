# Review: decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration

## Stage 1: Spec Compliance

### Requirement R1 — No `cortex_command.*` imports in the new MCP source
- **Expected**: `grep -E '^(from|import) cortex_command' plugins/cortex-overnight-integration/server.py` returns no matches; exit 1.
- **Actual**: Confirmed via grep — exit code 1, zero matches. The plugin source uses only `subprocess.run` and stdlib/MCP/Pydantic imports.
- **Verdict**: PASS

### Requirement R2 — Each MCP tool delegates via subprocess + JSON
- **Expected**: All five tools (`overnight_start_run`, `overnight_status`, `overnight_logs`, `overnight_cancel`, `overnight_list_sessions`) shell out to `cortex` and parse JSON. `tests/test_mcp_subprocess_contract.py` exits 0.
- **Actual**: All five `_delegate_*` functions in `plugins/cortex-overnight-integration/server.py:1394-1761` invoke `_run_cortex(["<verb>", "--format", "json", ...])` and parse the response via `_parse_json_payload`. The Pydantic input/output schemas are defined inline (no `cortex_command.mcp_server.schema` import). 17 tests pass in the contract suite.
- **Verdict**: PASS

### Requirement R3 — `cortex --print-root` flag emits versioned JSON
- **Expected**: Stdout JSON `{"version": "1.0", "root": ..., "remote_url": ..., "head_sha": ...}`, exit 0; the named acceptance pipeline exits 0.
- **Actual**: `_dispatch_print_root` at `cortex_command/cli.py:211-248` resolves the cortex root, shells out to git for `remote_url` + `head_sha` (without `check=True`, with `timeout=5`), and emits the four-field payload. Live invocation produced the expected shape with a 40-char head_sha. `test_cli_print_root.py` covers the contract.
- **Verdict**: PASS

### Requirement R4 — `cortex overnight start` emits structured JSON for atomic-claim collisions
- **Expected**: Versioned `{"error": "concurrent_runner", "session_id": ..., ...}` payload on collision; named pytest test exits 0.
- **Actual**: `cortex_command/overnight/cli_handler.py:177-196` performs the pre-flight `verify_runner_pid` check on the JSON path and emits the versioned envelope with non-zero exit. `_emit_json` at lines 43-50 stamps every payload with the schema version. `test_overnight_start_concurrent_runner_json_shape` passes.
- **Verdict**: PASS

### Requirement R5 — `cortex overnight logs` and `cortex overnight cancel` accept `--format json`
- **Expected**: Both verbs emit `{"version": "1.0", ...}` payloads parseable by `json.load`.
- **Actual**: `--format` flag added to both subparsers (`cli.py:417-421, 467-471`). `cli_handler.py::handle_cancel` and `handle_logs` route through `_emit_json` for both success and error envelopes (referenced by docs/mcp-contract.md lines 138-163, 106-136). `test_cli_overnight_format_json.py` covers the contract.
- **Verdict**: PASS

### Requirement R6 — Plugin-bundled MCP source is a PEP 723 single-file
- **Expected**: `# /// script` block with `requires-python = ">=3.12"` and `mcp>=1.27,<2`; `.mcp.json` invokes `uvx ${CLAUDE_PLUGIN_ROOT}/server.py`. The three grep checks must succeed.
- **Actual**: All three acceptance greps pass: `# /// script` present (line 2), `mcp>=1.27,<2` present (line 5, with `pydantic>=2.5,<3` co-pinned), `.mcp.json` payload `{"command": "uvx", "args": ["${CLAUDE_PLUGIN_ROOT}/server.py"]}`.
- **Verdict**: PASS

### Requirement R7 — `cortex mcp-server` removed; CLI verb becomes deprecation stub
- **Expected**: `cortex mcp-server` exits non-zero with a stderr message naming `cortex-overnight-integration`; `cortex_command/mcp_server/` deleted entirely.
- **Actual**: Live invocation produced rc=1 with stderr containing `cortex-overnight-integration` (also includes the T12-driven restart advisory). `test ! -d cortex_command/mcp_server` passes. Caller-enumeration grep across `cortex_command/`, `tests/`, `plugins/`, `docs/`, `skills/` returns zero matches. `test_cli_mcp_server_deprecated.py` covers all three behaviors (stub stderr, `.mcp.json` cutover, post-upgrade migration notice).
- **Verdict**: PASS

### Requirement R8 — Throttled MCP-side update check on tool dispatch
- **Expected**: First tool call runs `git ls-remote`; subsequent calls within the same MCP-server lifetime skip ls-remote and read the in-memory cache. Both named pytest tests exit 0.
- **Actual**: `_maybe_check_upstream` at `server.py:444-572` consults `_UPDATE_CHECK_CACHE` keyed on `(cortex_root, remote_url, "HEAD")` per spec, runs `git ls-remote ... --timeout 5` on cache miss, caches the boolean result. `test_throttle_cache_first_call_runs_ls_remote` and `test_throttle_cache_subsequent_call_skips_ls_remote` pass. Cache invalidation on success/error/flock-timeout is also wired (Tasks 8, 10, 11).
- **Verdict**: PASS

### Requirement R9 — Skip-predicate evaluation
- **Expected**: Skip when `CORTEX_DEV_MODE=1`, dirty tree, or non-main branch. Both named tests exit 0.
- **Actual**: `_evaluate_skip_predicates` at `server.py:387-441` evaluates predicates in spec order with dev-mode short-circuiting before any subprocess shell-out. Reasons logged once via `_SKIP_REASON_LOGGED` latch. `test_skip_predicate_dev_mode_suppresses_ls_remote`, `test_skip_predicate_dev_mode_tool_call_still_executes`, plus the additional `dirty_tree` and `feature_branch` coverage all pass.
- **Verdict**: PASS

### Requirement R10 [CONDITIONAL on R18=PASS] — `cortex upgrade` orchestration via subprocess
- **Expected**: On upstream advance with no skip, MCP spawns `cortex upgrade` (timeout 60s) followed by the verification probe before delegating. R18=PASS, so this requirement is active.
- **Actual**: `_orchestrate_upgrade` at `server.py:814-957` spawns `cortex upgrade` with `_CORTEX_UPGRADE_TIMEOUT_SECONDS = 60.0`, runs `_run_verification_probe` on success, and invalidates the R8 cache on every exit path per Technical Constraints. `test_upgrade_orchestration_invocation_order` passes — argv order is `git ls-remote → cortex upgrade → verification probe → user tool call`.
- **Verdict**: PASS

### Requirement R11 [CONDITIONAL on R18=PASS] — Concurrency-safe via flock
- **Expected**: `fcntl.flock(LOCK_EX)` on `$cortex_root/.git/cortex-update.lock` with 30s budget, post-acquire fresh re-verify, `try/finally` release; both named concurrency tests pass.
- **Actual**: `_acquire_update_flock` at `server.py:599-641` uses non-blocking polling with `_FLOCK_WAIT_BUDGET_SECONDS = 30.0` and `_FLOCK_POLL_INTERVAL_SECONDS = 0.1`. Post-acquire re-verify uses fresh `git ls-remote` + `git rev-parse HEAD` (per Technical Constraints "fresh ls-remote, not the captured pre-flock remote_sha"). Lock release in `try/finally` at lines 956-957. `test_concurrent_upgrade_only_one_subprocess_runs` and `test_concurrent_upgrade_both_processes_return_success` pass — note the test uses `multiprocessing.Process` (real OS processes) per the plan brief, which is the correct contention mechanism for a process-scoped flock; the spec's literal name `..._both_threads_return_success` is renamed to `..._both_processes_return_success` consistent with the plan's clarification.
- **Verdict**: PASS

### Requirement R12 [CONDITIONAL on R18=PASS] — Verification probe forces module import
- **Expected**: After `cortex upgrade` exits 0, run `cortex --print-root` then `cortex overnight status --format json` (forces `cli_handler` lazy-import); on probe failure, NDJSON-log + fall through. Both named tests exit 0.
- **Actual**: `_run_verification_probe` at `server.py:718-811` runs both probes with parseable-JSON assertion on each. The second probe correctly omits a trailing positional (per the architectural note carrying forward the R18 probe correction). `test_verification_probe_failure_falls_through_to_on_disk_cli` passes. `test_verification_probe_fails_on_corrupt_install` is `@pytest.mark.slow` (opt-in via `--run-slow`) because it runs a real `uv tool install` — the spec's `pytest -v` invocation exits 0 because the test is skipped (not failed); when run with `--run-slow` the test passes (verified locally). Acceptance is satisfied.
- **Verdict**: PASS

### Requirement R13 [CONDITIONAL on R18=PASS] — Synchronous schema-floor check
- **Expected**: When `MCP_REQUIRED_CLI_VERSION` major > CLI major, run `cortex upgrade` synchronously before delegating, regardless of throttle. Both named tests pass.
- **Actual**: `_schema_floor_violated` at `server.py:993-1014` and `_orchestrate_schema_floor_upgrade` at lines 1017-1125 implement the synchronous gate under R11 flock + R12 probe. `_gate_dispatch` at lines 1128-1162 correctly orders R13 before R8 throttle/R9 predicates per Technical Constraints. R9 predicates are NOT applied to R13 path (verified at line 1075 — the schema-floor path runs upgrade unconditionally once flock acquired). `test_schema_floor_triggers_synchronous_upgrade` and `test_schema_floor_tool_call_runs_after_upgrade` pass.
- **Verdict**: PASS

### Requirement R14 [CONDITIONAL on R18=PASS] — NDJSON error log + stderr summary
- **Expected**: NDJSON append at `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-error.log` with `{ts, stage, error, context}`; one-line stderr summary; cache invalidated. Both named tests exit 0.
- **Actual**: `_append_error_ndjson` at `server.py:318-372` writes the spec-shape record (UTC ISO 8601 with `Z` suffix, validates `stage` against `_NDJSON_ERROR_STAGES`, defensive try/except for filesystem failures so audit-write never breaks tool calls). Wired at every error site (`git_ls_remote` exception + non-zero, `cortex_upgrade` exception + non-zero, `verification_probe` failure, `flock_timeout`). `_invalidate_update_cache()` called at every error site per Technical Constraints. `test_ls_remote_timeout_appends_error_log`, `test_ls_remote_nonzero_returncode_appends_error_log`, `test_ls_remote_timeout_tool_call_still_returns`, `test_orchestration_error_invalidates_cache_for_retry`, and `test_ls_remote_nonzero_returncode_invalidates_cache` all pass.
- **Verdict**: PASS

### Requirement R15 — Two-axis `major.minor` versioning
- **Expected**: Every JSON payload carries `"version": "M.m"` string; major mismatch hard-rejected; minor-greater accepts and skips unknown fields. Three acceptance checks pass.
- **Actual**: `MCP_REQUIRED_CLI_VERSION = "1.0"` at `server.py:101`; `_check_version` at lines 126-176 parses major/minor and raises `SchemaVersionError` on mismatch. Pydantic output models all carry `model_config = ConfigDict(extra="ignore")` (`_FORWARD_COMPAT` at line 1174). `docs/mcp-contract.md` has multiple `"version":` mentions. `test_major_version_mismatch_is_rejected` and `test_minor_version_greater_skips_unknown_fields` pass.
- **Verdict**: PASS

### Requirement R16 — `cortex --print-root` JSON shape forever-public-API
- **Expected**: `grep -F 'Forever-public API' docs/mcp-contract.md` returns one match.
- **Actual**: `docs/mcp-contract.md:17` has the heading `### Forever-public API` plus prose at lines 19-23 explaining stability commitment and naming the four fields.
- **Verdict**: PASS

### Requirement R17 — Confused-deputy mitigation on `${CLAUDE_PLUGIN_ROOT}`
- **Expected**: MCP refuses to start when `__file__` is not under resolved `${CLAUDE_PLUGIN_ROOT}`; named pytest test exits 0.
- **Actual**: `_enforce_plugin_root` at `server.py:50-76` runs at import time (line 82, before any MCP machinery). Treats absent env var as mismatch. Stderr message includes literal `"plugin path mismatch"`. `test_plugin_path_mismatch_exits_nonzero` passes.
- **Verdict**: PASS

### Requirement R18 — Q#1 sandbox empirical probe
- **Expected**: probe-result note at `lifecycle/.../sandbox-probe-result.md` documents each operation's exit code and a verdict. Verdict PASS = all four operations succeed.
- **Actual**: `sandbox-probe-result.md` exists with the prescribed structure. All three Op grep counts succeed (`^## Verdict$` = 1; `^(PASS|FAIL|PARTIAL)$` ≥ 1; verdict line = `PASS`). The note documents an Op 4b PARTIAL on first run, root-causes it to a probe invocation-form bug (literal-empty-string positional that the CLI subparser rejects), corrects the probe source, and the user accepted diagnosis-as-evidence path B (recorded in commentary block) flipping the verdict to PASS. R10–R14 stay in scope.
- **Verdict**: PASS

### Requirement R19 [CONDITIONAL on R18=FAIL/PARTIAL] — Discoverability nudge fallback
- **Expected**: On FAIL/PARTIAL, MCP surfaces `cortex update available` notice instead of orchestrating. R18=PASS, so this requirement is inactive — Task 16 self-skipped.
- **Actual**: `git log --oneline | grep -F "Task 16 self-skipped"` returns one match (acfddbb). `grep -F 'cortex update available' plugins/cortex-overnight-integration/server.py` returns no matches (correct: no nudge code on the inactive verdict path). Empty checkpoint commit is by design per the plan's Conditional Replanning section.
- **Verdict**: PASS (correctly inactive; skip-marker present)

### Requirement R20 — Plugin-refresh semantics empirical investigation
- **Expected**: Investigation note at `plugin-refresh-semantics.md` describes observed behavior; `^## Observed behavior$` count = 1.
- **Actual**: `plugin-refresh-semantics.md` exists with the required heading (count = 1). Verdict resolved to `session_restart_required` (per the project memory entry, PID-equality check via `/reload-plugins` empirically falsified the subprocess-respawn hypothesis on 2026-04-27). The deprecation stub appends the restart advisory based on this verdict (verified live at the `cortex mcp-server` invocation: stderr ends with `Restart Claude Code after editing your .mcp.json`).
- **Verdict**: PASS

### Requirement R21 — Subprocess-overhead benchmark
- **Expected**: `perf-benchmark.md` reports p50/p95/p99 for both paths under both implementations; >200ms p95 added is documented as a known regression.
- **Actual**: `perf-benchmark.md` reports `overnight_status` p95 delta = +427.42ms and `overnight_logs` p95 delta = +393.25ms — both over the 200ms threshold. The "Threshold evaluation" section explicitly surfaces them as known regressions and lists candidate post-merge mitigations (long-lived JSON-RPC subprocess; batching; accept overhead given the ~30s polling cadence). The acceptance grep checks (`^## (overnight_status|overnight_logs|Integration smoke)$` = 3, p50/p95/p99 mentions ≥ 6) pass. Integration smoke covers all five MCP tools end-to-end with Pydantic validation.
- **Verdict**: PASS

### Requirement R22 — Auto-update threat-model documentation
- **Expected**: Threat Model section in spec acknowledges auto-RCE trade-off; readers see the deliberate choice.
- **Actual**: `spec.md` has a `## Threat Model` section (lines 100-106) explicitly acknowledging auto-RCE and citing `requirements/project.md`'s personal-tooling boundary. `docs/mcp-contract.md` mirrors the threat-model content (lines 171-187) for downstream readers, names existing mitigations (R9 skip predicates, bare-shell users, R13 schema-floor refusal), and explicitly carves `CORTEX_REPO_PIN_SHA` out of scope as a future follow-up.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None. The implementation matches both `requirements/project.md` (architectural constraints unchanged: file-based state, per-repo sandbox registration, defense-in-depth permissions; cortex-command remains personal tooling per the explicit threat-model carve-out) and `requirements/pipeline.md` (the only pipeline-relevant addition is the `--format json` surface on `overnight start/logs/cancel`, which extends the existing `cortex overnight {start|status|cancel|logs}` CLI contract without changing session orchestration, feature execution semantics, or any of the six functional-requirement sections in pipeline.md). The `cortex mcp-server` Dependencies bullet at pipeline.md:153 references the same five tools the new plugin exposes — the dependency relationship the requirements doc describes is preserved (the MCP exposes the same five overnight tools) even though the implementation site has moved to the plugin path. No new behavior is introduced that pipeline.md doesn't already accommodate.

**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Module-private helpers use leading-underscore (`_evaluate_skip_predicates`, `_orchestrate_upgrade`, `_gate_dispatch`); module-level constants use UPPER_SNAKE_CASE with units suffix where appropriate (`_FLOCK_WAIT_BUDGET_SECONDS`, `_CORTEX_UPGRADE_TIMEOUT_SECONDS`). Spec requirement IDs are referenced inline in docstrings throughout, matching the existing pattern in `cortex_command/init/settings_merge.py` and `cortex_command/overnight/cli_handler.py`. Pydantic input/output models follow the existing `<Verb>Input` / `<Verb>Output` naming.

- **Error handling**: Spec Technical Constraints honored throughout the new MCP source. Verified via grep: zero `check=True` occurrences in `plugins/cortex-overnight-integration/server.py` (all six matches are docstring references documenting the constraint). Every `subprocess.run` call carries `capture_output=True, text=True` with an explicit `timeout` (5s for `git ls-remote`, 30s for verification probe + tool delegation, 60s for `cortex upgrade`). Both exception (`TimeoutExpired`/`OSError`) and non-zero-returncode branches are handled separately at every shell-out site per spec's "never check=True; catch and handle errors explicitly" — particularly visible at `_maybe_check_upstream` (lines 503-560) and `_orchestrate_upgrade` (lines 908-950). NDJSON audit-write helper is defensive (best-effort on filesystem failures) so a failed audit-write never breaks the user's tool call. The pre-existing `_dispatch_upgrade` in `cli.py:251-294` retains three `check=True` calls inherited from before this lifecycle (commit 7541f9e); the spec's Technical Constraint targets the new MCP source as the architectural invariant, and modifying `_dispatch_upgrade` is out of scope for this ticket.

- **Test coverage**: Per-task verification commands from plan.md execute and pass. The new test suites (`test_cli_print_root.py`, `test_cli_overnight_format_json.py`, `test_cli_mcp_server_deprecated.py`, `test_mcp_subprocess_contract.py`, `test_mcp_auto_update_orchestration.py`) total 40 passing + 1 skipped (the `@pytest.mark.slow` corrupt-install probe test, which passes when run with `--run-slow`). All 16 named acceptance tests from the spec are present and pass. Full repo test suite: 314 passed, 5 skipped, 1 xfailed (one pre-existing flake in `test_runner_concurrent_start_race.py::test_two_starters_with_stale_preexisting_lock` resolved on re-run; not introduced by this lifecycle). Integration smoke from Task 13 covers all five MCP tools end-to-end via real subprocess+JSON delegation against a fixture session.

- **Pattern consistency**: Implementation follows the existing project conventions throughout. Flock pattern derived from `cortex_command/init/settings_merge.py:69-85` (cited in source comments). Atomic-write pattern documented but not exercised in this lifecycle (the NDJSON append uses plain `open(path, "a")` because audit log lines are append-only single-line records, not full-state rewrites — atomic-write semantics are not load-bearing here). The MCP-side cache-key construction (`(cortex_root, remote_url, "HEAD")`) and skip-predicate ordering match the spec exactly. The `# /// script` block follows the AWS-MCP-#2533-cited major-bound pattern. Documentation cross-references between `spec.md`, `docs/mcp-contract.md`, and the per-task plan briefs are bidirectional and keep semantics in sync.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
