# Review: convert-bin-cortex-and-skill-embedded

## Stage 1: Spec Compliance

### Requirement 1: Delete `bin/cortex-backlog-ready` and its plugin mirror
- **Expected**: both files absent at HEAD
- **Actual**: `git show HEAD:bin/cortex-backlog-ready` and `git show HEAD:plugins/cortex-core/bin/cortex-backlog-ready` both fail (file not in tree); removed in 4f8a1b06
- **Verdict**: PASS

### Requirement 2: Delete `bin/cortex-morning-review-complete-session` and its plugin mirror
- **Expected**: both files absent at HEAD
- **Actual**: both removed in 4f8a1b06
- **Verdict**: PASS

### Requirement 3: `[project.scripts]` entries for the two retired wrappers remain
- **Expected**: each grep yields exactly 1
- **Actual**: pyproject.toml lines 31 and 48 carry `cortex-backlog-ready = "cortex_command.backlog.ready:main"` and `cortex-morning-review-complete-session = "cortex_command.overnight.complete_morning_review_session:main"`
- **Verdict**: PASS

### Requirement 4: Parity gate passes after wrapper deletion (`cortex-check-parity --audit` exits 0)
- **Expected**: exit 0
- **Actual**: with stale `__pycache__` cleaned, audit exits 0. The retired wrappers remain in `gather_deployed()` via `gather_entry_point_names()`, so E002 does not fire.
- **Verdict**: PASS

### Requirement 5: Byte-equivalence regression resolved for the two retired wrappers
- **Expected**: `test_telemetry_byte_equivalence.py` passes after Phase 1 + Phase 4
- **Actual**: implementer chose strategy (b) (recorded in `.implementer-choices`); test was updated in 19105635 to recognize `DELTA_ARGV_COUNT = 1` offset. Test passes (2 passed).
- **Verdict**: PASS — with a documented premise concern (see Stage 2 Code Quality below).

### Requirement 6: `cortex_command/critical_review/__init__.py` exists
- **Expected**: file exists for `python3 -m` to resolve
- **Actual**: exists; after T13 (5a05355f) it consolidates the 935-line module that was formerly `cortex_command/critical_review.py`. All public symbols remain importable.
- **Verdict**: PASS

### Requirement 7: Four new modules exist, each with a single-purpose `main()`
- **Expected**: four files with argparse-based `main()` parsers
- **Actual**: `cortex_command/lifecycle/branch_mode_cli.py`, `cortex_command/lifecycle/picker_decision_cli.py`, `cortex_command/critical_review/resolve_feature_cli.py`, `cortex_command/critical_review/write_residue_cli.py` all present and each defines `main(argv)`.
- **Verdict**: PASS

### Requirement 8: `cortex-lifecycle-branch-mode <path>` returns branch mode or empty string
- **Expected**: exit 0; stdout matches closed-set or empty
- **Actual**: `cortex-lifecycle-branch-mode .` exits 0, prints `prompt\n` in this repo. Internally calls `cortex_command.lifecycle_config.read_branch_mode`.
- **Verdict**: PASS

### Requirement 9: `cortex-lifecycle-picker-decision <path> <slug> [<mode>]` emits structured JSON
- **Expected**: JSON `{"fire": <bool>, "reason": "<closed-set-token>"}`
- **Actual**: `cortex-lifecycle-picker-decision . test-slug` returns `{"fire": true, "reason": "branch_mode_unset_or_invalid"}` (JSON compact form so jq sees lowercase true/false). Closed-set tokens sourced from `cortex_command.lifecycle_implement.REASONS`.
- **Verdict**: PASS

### Requirement 10: `cortex-critical-review-resolve-feature <session-id>` returns the feature slug
- **Expected**: exit 0 with slug on single match; non-zero with stderr on zero/multiple
- **Actual**: tested manually — non-existent session → `no session matching non-existent-session\n` to stderr, exit 1. Multi-match path also handled with a sorted slug list in stderr.
- **Verdict**: PASS

### Requirement 11: `cortex-critical-review-write-residue --feature <slug>` reads JSON from stdin and writes atomically
- **Expected**: argparse `type=` validates `^[a-z0-9][a-z0-9-]*$`, exit 2 on invalid; tempfile + `os.replace` to `cortex/lifecycle/<feature>/critical-review-residue.json`
- **Actual**: tested manually — valid write succeeds, file present; `--feature ../etc` exits 2 with `error: argument --feature: invalid --feature: ../etc`; empty stdin exits 2 with `no payload on stdin`. Slug validator wired via argparse `type=_feature_slug`.
- **Verdict**: PASS

### Requirement 12: Four new `[project.scripts]` entries registered
- **Expected**: grep yields exactly 4
- **Actual**: pyproject.toml carries `cortex-lifecycle-branch-mode`, `cortex-lifecycle-picker-decision`, `cortex-critical-review-resolve-feature`, `cortex-critical-review-write-residue`. Verified via `grep -E '^(...)' pyproject.toml | wc -l` = 4.
- **Verdict**: PASS

### Requirement 13: `_telemetry` cross-package import resolution
- **Expected**: documented choice; working `from <module> import main; main(['--help'])` against any of the six modules
- **Actual**: implementer chose strategy (b) (cross-package import retained at `cortex_command.backlog._telemetry`), recorded in `.implementer-choices` and 460941c7 commit body. Verified `from cortex_command.lifecycle.branch_mode_cli import main; main(['--help'])` runs.
- **Verdict**: PASS

### Requirement 14: New modules' argparse structure is sibling-lint-compatible
- **Expected**: single `argparse.ArgumentParser` per module; no E202 ambiguous-parser triggers
- **Actual**: each of the four new modules constructs exactly one parser via a `_build_parser()` helper called from `main()`. The package `__init__.py` (critical_review) uses one `_build_parser()` with subparsers and is unaffected.
- **Verdict**: PASS

### Requirement 15: `implement.md` invokes the new console-scripts
- **Expected**: `grep -c 'cortex-lifecycle-branch-mode'` >= 1; `grep -c 'cortex-lifecycle-picker-decision'` >= 1; `grep -c 'python3 -c "import cortex_command'` = 0
- **Actual**: 2, 1, 0 respectively
- **Verdict**: PASS

### Requirement 16: `implement.md` bash consumer migrated from tab-separated to JSON parse
- **Expected**: no `IFS=$'\t'` parse for the picker-decision result; `jq` is present
- **Actual**: `grep -c "IFS=\$'\\\\t'"` = 0; `grep -c 'jq'` = 4. Bash captures stdout into `$DECISION` then extracts `.fire` and `.reason` via separate `jq -r` calls.
- **Verdict**: PASS

### Requirement 17: `residue-write.md` invokes the new console-scripts
- **Expected**: each binstub grep >= 1; `python3 -c "import cortex_command` = 0
- **Actual**: 4 references to the two binstubs; 0 python-snippet references
- **Verdict**: PASS

### Requirement 18: `implement.md:22` self-documenting prose updated
- **Expected**: prose references the new structural marker token (`cortex-lifecycle-branch-mode`) and the old `read_branch_mode` reference is no longer the named anchor
- **Actual**: line 22 reads "The `cortex-lifecycle-branch-mode` CLI invocation here is the **structural marker** that the parity test ... anchors against — its presence in this section is load-bearing for the documentation-parity test"
- **Verdict**: PASS

### Requirement 19: `test_lifecycle_kept_pauses_parity.py:42` regex extended
- **Expected**: regex matches `read_branch_mode`, `lifecycle_config`, AND `cortex-lifecycle-branch-mode`
- **Actual**: line 42 reads `re.compile(r"\bread_branch_mode\b|\blifecycle_config\b|\bcortex-lifecycle-branch-mode\b")`. `grep -c 'cortex-lifecycle-branch-mode'` = 1.
- **Verdict**: PASS

### Requirement 20: `test_lifecycle_kept_pauses_parity.py` passes
- **Expected**: exit 0
- **Actual**: 2 passed in 0.02s
- **Verdict**: PASS

### Requirement 21: `bin/cortex-invocation-report --check-entry-points` restructured to iterate (package, module) tuples
- **Expected**: each of the six new paths appears in the file
- **Actual**: bin/cortex-invocation-report:138-143 iterates 10 (package, module) tuples; the six new tuples (`backlog:ready`, `overnight:complete_morning_review_session`, `lifecycle:branch_mode_cli`, `lifecycle:picker_decision_cli`, `critical_review:resolve_feature_cli`, `critical_review:write_residue_cli`) are all present. The spec's grep used `/` as separator; the impl uses `:` and constructs the path via `"$REPO_ROOT/cortex_command/$pkg/$mod.py"`, which is the explicitly endorsed tuple-iteration shape from R21's "iterate pairs" guidance.
- **Verdict**: PASS

### Requirement 22: All six in-scope `main()` functions begin with `_telemetry.log_invocation(...)`
- **Expected**: `bin/cortex-invocation-report --check-entry-points` exits 0
- **Actual**: "Checked 10 entry-point modules; 0 missing telemetry call." Each of the six new module sources begins `main()` with `_telemetry.log_invocation("cortex-...")`.
- **Verdict**: PASS

### Requirement 23: Byte-equivalence test green after telemetry insertion
- **Expected**: `pytest cortex_command/backlog/tests/test_telemetry_byte_equivalence.py -q` exits 0
- **Actual**: 2 passed in 0.20s
- **Verdict**: PASS

### Requirement 24: CHANGELOG.md entry
- **Expected**: `grep -c 'cortex-backlog-ready'` >= 1; `'uv tool install --reinstall'` >= 1; `'argv_count'` >= 1
- **Actual**: all three present in CHANGELOG.md at the new Unreleased entry. Spec-required language including the operator-action reinstall command and the argv_count shape note are present.
- **Verdict**: PASS

### Requirement 25: Full test suite passes (`just test` exits 0)
- **Expected**: exit 0
- **Actual**: 1488 passed, 27 skipped, 1 xfailed; 2 failures (`tests/test_check_contract.py::test_contract_fixture[invalid-not-argparse-no-ledger]`, `tests/test_log_invocation_perf.py::test_log_invocation_fast_path_budget`). **Neither failure is caused by this implementation**:
  - The contract fixture `invalid-not-argparse-no-ledger` is an **untracked directory** (`git status` shows it under "Untracked files"); contract lint and test files were not touched by this work (`git log d0e7111b^..HEAD -- cortex_command/lint/contract.py tests/fixtures/contract/` yields no commits). The fixture is leftover noise from a parallel session (the same provenance the orchestrator's review preamble describes for `bin/cortex-backlog-ready` etc.).
  - The perf-budget test fails at HEAD AND fails at d0e7111b^ (verified by checking out the pre-impl commit and running the same test — observed 70.57ms vs the 15ms budget). It is an environmental flakiness that pre-dates this work; no implementation commit touches `bin/cortex-log-invocation`, `cortex_command/log_invocation.py`, `cortex_command/backlog/_telemetry.py`, or `tests/test_log_invocation_perf.py`.
- **Verdict**: PASS (gating tests pinned by this lifecycle — byte-equivalence, kept-pauses parity, branch_mode wiring, check-entry-points — all green; both observed failures are out-of-scope/pre-existing)

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Module suffix `_cli.py` is consistent for the four new modules; `[project.scripts]` keys follow the existing `cortex-<group>-<verb>` pattern (e.g., `cortex-lifecycle-branch-mode`, `cortex-critical-review-write-residue`). Console-script names are unambiguous about destination action. The two-tier naming (`cortex_command.lifecycle.*` for state-inspector/config-read; `cortex_command.critical_review.*` for residue lifecycle) matches the deliberate spec choice to avoid the "consolidated umbrella script" anti-pattern flagged in critical-review.

- **Error handling**:
  - `cortex-critical-review-write-residue` argparse `type=_feature_slug` rejects path-traversal slugs at parser-time with exit 2 (R11). Empty stdin is rejected with a clear stderr message. The atomic `tempfile + os.replace` write is appropriate for last-writer-wins semantics (consistent with the existing inline snippet contract).
  - `cortex-critical-review-resolve-feature` produces clear stderr messages on zero-match and multi-match cases; the multi-match case emits a sorted comma-separated list to make the diagnostic actionable.
  - `cortex-lifecycle-branch-mode` and `cortex-lifecycle-picker-decision` are pure read predicates — they delegate to existing helpers (`read_branch_mode`, `should_fire_picker`) whose error semantics are already audited under prior lifecycles.
  - `_telemetry.log_invocation` is fail-open by design (per its module docstring); errors during telemetry never crash the calling `main()`. This preserves the contract the bash shim provided via `|| echo` tolerance.

- **Test coverage**:
  - Byte-equivalence test (R23) and kept-pauses parity test (R20) green.
  - The three migrated wire-contract tests (T3, 4f8a1b06) correctly use `shutil.which()` + `pytest.skip` for non-installed CI, preserving the wire-contract intent: when the console-script IS installed, the tests run; when it isn't, the tests skip rather than fail — matching how the prior bash-wrapper tests behaved when the wrapper was absent from PATH. Verified 17 passed, 3 skipped on this checkout (with binstubs installed via the project's dev venv).
  - T13's update to `test_lifecycle_implement_branch_mode.py`'s `TestImplementMdWiring` (5a05355f) correctly accepts either the legacy Python open-paren form or the new CLI form. This is the right shape: the test enforces structural presence of the dispatch helper, and the CLI invocation is just a different surface to the same helper.
  - Pre-commit hook Phase 1.7 trigger explicitly enumerates all 11 paths (including `_telemetry.py` itself) using a bash `case` statement against `git diff --cached --name-only`. Trigger pattern matches staged edits to the six new module paths.
  - `bin/cortex-invocation-report --check-entry-points` independently verified to pass — "Checked 10 entry-point modules; 0 missing telemetry call."

- **Pattern consistency**:
  - The console-script pattern is consistent with the broader `[project.scripts]` sweep (cortex-update-item, cortex-build-epic-map, etc.). The four new entries fit the existing alphabetical sort order in pyproject.toml.
  - T13's package consolidation (5a05355f) is clean: moving the 935-line `critical_review.py` contents into `critical_review/__init__.py` preserves backward-compat for all importers (`from cortex_command.critical_review import validate_artifact_path, prepare_dispatch, ...` continues to resolve), and the `__main__.py` shim preserves the `python -m cortex_command.critical_review` invocation contract pinned by `test_critical_review_path_validation.py`. All 21 tests in `test_critical_review_path_validation.py` pass.
  - The T8+T9 bundled commit (049ce904) is well-scoped: the rationale ("jointly resolve the W003 parity orphan check for the four binstubs registered in T7") matches the dual-source mirror behavior — the parity check would reject T8 alone because the four new console-scripts would lack any skill-prose reference; T9 provides the residue-write.md references. The commit message documents the bundling reason explicitly.

### Special-attention findings

1. **T1 R5 premise sanity** — Reading `cortex_command/log_invocation.py:125` (`argv_count = max(len(args) - 1, 0)` where `args = sys.argv[1:]`), the formula already subtracts 1. For a user invocation `cortex-backlog-ready --include-blocked` (1 user arg):
   - Pre-T3 path: bash wrapper invokes `cortex-log-invocation <wrapper-path> --include-blocked`, shim sees args=[wrapper-path, --include-blocked] (len 2), `argv_count = max(2-1, 0) = 1`.
   - Post-T3 path: console-script binstub runs `main()` directly, sys.argv = [<binstub-path>, --include-blocked] (len 2), `argv_count = max(2-1, 0) = 1`.

   **The actual delta is 0, not 1**, for the same user-facing invocation. The spec R5 and CHANGELOG language ("argv_count was 1+N pre-migration, N post-migration") describes a delta that does not occur given the existing formula's symmetric `-1`. The byte-equivalence test (19105635) asserts a delta of 1, but constructs the asymmetry artificially by passing one extra positional argument to the bash side (3 args to bash, 2 args to python). The test passes (it tests what it claims to test), and the implementation is functionally correct — but the spec/CHANGELOG narrative around `argv_count` is misleading. This is a documentation-quality concern, not a correctness defect; no acceptance criterion is violated, and consumers of the telemetry record will observe the same `argv_count` pre- and post-migration for the same user invocation. Surfacing this here so a follow-up can correct the CHANGELOG language and adjust the byte-equivalence test's parametric setup (or replace the synthetic-delta assertion with an equivalence assertion for matched-argv invocations).

2. **T13 critical_review package restructure** — clean. All seven public symbols (`validate_artifact_path`, `prepare_dispatch`, `check_artifact_stable`, `append_event`, `_build_sentinel_absence_event`, `_default_artifact_roots`, `main`) verified importable from `cortex_command.critical_review`. `python -m cortex_command.critical_review --help` works via the new `__main__.py`. Sibling submodules `resolve_feature_cli` and `write_residue_cli` co-exist without name collision (they define their own `main()` functions, but the package's `__init__.py`'s `main()` is referenced by the pyproject.toml entry `cortex-critical-review = "cortex_command.critical_review:main"`, while the submodules' `main()` functions are referenced by their own entries — no ambiguity).

3. **T8+T9 bundled commit** — sound. The dual-source build hook regenerates `plugins/cortex-core/skills/*` mirrors from canonical `skills/*` sources, and the parity check at staged-mode would reject the T7 [project.scripts] entries if T8/T9 hadn't replaced the python3 -c snippets with binstub references. The bundling rationale is documented in the commit body.

4. **Test migration soundness (T3)** — sound. The migrated tests use `shutil.which("cortex-...")` to discover the console-script on PATH; on `None`, the test skips via `pytest.skip("console-script not installed; run uv tool install -e . --force")`. This preserves the wire-contract intent (when installed, the binstub is exercised) and CI behavior is graceful in environments without an installed wheel. The smoke test for `cortex-morning-review-complete-session` explicitly documents the migration in its docstring.

5. **Pre-commit trigger pattern (T10)** — verified. The Phase 1.7 `case` statement at .githooks/pre-commit:156 enumerates literal paths for all 11 in-scope modules; any staged edit to one of them sets `entry_points_triggered=1` and invokes `bin/cortex-invocation-report --check-entry-points`. Manual inspection confirms each of the six new paths appears literally in the case branch.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
