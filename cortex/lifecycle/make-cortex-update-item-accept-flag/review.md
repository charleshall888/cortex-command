# Review: make-cortex-update-item-accept-flag

## Stage 1: Spec Compliance

### Requirement 1: Argparse rewrite preserves existing field-set semantics
- **Expected**: New CLI accepts `status`, `complexity`, `criticality`, `spec`, `lifecycle_slug`, `lifecycle_phase`, `session_id`, `priority`, `parent`, `blocked-by`, `rework_of` plus list fields (`areas`, `tags`); `--help` exits 0 and lists the flags; internal `update_item(item_path, ...)` signature unchanged.
- **Actual**: `cortex_command/backlog/update_item.py` defines `_SCALAR_FLAGS` and explicit `--areas`/`--tags` list flags via `argparse`. `--help` exits 0 and lists all expected flags plus the positional `slug`. `grep -nE "def update_item\(item_path" ...` returns exactly one line at `:328` (signature unchanged: `update_item(item_path, fields, backlog_dir, session_id=None)`).
- **Verdict**: PASS
- **Notes**: The argparse layer also adds `--type` (mapped to frontmatter key `type` via `dest="item_type"`), which is not enumerated in the R1 spec field-set but is a superset, not a regression. R1 says "the same set of scalar fields the current CLI accepts" — this is an additive extension not required by but compatible with R1.

### Requirement 2: `null` / `none` / `""` coercion preserved for scalar fields, list elements not coerced
- **Expected**: For scalar flags, values `null`/`none`/`""` (case-insensitive) coerce to Python `None`. List elements pass through literally.
- **Actual**: `main()` lines 555-559 implement the coercion (`if value.lower() in ("null", "none", "")`). Verified empirically: `parse_args(["257", "--areas", "", "a", "b"]).areas == ["", "a", "b"]`. Unit test `test_scalar_null_sentinel_coerces_to_python_none` covers all sentinels for the `--status` scalar. List-element non-coercion is verified empirically (working tree) — there is no dedicated unit test asserting `--areas '' a b` produces `['', 'a', 'b']`, though the parse path is the same as for any list flag, and the spec acceptance criteria called for that explicit assertion.
- **Verdict**: PARTIAL
- **Notes**: The list-element non-coercion assertion called out in R2 acceptance criteria is not implemented as a named test function. The behavior is correct, but the explicit unit test prescribed by spec is missing. Minor coverage gap.

### Requirement 3: List fields use `nargs='*'` for single-flag multi-value shape
- **Expected**: `--areas a b c` → `['a','b','c']`; bare `--areas` → `[]`; duplicate flags last-wins.
- **Actual**: `_build_parser()` lines 521-522 declare `--areas` and `--tags` with `nargs="*"`. Unit tests cover bare `--areas` → `[]` (`test_list_flag_areas_bare_yields_empty_list`) and duplicate-flag last-wins (`test_list_flag_areas_last_wins_on_duplicate`). The first acceptance assertion (`--areas overnight-runner backlog` → list of 2) is not explicitly tested as a named function, but its behavior follows trivially from argparse `nargs='*'` and is verified empirically.
- **Verdict**: PASS

### Requirement 4: `allow_abbrev=False` on parser
- **Expected**: Prefix-shortened flags (`--stat`) raise `SystemExit`.
- **Actual**: `_build_parser()` line 506 sets `allow_abbrev=False`. Test `test_allow_abbrev_false_rejects_prefix_shortened_flag` passes.
- **Verdict**: PASS

### Requirement 5: Argv pre-flight migration hint catches legacy `key=value` form
- **Expected**: Scan `sys.argv[1:]` for `^[a-z_][a-z_]*=`; on match, print to stderr the literal substring `Detected legacy key=value form '<arg>'. Use --<key> <value> instead. See cortex-update-item --help.` and exit 2.
- **Actual**: `_argv_preflight` (lines 482-499) implements the regex correctly and exits 2. However, the printed message is `Detected legacy positional argument '<arg>'. The CLI now requires --<key> <value>. See 'cortex-update-item --help' for the full flag list.` — semantically equivalent but does NOT contain the exact spec substring `Detected legacy key=value form`. Tests assert `"Detected legacy positional argument" in err` (i.e. the tests pass but they pin the implementation's wording, not the spec's). All three sub-cases (bare `key=value`, bracket-list, negative `--status=complete`) behave as specced.
- **Verdict**: PARTIAL
- **Notes**: Behavior is correct (exits 2, hint is actionable, scope of detection matches spec). Wording diverges from spec acceptance text. Reviewer judgment: substantive intent is met but the literal acceptance-criteria substring check would fail if applied strictly. If the wording change was intentional, the spec acceptance text should be updated to match (or vice versa).

### Requirement 6: Module docstring reflects new CLI; legacy `Usage:` removed
- **Expected**: `grep -nE "key=value" cortex_command/backlog/update_item.py` returns zero matches.
- **Actual**: Only match is inside `_argv_preflight`'s docstring at line 483 (`"""Detect legacy positional ``key=value`` args ..."""`) — narrative reference, not a CLI usage string. Module docstring (lines 1-9) does not reference `key=value`. The `main()` Usage error string referencing `key=value` has been removed.
- **Verdict**: PARTIAL
- **Notes**: Strict reading of acceptance criteria (`grep` returns zero) does not hold; there is one match in a narrative docstring describing the migration-hint function. This is not a usage string and does not mislead callers, but it does cause the spec's literal grep check to fail.

### Requirement 7: New CLI argparse unit-test file exists and covers the surface
- **Expected**: `tests/test_update_item_cli.py` exists, `pytest` exits 0, `grep -c "^def test_"` ≥ 5.
- **Actual**: File exists with 10 named `def test_` functions. `python3 -m pytest tests/test_update_item_cli.py -v` exits 0 (14 collected including parametrized cases, all pass).
- **Verdict**: PASS

### Requirement 8: All in-repo executable callers migrated
- **Expected**: `grep -rnE 'cortex-update-item[^|]*[ "'\''"][a-z_][a-z_-]*=' skills/ docs/ justfile tests/ bin/ hooks/ claude/ cortex_command/ plugins/` returns zero matches.
- **Actual**: Returns three matches: `docs/index.html:6341` (HTML span describing CLI in a generated docs index — `<span class="cmd">cortex-update-item</span><span class="desc">atomic frontmatter write-back</span>`, not a legacy invocation), `tests/fixtures/contract/valid-non-argparse-exempt/skills/demo/SKILL.md:6` and `:12` (contract-lint fixture intentionally documenting the legacy non-argparse pattern for an exempt fixture — this is fixture content scoped to a test of the new contract lint, not an executable caller). None are executable invocations of the legacy form.
- **Verdict**: PASS
- **Notes**: The acceptance grep returns matches, but on inspection all are descriptive content (HTML desc string + intentional contract-lint fixture text), not executable invocations. The spec's grep was not written tightly enough to exclude these descriptive contexts; the implementation is correct in spirit.

### Requirement 9: Test fixture migrated in same commit as skill prose
- **Expected**: `CLOSE_ARG = "--status complete"` in `tests/test_morning_review_status_close_ordering.py`; tests pass.
- **Actual**: Line 22 contains `CLOSE_ARG = "--status complete"`. All three tests pass under `pytest`.
- **Verdict**: PASS

### Requirement 10: Plugin mirrors regenerated
- **Expected**: After `just build-plugin`, `cortex-update-item ... key=value` returns zero matches in `plugins/`.
- **Actual**: `plugins/cortex-core/skills/` and `plugins/cortex-overnight/skills/` mirror the canonical migrations (`cortex-update-item 078 --status complete`, `cortex-update-item {backlog_id} --status complete`). Grep over `plugins/` returns zero legacy invocations.
- **Verdict**: PASS

### Requirement 11: Wheel reinstalled before binstub-tier verification
- **Expected**: `cortex-update-item --help` (binstub on PATH) exits 0 and stdout contains `--status`.
- **Actual**: `/Users/charlie.hall/.local/bin/cortex-update-item --help` exits 0; stdout contains `--status STATUS`. Binstub reflects the new flag set.
- **Verdict**: PASS

### Requirement 12: Parity check confirms migration does not regress existing checks
- **Expected**: `cortex-check-parity --audit` exits 0.
- **Actual**: Exits 1, but failures are unrelated to this ticket — they are in `bin/cortex-check-contract` (4 callsites), `justfile:389`, and various `__pycache__` artifacts. None reference `cortex-update-item` or its callers. The allowlist was correctly updated (commit `56ee6641`) for this ticket's `tests/test_morning_review_status_close_ordering.py` docstring references. Pre-existing parity-audit failures appear scoped to ticket 248 (`python3 -m` migration) and the `__pycache__` byproduct of running the test suite.
- **Verdict**: PARTIAL
- **Notes**: The spec acceptance criteria literally state "exits 0." That is not met. However, the spec rationale ("confirms the migration does not break parity's existing scope") IS met — no parity regression is attributable to this ticket's changes. Reviewer judgment: the failures are pre-existing and unrelated; this is environment-state drift, not a regression introduced by this work.

### Requirement 13: Automated migration-hint integration test
- **Expected**: A subprocess-based test invokes `python3 -m cortex_command.backlog.update_item 257 status=complete`, asserts exit 2 and stderr substring `Detected legacy key=value form 'status=complete'.`
- **Actual**: `test_subprocess_legacy_positional_exits_2_with_hint` performs the subprocess invocation, asserts `result.returncode == 2`, and asserts `"Detected legacy positional argument" in result.stderr`. Same wording divergence as R5 — the test passes against the implemented message, but the spec's literal substring (`Detected legacy key=value form`) does not appear.
- **Verdict**: PARTIAL
- **Notes**: Same reasoning as R5 — behavior correct, exit code correct, wording diverges from spec literal.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. `_SCALAR_FLAGS`, `_SCALAR_DESTS`, `_DEST_TO_FRONTMATTER_KEY` follow the module-private `_UPPER_SNAKE` convention used elsewhere in `cortex_command/`. CLI helpers `_argv_preflight`, `_build_parser` follow the project's `_lowercase_snake` private-helper convention. Frontmatter key vs. argparse dest distinction is cleanly encoded in `_DEST_TO_FRONTMATTER_KEY`.
- **Error handling**: Pre-flight raises `SystemExit(2)` with an actionable stderr message before argparse runs, matching the spec's exit-2 semantics. argparse's own errors (unknown flag, missing positional) propagate naturally with stdlib exit-2. The `main()` "Item not found" path exits 1 (unchanged from prior behavior). One observation: the internal `update_item` API is untouched and continues to handle frontmatter writes atomically via `atomic_write` — no new failure surfaces introduced.
- **Test coverage**: 14 collected test functions exercise scalar parsing, list parsing (bare/last-wins), `allow_abbrev=False`, scalar `null/none/""` coercion (5 parametrized sentinels), pre-flight bare/bracket-list/negative-case detection, and a subprocess integration test. Coverage gap: no dedicated test for list-element non-coercion (`--areas '' a b → ['', 'a', 'b']`) called out in R2 acceptance criteria — though the behavior is correct and verifiable. Two of three acceptance assertions in R3 are explicit tests; the third (`--areas a b → ['a','b']`) is implicit via the last-wins test.
- **Pattern consistency**: Follows the project's "Skill-helper modules" idiom — `cortex-update-item` is a `[project.scripts]` console-script (R11 verifies the binstub). Pre-flight + argparse + dispatch to internal API matches the structure of sibling CLIs (`cortex-create-backlog-item`, `cortex-resolve-backlog-item`). The migration of skill prose, justfile, docs, plugins/, and the morning-review test fixture in a single coordinated rollout matches the project's "atomic caller migration" pattern.

## Verdict

{"verdict": "APPROVED", "cycle": 1, "issues": ["R5/R13 stderr message wording diverges from spec acceptance text — implementation prints 'Detected legacy positional argument' instead of the spec's literal 'Detected legacy key=value form'; behavior is equivalent but tests pin implementation wording, not spec wording", "R6 grep -nE 'key=value' returns one match inside _argv_preflight's narrative docstring, not zero as the acceptance criteria literally state — match is descriptive prose, not a Usage string", "R12 cortex-check-parity --audit exits 1 due to pre-existing unrelated failures (bin/cortex-check-contract, justfile:389, __pycache__ artifacts) attributable to ticket 248's scope, not this ticket — spec's literal 'exits 0' criterion not met but no regression introduced by this work", "R2 acceptance criteria called for a dedicated unit test asserting --areas '' a b → ['', 'a', 'b'] list-element non-coercion; the behavior is correct but no named test function asserts it"], "requirements_drift": "none"}
