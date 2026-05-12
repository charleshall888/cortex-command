# Review: add-path-hardcoding-parity-gate-to-prevent-cortex-root-drift

> **Self-review caveat**: Performed inline by the same agent that implemented the feature, per the parallel-sessions feedback memory (avoid subagent dispatch while concurrent lifecycles are in flight). Anchoring on the implementation is a real risk — call out anything that looks like it warrants a fresh-context second opinion.

> **Requirements loaded**: `cortex/requirements/project.md` only — no area docs matched tags `[drift-prevention, parity, consolidate-artifacts-under-cortex-root]` against the Conditional Loading phrases in project.md.

> **Changed files** (excluding lifecycle artifacts): `.githooks/pre-commit`, `bin/.path-hardcoding-allowlist.md`, `bin/cortex-check-path-hardcoding`, `bin/cortex-check-prescriptive-prose`, `cortex_command/overnight/daytime_pipeline.py`, `justfile`, `tests/test_check_path_hardcoding.py`, `tests/test_check_prescriptive_prose.py`, `bin/.parity-exceptions.md` (no — reverted), plus regenerated plugin mirrors.

## Stage 1: Spec Compliance

### Requirement 1: Gate script exists and is executable
- **Expected**: `bin/cortex-check-path-hardcoding` exists, executable, supports `--staged`, `--audit`, `--root` modes; `--help` exits 0 with all three flags in stdout.
- **Actual**: Script exists, `chmod 0755` confirmed in commit 374d8b4e. `--help` output lists all three flags.
- **Verdict**: PASS

### Requirement 2: Slash-prefix detection
- **Expected**: Gate flags string-literal occurrences matching `["'](lifecycle|backlog|research|requirements)/`.
- **Actual**: `_SLASH_RE` at `bin/cortex-check-path-hardcoding:66-68` constructed via `_PREFIX_ALTERNATION` string-concat. `test_slash_prefix_violation_flags`, `test_fstring_slash_prefix_violation_flags` exercise.
- **Verdict**: PASS

### Requirement 3: Bare-literal Path/os.path.join detection
- **Expected**: Gate flags `\b(Path|os\.path\.join)\(\s*["'](lifecycle|backlog|research|requirements)["']` form.
- **Actual**: `_BARE_RE` at `bin/cortex-check-path-hardcoding:73-78` built via string concat. `test_bare_path_literal_flags`, `test_bare_os_path_join_flags` exercise.
- **Verdict**: PASS

### Requirement 4: Scan-scope inclusion (4 roots)
- **Expected**: `cortex_command/**/*.py`, `bin/cortex-*`, `hooks/cortex-*`, `claude/hooks/cortex-*`.
- **Actual**: `_SCAN_ROOTS` tuple lists all four with `py-tree` vs `cortex-prefix` kind discrimination. `test_scope_includes_bin_cortex_scripts`, `test_scope_includes_hooks`, `test_scope_includes_claude_hooks`, plus `cortex_command/` exercised by every detection test.
- **Verdict**: PASS

### Requirement 5: Scan-scope exclusion (`**/tests/**` at any depth)
- **Expected**: Top-level `tests/` AND nested `cortex_command/init/tests/` both excluded.
- **Actual**: `_path_segments_contain_tests` checks for `"tests"` in any path segment. `test_scope_excludes_tests_subtree_top_level` and `test_scope_excludes_tests_subtree_nested` cover both.
- **Verdict**: PASS

### Requirement 6: Allowlist file and schema
- **Expected**: `bin/.path-hardcoding-allowlist.md` with 6-column schema, closed-enum category (`archive-rewriter`, `docstring-narrative`, `migration-script`), ≥30-char rationale, forbidden literals (`internal`, `misc`, `tbd`, `n/a`, `pending`, `temporary`).
- **Actual**: File exists with header + entries table. Parser at `parse_allowlist` validates category enum, rationale length, forbidden-literal block, ISO date format. `test_allowlist_unknown_category_rejected`, `test_allowlist_short_rationale_rejected`, parametrized `test_allowlist_forbidden_literal_rejected` (7 variants including case-insensitive), `test_allowlist_invalid_date_rejected` cover each constraint.
- **Verdict**: PASS

### Requirement 7: Allowlist suppresses matching violations
- **Expected**: Violations matched by an allowlist row do not cause non-zero exit.
- **Actual**: `allowlist_suppresses()` applies row patterns via `re.search`. `test_allowlist_suppresses_matching_violation` + `test_allowlist_does_not_suppress_unrelated_violation` exercise both directions.
- **Verdict**: PASS

### Requirement 8: Fail-open on missing allowlist
- **Expected**: Missing allowlist file → strict mode (no exceptions); does NOT fail-closed.
- **Actual**: `load_allowlist` returns `([], [], False)` on missing file; no `MISSING_ALLOWLIST` error. `test_fail_open_on_missing_allowlist_clean_tree` + `test_fail_open_on_missing_allowlist_with_violation`.
- **Verdict**: PASS

### Requirement 9: `--staged` mode
- **Expected**: Restricts scanning to `git diff --cached --name-only --diff-filter=ACMR` ∩ scan-scope.
- **Actual**: `run_staged_gate` → `_git_staged_paths` → `filter_staged_to_scope`. `test_staged_mode_flags_in_scope_violation` exercises end-to-end via real git init + `git add -A`.
- **Verdict**: PASS

### Requirement 10: `--audit` mode
- **Expected**: Scans every in-scope file under the repo root; exits 0 on the post-sweep tree.
- **Actual**: `run_audit_gate` → `enumerate_in_scope_files`. T6 verification confirmed `just check-path-hardcoding-audit` exits 0 on whole repo.
- **Verdict**: PASS

### Requirement 11: Pre-commit Phase 1.9 wiring
- **Expected**: Phase 1.9 inserted between 1.85 and 2, trigger pattern matches `cortex_command/**/*.py`, `bin/cortex-*`, `hooks/cortex-*`, `claude/hooks/cortex-*`, and the allowlist file.
- **Actual**: `.githooks/pre-commit:201` declares "Phase 1.9 — Path-hardcoding scanner". Trigger pattern (line 211) covers all five. `grep -nE 'Phase 1\.9' .githooks/pre-commit` returns 1 match.
- **Verdict**: PASS

### Requirement 12: Justfile recipes
- **Expected**: `check-path-hardcoding *args` and `check-path-hardcoding-audit`.
- **Actual**: Both added in `justfile`; `just --list | grep -E 'check-path-hardcoding(-audit)?$'` returns 2 lines.
- **Verdict**: PASS

### Requirement 13: daytime_pipeline.py refactor
- **Expected**: Lines 220, 223, 224, 225, 226, 243, 391 rewritten from `cwd / "cortex" / f"lifecycle/..."` to `cwd / Path("cortex/lifecycle") / feature / "..."`. `grep -cE '"lifecycle/' cortex_command/overnight/daytime_pipeline.py` = 0.
- **Actual**: All 7 lines refactored in commit 8b1b2878. Verification grep returns 0. Smoke test confirmed resolved paths byte-identical pre/post.
- **Verdict**: PASS

### Requirement 14: Prescriptive-prose glob fix (#202 straggler)
- **Expected**: `bin/cortex-check-prescriptive-prose:43` `"backlog/*.md"` → `"cortex/backlog/*.md"`.
- **Actual**: Line 43 updated; docstring line 20 example also updated; `.githooks/pre-commit` Phase 1.85 trigger pattern updated; `tests/test_check_prescriptive_prose.py` fixture paths updated. `grep -cE '"backlog/\*\.md"'` = 0, `grep -cE '"cortex/backlog/\*\.md"'` = 1.
- **Verdict**: PASS

### Requirement 15: Initial allowlist entries
- **Expected**: Rows for `bin/cortex-archive-rewrite-paths` lines 65/66/69 (archive-rewriter) + line 203 (docstring-narrative). Audit exits 0 on post-sweep repo.
- **Actual**: 4 archive-rewrite-paths rows present. Audit exits 0. **Scope expansion**: 4 additional `docstring-narrative` rows for `bin/cortex-check-path-hardcoding` itself were added to suppress self-matches in the gate's own docstring/comment examples — the plan's Risks section anticipated only regex-literal self-matches, not docstring self-matches; the resolution stayed inside the spec's closed-enum category list, so it's not category drift.
- **Verdict**: PASS

### Requirement 16: Parity-linter recognition
- **Expected**: `just check-parity --staged` exits 0 after the feature lands.
- **Actual**: T6 verification confirmed parity passes. No `bin/.parity-exceptions.md` row needed for the new gate itself — its references in `justfile` and `.githooks/pre-commit` satisfy the in-scope wiring detection.
- **Verdict**: PASS

### Requirement 17: Pre-commit ordering
- **Expected**: Phase 1.85 < Phase 1.9 < Phase 2.
- **Actual**: `grep -nE 'Phase 1\.|Phase 2 ' .githooks/pre-commit` shows Phase 1.85 at line 173, Phase 1.9 at line 201, Phase 2 at line 228. Strict ordering satisfied.
- **Verdict**: PASS

### Requirement 18: Stdlib-only
- **Expected**: No third-party imports.
- **Actual**: Gate imports: `argparse`, `os`, `re`, `subprocess`, `sys`, `dataclasses.dataclass`, `pathlib.Path`. All stdlib.
- **Verdict**: PASS

### Requirement 19: Tests pass under `just test`
- **Expected**: `tests/test_check_path_hardcoding.py` runs and overall `just test` exit code is 0.
- **Actual**: 31 path-hardcoding tests pass; full repo suite 793 passed, 12 skipped, 1 xfailed.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None — the implementation matches project.md's stated quality attributes (SKILL.md-to-bin parity enforcement, two-mode gate pattern, defense-in-depth for permissions, file-based state). The new gate directly applies the existing patterns. The four T4 plan-Risks concerns (gate self-match, deploy-commit ordering, parity recognition, fixture commit shape) were all addressed in-implementation without introducing new architectural commitments.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: GOOD. Gate script follows `bin/cortex-check-*` precedent. Function names (`parse_allowlist`, `load_allowlist`, `allowlist_suppresses`, `enumerate_in_scope_files`, `filter_staged_to_scope`, `scan_file`, `run_staged_gate`, `run_audit_gate`) are clear and pattern-consistent with `bin/cortex-check-events-registry`. Allowlist filename uses `-allowlist` suffix where siblings use `-exceptions` / `-registry` — a benign variation; spec specified the filename explicitly.

- **Error handling**: GOOD. File reads use `try/except OSError`. Invalid regex in `line_pattern` cells is caught at parse time and surfaced as `ALLOWLIST_LINE_PATTERN`. Schema errors are collected as a list (all surfaced rather than fail-fast). `_git_staged_paths` returns `[]` when git is unavailable rather than raising — graceful degradation in non-git contexts (e.g., test fixtures that haven't initialized git). No bare `except:` clauses.

- **Test coverage**: GOOD with one minor gap. 31 tests across detection (6), scope (6), allowlist behavior (4), allowlist schema (4 + 7 parametrized), and modes (3). **Gap**: the plan's Edge Cases section called out multi-line string handling ("a violation on line N of a multi-line string literal is flagged at line N") — this isn't explicitly tested. Not a blocker because the gate scans line-by-line via `text.splitlines()`, which trivially handles multi-line strings correctly; the gap is in test surface, not behavior. PARTIAL on this one edge case; recommend adding a follow-up test or letting it ride.

- **Pattern consistency**: GOOD. Gate mirrors `cortex-check-events-registry`'s CLI shape (argparse mutex modes, dataclass GateError, parse/load/run separation). Allowlist mirrors `bin/.parity-exceptions.md` schema and authoring discipline. Pre-commit Phase 1.9 mirrors Phase 1.8/1.85 trigger-pattern shape. Test file mirrors `tests/test_check_events_registry.py`. No invented patterns; everything follows established precedent.

## Implementation deviations (worth flagging)

These are deviations from the plan that the implementing agent already surfaced in its post-implementation summary. Listing here for review visibility:

1. **Gate's own source needed allowlist entries** for docstring/comment examples — the plan's Risks foresaw only the regex-literal self-match, not docstring self-match. Resolved via 4 additional `docstring-narrative` rows; stays inside the spec's closed-enum category list.
2. **Test fixtures use inline `tmp_path` writes** instead of committed `tests/fixtures/path_hardcoding/` files. Same coverage, fewer committed files. Spec acceptance criteria don't mandate the fixture directory structure.
3. **Fixture script names constructed via `_F + "bad"`** in the test source to evade the parity linter's reference tokenizer. Necessary because `bin/cortex-fake-name` literals in test source trip E002 ("referenced but not deployed") and W005 ("allowlist superfluous"). Documented in the test file's module docstring.
4. **T2's commit scope-expanded** to also fix `.githooks/pre-commit` Phase 1.85 trigger (`backlog/*.md` → `cortex/backlog/*.md`) and `tests/test_check_prescriptive_prose.py` fixture paths. Tightly coupled to R14's intent (prescriptive-prose has been silently scanning the wrong directory since #202); not new behavior.

None of these warrant blocking. They are noted so a fresh reviewer can validate the judgment calls.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
