# Plan: close-plugin-cli-auto-update-gaps

## Overview

Close Gaps A/B/C end-to-end via a four-phase landing: (1) versioning baseline — adopt hatch-vcs for the CLI wheel and migrate the JSON envelope's `version` field semantic from schema-floor M.m to PEP 440 package version, introducing a new `schema_version` field that carries the old M.m semantic (major bump 1.x → 2.0 per `docs/internals/mcp-contract.md:19`); (2) plugin auto-update wiring — vendor `install_guard` as a sibling of `server.py` with byte-level parity, wire `_ensure_cortex_installed` to compare package versions via `packaging.version.Version`, replace `_parse_major_minor`, replace the R13 silent short-circuit with stderr remediation; (3) auto-release on push to main — `auto-release.yml` workflow + two new bin helpers (`cortex-auto-bump-version`, `cortex-rewrite-cli-pin`) + CI lint at `release.yml` as defense-in-depth; (4) tests, docs, cleanup — real-install integration test, release-artifact invariant test, install_guard parity test, authoritative `docs/internals/auto-update.md`, #210 doc rewrites, supersede #211/#212, CHANGELOG.

## Outline

### Phase 1: Versioning baseline (CLI side) (tasks: 1, 2, 3, 4, 5, 6, 7)
**Goal**: Migrate the CLI wheel to hatch-vcs dynamic versioning AND repurpose the JSON envelope's `version` field to mean PEP 440 package version, with a new `schema_version` field carrying the schema-floor M.m semantic.
**Checkpoint**: `cortex --print-root --format json` emits both `version` (package) and `schema_version="2.0"`; mcp-contract.md reflects the new envelope; `just test` green for all tests touching the envelope.

### Phase 2: Plugin auto-update wiring (tasks: 8, 9, 10, 11, 12)
**Goal**: `_ensure_cortex_installed` reinstalls on `CLI_PIN[0]` mismatch using `packaging.version.Version`, honors the vendored install_guard sibling, and `_schema_floor_violated` emits a stderr remediation surface under wheel install.
**Checkpoint**: `_parse_major_minor` is gone, the vendored sibling exists with pre-commit parity, R4 has a working version-compare branch, and R13 surfaces remediation on schema-floor violations under wheel install.

### Phase 3: Auto-release + CI lint safety net (tasks: 13, 14, 15, 16, 17, 18)
**Goal**: Land `auto-release.yml` plus the two helper scripts so push-to-main auto-bumps `CLI_PIN` and tags via PAT; add a CI lint in `release.yml` as defense-in-depth (subsumes #212); update commit skill + release-process docs.
**Checkpoint**: `auto-release.yml` exists with workflow_dispatch + concurrency + rebase + PAT; both bin scripts ship with unit tests; CI lint enforces CLI_PIN drift; release-process.md has the PAT setup runbook.

### Phase 4: Tests, docs, and cleanup (tasks: 19, 20, 21, 22, 23, 24, 25)
**Goal**: Land the agent-verifiable integration test (six explicit phases) + the invariant test + the parity test + the authoritative internals doc + #210 doc rewrites + #211/#212 supersession + CHANGELOG.
**Checkpoint**: All four new test files exit 0 individually under `just test --`; `docs/internals/auto-update.md` is cross-referenced from setup.md/README.md/CLAUDE.md; #211/#212 marked superseded; CHANGELOG names Gap A/B/C closure + BREAKING.

## Tasks

### Task 1: Adopt hatch-vcs in pyproject; gitignore _version.py

- **Files**: `pyproject.toml`, `.gitignore`
- **What**: Switch the CLI wheel to dynamic versioning sourced from git tags. Adds `dynamic = ["version"]` in `[project]`, drops the static `version = "0.1.0"`, configures `[tool.hatch.version]`, `[tool.hatch.version.raw-options]` (`local_scheme = "no-local-version"`), `[tool.hatch.build.hooks.vcs]` (`version-file = "cortex_command/_version.py"`), and adds `hatch-vcs` to `[build-system] requires`. Adds `cortex_command/_version.py` to `.gitignore`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing `[build-system]` already uses `hatchling.build`. The `[tool.hatch.build.targets.wheel]` and `force-include` sections stay unchanged — hatch-vcs is purely additive. Per research §FD1, `local_scheme = "no-local-version"` is critical to keep `1.0.3+gabc1234` suffixes off dirty-checkout wheels. Spec R1, R2.
- **Verification**: `grep -E '^version\s*=\s*"' pyproject.toml | wc -l` returns 0 — pass if 0; `grep -cE '\[tool\.hatch\.version\]' pyproject.toml` returns 1; `grep -cE 'hatch-vcs' pyproject.toml` returns at least 1; `git check-ignore cortex_command/_version.py` exits 0.
- **Status**: [ ] pending

### Task 2: Update release.yml for hatch-vcs (fetch-depth: 0, fetch-tags: true)

- **Files**: `.github/workflows/release.yml`
- **What**: Add `fetch-depth: 0` and `fetch-tags: true` to the `actions/checkout@v4` step so hatch-vcs has full history at wheel-build time. Without these, the shallow checkout strips tags and hatch-vcs reports the wrong version.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Current step is at `release.yml:26` (`uses: actions/checkout@v4`) with no `with:` block. Per research adversarial §2.K and spec R3. The CI lint for CLI_PIN drift lands in T15, not here.
- **Verification**: `grep -cE 'fetch-depth:\s*0' .github/workflows/release.yml` returns 1; `grep -cE 'fetch-tags:\s*true' .github/workflows/release.yml` returns 1.
- **Status**: [ ] pending

### Task 3: Rewire print-root envelope `version` → package version; add `schema_version` field; bump _JSON_SCHEMA_VERSION to "2.0"

- **Files**: `cortex_command/cli.py`, `cortex_command/overnight/cli_handler.py`
- **What**: At `cortex_command/cli.py:225-231` (the `_dispatch_print_root` envelope), source `version` from `importlib.metadata.version("cortex-command")` with a `try/except PackageNotFoundError` fallback to `"0.0.0+source"` for the editable/source path, and add a `schema_version` field set to the new constant. In `cortex_command/overnight/cli_handler.py:107`, update `_JSON_SCHEMA_VERSION = "1.0"` → `"2.0"`. Note: do NOT yet change `_emit_json`'s stamping key — that flip lives in T4 so the producer-side change is atomic with consumer migration.
- **Depends on**: none
- **Complexity**: simple
- **Context**: cli.py:166-170's docstring already documents the envelope-vs-package distinction. The sentinel fallback parses cleanly via `packaging.version.Version("0.0.0+source")`. Spec R4, R5. `importlib.metadata` returns the PEP 440 form (`"0.1.0"`, no leading `v`). The implementer should reinstall the wheel locally (`uv tool install --force .` or equivalent) before running the verification command, since `importlib.metadata` reads installed-package metadata.
- **Verification**: `cortex --print-root --format json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["schema_version"] == "2.0", d' && echo OK` prints `OK`; `cortex --print-root --format json | python3 -c 'import json,sys,importlib.metadata; d=json.load(sys.stdin); v=importlib.metadata.version("cortex-command"); assert d["version"] in (v, "0.0.0+source"), d' && echo OK` prints `OK`; `grep -nE '^_JSON_SCHEMA_VERSION\s*=\s*"2\.0"' cortex_command/overnight/cli_handler.py` returns one match.
- **Status**: [ ] pending

### Task 4: Flip `_emit_json` producer to stamp `schema_version`; migrate CLI-side test mocks

- **Files**: `cortex_command/overnight/cli_handler.py`, `tests/test_cli_print_root.py`, `tests/test_cli_overnight_format_json.py`
- **What**: At `cortex_command/overnight/cli_handler.py:116`, flip the `_emit_json` helper's stamping key from `"version": _JSON_SCHEMA_VERSION` to `"schema_version": _JSON_SCHEMA_VERSION`. Migrate test-mock assertions in `tests/test_cli_print_root.py` and `tests/test_cli_overnight_format_json.py`. Two distinct assertion shapes exist and require different migrations: (a) **literal dict-key assertions** matching `"version": "1.x"` → flip the key to `"schema_version": "2.0"`; (b) **`payload["version"].startswith("1.")` assertions** at `tests/test_cli_overnight_format_json.py:119, 179, 254` (and any sibling files) → rewrite to `payload["schema_version"].startswith("2.")` AND add a separate PEP 440 check `payload["version"]` for the package-version field where the test exercises print-root. There are 19 `_emit_json` call sites in `cli_handler.py` (definition at line 110, calls at 543, 596, 622, 855, 918, 965, 1153, 1175, 1250, 1376, 1515, 1525, 1544, 1553, 1568, 1584, 1590, 1617, 1642 — verify count at implement time); call sites require NO changes, only the helper.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Splitting the migration across T4 and T5 is required so each task stays inside the 1-5 file budget. After T4 lands, the MCP-side test suite is temporarily broken (mocks in test_mcp_*.py still assert `"version": "1.x"`); T5 finishes the in-test-mock migration; T9 finalizes consumer-read migration in plugin server.py. T4's verification is grep-only (does NOT run the full suite). The whole T4-T9 sequence MUST land atomically in one PR — intermediate commits exist only on the feature branch and never on `main` (see Risks: "T4-to-T9 window is a runtime functional regression").
- **Verification**: `grep -cE '"schema_version":\s*_JSON_SCHEMA_VERSION' cortex_command/overnight/cli_handler.py` returns 1; `grep -rE '"version":\s*"[0-9]+\.[0-9]+",?' tests/test_cli_print_root.py tests/test_cli_overnight_format_json.py | wc -l` returns 0 (no remaining schema-style M.m literals; `,?` covers the trailing-comma case the earlier `$`-anchored grep missed); `grep -cE 'payload\["version"\]\.startswith\("1\.' tests/test_cli_overnight_format_json.py` returns 0 (the legacy startswith pattern is gone).
- **Status**: [ ] pending

### Task 5: Migrate MCP-side test mocks under `tests/` to `schema_version`

- **Files**: `tests/test_mcp_auto_update_orchestration.py`, `tests/test_mcp_subprocess_contract.py`, `tests/test_mcp_cortex_cli_missing.py`, `tests/test_no_clone_install.py`
- **What**: Two distinct envelope-mock shapes exist in these files and require different migrations: (a) **`_emit_json` envelope mocks** (every `"version": "1.0"` literal across `test_mcp_*.py` — these mock overnight subcommand output) → flip the key to `"schema_version": "2.0"`; (b) **print-root envelope mocks** (e.g., `tests/test_no_clone_install.py:346` `"version": "1.1"` inside `_print_root_success_stdout`) → DO NOT mechanically rename; instead, set `"version"` to a PEP 440 package version string (e.g., `"0.1.0"`) AND add a new sibling field `"schema_version": "2.0"`, since print-root envelopes post-T3 carry BOTH fields. Disambiguate by inspecting each mock's surrounding context before editing. Enumerate via `grep -rnE '"version":\s*"[0-9]+\.[0-9]+"' tests/test_mcp_*.py tests/test_no_clone_install.py` at implement time. T6 covers the plugin's tests in parallel.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: The blind "flip the key" rule applied to a print-root mock would produce `"schema_version": "1.1"` — an invalid envelope (the post-bump schema is "2.0"). Treat `_emit_json` mocks and print-root mocks as separate migrations. The MCP test suite remains partially red after T5+T6 (plugin server.py consumer reads not yet migrated — T9's scope).
- **Verification**: `grep -rE '"version":\s*"1\.[01]",?' tests/test_mcp_auto_update_orchestration.py tests/test_mcp_subprocess_contract.py tests/test_mcp_cortex_cli_missing.py tests/test_no_clone_install.py | wc -l` returns 0 (the `,?` covers the trailing-comma case; no remaining 1.x schema-style literals); `grep -rE '"schema_version":\s*"2\.0"' tests/test_mcp_auto_update_orchestration.py tests/test_mcp_subprocess_contract.py tests/test_mcp_cortex_cli_missing.py tests/test_no_clone_install.py | wc -l` returns at least 3 (at least three of the four migrated files picked up the new key); `grep -nE '"schema_version":\s*"1\.' tests/test_no_clone_install.py` returns 0 (the print-root mock did NOT get the blind key-rename treatment).
- **Status**: [ ] pending

### Task 6: Migrate plugin and overnight package test mocks to `schema_version`

- **Files**: `plugins/cortex-overnight/tests/test_overnight_schedule_run.py`, `plugins/cortex-overnight/tests/test_overnight_start_run.py`, `cortex_command/overnight/tests/test_cli_schedule.py`, `cortex_command/overnight/tests/test_cancel_scheduled.py`
- **What**: Flip every `_emit_json`-mock `"version": "1.0"` literal/assertion across the two `plugins/cortex-overnight/tests/` files AND the two `cortex_command/overnight/tests/` files (`test_cli_schedule.py:140` `assert payload["version"] == "1.0"`; `test_cancel_scheduled.py:230` same shape) to `"schema_version": "2.0"`. Confirmed via `grep -rE '"version":\s*"[0-9]+\.[0-9]+"' plugins/cortex-overnight/tests/ cortex_command/overnight/tests/` at implement time. The `cortex_command/overnight/tests/` directory was omitted in the original plan and surfaced by critical-review — it directly exercises the `_emit_json` producer flipped at T4.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Per spec R6 enumeration plus critical-review R2F1. Each file has 1-3 occurrences. The MCP test suite is still partially red until T9 migrates plugin server.py reads.
- **Verification**: `grep -rE '"version":\s*"1\.[01]",?' plugins/cortex-overnight/tests/ cortex_command/overnight/tests/test_cli_schedule.py cortex_command/overnight/tests/test_cancel_scheduled.py | wc -l` returns 0; `grep -rE '"schema_version":\s*"2\.0"' plugins/cortex-overnight/tests/ cortex_command/overnight/tests/test_cli_schedule.py cortex_command/overnight/tests/test_cancel_scheduled.py | wc -l` returns at least 4.
- **Status**: [ ] pending

### Task 7: Update mcp-contract.md for major-2.0 envelope shape

- **Files**: `docs/internals/mcp-contract.md`
- **What**: Rewrite the JSON envelope reference and example envelopes to carry both `version` (PEP 440 package version) and `schema_version` (M.m schema floor). Update all `"version": "1.1"` examples to the new pair. Add a "Schema evolution log" subsection citing #213 with the major-bump rationale.
- **Depends on**: [3, 4, 5, 6]
- **Complexity**: simple
- **Context**: The doc's forever-public-API rule at `docs/internals/mcp-contract.md:19` is what mandates the major bump. Soft positive-routing per CLAUDE.md MUST-policy. Spec R8.
- **Verification**: `grep -cE '"schema_version":' docs/internals/mcp-contract.md` returns at least 3; `grep -cE '"version":\s*"1\.[01]"' docs/internals/mcp-contract.md` returns 0; `grep -cE '^##.*Schema evolution log' docs/internals/mcp-contract.md` returns 1.
- **Status**: [ ] pending

### Task 8: Refactor `cortex_command/install_guard.py`; vendor sibling at `plugins/cortex-overnight/install_guard.py`; add `just sync-install-guard` regen + pre-commit parity gate

- **Files**: `cortex_command/install_guard.py`, `plugins/cortex-overnight/install_guard.py`, `.githooks/pre-commit`, `justfile`
- **What**: Extract `check_in_flight_install_core(active_session_path: Path, pid_verifier: Callable, now: Callable=time.time) -> Optional[str]` from `cortex_command/install_guard.py` as a stdlib-only function (the pid-verifier callable AND a `now` callable are parameters to preserve stdlib-only contract — `now` enables deterministic tests). Leave the existing `check_in_flight_install` as a thin wrapper providing the CLI-specific pid-verifier (psutil-backed) and carve-outs. Write the core function verbatim to `plugins/cortex-overnight/install_guard.py`. Add a `sync-install-guard` recipe to `justfile` that auto-regenerates the plugin sibling from the canonical via AST/regex extraction (analogous to `just build-plugin`'s rsync model). Extend `.githooks/pre-commit` to (i) run `just sync-install-guard --check` to verify byte-identity, OR (ii) invoke the regeneration step and diff. **Canonical side**: `cortex_command/install_guard.py` is source-of-truth; the plugin sibling is a downstream artifact. macOS pid-verifier uses `os.kill(pid, 0)` + `ps -p <pid> -o lstart=` (start_time, NOT `comm=`) to preserve recycled-pid semantics across both implementations (parses POSIX-formatted lstart for ±2s compare against `runner.pid`'s recorded `start_time`). The macOS lstart format is parseable via stdlib `time.strptime`.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Per spec R11. The vendored sibling pattern works because the plugin's PEP 723 venv can `sys.path.insert(0, plugin_dir)` and import `install_guard` as a module. Carve-out signals (`CORTEX_ALLOW_INSTALL_DURING_RUN`, `CORTEX_RUNNER_CHILD`, `PYTEST_CURRENT_TEST`, `"pytest" in sys.modules`) live in the wrappers, NOT the core. **Critical-review correction**: the original plan said `ps -p <pid> -o comm=` (process name only), which cannot replicate `psutil.Process(pid).create_time()` recycled-pid semantics — `lstart=` parses the start time and CAN. **Regeneration recipe** rationale: `inspect.getsource` byte-identity is whitespace-brittle; without a regeneration command, autoformatter passes break parity. `just sync-install-guard` self-heals the way `just build-plugin` does for BUILD_OUTPUT_PLUGINS.
- **Verification**: `just sync-install-guard --check` exits 0 (byte-identical source-of-truth → mirror); `diff <(python3 -c 'import inspect, cortex_command.install_guard as g; print(inspect.getsource(g.check_in_flight_install_core))') <(python3 -c 'import sys, inspect; sys.path.insert(0, "plugins/cortex-overnight"); import install_guard as g; print(inspect.getsource(g.check_in_flight_install_core))')` returns empty stdout (byte-identical); `grep -E 'install_guard|sync-install-guard' .githooks/pre-commit` returns at least one match (parity gate wired).
- **Status**: [ ] pending

### Task 9: Migrate `_check_version` + `_schema_floor_violated` to read `schema_version`; remove `_parse_major_minor`

- **Files**: `plugins/cortex-overnight/server.py`
- **What**: At `_check_version` (line 137) and `_schema_floor_violated` (line ~1499), replace `payload.get("version")` reads with `payload.get("schema_version")`. Replace `_parse_major_minor` (line 124) callers with simple stdlib int-cast on the major component (`int(payload["schema_version"].split(".")[0])`) — `packaging.version.Version` is overkill for the M.m schema-floor compare. Then delete `_parse_major_minor` entirely.
- **Depends on**: [5, 6, 10]
- **Complexity**: simple
- **Context**: Per spec R6 (consumer reads), R14 (`_parse_major_minor` removal). T10 (CLI_PIN bump) is a prerequisite because the schema-floor check post-migration reads "2.0" from envelopes and must compare against `MCP_REQUIRED_CLI_VERSION="2.0"` (set by T10). T9's verification is grep-only — the `just test` whole-suite gate moves to T11 (where the R4 wiring + vendored install_guard sibling are also in place; tests exercising `_ensure_cortex_installed` need the new branch landed to pass). Critical-review correction: T9's original "just test exit 0" claim was unreachable until T11 wired the version-compare branch.
- **Verification**: `grep -cE 'def _parse_major_minor|_parse_major_minor\(' plugins/cortex-overnight/server.py` returns 0; `grep -cE 'payload\.get\(["\x27]schema_version["\x27]\)' plugins/cortex-overnight/server.py` returns at least 2 matches (one in `_check_version`, one in `_schema_floor_violated`).
- **Status**: [ ] pending

### Task 10: Bump CLI_PIN[1] and MCP_REQUIRED_CLI_VERSION to "2.0"

- **Files**: `plugins/cortex-overnight/server.py`
- **What**: At `plugins/cortex-overnight/server.py:105`, update `CLI_PIN = ("v0.1.0", "1.0")` → `CLI_PIN = ("v0.1.0", "2.0")`. The CLI_PIN[0] tag string stays at the current tag value (auto-release at T13 bumps it on next push). `MCP_REQUIRED_CLI_VERSION = CLI_PIN[1]` derivation at line 112 propagates the bump automatically.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Per spec R17. The schema major must match `_JSON_SCHEMA_VERSION` (T3). Lockstep is enforced by `tests/test_release_artifact_invariants.py` (T20).
- **Verification**: `grep -nE 'CLI_PIN\s*=\s*\("v?[0-9]+\.[0-9]+\.[0-9]+",\s*"2\.0"\)' plugins/cortex-overnight/server.py` returns one match.
- **Status**: [ ] pending

### Task 11: Wire R4 version-comparison branch (packaging.version.Version + in-flight guard + absolute-path verification + NDJSON stages); add `packaging` to PEP 723 deps

- **Files**: `plugins/cortex-overnight/server.py`
- **What**: At `_ensure_cortex_installed` (line 443-470), after the existing `shutil.which("cortex") is not None` early-return passes, add a version-comparison block: invoke `cortex --print-root --format json`, parse `payload["version"]` (post-T4 this is the package version), compare to `CLI_PIN[0]` via `packaging.version.Version(installed) != packaging.version.Version(CLI_PIN[0].lstrip("v"))`. On mismatch, invoke the vendored `install_guard.check_in_flight_install_core(...)` (from T8) — if it returns a reason-string, emit NDJSON with `stage="version_mismatch_blocked_by_inflight_session"` and abort. Otherwise fall through to the existing reinstall branch (lines 524-555), preserving sentinel/flock/post-install-verification logic. Pin the post-install probe to the absolute path emitted by `uv tool list --show-paths` (or parsed from install stdout) instead of bare `cortex` via PATH. Wrap version parsing in `try/except packaging.version.InvalidVersion` — on parse failure, emit NDJSON with `stage="version_mismatch_reinstall_parse_failure"` (distinct from `version_mismatch_reinstall`). Register all three new stage values in `_NDJSON_ERROR_STAGES` at lines 772-780. Add `packaging` to the PEP 723 dependency list in the script header (lines 1-15) alongside `mcp` and `pydantic`.
- **Depends on**: [8, 9]
- **Complexity**: complex
- **Context**: Per spec R9, R10, R12, R15, R16. The branch design protects three failure modes: (1) legitimate version mismatch → reinstall; (2) `InvalidVersion` → flagged-as-fallback reinstall (still reinstalls but with distinct stage label so tests can disambiguate); (3) in-flight overnight session → abort with explicit NDJSON record. Absolute-path pinning closes the PATH-poisoning surface (research adversarial §H/§I). The existing R4 first-install path (`shutil.which → None`) is preserved unchanged.
- **Verification**: `awk '/^def _ensure_cortex_installed/,/^def /' plugins/cortex-overnight/server.py | grep -cE 'packaging\.version\.Version'` returns at least 1 (the version-compare branch is wired); `grep -cE 'version_mismatch_reinstall|version_mismatch_reinstall_parse_failure|version_mismatch_blocked_by_inflight_session' plugins/cortex-overnight/server.py` returns at least 6 (each stage registered once + emitted at least once); `awk '/^def _ensure_cortex_installed/,/^def /' plugins/cortex-overnight/server.py | grep -cE 'subprocess\.run\(\["cortex"'` returns 0 (no bare-PATH cortex calls in the function); `grep -cE '"packaging' plugins/cortex-overnight/server.py | head -1` returns at least 1 line inside the PEP 723 metadata block (lines 1-15); each of the three new stage values is in the `_NDJSON_ERROR_STAGES` registry set: `python3 -c 'import sys; sys.path.insert(0, "plugins/cortex-overnight"); import server; missing = {"version_mismatch_reinstall", "version_mismatch_reinstall_parse_failure", "version_mismatch_blocked_by_inflight_session"} - set(server._NDJSON_ERROR_STAGES); sys.exit(0 if not missing else f"MISSING: {missing}")'` exits 0; `just test` exits 0 (whole suite green at this boundary — this is where consumer migration from T9 + R4 wiring + vendored install_guard come together).
- **Status**: [ ] pending

### Task 12: Replace R13 silent short-circuit with stderr remediation surface

- **Files**: `plugins/cortex-overnight/server.py`
- **What**: At `_schema_floor_violated` (lines 1499-1565), when the gate fires AND `cortex_root` has no `.git` dir (wheel install), emit a single-line stderr message in the form `Schema-floor violation: installed CLI schema_version=X.Y, required={CLI_PIN[1]}; run 'uv tool install --reinstall git+...@{CLI_PIN[0]}' to upgrade` before returning. Preserve the existing return value semantics so callers are unaffected.
- **Depends on**: [4, 9]
- **Complexity**: simple
- **Context**: Per spec R13. The silent short-circuit at line 1561 was the original wheel-install dormancy bug. Verified end-to-end by T19 phase (f).
- **Verification**: T19 phase (f) asserts stderr contains the literal substrings `"Schema-floor violation: installed CLI schema_version="` AND `"uv tool install --reinstall git+"`. Static check: `grep -cE 'Schema-floor violation: installed CLI schema_version=' plugins/cortex-overnight/server.py` returns at least 1.
- **Status**: [ ] pending

### Task 13: Author `.github/workflows/auto-release.yml` (with forward references to T14/T15 helpers)

- **Files**: `.github/workflows/auto-release.yml`
- **What**: New workflow on `push: branches: [main]` + `workflow_dispatch`. `permissions: contents: write`. `concurrency: { group: auto-release, cancel-in-progress: true }` (coalescing — push-storms collapse to latest push for idempotent release). **Self-retrigger guard at workflow level**: top-level `if:` filters out commits whose message contains `[release-type: skip]` OR matches `^Release v[0-9]+\.[0-9]+\.[0-9]+$` (the auto-generated release commit shape). Job structure splits PAT exposure: **Job A (validate, low-privilege)** uses default `GITHUB_TOKEN`, fetches with `actions/checkout@v4` (no `token:` override) + `persist-credentials: false`, then runs validate.yml's checks (`just test`, etc.). **Job B (release, high-privilege, `needs: validate`)** also uses `persist-credentials: false` initially; then performs steps: (a) `actions/checkout@v4` with `persist-credentials: false`, `fetch-depth: 0`, `fetch-tags: true`, `ref: main`; (a.5) `git pull --rebase origin main`; (c) invoke `bin/cortex-auto-bump-version` to determine the next tag; (d) when stdout is `no-bump\n`, exit cleanly BEFORE invoking the rewriter (gate); (e) invoke `bin/cortex-rewrite-cli-pin <new-tag>` to update `CLI_PIN[0]` in plugin source; (f) `git commit -m "$(printf 'Release vX.Y.Z\n\n[release-type: skip]\n')"` — the auto-generated commit message MUST embed `[release-type: skip]` as a standalone-line body marker so any re-trigger path (if the workflow-level filter is bypassed) self-no-bumps; (g) `git tag vX.Y.Z`; (h) push step explicitly authenticates only at the push moment: `git -c http.https://github.com/.extraheader="AUTHORIZATION: bearer ${{ secrets.AUTO_RELEASE_PAT }}" push origin main && git -c http.https://github.com/.extraheader="AUTHORIZATION: bearer ${{ secrets.AUTO_RELEASE_PAT }}" push origin vX.Y.Z` (or equivalent — the PAT is NEVER persisted to `.git/config` for the validate job, and only injected at the push command in Job B). On non-fast-forward push failure, `git pull --rebase origin main` once and retry; on second failure fail the job with a manual-recovery error message naming `workflow_dispatch`. Also add a **scheduled PAT-expiry probe**: a sibling job in `auto-release.yml` triggered by `schedule: [cron: '0 12 * * MON']` runs `gh api /repos/{owner}/{repo}/actions/secrets/AUTO_RELEASE_PAT` against itself and posts a workflow annotation if the secret is missing — partial monitoring for silent expiry.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Per spec R19. The forward references to `bin/cortex-auto-bump-version` and `bin/cortex-rewrite-cli-pin` are landable before the scripts exist — the parity check at `bin/cortex-check-parity` flags `deployed-but-unreferenced` (W003), NOT `referenced-but-undeployed`. Both scripts land in T14 and T15 immediately after this task. **Critical-review corrections applied**: (1) `cancel-in-progress: true` (was `false`) — release is idempotent; coalescing avoids unbounded queue under push-storms; (2) PAT isolation — `persist-credentials: false` on every checkout; PAT only injected at the final push command in Job B, never persisted to `.git/config` for validate job; (3) `[release-type: skip]` embedded in the auto-generated commit message body (standalone-line, parseable by `cortex-auto-bump-version` regex); (4) Workflow-level commit-message `if:` filter as belt-and-suspenders against the workflow re-trigger; (5) Scheduled PAT-expiry probe for partial silent-expiry mitigation. `AUTO_RELEASE_PAT` setup is a one-time interactive step the maintainer performs (documented in T18).
- **Verification**: `test -f .github/workflows/auto-release.yml`; `grep -cE 'branches:\s*\[?main\]?' .github/workflows/auto-release.yml` returns at least 1; `grep -cE 'workflow_dispatch' .github/workflows/auto-release.yml` returns at least 1; `grep -cE 'AUTO_RELEASE_PAT' .github/workflows/auto-release.yml` returns at least 1; `grep -cE 'contents:\s*write' .github/workflows/auto-release.yml` returns at least 1; `grep -cE 'cancel-in-progress:\s*true' .github/workflows/auto-release.yml` returns at least 1 (coalescing concurrency); `grep -cE 'persist-credentials:\s*false' .github/workflows/auto-release.yml` returns at least 2 (validate + release jobs both); `grep -cE '\[release-type: skip\]' .github/workflows/auto-release.yml` returns at least 2 (commit message embedding + workflow-level filter); `grep -cE 'pull --rebase' .github/workflows/auto-release.yml` returns at least 1; `grep -cE 'bin/cortex-auto-bump-version' .github/workflows/auto-release.yml` returns at least 1; `grep -cE 'bin/cortex-rewrite-cli-pin' .github/workflows/auto-release.yml` returns at least 1; `grep -cE 'schedule:|cron:' .github/workflows/auto-release.yml` returns at least 1 (PAT-expiry probe wired).
- **Status**: [ ] pending

### Task 14: Author `bin/cortex-auto-bump-version` with `--dry-run` + unit tests

- **Files**: `bin/cortex-auto-bump-version`, `tests/test_cortex_auto_bump_version.py`
- **What**: Python helper (stdlib-only, chmod +x, shebang `#!/usr/bin/env python3`). No required args; supports `--dry-run`. Logic per spec R20: (i) read latest tag via `git describe --tags --abbrev=0`; (ii) read full commit messages since latest tag via `git log <latest-tag>..HEAD --format=%B%x00` (NUL-delimited); (iii) parse each message for `(?im)^\s*\[release-type:\s*(major|minor|skip)\s*\]\s*$`; (iv) precedence skip > major > minor > patch; (v) `BREAKING:` / `BREAKING CHANGE:` standalone-line fallback fires major-bump; (vi) on skip OR HEAD==latest-tag, emit `no-bump\n` and exit 0; (vii) otherwise emit `vX.Y.Z\n` per bump scope. Unit test ≥10 cases per spec R20 acceptance.
- **Depends on**: [13]
- **Complexity**: simple
- **Context**: Per spec R20 + R19.5 caveat. The script must invoke `cortex-log-invocation` as the first runtime line per the existing pattern at `bin/cortex-check-parity:15`. Consumer wiring: workflow at `.github/workflows/auto-release.yml` (T13) references the script — satisfies parity check at commit time. Also referenced by `docs/release-process.md` (T18). Standalone-line marker regex is the contract surface — be strict about NOT matching prose-embedded markers.
- **Verification**: `test -x bin/cortex-auto-bump-version`; `just test -- tests/test_cortex_auto_bump_version.py -v` exits 0 AND output lists at least 10 PASSED lines; `bin/cortex-check-parity` exits 0 (no W003 orphan).
- **Status**: [ ] pending

### Task 15: Author `bin/cortex-rewrite-cli-pin` with pattern-based contract + unit tests

- **Files**: `bin/cortex-rewrite-cli-pin`, `tests/test_cortex_rewrite_cli_pin.py`
- **What**: Python helper taking one positional arg (new tag, `vX.Y.Z` form). Contract per spec R19.5: (i) pattern-based regex anchored on `^CLI_PIN\s*=\s*\(` start-of-line (NOT line-anchored to 105); (ii) format-tolerant for single-line/multi-line/single-quoted/double-quoted variants; (iii) read-modify-write preserves `CLI_PIN[1]` value unchanged; (iv) fail-loud on 0-or-≥2 matches with file + match count in error; (v) idempotent on no-op (current value == target); (vi) post-rewrite `git diff` verification — exactly one line changed AND old line contains old tag AND new line contains new tag AND both have same CLI_PIN[1]. Unit test ≥8 cases per spec R19.5 acceptance: single-line, multi-line, single-quote, idempotent, zero-matches fail, two-matches fail, moved-line, CLI_PIN[1] preserved.
- **Depends on**: [13]
- **Complexity**: simple
- **Context**: Per spec R19.5. Same `cortex-log-invocation` convention as T14. Consumer wiring: `.github/workflows/auto-release.yml` (T13) references the script. The `git diff` verification step at end is what catches accidental over-writes.
- **Verification**: `test -x bin/cortex-rewrite-cli-pin`; `just test -- tests/test_cortex_rewrite_cli_pin.py -v` exits 0 AND output lists at least 8 PASSED lines; `bin/cortex-check-parity` exits 0.
- **Status**: [ ] pending

### Task 16: Add CI lint to `release.yml` for CLI_PIN drift (defense-in-depth)

- **Files**: `.github/workflows/release.yml`
- **What**: Add a job/step on `push: tags: v*.*.*` that compares the `CLI_PIN[0]` literal in `plugins/cortex-overnight/server.py:~105` to `${{ github.ref_name }}` (or `$GITHUB_REF_NAME`). Mismatch exits non-zero, blocking the release. Subsumes #212's lint goal. This is redundant with the auto-release workflow but catches drift on manual emergency tag pushes (PAT revoked, workflow disabled, etc.).
- **Depends on**: [2, 15]
- **Complexity**: simple
- **Context**: Per spec R18. The lint can read CLI_PIN with the same pattern as T15's `cortex-rewrite-cli-pin` (or even shell out to a `--check` mode of `cortex-rewrite-cli-pin` — implementer's choice). Test coverage at the invariant test in T20 catches drift pre-CI.
- **Verification**: `grep -cE 'CLI_PIN\[0\]|cli_pin\[0\]' .github/workflows/release.yml` returns at least 1; `grep -cE 'tags:' .github/workflows/release.yml` returns at least 1 (verify the on:push:tags filter exists for the new job).
- **Status**: [ ] pending

### Task 17: Update `/cortex-core:commit` skill prose for `[release-type: …]` marker convention

- **Files**: `skills/commit/SKILL.md`
- **What**: Add a section describing the three marker tokens (`[release-type: major|minor|skip]`) and their semantics. Specify the positional anchor (markers MUST appear as the entire content of their own line modulo whitespace; reproduce the regex from T14's contract). Include 3 examples (one per token). Document implicit-patch default. Cross-reference `bin/cortex-auto-bump-version --dry-run` for pre-merge verification. Document the `BREAKING:` / `BREAKING CHANGE:` fallback (T14 step v). Do NOT edit the plugin mirror at `plugins/cortex-core/skills/commit/SKILL.md` — the pre-commit hook regenerates it automatically.
- **Depends on**: [14]
- **Complexity**: simple
- **Context**: Per spec R22 + CLAUDE.md dual-source enforcement. The commit hook validator at `hooks/commit-msg.sh` (or wherever the validator lives) already accepts free-form body content per repo convention — verify at implement time that `[release-type: …]` standalone lines do not trip rejection. If validator restricts body content, extend it; otherwise no change needed.
- **Verification**: `grep -cE '^##.*release-type|release-type:' skills/commit/SKILL.md` returns at least 3 (section header + examples); after pre-commit hook regenerates the mirror, `grep -cE '^##.*release-type|release-type:' plugins/cortex-core/skills/commit/SKILL.md` also returns at least 3.
- **Status**: [ ] pending

### Task 18: Update `docs/release-process.md` with PAT setup, retry path, and runaway-workflow runbook

- **Files**: `docs/release-process.md`
- **What**: Add `## Auto-release PAT setup (one-time)` section per spec R21: (a) create fine-grained PAT scoped to the repo; (b) required `contents: write` permission; (c) store as `AUTO_RELEASE_PAT` secret; (d) 90-day rotation cadence; (e) PRE-MERGE ordering — PAT must exist before merging #213 implement-PR; (f) failure-recovery runbook (`gh secret set` + `gh workflow run auto-release.yml --ref main`); (g) runaway-workflow recovery (`gh workflow disable` + `gh run cancel` iteration + queue verification); (h) **expiry monitoring**: document the scheduled PAT-expiry probe in `auto-release.yml` (cron-triggered weekly check, posts workflow annotation when secret is missing) and recommend a calendar reminder at T+80 days for pre-expiry rotation; (i) **force-push prevention**: document that the maintainer should enable GitHub branch protection on the `v*` tag namespace (Settings → Tags → Add rule → `v*` pattern, "Restrict force-pushes") as a recommended one-time setup that complements T16's CI lint. Update the existing "Conditional Bump the plugin's CLI_PIN" section (lines ~98-120) to describe the post-fix flow: auto-release on push handles bump; manual edit only needed on emergency tags (where CI lint at T16 catches drift).
- **Depends on**: [13, 14, 15]
- **Complexity**: simple
- **Context**: Per spec R21. References `bin/cortex-auto-bump-version` and `bin/cortex-rewrite-cli-pin` by name — adds doc-reference wiring for parity. Soft positive-routing per CLAUDE.md MUST-policy.
- **Verification**: `grep -cE '^## Auto-release PAT setup' docs/release-process.md` returns 1; `grep -cE 'AUTO_RELEASE_PAT' docs/release-process.md` returns at least 2; `grep -cE 'workflow_dispatch|gh workflow run' docs/release-process.md` returns at least 1; `grep -cE 'gh workflow disable|gh run cancel' docs/release-process.md` returns at least 1; `grep -cE 'bin/cortex-auto-bump-version|bin/cortex-rewrite-cli-pin' docs/release-process.md` returns at least 1; `grep -cE 'expiry|rotation' docs/release-process.md` returns at least 1; `grep -cE 'branch protection|tag protection|Restrict force-pushes' docs/release-process.md` returns at least 1.
- **Status**: [ ] pending

### Task 19: Write `tests/test_mcp_auto_update_real_install.py` with six per-branch assertion phases

- **Files**: `tests/test_mcp_auto_update_real_install.py`, `pyproject.toml`
- **What**: Real-install integration test with `tmp_path`-isolated env (`UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`/`UV_CACHE_DIR` redirected). Six explicit test functions per spec R23: (a) `test_baseline_install_reports_package_version` — build wheel at synthetic v0.1.0 via `HATCH_BUILD_HOOK_VCS_FALLBACK_VERSION` env-var (overrides PEP 440 package version), install, assert `cortex --print-root --format json` reports `version="0.1.0"` AND `schema_version="2.0"`; (b) `test_synthetic_v_0_2_0_wheel_builds` — build v0.2.0 wheel; (c) `test_version_mismatch_fires_reinstall` — rewrite loaded plugin source with `CLI_PIN = ("v0.2.0", "2.0")`, invoke `_ensure_cortex_installed()`, assert reinstall fires, post-install version is 0.2.0, NDJSON stage exactly `version_mismatch_reinstall` (NOT `_parse_failure`); (d) `test_matching_version_passes_through` — no mismatch, reinstall does NOT fire, no `version_mismatch_*` NDJSON; (e) `test_active_session_blocks_reinstall` — construct a `runner.pid` file containing magic `"cortex-runner-v1"`, `schema_version="2.0"`, the test's own pid, AND `start_time` set to the test process's `psutil.Process().create_time()` so the canonical verifier accepts it as live (writing only the pid without magic+start_time would not satisfy `verify_runner_pid` semantics — critical-review finding); write the active-session.json pointer; invoke with version-mismatch; assert reinstall does NOT fire AND NDJSON stage exactly `version_mismatch_blocked_by_inflight_session`; (f) `test_r13_schema_floor_emits_remediation_stderr` — **schema_version is a Python constant, NOT a hatch-vcs-derivable value**, so env-var injection cannot override it. Instead, post-checkout, source-edit `cortex_command/overnight/cli_handler.py` to set `_JSON_SCHEMA_VERSION = "1.0"` before `uv build --wheel` (or build from a pre-T3 git ref). Install that wheel, invoke a tool-call path that triggers R13, assert stderr contains `"Schema-floor violation: installed CLI schema_version="` AND `"uv tool install --reinstall git+"` (literal substrings). Marked `@pytest.mark.slow` + `@pytest.mark.serial`. **Fails-loud expanded**: NOT just on `uv tool` absence — ALSO on the `uv build --wheel` `system-configuration` panic that the canonical fixture template at `tests/test_no_clone_install.py:84-92` silently skips. Capture the panic via `subprocess.run(..., capture_output=True)` and route any `system-configuration` / `Tokio executor failed` match to `pytest.fail(...)` not `pytest.skip(...)`. Add `xfail_strict = true` to `pyproject.toml [tool.pytest.ini_options]` if not present.
- **Depends on**: [11, 12]
- **Complexity**: complex
- **Context**: Per spec R23. Fixture pattern from `tests/test_no_clone_install.py:113-144` (`_install_wheel_isolated`) and `tests/test_mcp_auto_update_orchestration.py:1116-1158` are canonical templates, BUT the canonical templates' silent skip-on-egress-panic surface MUST be overridden so sandboxed CI fails loudly rather than silently passing. `$TMPDIR` is in the global sandbox allowWrite — no allowWrite expansion. Each test function emits a distinct counter/NDJSON stage record so the acceptance gate can verify all 6 branches fired (not just exit-0). **Critical-review corrections applied**: phase (f) drops the broken env-var-injection approach in favor of source-edit-before-build; phase (e) augmented with proper `runner.pid` payload (magic + schema_version + start_time) so canonical verifier accepts; `pytest.fail` boundary widened to the egress-panic case the canonical fixture silently skips.
- **Verification**: `just test -- tests/test_mcp_auto_update_real_install.py -v` exits 0 AND output contains all 6 `PASSED` lines for the six named test functions; `grep -cE 'xfail_strict\s*=\s*true' pyproject.toml` returns at least 1; `grep -cE 'system-configuration|Tokio executor failed' tests/test_mcp_auto_update_real_install.py` returns at least 1 (egress-panic fails-loud surface wired).
- **Status**: [ ] pending

### Task 20: Write `tests/test_release_artifact_invariants.py`

- **Files**: `tests/test_release_artifact_invariants.py`
- **What**: Asserts: (a) at any tag matching `v*.*.*` whose tag-date is later than the v1.0.2 tag-date, the `CLI_PIN[0]` literal at `plugins/cortex-overnight/server.py` equals the tag string; (b) `package_version` reported by `uv build --wheel` of HEAD matches `git describe --tags HEAD` (with `v` stripped). Source contains an explicit comment block enumerating the four historical violating tags (v0.1.0, v1.0.0, v1.0.1, v1.0.2) and the date-scoping rationale.
- **Depends on**: [1, 10]
- **Complexity**: simple
- **Context**: Per spec R24. Iterating tags via `git for-each-ref --format='%(refname:short) %(taggerdate:unix)' refs/tags/v*` — filter by date > v1.0.2 tag date. For each post-v1.0.2 tag, checkout the tag's tree and grep CLI_PIN[0]. Tests are CI-friendly; no network dep beyond git's own tag walk.
- **Verification**: `just test -- tests/test_release_artifact_invariants.py -v` exits 0; `grep -cE 'v0\.1\.0|v1\.0\.0|v1\.0\.1|v1\.0\.2' tests/test_release_artifact_invariants.py` returns at least 4.
- **Status**: [ ] pending

### Task 21: Write `tests/test_install_guard_parity.py`

- **Files**: `tests/test_install_guard_parity.py`
- **What**: Asserts: (a) byte-level source identity between `cortex_command/install_guard.py:check_in_flight_install_core` and `plugins/cortex-overnight/install_guard.py:check_in_flight_install_core` via `inspect.getsource`; (b) decision parity across 8 parameterized fixture cases at the **core** level per spec R25: (i) no active-session.json → both None; (ii) live pid → both same reason-string; (iii) dead pid → both None; (iv) recycled pid → both None (start_time mismatch caught by both implementations' pid-verifier — Linux via psutil, macOS via `ps -p <pid> -o lstart=` parse); (v) `CORTEX_ALLOW_INSTALL_DURING_RUN=1` + live → both None; (vi) `CORTEX_RUNNER_CHILD=1` + live → both None; (vii) `PYTEST_CURRENT_TEST` + live → both None; (viii) `"pytest" in sys.modules` + live → both None. (c) **Wrapper-level parity** (added per critical-review): exercise the production wrappers (CLI-side `check_in_flight_install` vs plugin-side equivalent) directly with each carve-out env-var permutation; assert both wrappers' carve-out evaluation order produces identical decisions. This closes the gap where the core's stdlib-only contract preserved parity but the wrappers (where carve-outs live) could silently diverge.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: Per spec R25 + critical-review carve-out finding. Parametrize via `pytest.mark.parametrize`. Source-identity test is separate from the 8 core-level + N wrapper-level parameterized cases.
- **Verification**: `just test -- tests/test_install_guard_parity.py -v` exits 0 AND output contains at least 13 PASSED lines (1 source-identity + 8 core-level + ≥4 wrapper-level for the env-var carve-outs).
- **Status**: [ ] pending

### Task 22: Author `docs/internals/auto-update.md` + cross-references in setup.md, README.md, CLAUDE.md

- **Files**: `docs/internals/auto-update.md`, `docs/setup.md`, `README.md`, `CLAUDE.md`
- **What**: Sections per spec R26 with populated bodies (≥10 words per audit-table cell, no TODO/TBD): Intent (user-visible promise, ≥3 sentences); Two-layer architecture (Layer 1 marketplace + Layer 2 MCP-tool-call-gated; wheel-vs-editable; Bash-tool subprocess carve-out from #145; ≥150 words); Component map (markdown table with ≥6 rows naming `CLI_PIN`, `_resolve_cortex_argv`, `_ensure_cortex_installed`, `_maybe_check_upstream` legacy, `_schema_floor_violated`, print-root envelope, `install_guard.check_in_flight_install_core`, CI lint — each row with file:line + one-sentence role); Release ritual (push to main → auto-release workflow bumps + tags via PAT → release.yml fires on tag → wheel published → CI lint at release.yml = defense-in-depth); Intent vs currently-wired audit table (≥6 rows, 3 columns: Component | Intended | Currently-wired). Cross-references: add link to `docs/internals/auto-update.md` from each of `docs/setup.md`, `README.md`, `CLAUDE.md` (the overnight-docs source-of-truth list around line 50). Soft positive-routing per MUST-policy.
- **Depends on**: [11, 12, 16]
- **Complexity**: complex
- **Context**: Per spec R26, R27. Sibling-doc pattern of `docs/internals/{events-registry.md, mcp-contract.md, one-shot-scripts.md, pipeline.md, sdk.md}`. CLAUDE.md overnight-docs list at `CLAUDE.md:50`.
- **Verification**: `test -f docs/internals/auto-update.md`; `grep -cE '^## (Intent|Two-layer architecture|Component map|Release ritual|Intent vs currently-wired)' docs/internals/auto-update.md` returns 5; `awk '/^## Component map/,/^## /' docs/internals/auto-update.md | grep -cE '\|.*server\.py:[0-9]+'` returns at least 6; `awk '/^## Intent vs currently-wired/,/^## /' docs/internals/auto-update.md | grep -cE '^\|'` returns at least 8; `grep -cE 'TODO|TBD|TKTK' docs/internals/auto-update.md` returns 0; `grep -lE 'docs/internals/auto-update' docs/setup.md README.md CLAUDE.md | wc -l` returns 3.
- **Status**: [ ] pending

### Task 23: Rewrite #210 docs (setup.md upgrade section, README, implement.md §1a, install.sh)

- **Files**: `docs/setup.md`, `README.md`, `skills/lifecycle/references/implement.md`, `install.sh`
- **What**: Per spec R28: shorten `docs/setup.md ## Upgrade & maintenance` (lines 188-227) to a user-facing summary pointing to `docs/internals/auto-update.md`. Shorten `README.md` line 33 "Recommended:" bullet; point to internals doc. Replace `skills/lifecycle/references/implement.md` §1a hardcoded `@v0.1.0` (around lines 90-101) with `uv tool upgrade cortex-command` (defers tag resolution). Replace `install.sh:41`'s `tag="${CORTEX_INSTALL_TAG:-v0.1.0}"` with a `git ls-remote`-resolved latest-tag default (or equivalent — implement-time decides exact form). Update `docs/setup.md:27` Quickstart install command to reference `@latest-tag` or the same resolver.
- **Depends on**: [22]
- **Complexity**: simple
- **Context**: Per spec R28. Soft positive-routing in #210 rewrites. The `implement.md` §1a edit is outside the kept-pauses inventory tracked at `skills/lifecycle/SKILL.md:189-201` — verified safe for prose-only edit.
- **Verification**: `git grep -nE '@v0\.1\.0' -- ':!cortex/lifecycle/' ':!CHANGELOG.md' ':!cortex/backlog/' ':!docs/release-process.md'` returns 0 matches; `grep -cE 'docs/internals/auto-update' docs/setup.md README.md` returns at least 2.
- **Status**: [ ] pending

### Task 24: Supersede backlog #211 and #212; regenerate backlog index

- **Files**: `cortex/backlog/211-r8-should-track-installed-wheel-commit-not-cwd-working-tree-head-146-follow-up.md`, `cortex/backlog/212-cli-pin-drift-lint-146-hygiene.md`, `cortex/backlog/index.md`
- **What**: Per spec R29: flip `cortex/backlog/211-*.md` `status:` to `superseded` and append a body note pointing to #213 with one-line rationale (R8 reformat decision was absorbed into #213's R4 wiring). Flip `cortex/backlog/212-*.md` to `status: superseded` with body note that the CI lint at T16 realizes #212's lint goal AND auto-release workflow at T13 closes the root cause. Regenerate `cortex/backlog/index.md` via `just backlog-index` (auto-generated; the regeneration is a tool-driven side effect, not a hand-edit).
- **Depends on**: [16]
- **Complexity**: simple
- **Context**: Per spec R29. Use `cortex-update-item` helper to flip status fields cleanly (or hand-edit YAML frontmatter). `just backlog-index` regenerates the index after flips. The dependency on T16 ensures the CI lint task is in place before the #212 closure note references it.
- **Verification**: `grep -cE '^status:\s*(superseded|complete)' cortex/backlog/211-*.md cortex/backlog/212-*.md` returns 2; `grep -lE '#213' cortex/backlog/211-*.md cortex/backlog/212-*.md | wc -l` returns at least 2.
- **Status**: [ ] pending

### Task 25: Update CHANGELOG.md with Gap-A/B/C closure entries

- **Files**: `CHANGELOG.md`
- **What**: New section for the upcoming release tag (e.g., `## [v2.0.0]`) with separate bullets per spec R30: (a) Gap A closed via auto-release workflow on push to main (subsumes #212); (b) Gap B closed via hatch-vcs + envelope schema-major bump 1.x → 2.0; (c) Gap C closed via R4 version-comparison branch; (d) install_guard vendored as sibling with dual-source parity; (e) BREAKING: print-root envelope `version` semantic changes from M.m to PEP 440 package version; new `schema_version` field carries M.m.
- **Depends on**: [1, 4, 8, 11, 13, 19, 20, 21, 22, 23, 24]
- **Complexity**: simple
- **Context**: Per spec R30. The exact tag version (`v2.0.0` vs whatever T13's auto-release picks) is implementer-decided based on what tag the merge will trigger. Mention the marker convention in the PR body so the auto-release picks the right bump.
- **Verification**: `awk '/^## \[v/{p=NR} p && /Gap A|Gap B|Gap C|BREAKING|install_guard/{c++} END{print c}' CHANGELOG.md` returns at least 5.
- **Status**: [ ] pending

## Risks

- **Schema major-bump blast radius**: T4 + T5 + T6 atomically migrate producer + ≥6 test files; T9 finalizes consumer reads; T11 wires the R4 branch + vendored install_guard. If any consumer was missed in the enumeration grep, that consumer fails silently (reads `payload.get("version")` and gets the PEP 440 package string instead of M.m). Mitigation: T11's `just test` whole-suite-green gate (the meaningful boundary) plus T19's integration test exercises the live envelope. Residual: untested external consumers (none currently known); `cortex_command/overnight/tests/` was missed in initial plan but covered by T6 after critical-review.
- **T4-to-T11 window is a runtime functional regression at the MCP boundary, NOT merely test-suite redness**: after T4 flips `_emit_json` to stop stamping `version`, every overnight MCP call hits `_check_version` (`server.py:154`) which does `payload.get("version")` → `None` → raises `SchemaVersionError` for every verb except the `overnight_status` carve-out. The plan's mitigation is procedural: ALL of T4-T11 land in one PR (single atomic merge to `main`). Intermediate commits exist on the feature branch only — never on `main`. Critical-review correction: this is a functional regression at the MCP boundary, not a test-suite redness window. There is no structural enforcement (no merge gate beyond reviewer discipline); the safety property rests on PR-level review and feature-branch isolation.
- **Pre-v2.0 plugin + v2.0+ CLI incompatibility**: documented BREAKING change in T24 + T22 internals doc. Forces a one-time coordinated reinstall. Acceptable per spec Non-Requirements; user confirmed at spec critical-review.
- **PAT lifecycle and security**: `AUTO_RELEASE_PAT` is a long-term secret with 90-day rotation. T13 isolates the PAT to the push step (`persist-credentials: false` on validate-job checkout; explicit `git -c http.extraheader` injection only at push time) so test code does NOT see the PAT (closes the original critical-review concern about checkout token persistence). T13 also includes a scheduled cron job (`schedule: [cron: '0 12 * * MON']`) that probes for secret presence and posts a workflow annotation on missing — partial monitoring for silent expiry. T18's runbook documents `gh secret set` recovery + `workflow_dispatch` retry + recommends a calendar reminder at T+80 days. The CI lint (T16) catches drift on the manual-tag emergency fallback path. Residual: PAT theft via runtime workflow log scraping is still possible if a future workflow step is added that prints the PAT — guard via code review.
- **Auto-release on every push to main**: noisy if every commit triggers a tag. Mitigation: `[release-type: skip]` marker convention (T14 step iii) + the `no-bump` gate at T13 step (d) when no commits OR explicit skip + workflow-level `if:` filter excluding commits matching `^Release v[0-9]+\.[0-9]+\.[0-9]+$` shape + auto-injected `[release-type: skip]` marker in the auto-generated release commit body. User-confirmed default at critical-review: implicit-patch is the intentional release default for the single-maintainer phase. Maintainer discipline lives in T17's skill prose.
- **Workflow self-retrigger via PAT-authored push**: GitHub re-triggers `push: branches: [main]` workflows on PAT-authored pushes (unlike `GITHUB_TOKEN`-authored pushes). T13's defenses: (i) workflow-level `if:` filter excludes `Release vX.Y.Z`-shaped commits AND commits containing `[release-type: skip]`; (ii) auto-generated commit body embeds `[release-type: skip]` so `bin/cortex-auto-bump-version` returns `no-bump` even if filter (i) is bypassed; (iii) `concurrency: cancel-in-progress: true` coalesces push storms to latest. Critical-review surfaced this; correction applied.
- **Force-pushed tag identity collision**: documented residual risk in T22 internals doc. CI lint at T16 cannot detect it; recommended remediation is `uv cache clean cortex-command` on rebuild.
- **Marketplace fast-forward layer unmocked — material downgrade from spec §E, not just a "re-scoping"**: T19 exercises cortex-command-side mismatch detection only. The original spec §E criterion required an observable end-to-end trace (`git -C ~/.claude/plugins/marketplaces/cortex-command/ reflog` + fresh sentinel + `install.lock`) of the full chain. The plan splits that into two pieces — T13's auto-release workflow (Github-side push-and-tag, executable agent-side at workflow-run time but the "first run end-to-end" check is acknowledged as manual maintainer setup, not agent-verifiable) AND T19's in-process detection — leaving the middle link (Claude Code marketplace clone-fast-forward) uncovered by either. This is acknowledged as residual; framing it as "re-scoping" understated the gap. The CI lint at T16 catches CLI_PIN drift at tag-push time (defense-in-depth), and T19's full set of six per-branch assertions catches the cortex-side detection. The marketplace clone-fast-forward remains agent-unverifiable.
- **Concurrent push-to-main during auto-release**: T13 step (a.5) rebases before the bump commit; on push collision, single rebase-retry then fail-with-clear-error. Manual recovery via `workflow_dispatch`. Surface acceptable per spec edge case "Auto-release workflow concurrent with manual tag push" — maintainer disables workflow before emergency manual pushes.

## Acceptance

Whole-feature acceptance criterion: after all 25 tasks complete, (1) `cortex --print-root --format json` reports `{"version": "<pep440-pkg-version>", "schema_version": "2.0", ...}`; (2) `tests/test_mcp_auto_update_real_install.py` (T19) lists all six PASSED test functions including `version_mismatch_reinstall`, `version_mismatch_blocked_by_inflight_session`, and R13 stderr remediation; (3) `tests/test_release_artifact_invariants.py` (T20) and `tests/test_install_guard_parity.py` (T21) exit 0; (4) `docs/internals/auto-update.md` is cross-referenced from `docs/setup.md`, `README.md`, `CLAUDE.md`; (5) `cortex/backlog/211-*.md` and `cortex/backlog/212-*.md` are status:superseded with #213 backreference; (6) merging the implement-PR to main triggers the auto-release workflow's first run end-to-end (PAT configured pre-merge per T18 gate — partial coverage only: the GitHub-side push-and-tag is observable via the workflow run, but the Claude Code marketplace clone-fast-forward is NOT agent-verifiable). The whole-suite `just test` gate exits 0 at the T11 boundary and again at completion.
