# Review: cortex-check-contract-false-positives-on

## Stage 1: Spec Compliance

### Requirement R1: Command-position guard for invocation detection
- **Expected**: Per-match predicate `_is_invocation(left, token, right)` applied inside `_emit_fenced` and the inline-span loop before `Invocation` construction; extension-rejection wins over command-position acceptance; path-prefixed token with flags is a real run; probe-operand rejection; `=`-RHS bare-value rejection with `=$(` exempt; bare-no-tail skip made symmetric between fenced and inline; audit emits zero E101.
- **Actual**: `_is_invocation` is implemented at lines 576–658 with the four rules in the correct precedence order (extension → path-prefix-with-argv → probe → `=`-RHS → command-position). Applied in `_emit_fenced` (line 770) and in the inline loop (line 861) before `Invocation` construction. Bare-no-tail skip is present in `_emit_fenced` (line 775, symmetric with inline line 866). Load-bearing cases verified manually: `bin/cortex-worktree-create --base-branch main` → True; `cortex-worktree-create feature/foo` → True; `cortex-worktree-create.sh` at span start → False (extension rule wins); `worktree_path=$(cortex-worktree-create --feature foo)` → True (`$(` is a shell separator); `FOO=1 cortex-worktree-create --base-branch main` → True (env prefix). Full-corpus audit exits 0 with zero E101 (confirmed by running `PYTHONPATH=... .venv/bin/python -m cortex_command.lint.contract --audit --root ...`).
- **Verdict**: PASS
- **Notes**: The `_SHELL_SEP_RE` includes `$(`; the `_ENV_PREFIX_RE` correctly handles the space-separated env-prefix form; `_BARE_COMMAND_RE` correctly accepts bare `command` execution. Rule precedence is structural (early returns), not prose-only.

### Requirement R2: Genuine E101 detection preserved, including false-negative-trap shapes
- **Expected**: Fixtures `invalid-missing-feature-baseline`, `invalid-missing-feature-positional`, `invalid-missing-feature-piped`, `invalid-missing-feature-envprefix`, `invalid-missing-feature-bin-path` each exit 1 with exact-set `["E101"]`.
- **Actual**: All five fixtures are present with correctly structured `pyproject.toml`, `stub_worktree_create.py` (–feature required, –base-branch optional), `skills/demo/SKILL.md`, and `expected.json` = `["E101"]`. All five pass under `pytest`. The positional case (`feature/foo`) correctly flags because path-component rejection keys on the token, not the tail. The env-prefix case (`FOO=1 cortex-worktree-create`) correctly flags via `_ENV_PREFIX_RE`. The `bin/cortex-worktree-create --base-branch main` case correctly flags via rule 1b (path-prefixed with argv → accept, then rule 2 validates flag presence).
- **Verdict**: PASS

### Requirement R3: False-positive shapes locked as valid-* fixtures
- **Expected**: `valid-hook-filename-inline`, `valid-hook-filename-table`, `valid-hook-filename-fenced` (`.sh` mentions), `valid-command-v-probe` (fenced `command -v … >/dev/null 2>&1`), `valid-which-type-hash-probe`, and `invalid-mixed-span` (exact-set `["E101"]`). `valid-command-v-probe` must use fenced+redirection shape so it exercises probe rule (3) rather than the bare-no-tail skip.
- **Actual**: All six fixtures present and passing. `valid-command-v-probe` correctly uses a fenced block with `command -v cortex-worktree-create >/dev/null 2>&1` (non-empty right-context `>/dev/null 2>&1`), ensuring probe rule fires before the bare-no-tail skip. `valid-which-type-hash-probe` uses fenced blocks with empty tails; probe rule (3) still fires first in `_is_invocation` (before the bare-no-tail skip at line 775/866) because `_PROBE_HEAD_RE.search` on `'which '`/`'type '`/`'hash '` matches at rule-3 evaluation. `invalid-mixed-span` has both a `.sh` path-mention (dropped) and a real missing-flag run (kept) in one fenced block; exits 1 with exact-set `["E101"]`.
- **Verdict**: PASS
- **Notes**: The valid-hook-filename-fenced fixture uses `claude/hooks/cortex-worktree-create.sh` (with path prefix). The pure span-start case (`cortex-worktree-create.sh` with empty left) from the real corpus (sdk.md:157) is validated by the audit acceptance command rather than a dedicated fixture; spec R3 names the shapes at the level of inline/table/fenced, not at the specific span-start sub-variant.

### Requirement R4: Exact-set invalid-* assertion
- **Expected**: `grep -c "any(code in expected_codes" tests/test_check_contract.py` = 0; harness asserts `sorted(actual_codes) == sorted(expected_codes)`.
- **Actual**: `grep` count = 0. Assertion at line 113 uses `sorted(actual_codes) == sorted(expected_codes)`. The `invalid-missing-required-flag/expected.json` was updated to `["E101", "E101"]` (the fixture had two required flags missing, which the old `any`-membership check silently accepted but the multiset check correctly requires).
- **Verdict**: PASS

### Requirement R5: Defect B verified and regression-locked
- **Expected**: `valid-subcommand-flag` exits 0 (empty); `invalid-unknown-subcommand-flag` exits 1 with exact-set `["E102"]`.
- **Actual**: Both fixtures present. `stub_discovery.py` models `cortex-discovery emit-research-sizing` with `--topic`/`--complexity`/`--criticality` required (matching the spec's reference to `discovery.py`). `valid-subcommand-flag` documents the correct full invocation; `invalid-unknown-subcommand-flag` adds `--nope`. Both pass under `pytest`.
- **Verdict**: PASS

### Requirement R6: No regression to E104 / ledger / self-test / two-mode
- **Expected**: `pytest tests/test_check_contract.py -q` exits 0; `--self-test` exits 0; `--validate-exceptions` exits 0.
- **Actual**: All three acceptance commands confirmed: 38 tests pass in 1.25s; `--self-test` prints "self-test passed", exits 0; `--validate-exceptions` exits 0. The E104 `extraction_status != "ok"` early-continue at line 1446 is untouched. The ledger match-key `(binary, flag, path)` shape is untouched. Two-mode split (`--staged` → `_scan_staged`, else → `scan_corpus`) is preserved at lines 1734–1739.
- **Verdict**: PASS

### Requirement R7: Deferred latent items documented at code sites; stale-wheel protocol recorded
- **Expected**: `grep -c "DEFERRED (#279)" cortex_command/lint/contract.py` ≥ 4 AND `grep -c "CORTEX_COMMAND_FORCE_SOURCE" cortex_command/lint/contract.py` ≥ 1; four comments at four distinct sites.
- **Actual**: Count = 4 DEFERRED comments, 1 CORTEX_COMMAND_FORCE_SOURCE reference. Sites are: (iii) line 1072 in `_collect_parser_nodes` docstring (helper-injected-flag AST blindness); (iv) line 1484 in `validate()` at the subcommand resolution branch (parent-flag-loss); (i) line 1493 in `validate()` after the subcommand loop (unknown-subcommand fall-through); (ii) line 1515 in `validate()` at the flag-validation loop (allow_abbrev). The stale-wheel protocol comment is at line 1726 in `main()` at the gather-invocations dispatch site. All four sites are distinct. The allow_abbrev comment explicitly records that exact-match is the intended contract (not a bug), matching the spec's requirement.
- **Verdict**: PASS
- **Notes**: (i) and (iv) are in close proximity within the same `if surf.subcommands:` block (lines 1479–1499), but they annotate logically distinct behaviors (parent-flag-loss on match vs. unknown-subcommand fall-through on no-match), satisfying the spec's "four distinct sites" requirement.

### Requirement R8: --staged membership congruent with --audit (commit-time gate reaches deep files)
- **Expected**: `_in_scan_scope` helper using regex-based recursive glob (`**` = zero-or-more segments); Python-3.12-safe (no `PurePath.full_match`); depth-1 `.md`, depth-≥3 `.md`, `hooks/**`, and exact-name membership all pass; staged depth-≥3 file with violation is flagged; `grep -c "full_match" cortex_command/lint/contract.py` = 0.
- **Actual**: `_glob_to_regex` (lines 430–462) translates each `_SCAN_GLOBS` entry to a compiled regex with `**` = "zero or more segments" (`(?:[^/]+/)*`). Pre-compiled as `_SCAN_GLOB_PATTERNS` at import time. `_in_scan_scope` (lines 471–482) iterates patterns. `_scan_staged` (line 1620) calls `_in_scan_scope` with the comment explaining the Python 3.12 rationale. `grep -c "full_match"` = 0. All 16 `test_in_scan_scope` parametrize cases pass (covering depth-1, depth-2, depth-≥3 `.md`, `hooks/**`, exact-names, and negative cases). `test_staged_deep_file_violation_detected` passes (depth-3 staged file `skills/lifecycle/references/implement.md` triggers E101). The `hooks/**` shape uses the `glob.endswith("/**")` branch (line 446–449) matching any file at any depth under `hooks/`, providing correct depth-1 hook file coverage.
- **Verdict**: PASS

### Non-Requirements / Edge Cases
- No shell-lexing introduced (confirmed: `shlex` only used in the existing `validate()` tail-normalization, not in the command-position predicate).
- No exception-ledger suppression for the 8 FPs (all cleared by detection fix; ledger unchanged).
- Parent-flag-loss not fixed — documented as DEFERRED (#279) item (iv).
- `bin/cortex-check-contract` wrapper untouched (no diff to that file).
- Edge case `worktree_path=$(cortex-worktree-create --feature …)`: correctly classified as real invocation (left ends with `$(`, which is a shell separator in `_SHELL_SEP_RE`).
- Edge case `FOO=1 cortex-worktree-create --base-branch main`: correctly classified as real run (`_ENV_PREFIX_RE` matches).
- Edge case `cortex-worktree-create feature/foo`: correctly classified as real run (token itself has no path prefix, tail path-likeness is irrelevant to the rule).
- Mixed span: per-match predicate processes each `_BINARY_RE` match independently — path-mention dropped, real run kept.
- Orphaned ledger rows: none — ledger entries cover non-argparse binaries and intentional-omission cases, none related to `cortex-worktree-create` path-mentions or probes.

## Requirements Drift
**State**: detected
**Findings**:
- The "Two-mode gate pattern" constraint in `cortex/requirements/project.md` (line 92) states that pre-commit gates pair `--staged` with `--audit`. R8 establishes a new invariant: the `--staged` corpus membership must be congruent with `--audit` (same files in scope at all depths), using a recursive-glob matcher. This corpus-congruence property is not captured anywhere in the project requirements document, yet it is now structurally enforced by `_in_scan_scope` and tested by `test_staged_deep_file_violation_detected`. Without documentation, a future maintainer who refactors `_scan_staged`'s membership check may silently reintroduce the depth-restriction bug.
**Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update
**File**: `cortex/requirements/project.md`
**Section**: Architectural Constraints → Two-mode gate pattern (line 92)
**Content**: Append the following to the bullet: `; the \`--staged\` mode membership must be corpus-congruent with \`--audit\` (same files in scope at all depths) — enforced by \`_in_scan_scope\` in \`cortex_command/lint/contract.py\` using a recursive-glob matcher safe on Python 3.12+.`

## Stage 2: Code Quality

- **Naming conventions**: Consistent with existing project patterns. `_is_invocation`, `_in_scan_scope`, `_glob_to_regex`, `_SCAN_GLOB_PATTERNS`, `_PROBE_HEAD_RE`, `_EXT_SUFFIX_RE`, `_ARGV_TOKEN_RE`, `_ENV_PREFIX_RE`, `_BARE_COMMAND_RE`, `_PATH_PREFIX_CHARS` all follow the established `_SCREAMING_SNAKE` / `_lowercase` internal conventions in the file. The new fixture directories follow the `valid-*` / `invalid-*` naming scheme already established.

- **Error handling**: Appropriate for context. `_is_invocation` is a pure predicate with no I/O; no error handling needed. `_glob_to_regex` handles the three distinct glob shapes (`/**` suffix, no `**`, `**/` interior) without silent fall-through. `_scan_staged` retains the existing `try/finally` for temp-file cleanup.

- **Test coverage**: The acceptance commands all pass. The `test_in_scan_scope` parametrize table covers all spec-required depth shapes plus negative cases. `test_staged_deep_file_violation_detected` provides end-to-end staged-mode coverage. The `valid-command-v-probe` fixture correctly uses a fenced+redirection shape, exercising probe rule (3) with a non-empty right-context rather than relying on the bare-no-tail skip. The `valid-which-type-hash-probe` fixtures use fenced blocks with empty tails; this is acceptable because `_is_invocation` (and therefore probe rule 3) is evaluated before the bare-no-tail check in `_emit_fenced` — probe rule fires first in all cases. The 5 `invalid-missing-feature-*` fixtures cover all false-negative traps named in the spec. The `invalid-mixed-span` fixture directly tests per-match independence.

- **Pattern consistency**: `_glob_to_regex` is factored as a helper and pre-compiled at import time (consistent with how `_BINARY_RE`, `_FENCE_RE`, `_INLINE_CODE_RE`, `_PLACEHOLDER_RE` are pre-compiled). The `_is_invocation` predicate is factored separately from the scanner loop (consistent with the existing `_has_sentinel`, `_is_hard_excluded`, `_in_scan_scope` factoring pattern). The DEFERRED comments follow the `# DEFERRED (#279): (label) — ...` format consistently across all four sites.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
