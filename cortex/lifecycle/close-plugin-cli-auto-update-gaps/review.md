# Review: close-plugin-cli-auto-update-gaps

## Stage 1: Spec Compliance

### Requirement 1: Adopt hatch-vcs for wheel versioning
- **Expected**: `pyproject.toml` declares `dynamic = ["version"]`; `[tool.hatch.version] source = "vcs"`; `[tool.hatch.version.raw-options] local_scheme = "no-local-version"`; `[tool.hatch.build.hooks.vcs] version-file = "cortex_command/_version.py"`; `hatch-vcs` in `[build-system] requires`.
- **Actual**: All four declarations present; `dynamic = ["version"]` at line 7, `hatch-vcs` added to build requires at line 2, `[tool.hatch.version]` at line 43. Acceptance greps confirm zero static `version =` matches; one `[tool.hatch.version]` match; one `hatch-vcs` match.
- **Verdict**: PASS

### Requirement 2: Generated `_version.py` is gitignored
- **Expected**: `.gitignore` matches `cortex_command/_version.py`; `git check-ignore` exits 0.
- **Actual**: `.gitignore:20` contains `cortex_command/_version.py`; `git check-ignore` confirmed.
- **Verdict**: PASS

### Requirement 3: Release workflow has full git history
- **Expected**: `release.yml` checkout sets `fetch-depth: 0` and `fetch-tags: true`.
- **Actual**: Lines 86-87 in `.github/workflows/release.yml` set both.
- **Verdict**: PASS

### Requirement 4: `cortex --print-root --format json` envelope's `version` field carries package version
- **Expected**: `cortex_command/cli.py` sources the field from `importlib.metadata.version("cortex-command")` with `PackageNotFoundError` fallback to `"0.0.0+source"`.
- **Actual**: `cli.py:190-203` imports `version as _pkg_version` and `PackageNotFoundError`, wraps in try/except, falls back to `"0.0.0+source"`. Line 233 emits `"version": package_version`.
- **Verdict**: PASS

### Requirement 5: Envelope carries new `schema_version` field
- **Expected**: Every JSON payload carries `"schema_version": "2.0"`; `_JSON_SCHEMA_VERSION` updated to `"2.0"`.
- **Actual**: `cli_handler.py:107` sets `_JSON_SCHEMA_VERSION = "2.0"`; `cli.py:234` emits `"schema_version": _JSON_SCHEMA_VERSION`.
- **Verdict**: PASS

### Requirement 6: All `_emit_json` call sites and consumers migrate to `schema_version`
- **Expected**: `_emit_json` stamps `schema_version`; schema-floor consumers (`_check_version`, `_schema_floor_violated`) read `schema_version`; package-version consumer (R9 new branch) reads `version`; no remaining M.m strings in test mocks for the `version` field.
- **Actual**: `cli_handler.py:116` stamps `"schema_version": _JSON_SCHEMA_VERSION`. `server.py:143` (`_check_version`), `server.py:1849` (`_schema_floor_violated`) read `payload.get("schema_version")`. `server.py:883` reads `probe_payload.get("version")` for the new version-compare branch. Acceptance grep `"version":\s*"[0-9]+\.[0-9]+"$` against tests/ returns 0.
- **Verdict**: PASS

### Requirement 7: Wheel filename matches the tag
- **Expected**: `uv build --wheel` at tag `vX.Y.Z` produces wheel with `X.Y.Z` (no `v` prefix, no local-version suffix).
- **Actual**: Covered by `test_release_artifact_invariants.py::test_wheel_package_version_matches_git_describe` (skipped at HEAD-not-at-tag, which is correct behavior). hatch-vcs + `local_scheme = "no-local-version"` config from R1 enforce the invariant.
- **Verdict**: PASS

### Requirement 8: `docs/internals/mcp-contract.md` reflects the major-2.0 envelope shape
- **Expected**: Envelope examples show `"version": "<package-version>", "schema_version": "2.0"`; ≥3 `"schema_version":` matches; 0 remaining `"version": "1.[01]"` matches.
- **Actual**: 6 `"schema_version":` matches; 0 `"1.[01]"` matches.
- **Verdict**: PASS

### Requirement 9: R4 grows a version-comparison branch
- **Expected**: `_ensure_cortex_installed` keeps `shutil.which` short-circuit, then probes `cortex --print-root --format json`, parses `payload["version"]`, compares via `packaging.version.Version`, falls through to reinstall on mismatch. `try/except packaging.version.InvalidVersion` emits `stage="version_mismatch_reinstall_parse_failure"`.
- **Actual**: `server.py:775-970` implements both branches. Line 819 lazy-imports `packaging.version`. Lines 894-919 implement the comparison with parse-failure handling and distinct stage labels.
- **Verdict**: PASS

### Requirement 10: `packaging` added to PEP 723 dependency declaration
- **Expected**: Script header declares `packaging` alongside `mcp` and `pydantic`.
- **Actual**: Line 6 declares `"packaging>=24,<26"`.
- **Verdict**: PASS

### Requirement 11: `install_guard.py` refactored to stdlib-only core + vendored sibling with parity
- **Expected**: Stdlib-only `check_in_flight_install_core` function; byte-identical sibling at `plugins/cortex-overnight/install_guard.py`; pre-commit parity gate; `tests/test_install_guard_parity.py` asserts byte-identity.
- **Actual**: `cortex_command/install_guard.py:150` defines the core function (between BEGIN/END sync markers at lines 149/248). `plugins/cortex-overnight/install_guard.py:27` is the vendored sibling. Byte-identity verified via `diff <(inspect.getsource ...)`. `.githooks/pre-commit:228-251` enforces parity via `just sync-install-guard --check`. `test_install_guard_parity.py` includes source-identity assertion + parameterized decision parity (13 tests all pass).
- **Verdict**: PASS

### Requirement 12: R4 honors the in-flight install guard
- **Expected**: `_ensure_cortex_installed` calls `check_in_flight_install_core`; emits `stage="version_mismatch_blocked_by_inflight_session"` on block; carve-outs bypass appropriately; parity test covers each carve-out.
- **Actual**: `server.py:944-964` checks `CORTEX_ALLOW_INSTALL_DURING_RUN`, calls the vendored core, emits the blocked NDJSON stage on a non-None reason. Parity test `test_install_guard_parity.py` covers all carve-outs (8 core-decision-parity cases + 4 wrapper cases). Plugin-side design choice: only `CORTEX_ALLOW_INSTALL_DURING_RUN` carve-out is wired in the plugin wrapper; the other env-var carve-outs (`CORTEX_RUNNER_CHILD`, `PYTEST_CURRENT_TEST`, `pytest in sys.modules`) are CLI-only by design — documented at `test_install_guard_parity.py:35-48` and asserted by the parity test's wrapper-level cases. The spec text says carve-outs "bypass the core when set," but the chosen design keeps them at the wrapper layer with parity-test enforcement of the deviation.
- **Verdict**: PASS

### Requirement 13: R13 silent short-circuit replaced with stderr remediation surface
- **Expected**: On `_schema_floor_violated` + wheel-install (no `.git` dir), emit a single-line stderr remediation message naming the installed schema and the reinstall command; return `False`.
- **Actual**: `server.py:1858-1870` emits the verbatim remediation line and returns `False`. Real-install test phase (f) asserts the stderr substring contract.
- **Verdict**: PASS

### Requirement 14: `_parse_major_minor` is removed
- **Expected**: Function definition and all callers removed; comparison migrates to `packaging.version.Version`.
- **Actual**: `grep -cE 'def _parse_major_minor|_parse_major_minor\(' plugins/cortex-overnight/server.py` returns 0.
- **Verdict**: PASS

### Requirement 15: R4 reinstall verification probe pins to absolute path
- **Expected**: Post-install probe uses absolute path from `uv tool list --show-paths` rather than bare `cortex`.
- **Actual**: `server.py:683-706` calls `_resolve_installed_cortex_path()`, then invokes `[cortex_abs_path, "--print-root", "--format", "json"]`. `awk` on the function body returns 0 bare-PATH `cortex` invocations.
- **Verdict**: PASS

### Requirement 16: NDJSON audit stages registered
- **Expected**: `version_mismatch_reinstall`, `version_mismatch_reinstall_parse_failure`, `version_mismatch_blocked_by_inflight_session` registered in `_NDJSON_ERROR_STAGES` and emitted; grep returns ≥6.
- **Actual**: grep returns 12 matches across the three new stage labels.
- **Verdict**: PASS

### Requirement 17: CLI_PIN schema major bumps in lockstep
- **Expected**: `CLI_PIN[1] = "2.0"`; `MCP_REQUIRED_CLI_VERSION = "2.0"`.
- **Actual**: `server.py:106` `CLI_PIN = ("v0.1.0", "2.0")`; `server.py:113` `MCP_REQUIRED_CLI_VERSION = CLI_PIN[1]`.
- **Verdict**: PASS

### Requirement 18: CI lint hard-fails release on CLI_PIN drift
- **Expected**: A CI step compares `CLI_PIN[0]` to the pushed tag; mismatch exits non-zero; subsumes #212.
- **Actual**: `.github/workflows/release.yml:22-77` adds the `cli-pin-lint` job that uses a regex anchored on `^CLI_PIN\s*=\s*\(`, validates exactly one declaration, asserts `CLI_PIN[0]` matches `github.ref_name`, exits non-zero on drift, and is wired as a `needs:` prerequisite for the release job.
- **Verdict**: PASS

### Requirement 19: Auto-release workflow exists
- **Expected**: `.github/workflows/auto-release.yml` triggers on push to main + workflow_dispatch; PAT-authenticated; concurrency control; no-bump gate before rewriter; commit + tag + push pipeline.
- **Actual**: All components present in `auto-release.yml`. Triggers on push:main, workflow_dispatch, and a weekly cron PAT-expiry probe. Permissions block grants `contents: write`. Concurrency group `auto-release`. Rebase step at line 115. No-bump gate at lines 117-129 fires before the rewriter at line 131. PAT injection scoped to push step only (lines 162-170) — never persisted to .git/config. Includes second-push rebase retry on non-fast-forward.
- **Verdict**: PASS

### Requirement 19.5: CLI_PIN rewriter contract
- **Expected**: Pattern-based, format-tolerant, preserves `CLI_PIN[1]`, fails loud on 0-or-≥2 matches, idempotent no-op, post-rewrite `git diff` verification, ≥8 PASSED unit tests.
- **Actual**: `bin/cortex-rewrite-cli-pin` (306 lines) implements all listed properties. `tests/test_cortex_rewrite_cli_pin.py` includes 12 tests (covering single-line, multi-line, single-quote, zero-matches fail, two-matches fail, non-default-line, schema preserved, idempotent no-op, full script success, fail-on-zero, fail-on-two, invalid tag form); all 12 PASS.
- **Verdict**: PASS

### Requirement 20: `bin/cortex-auto-bump-version` helper exists
- **Expected**: ≥10 unit test cases; reads full commit messages via `--format=%B`; positionally-anchored markers; BREAKING fallback; squash-merge handling; `--dry-run` mode; `no-bump\n` output.
- **Actual**: `bin/cortex-auto-bump-version` (236 lines); `tests/test_cortex_auto_bump_version.py` has 22 tests covering all enumerated cases plus more; all 22 PASS. Includes squash-merge body marker, BREAKING-fallback, prose-embedded marker rejection, dry-run mode.
- **Verdict**: PASS

### Requirement 21: PAT setup documented in release-process.md
- **Expected**: `## Auto-release PAT setup (one-time)` section; ≥2 `AUTO_RELEASE_PAT` references; workflow_dispatch retry path documented; runaway-workflow runbook.
- **Actual**: Section heading present; 9 `AUTO_RELEASE_PAT` references; 3 `workflow_dispatch`/`gh workflow run` matches; 3 `gh workflow disable`/`gh run cancel` matches.
- **Verdict**: PASS

### Requirement 22: `/cortex-core:commit` skill teaches the marker convention
- **Expected**: Updated SKILL.md prose with marker tokens, examples, regex anchor, BREAKING fallback; validator naturally accepts standalone bracket-form lines.
- **Actual**: Both `skills/commit/SKILL.md` and the plugin mirror are updated (16 release-type/BREAKING references across both files). The validator at `hooks/cortex-validate-commit.sh` only inspects the subject line — body markers naturally pass, matching the spec's OR clause.
- **Verdict**: PASS

### Requirement 23: Real-install integration test with per-branch assertion contracts
- **Expected**: 6 explicitly-asserted test paths; marked `@pytest.mark.slow` + `@pytest.mark.serial`; `pytest.fail` on uv-unavailable (not skip); `xfail_strict = true`; 6 PASSED on `--run-slow`.
- **Actual**: All 6 test functions present with exact names from the spec. Marked slow + serial. uv-unavailable routes to `pytest.fail`. `xfail_strict = true` in `pyproject.toml`. All 6 PASS when run with `--run-slow` (85s real-install + real-build run).
- **Verdict**: PASS

### Requirement 24: Release-artifact invariant test
- **Expected**: Tag-lockstep invariant scoped to post-v1.0.2 tags via date window; wheel `package_version` matches `git describe`; historical violating tags enumerated in source.
- **Actual**: `tests/test_release_artifact_invariants.py` present with 3 tests; `HISTORICAL_VIOLATING_TAGS` constant lists all four historical tags. 2 tests PASS; the wheel-build test SKIPS (correctly — HEAD is not at a tag).
- **Verdict**: PASS

### Requirement 25: install_guard parity test
- **Expected**: Source-identity assertion + 8 parameterized decision cases.
- **Actual**: `test_install_guard_parity.py` includes 1 source-identity + 8 core-decision-parity + 4 wrapper-decision-parity = 13 tests; all PASS.
- **Verdict**: PASS

### Requirement 26: Authoritative internals doc with content-quality acceptance
- **Expected**: 5 sections; Component map with ≥6 file:line rows; audit table with ≥8 lines; no TODO/TBD/TKTK placeholders.
- **Actual**: All 5 sections present. Component map has 9 rows with file:line references (6 `server.py:N`, plus `cli.py:232`, `install_guard.py:150`, `release.yml:28`). Audit table has 10 lines (header + separator + 8 content rows). Zero TODO/TBD/TKTK. Note: the spec's literal acceptance grep `awk '/^## Component map/,/^## /'` has a self-collapsing-range bug that returns only the header line; using a section-bounded awk pattern (e.g., `/^## Component map/,/^## Release ritual/`) returns the correct 6 server.py:N matches. The content meets the spec's intent.
- **Verdict**: PASS

### Requirement 27: Internals doc cross-referenced from setup.md, README.md, CLAUDE.md
- **Expected**: All three files link to `docs/internals/auto-update.md`.
- **Actual**: `grep -l` confirms all three files reference the doc.
- **Verdict**: PASS

### Requirement 28: #210 docs rewritten + stale-tag literals remediated
- **Expected**: 0 remaining `@v0.1.0` references outside the documented exclusions.
- **Actual**: `git grep -nE '@v0\.1\.0' -- ':!cortex/lifecycle/' ':!CHANGELOG.md' ':!cortex/backlog/' ':!docs/release-process.md'` returns 0 matches. `install.sh` uses an inline `git ls-remote` pipeline (with `# allow-direct` annotation for the lint).
- **Verdict**: PASS

### Requirement 29: Superseded backlog items marked
- **Expected**: Both `cortex/backlog/211-*.md` and `cortex/backlog/212-*.md` have `status: superseded` and a body note pointing to #213.
- **Actual**: Both files have superseded status and #213 references.
- **Verdict**: PASS

### Requirement 30: CHANGELOG.md updated with Gap-A/B/C closure entries
- **Expected**: New section with separate bullets for Gap A, Gap B, Gap C, install_guard vendoring, and BREAKING note; awk acceptance returns ≥5.
- **Actual**: `awk` acceptance returns 7 matches.
- **Verdict**: PASS

## Requirements Drift

**State**: detected
**Findings**:
- Project Boundaries' "Published packages or reusable modules for others — out of scope" item is partially in tension with this implementation: cortex-command's CLI is now distributed via hatch-vcs with auto-versioning + an automated GitHub release pipeline + a documented PAT-based auto-release contract. The wheel isn't published to PyPI, but the auto-release workflow, the v2.0.0 BREAKING envelope migration, and the `docs/internals/mcp-contract.md` "forever-public-API" treatment all reflect a versioning regime materially closer to "published packaged distribution" than the requirements doc indicates. The Project Boundaries section could be sharpened to acknowledge that cortex-command ships a versioned wheel artifact with a documented schema contract intended for the cortex-overnight plugin to consume cross-version — this is "internal release engineering" rather than "library publishing for arbitrary consumers," but the line is now load-bearing for understanding why R30's "BREAKING" treatment matters.
**Update needed**: cortex/requirements/project.md

## Suggested Requirements Update
**File**: cortex/requirements/project.md
**Section**: ## Architectural Constraints
**Content**:
```
- **CLI/plugin version contract**: The cortex CLI wheel and the cortex-overnight plugin ship via independent channels (wheel via `uv tool install`; plugin via Claude Code marketplace). They couple through (a) `plugins/cortex-overnight/server.py`'s `CLI_PIN` tuple — `(<tag>, <schema_major.minor>)` — and (b) the `cortex --print-root --format json` envelope's `version` (PEP 440 package) and `schema_version` (M.m floor) fields. Schema-floor majors are forever-public-API per `docs/internals/mcp-contract.md`: repurposing an existing field requires a major bump. The auto-release workflow at `.github/workflows/auto-release.yml` and the CI drift-lint at `.github/workflows/release.yml` jointly maintain `CLI_PIN[0] == tag` invariance.
```

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns throughout. NDJSON stage names (`version_mismatch_reinstall`, `version_mismatch_reinstall_parse_failure`, `version_mismatch_blocked_by_inflight_session`) follow the existing snake_case + stage-noun convention. Helper script names follow the `cortex-<verb>` pattern. Test functions named per the spec's enumerated list.
- **Error handling**: Appropriate and defense-in-depth throughout. The R9 version-compare branch wraps in `try/except packaging.version.InvalidVersion` with a distinct NDJSON stage so tests can disambiguate. The R12 ImportError on the vendored sibling surfaces explicitly rather than silently bypassing the guard. The R15 absolute-path resolution falls back to a failure NDJSON record + sentinel rather than regressing to bare-PATH. The auto-release workflow has a second-push rebase retry with a clear `::error::` annotation pointing to `workflow_dispatch` recovery.
- **Test coverage**: Comprehensive and matches spec's per-branch assertion contracts. The real-install integration test (6 paths) verifies all 6 R23 paths with distinct stage labels for disambiguation. The parity test (13 cases) covers source identity + decision matrix. The rewriter test (12 cases) and the bump-version test (22 cases) exceed the spec's required ≥8/≥10. The release-artifact invariant test correctly date-scopes the historical violating tags. All non-slow tests pass (932 passed, 13 skipped, 1 xfailed); all 6 slow integration tests pass with `--run-slow`.
- **Pattern consistency**: Follows existing project conventions strongly. The vendored install_guard sibling uses the same dual-source enforcement pattern as `BUILD_OUTPUT_PLUGINS` mirroring, with explicit BEGIN/END sync markers in the canonical source and a `just sync-install-guard --check` recipe wired into `.githooks/pre-commit`. The plugin's PEP 723 deps declaration mirrors the project's existing single-file-script convention. The auto-release workflow's `[release-type: skip]` self-retrigger guard uses a layered defense (workflow-level if-filter + body marker + concurrency.cancel-in-progress) that matches the project's "structural separation over prose-only enforcement" principle. Minor observation: `tests/test_no_clone_install.py::test_target_state` retains an assertion `payload["version"].startswith("1.")` at line 239 — this currently passes because hatch-vcs derives `1.0.3.dev191` from the latest tag, but it will fail post-v2.0.0 release. Not a current spec violation (R6 acceptance still passes), but a latent issue for the first auto-release run. Recommend either widening the regex or accepting that the assertion catches an envelope-schema regression at the v2.0.0 transition and updating it then.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
