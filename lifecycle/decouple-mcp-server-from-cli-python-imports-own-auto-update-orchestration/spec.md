# Specification: Decouple MCP server from CLI Python imports + own auto-update orchestration

Refers to backlog item `146-decouple-mcp-server-from-cli-python-imports-via-subprocessjson-contract.md` and research artifact `lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/research.md`.

## Problem Statement

The cortex MCP server (`cortex_command/mcp_server/`) currently imports `cortex_command.overnight.{cli_handler, ipc, logs}` directly. This couples the MCP runtime to the CLI install: plugin auto-update cannot refresh MCP runtime behavior independently of the CLI, and a long-running MCP server holds `cortex_command` modules in memory so even an on-disk CLI update doesn't take effect until Claude Code restarts. Additionally, ticket 145's inline auto-update gate inside `cortex_command/cli.py::main()` was rejected because the `CLAUDECODE` skip predicate made it inactive on the user's primary path (Claude sessions invoke `cortex` via MCP tool calls, not bare-shell). This spec refactors the MCP into a thin protocol-translation layer that has no shared Python imports against the CLI (only a versioned subprocess+JSON contract) and additionally makes the MCP server own auto-update orchestration so the MCP-primary user path stays current without an inline CLI gate. Beneficiaries: cortex users on the MCP-primary path (no CLI staleness without Claude Code restart; independent update cadence between plugin and CLI). Cost of not building: continued staleness on the primary user path; manual `cortex upgrade` remains the only way to refresh the CLI for end users.

## Requirements

### Decoupling

1. **R1 — No `cortex_command.*` imports in the new MCP source.** The plugin-bundled MCP source must not contain any `from cortex_command` or `import cortex_command` statement. Acceptance: `grep -E '^(from|import) cortex_command' plugins/cortex-overnight-integration/server.py` returns no matches; exit code 1 (no match found).

2. **R2 — Each MCP tool delegates to a CLI subcommand via subprocess + JSON.** All five existing MCP tools (`overnight_start_run`, `overnight_status`, `overnight_logs`, `overnight_cancel`, `overnight_list_sessions`) shell out to `cortex` and parse the CLI's JSON output. Acceptance: `uv run pytest tests/test_mcp_subprocess_contract.py -v` exits 0. Each test in that file mocks `subprocess.run` and asserts the MCP tool invokes the expected `cortex <verb> --format json` command and parses the response correctly.

3. **R3 — `cortex --print-root` flag exists and emits versioned JSON.** New CLI flag returns `{"version": "1.0", "root": "<abs path>", "remote_url": "<git remote>", "head_sha": "<git rev-parse HEAD>"}` to stdout, exit 0. Acceptance: `cortex --print-root | python3 -c "import json, sys; d = json.load(sys.stdin); assert d['version'].startswith('1.'); assert d['root']; assert d['remote_url']; assert len(d['head_sha']) == 40"` exits 0.

4. **R4 — `cortex overnight start` emits structured JSON for atomic-claim collisions.** When `--format json` is set and the claim collides (concurrent runner already alive), exit code is non-zero and stdout contains `{"version": "1.0", "error": "concurrent_runner", "session_id": "<existing>", ...}`. Acceptance: `uv run pytest tests/test_mcp_subprocess_contract.py::test_overnight_start_concurrent_runner_json_shape -v` exits 0. That test pre-writes a `runner.pid` file, invokes `cortex overnight start --format json --in-flight-guard-bypass=false`, and asserts the JSON shape and a non-zero exit code.

5. **R5 — `cortex overnight logs` and `cortex overnight cancel` accept `--format json`.** Each emits `{"version": "1.0", ...}` payloads with the same schema versioning as the rest of the contract. Acceptance: `cortex overnight logs --format json <known-session-id>` and `cortex overnight cancel --format json <known-session-id>` both produce JSON parseable by `python3 -c "import json, sys; json.load(sys.stdin)"` with exit code 0.

6. **R6 — Plugin-bundled MCP source distribution as PEP 723 single-file.** `plugins/cortex-overnight-integration/server.py` is a single Python file with inline `# /// script` block declaring `requires-python = ">=3.12"` and pinned major bounds: `dependencies = ["mcp>=1.27,<2", "pydantic>=2.5,<3"]`. The plugin's `.mcp.json` invokes `uvx ${CLAUDE_PLUGIN_ROOT}/server.py`. Acceptance: `head -10 plugins/cortex-overnight-integration/server.py | grep -F '# /// script'` returns one match; `grep -F 'mcp>=1.27,<2' plugins/cortex-overnight-integration/server.py` returns one match; `python3 -c "import json; d = json.load(open('plugins/cortex-overnight-integration/.mcp.json')); assert 'uvx' in d['mcpServers']['cortex-overnight']['command'] or 'uvx' in d['mcpServers']['cortex-overnight']['args']"` exits 0.

7. **R7 — `cortex mcp-server` subcommand is removed; CLI verb becomes a deprecation stub.** `cortex_command/mcp_server/{server.py, tools.py, schema.py}` is deleted entirely. The `cortex mcp-server` argparse entry remains only as a deprecation stub: invoking it prints a one-line migration message to stderr (e.g., `cortex mcp-server is removed; install the cortex-overnight-integration plugin (/plugin install cortex-overnight-integration) and update your .mcp.json to point at uvx ${CLAUDE_PLUGIN_ROOT}/server.py`) and exits non-zero. Acceptance:
   - `cortex mcp-server` exits non-zero (e.g., `cortex mcp-server; echo $?` prints a non-zero value).
   - `cortex mcp-server 2>&1 1>/dev/null | grep -F 'cortex-overnight-integration'` returns at least one match (the deprecation message names the migration target).
   - `test -d cortex_command/mcp_server && echo "exists" || echo "removed"` outputs `removed`.

### Auto-update orchestration

8. **R8 — MCP-side update check on tool-call dispatch.** Before delegating a tool call, the MCP runs `git ls-remote <remote-url> HEAD` (timeout 5s) and compares against the local `head_sha`. The check is throttled with a per-MCP-server-lifetime instance cache: first tool call pays the ls-remote cost (~150ms p50), subsequent calls in the same MCP-server lifetime read an in-memory boolean. Cache key is `(cortex_root absolute path, remote URL, HEAD ref name)` to handle multi-fork installs. Acceptance:
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_throttle_cache_first_call_runs_ls_remote -v` exits 0. That test mocks `subprocess.run` for `git ls-remote` and asserts it was invoked on the first tool call.
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_throttle_cache_subsequent_call_skips_ls_remote -v` exits 0. That test mocks `subprocess.run` and asserts that on the second tool call within the same MCP-server lifetime, `git ls-remote` is NOT invoked and only the in-memory cache is consulted.

9. **R9 — Skip-predicate evaluation.** The update check is skipped (logged once to stderr with reason) when ANY of: (a) `CORTEX_DEV_MODE=1` env var is set, (b) `git status --porcelain` returns non-empty (dirty tree), (c) `git rev-parse --abbrev-ref HEAD` is not `main`. When skipped, the user's intended tool call proceeds against the on-disk CLI. Acceptance:
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_skip_predicate_dev_mode_suppresses_ls_remote -v` exits 0. That test sets `CORTEX_DEV_MODE=1` in the MCP environment, mocks `subprocess.run`, and asserts no `git ls-remote` call is made.
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_skip_predicate_dev_mode_tool_call_still_executes -v` exits 0. That test asserts the user's intended tool call still executes when the predicate fires.

10. **R10 [CONDITIONAL on R18=PASS] — `cortex upgrade` orchestration via subprocess.** When the update check detects upstream advance AND skip predicates do not fire, the MCP spawns `cortex upgrade` as a subprocess (timeout 60s). After successful exit, the MCP runs the verification probe (R12) before delegating the user's tool call. Acceptance: `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_upgrade_orchestration_invocation_order -v` exits 0. That test mocks `subprocess.run`, simulates upstream advance, and asserts calls appear in the order: `git ls-remote` → `cortex upgrade` → verification probe (`cortex --print-root` then `cortex overnight status --format json`) → user-intended tool call.

11. **R11 [CONDITIONAL on R18=PASS] — Concurrency-safe via flock at `$cortex_root/.git/cortex-update.lock`.** The MCP acquires `fcntl.flock(LOCK_EX)` on the lock file before running `cortex upgrade`. Lock is released in a `try/finally` block after the upgrade-and-verify cycle completes. Wait budget is 30 seconds; if the lock is still held after the budget, the MCP logs to stderr and proceeds without upgrading. **Post-flock-acquire re-verification**: after acquiring the lock, the MCP re-runs `git -C $cortex_root rev-parse HEAD` and compares to the captured pre-flock remote_sha; if they match (another MCP already applied the update), the MCP skips the redundant `cortex upgrade` invocation. Acceptance:
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_concurrent_upgrade_only_one_subprocess_runs -v` exits 0. That test (following the `cortex_command/init/tests/test_settings_merge.py:340-429` pattern) spawns two threads that both detect upstream advance and asserts only one `cortex upgrade` subprocess is invoked.
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_concurrent_upgrade_both_threads_return_success -v` exits 0. That test asserts both threads return success after the race.

12. **R12 [CONDITIONAL on R18=PASS] — Verification probe forces module import.** After `cortex upgrade` exits 0, the MCP runs `cortex --print-root` followed by `cortex overnight status --format json` against an empty/unknown session id. Both must exit 0 with parseable JSON. The second probe forces import of `cortex_command.overnight.cli_handler` (the lazy-import failure mode identified in 145 research) — this catches partial-install corruption from a `uv tool install --force` that succeeded at the shim layer but failed mid-rewrite of the module files. If the probe fails, the MCP logs the failure to NDJSON and falls through to delegating against the on-disk CLI (degraded path; user sees the upgrade-failure error in the tool-call response). Acceptance:
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_verification_probe_fails_on_corrupt_install -v` exits 0. That test mocks `cortex upgrade` to succeed but pre-corrupts the `cortex_command/overnight/cli_handler.py` path; asserts the verification probe returns a non-zero exit and the failure is logged.
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_verification_probe_failure_falls_through_to_on_disk_cli -v` exits 0. That test asserts the MCP proceeds with the user's tool call against the on-disk CLI after a probe failure.

13. **R13 [CONDITIONAL on R18=PASS] — Synchronous schema-floor check before tool delegation.** When the MCP's required CLI schema version (`MCP_REQUIRED_CLI_VERSION`, baked into the MCP source) is greater than the CLI's reported `version` (from `cortex --print-root`), the MCP runs `cortex upgrade` synchronously before delegating any tool call — regardless of throttle policy. This closes the bidirectional staleness window during plugin-update + CLI-update interaction. Acceptance:
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_schema_floor_triggers_synchronous_upgrade -v` exits 0. That test mocks `cortex --print-root` to return `{"version": "0.9", ...}` while the MCP source declares `MCP_REQUIRED_CLI_VERSION = "1.0"`, and asserts `cortex upgrade` is invoked synchronously before the user's tool call.
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_schema_floor_tool_call_runs_after_upgrade -v` exits 0. That test asserts the tool call is delegated against the upgraded CLI after the schema-floor upgrade completes.

14. **R14 [CONDITIONAL on R18=PASS] — Failure surface: NDJSON error log + stderr.** Errors at any update-orchestration stage (`git ls-remote`, `cortex upgrade`, verification probe) append a JSON line to `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-error.log` with `{"ts": "<ISO 8601>", "stage": "<name>", "error": "<message>", "context": {...}}`. The MCP also writes a one-line summary to its stderr (e.g., `cortex auto-update failed at git_ls_remote: timeout; falling through to on-disk CLI`). The user's intended tool call still executes against the on-disk CLI version (degraded but not broken). Acceptance:
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_ls_remote_timeout_appends_error_log -v` exits 0. That test mocks `git ls-remote` to raise a `subprocess.TimeoutExpired` exception and asserts a JSON line is appended to the error log path.
   - `uv run pytest tests/test_mcp_auto_update_orchestration.py::test_ls_remote_timeout_tool_call_still_returns -v` exits 0. That test asserts the user's tool call returns successfully after the timeout failure.

### Schema versioning

15. **R15 — Two-axis `major.minor` versioning per Terraform `format_version`.** Every JSON payload emitted by the CLI for MCP consumption (R3–R5, plus future verbs) includes a `"version": "M.m"` string field (string, not number, so `"1.10"` parses correctly). Major bump (M increments) = breaking change; consumer rejects mismatched major with a clear error. Minor bump (m increments) = additive change; consumer skips unknown fields for forward-compat. Initial version: `"1.0"`. Acceptance:
   - `grep -F '"version":' docs/mcp-contract.md` returns at least one match (i.e., the contract doc exists and documents the version field).
   - `uv run pytest tests/test_mcp_subprocess_contract.py::test_major_version_mismatch_is_rejected -v` exits 0. That test asserts the MCP refuses payloads whose major component differs from `MCP_REQUIRED_CLI_VERSION`.
   - `uv run pytest tests/test_mcp_subprocess_contract.py::test_minor_version_greater_skips_unknown_fields -v` exits 0. That test asserts the MCP accepts payloads with a greater minor version and silently skips the unknown fields.

16. **R16 — `cortex --print-root` JSON shape is forever-public-API.** The current shape `{"version": "1.0", "root": str, "remote_url": str, "head_sha": str}` is append-only after publication. Future additions go through minor bumps; the existing fields never change semantics or types without a major bump. Acceptance: `grep -F 'Forever-public API' docs/mcp-contract.md` returns one match, confirming the contract doc includes the required stability-commitment section.

17. **R17 — Confused-deputy mitigation on `${CLAUDE_PLUGIN_ROOT}`.** The plugin-bundled MCP source verifies, at startup, that its own `__file__` path is a prefix-match of the resolved `${CLAUDE_PLUGIN_ROOT}` (or the path declared in the plugin's manifest). On mismatch, the MCP refuses to start with a clear error. This prevents an attacker who can override `CLAUDE_PLUGIN_ROOT` from pointing uvx at arbitrary Python. Acceptance: `uv run pytest tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero -v` exits 0. That test invokes the MCP source with `CLAUDE_PLUGIN_ROOT=/tmp/attacker-controlled` and asserts it exits non-zero with a message containing "plugin path mismatch".

### Sandbox & operability

18. **R18 — Q#1 sandbox empirical probe is the first task in implementation; gates R10–R14.** Before any other R10–R14 implementation work, run a probe: invoke a minimal MCP source as a real MCP server from a real Claude Code session on the user's macOS machine. From inside an MCP tool handler, exercise the four operations R10–R14 actually perform:
    1. **Filesystem write to `.git/`**: `pathlib.Path(f"{cortex_root}/.git/.cortex-write-probe").touch()`.
    2. **`flock` acquisition** (R11 surface): open `f"{cortex_root}/.git/cortex-update.lock"` with `os.O_RDWR | os.O_CREAT`, attempt `fcntl.flock(fd, fcntl.LOCK_EX)`, then release.
    3. **`uv tool install --force`** (R10 surface): `subprocess.run(["uv", "tool", "install", "-e", str(cortex_root), "--force"], capture_output=True, text=True, timeout=60)`. Verify writes landed at both `~/.local/share/uv/tools/cortex-command/lib/` (module rewrites) and `~/.local/bin/cortex` (shim rewrite).
    4. **Post-upgrade subprocess execution** (R12 surface): `subprocess.run(["cortex", "--print-root"], ...)` and `subprocess.run(["cortex", "overnight", "status", "--format", "json"], ...)` against an empty/unknown session id. Both must exit 0 with parseable JSON.

    Acceptance: probe-result note at `lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/sandbox-probe-result.md` documents each operation's exit code and any error messages, plus a verdict. **PASS** = all four operations succeed; **FAIL** = any of operations 1–4 is blocked by sandbox (or any other macOS-level restriction such as TCC); **PARTIAL** = some succeed, some fail — document which, and treat as FAIL for R10–R14 scoping (the R10–R14 set requires all four operations to function). If verdict is PASS, proceed with R10–R14 as specified. If verdict is FAIL or PARTIAL, scope changes per R19. R8–R9 and R15–R17 proceed regardless of probe verdict (they do not depend on the four probe operations). The probe must not be run as a `Bash` tool invocation (which inherits Claude Code's bash sandbox) — it must run as MCP tool handler code spawned by Claude Code's MCP-launch path, mirroring the production R10–R14 execution context.

19. **R19 — Fallback if R18 returns FAIL or PARTIAL: degrade to Alternative D (notice-only).** If the sandbox probe in R18 returns FAIL or PARTIAL, R10–R14 (orchestration, flock, verification probe, schema-floor gate, NDJSON error log) become out-of-scope. Instead: the MCP runs the throttled `git ls-remote` check (R8) and skip-predicate evaluation (R9) but on detecting upstream advance, surfaces a one-line `"cortex update available — run \`cortex upgrade\`"` notice in each tool-call response (no `cortex upgrade` invocation, no flock, no verification probe, no schema-floor gate). The user runs `cortex upgrade` from a bare shell.

    Scope reduction map for FAIL/PARTIAL path: **out-of-scope** = R10, R11, R12, R13, R14. **In-scope** = R1–R9 (decoupling, JSON contract, throttled update-check, skip predicates) and R15–R17 (schema versioning machinery, `cortex --print-root` forever-public-API, confused-deputy mitigation). R15–R17 are retained on the FAIL path for two reasons: (a) the JSON contract between MCP and CLI exists regardless of which path applies the upgrade — staleness via a stale `.mcp.json` against a newly-upgraded CLI still requires the MCP to detect schema mismatch and refuse to serve; (b) the `cortex --print-root` flag (R3) is consumed by R8's update check and by the discoverability nudge surface, so its forever-public-API stability commitment (R16) earns its keep without R13.

    Partial-implementation rollback contract: if R10, R11, R12, R13, or R14 implementation has begun before R18 returns FAIL/PARTIAL (e.g., a teammate implemented R8 throttle scaffolding alongside an exploratory R12 verification probe), all R10–R14 code paths are deleted; no latent infrastructure is retained. The R8 throttle cache is rewired to gate the discoverability nudge instead of the upgrade-orchestration call site.

    Acceptance:
    - If R18 verdict is FAIL or PARTIAL, `lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/sandbox-probe-result.md` contains the rationale and the scope-cut diff (which R10–R14 acceptance criteria are dropped).
    - If R18 verdict is FAIL or PARTIAL, a follow-up backlog ticket is filed to investigate `cortex init` allowWrite registration of `$cortex_root/.git/` and `~/.local/share/uv/tools/cortex-command/` paths for a future revisit of R10–R14.
    - On the FAIL/PARTIAL path, `grep -F 'cortex update available' plugins/cortex-overnight-integration/server.py` returns at least one match (the discoverability nudge string is present in source).

20. **R20 — Plugin-refresh semantics empirical investigation.** Investigate Claude Code's behavior when the plugin updates: does it restart MCP servers, only on session restart, or asynchronously? Document in spec implementation. The result determines whether Value bullet 2 ("no Claude Code restart needed for CLI updates to take effect") holds. Acceptance: a brief investigation note at `lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/plugin-refresh-semantics.md` describes the observed behavior; if MCP restart requires Claude Code restart, this is documented as a known limitation in the spec's Edge Cases.

### Operability & performance

21. **R21 — Subprocess-overhead benchmark.** Measure the per-tool-call overhead added by the new subprocess+JSON path. Benchmark scenario: `overnight_status` polled at 30-second intervals (overnight-runner cadence) and `overnight_logs` cursor-paginated at the dashboard's actual rate. Compare overhead vs. the current in-process implementation. Acceptance: benchmark results exist at `lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/perf-benchmark.md` showing p50, p95, p99 latencies for both `overnight_status` and `overnight_logs` paths under both implementations. If the new implementation adds more than 200ms p95 to either path, document in the spec's Edge Cases as a known regression to evaluate post-merge.

### Threat model

22. **R22 — Auto-update threat-model documentation.** The spec includes a "Threat Model" section (in this spec) acknowledging that MCP-orchestrated auto-update is auto-RCE: if the cortex GitHub repo is compromised, the next MCP-triggered `cortex upgrade` runs attacker-controlled code with the user's privileges. Trade-off accepted because cortex-command is personal tooling per `requirements/project.md` ("Published packages or reusable modules for others — out of scope"). Bare-shell users always have explicit control via `cortex upgrade`. No env-var opt-in tamper window in this ticket. Acceptance: this spec's Threat Model section (below) covers this; downstream readers see the deliberate choice.

## Threat Model

MCP-orchestrated auto-update is auto-RCE. If the upstream cortex repository on GitHub is compromised (account takeover, malicious PR merged, dependency poisoning of the install script), the next MCP-triggered `cortex upgrade` runs attacker-controlled code with the user's privileges — including filesystem write access to `~/.local/share/uv/tools/cortex-command/`, `~/.local/bin/cortex`, and any path the cortex CLI subsequently reaches.

**Trade-off accepted**: cortex-command is personal tooling per `requirements/project.md` ("Published packages or reusable modules for others — out of scope"). The user is responsible for the trustworthiness of the upstream repository (their own GitHub account). Skip predicates (R9) provide a per-machine kill switch for the dogfooding case (`CORTEX_DEV_MODE=1`); bare-shell users always have explicit control via `cortex upgrade` from a terminal — no MCP-orchestrated upgrade fires for them.

**Not in scope for this ticket**: a `CORTEX_REPO_PIN_SHA` env var to pin updates to a specific commit. If a future user wants a tamper window, that is a small follow-up; not required to ship this work.

## Non-Requirements

- **No inline auto-update gate inside `cortex_command/cli.py::main()`.** Rejected during ticket 145's plan-phase critical review; reaffirmed rejected here. The CLI keeps its existing explicit `cortex upgrade` verb (`cli.py:85-119`).
- **No removal of CLI's overnight orchestration logic.** The CLI keeps owning all heavyweight code; the MCP only delegates.
- **No remote MCP transport.** Stdio remains the only transport.
- **No Python deps bundling for the plugin.** PEP 723's `# /// script` block plus uvx caching is the deps mechanism. No vendored deps.
- **No multi-version compatibility between MCP and CLI.** First implementation pins MCP to a single CLI major schema version; cross-version compatibility is a future concern.
- **No auto-update for bare-shell `cortex` invocations.** Bare-shell users explicitly run `cortex upgrade`. A discoverability nudge ("update available") for bare-shell is a small follow-up if needed, not load-bearing for this ticket.
- **No second flock at `~/.local/share/uv/tools/cortex-command/.cortex-update.lock` for cross-tool serialization.** Carved out as out-of-scope: external `uv tool upgrade cortex-command` invocations from a separate shell, while the MCP is mid-upgrade, may produce indeterminate results. Document this in `docs/mcp-contract.md`.
- **No `CORTEX_REPO_PIN_SHA` env-var opt-in for tamper window.** Cortex is personal tooling; the trade-off is documented in this spec's Threat Model and accepted. A future ticket can add the env var if a stability-conscious user emerges.
- **No `cortex selftest` new command.** Verification probe (R12) reuses two existing verbs — `cortex --print-root` and `cortex overnight status --format json`. Add a new `selftest` verb only if multiple consumers (CI, dashboard health-check, MCP probe) emerge, which would be a separate follow-up.

## Edge Cases

- **Q#1 sandbox probe FAIL**: covered by R19 (fallback to notice-only).
- **`cortex` not on PATH**: discovery chain (R3 → editable-install `.pth` → `$HOME/.cortex` → hard-fail). Hard-fail surfaces as a structured MCP error, not silent fallback against a phantom directory.
- **`git ls-remote` timeout / network failure**: skip predicate fires implicitly; cached attempt; user's tool call proceeds against on-disk CLI. Re-tries on next MCP server startup.
- **`cortex upgrade` fails halfway (partial install)**: verification probe (R12) catches this; MCP logs the failure to NDJSON and falls through to the on-disk CLI (R14). User sees the upgrade-failure error in their tool-call response; manual `cortex upgrade` from bare shell is the recovery path.
- **Concurrent MCP processes (multiple Claude sessions)**: blocking flock (R11); post-acquire HEAD re-verification skips redundant `cortex upgrade` invocations.
- **External `uv tool upgrade cortex-command` from a separate shell**: out-of-scope per Non-Requirements. May produce indeterminate results during MCP-orchestrated upgrade; documented in `docs/mcp-contract.md`.
- **Plugin-refresh requires Claude Code restart** (per R20 empirical investigation): if the empirical investigation shows MCP restart requires Claude Code restart, document as known limitation. Value bullet 2 holds with the addendum "after the next Claude Code session starts".
- **MCP source older than CLI** (e.g., user installs new CLI manually then opens an old MCP source from a stale plugin install): MCP's schema-version check (R15) rejects payloads with major-mismatch; MCP logs the error and refuses to start.
- **CLI older than MCP source** (the bidirectional staleness window during plugin-update + CLI-update): handled by R13 synchronous schema-floor gate.
- **`uvx` first-run offline**: documented as acceptable degradation per ticket scope. MCP server fails to start; Claude Code shows server-unavailable error. User goes online, retries.
- **Subprocess overhead under high tool-call rates** (overnight polling, dashboard cursor pagination): R21 benchmark establishes the actual cost. If >200ms p95 added to either path, documented as known regression for post-merge evaluation.

## Changes to Existing Behavior

- **MODIFIED**: `plugins/cortex-overnight-integration/.mcp.json` — points at `uvx ${CLAUDE_PLUGIN_ROOT}/server.py` instead of `cortex mcp-server`. Existing plugin installs auto-update via Claude Code's plugin-refresh mechanism (R20 investigation determines whether Claude Code restarts the MCP automatically).
- **REMOVED**: `cortex_command/mcp_server/{server.py, tools.py, schema.py}` — deleted entirely. The MCP source's sole canonical location is `plugins/cortex-overnight-integration/server.py` (R6). `cortex_command/mcp_server/` directory is removed from the package.
- **MODIFIED**: `cortex mcp-server` CLI verb — repurposed as a deprecation stub (R7). Argparse entry remains; invocation prints a one-line migration message naming `cortex-overnight-integration` as the migration target and exits non-zero. Users with stale `.mcp.json` pointing at `cortex mcp-server` see the message in Claude Code's MCP-server-failed-to-start error and migrate to the plugin path.
- **ADDED**: `cortex --print-root` CLI flag (R3).
- **ADDED**: `--format json` on `cortex overnight start`, `cortex overnight logs`, `cortex overnight cancel` (R4, R5). `cortex overnight status` already has it.
- **ADDED**: `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-error.log` NDJSON error log (R14).
- **ADDED**: `$cortex_root/.git/cortex-update.lock` flock file (R11).
- **ADDED**: `docs/mcp-contract.md` documenting the versioned JSON contract (R15, R16, plus the cross-tool uv invocation carve-out).
- **ADDED**: `lifecycle/.../sandbox-probe-result.md`, `plugin-refresh-semantics.md`, `perf-benchmark.md` artifacts (R18, R20, R21).
- **UNCHANGED**: `cortex upgrade` CLI verb continues to work (`cli.py:85-119`); existing pre-install in-flight guard semantics (`CORTEX_ALLOW_INSTALL_DURING_RUN`, `CORTEX_RUNNER_CHILD`) unchanged.

## Technical Constraints

- **No `cortex_command.*` imports in `plugins/cortex-overnight-integration/server.py`.** This is the architectural invariant of the refactor (R1).
- **PEP 723 deps must use major bounds, not bare names.** AWS MCP issue #2533 (fastmcp 3.x cold-cache breakage) is the cited precedent; bare names are unsafe.
- **All flocks acquired with `try/finally` to release.** Existing pattern in `cortex_command/init/settings_merge.py:69-85`.
- **All atomic writes use tempfile-in-same-directory + `os.replace()`.** Existing pattern in `cortex_command/common.py:366-407`.
- **All subprocess invocations use `subprocess.run(..., capture_output=True, text=True, timeout=N)`.** Never `check=True`; catch and handle errors explicitly. Set `timeout` on long-running calls (5s for `git ls-remote`, 60s for `cortex upgrade`).
- **Schema versioning is two-axis `major.minor` string per Terraform `format_version`.** Initial version `"1.0"`. Major-bump = hard-equality check; minor-bump = skip-unknown for forward-compat.
- **`cortex --print-root` JSON shape is forever-public-API.** Append-only after publication; existing fields never change semantics or types without a major bump.
- **MCP's required CLI schema version is baked into the MCP source** as a constant (e.g., `MCP_REQUIRED_CLI_VERSION = "1.0"`). This is the floor the MCP refuses to operate below.
- **Skip predicates evaluated MCP-side, not CLI-side**: `CORTEX_DEV_MODE`, dirty tree, non-main branch.
- **Plugin auto-update is Claude Code's responsibility**: cortex's MCP does not orchestrate plugin updates; Claude Code's `/plugin install`/refresh path handles that.
- **Stdio MCP transport only.** No HTTP/SSE.
- **Gate dispatch order on every tool call** (resolves the R8/R10/R11/R13 interaction the critical review flagged):
  1. **R13 schema-floor check first.** Read CLI's reported `version` via `cortex --print-root` (cached for the MCP-server lifetime; the discovery cache is separate from R8's update-check cache and never expires). If `MCP_REQUIRED_CLI_VERSION > CLI version`, run `cortex upgrade` synchronously (under R11 flock) and the verification probe (R12) before delegating. Skip predicates (R9) do NOT apply to R13 — schema-floor mismatch must be resolved or the MCP cannot serve any tool call.
  2. **R8 throttle check second**, only if R13 did not fire. Apply skip predicates (R9) before the ls-remote check.
  3. **R10 + R11 + R12** fire if R8 detected upstream advance and skip predicates didn't fire.
- **Cache invalidation rules for R8's instance cache**:
  - On any successful upgrade (R10 or R13), the cache MUST be marked unset so the next tool call re-checks. (After upgrade, the local HEAD has advanced; treating the cache as "checked = current upstream" would mask any further upstream advance that landed during the upgrade window.)
  - On R11 flock-budget expiry (lock held >30s, MCP proceeds without upgrading), the cache MUST be marked unset so the next tool call retries the ls-remote and the flock attempt. The "known-needed upgrade" must not be silently abandoned for the rest of the MCP lifetime.
  - On any update-orchestration error (R14 NDJSON-logged failure), the cache MUST be marked unset so the next tool call retries.
- **R11 post-acquire HEAD re-verification reference point**: after acquiring the flock, the MCP runs a *fresh* `git ls-remote <remote-url> HEAD` (not the captured pre-flock remote_sha) and compares to the freshly-read `git -C $cortex_root rev-parse HEAD`. If they match, skip the redundant `cortex upgrade`. This handles the case where another MCP's R13- or R10-triggered upgrade landed past the captured pre-flock remote_sha during the flock wait.

## Open Decisions

None deferred to plan-phase. All sub-decisions resolved in Spec. Note: R10–R14 are explicitly conditional on R18 PASS verdict; R19 specifies the FAIL-path scope reduction. This is a specified branch in the spec, not a deferred decision.
