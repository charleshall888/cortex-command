# Specification: add-path-hardcoding-parity-gate-to-prevent-cortex-root-drift

## Problem Statement

After #202 relocated lifecycle/, backlog/, research/, and requirements/ under the `cortex/` umbrella, no automated check prevents new Python code from re-introducing bare-prefix path literals (`Path("lifecycle/...")`, `f"backlog/{x}"`, etc.). Existing copy-paste vectors already exist in the codebase (e.g., `cortex_command/overnight/daytime_pipeline.py` constructs `cwd / "cortex" / f"lifecycle/{feature}/..."`, where the bare `f"lifecycle/..."` segment is exactly the literal a contributor might copy without its `cwd / "cortex" /` wrapper). A pre-commit parity gate scanning Python sources for these patterns, with an allowlist for legitimate exceptions, prevents silent regression to the pre-relocation layout. Benefits accrue to every contributor and every overnight session — drift caught at commit time is cheap; drift discovered when a path-dependent feature breaks in production is expensive.

## Phases

- **Phase 1: Gate implementation** — Build `bin/cortex-check-path-hardcoding`, its allowlist file, and unit/integration tests.
- **Phase 2: Pre-commit wiring + sweep** — Wire the gate into `.githooks/pre-commit` and `justfile`, then refactor the two empirically-surfaced drift sites (`daytime_pipeline.py`, `cortex-check-prescriptive-prose:43`) and seed the allowlist.

## Requirements

1. **Gate script exists and is executable**: `bin/cortex-check-path-hardcoding` exists, is executable (`test -x bin/cortex-check-path-hardcoding` exits 0), and supports three modes: `--staged`, `--audit`, and `--root <path>`. Acceptance: `bin/cortex-check-path-hardcoding --help` exits 0 and stdout contains all three flag names. **Phase**: Phase 1.

2. **Detection patterns — slash-prefix literals**: The gate flags any string-literal occurrence matching the regex `["'](lifecycle|backlog|research|requirements)/` in scanned files. Acceptance: a fixture file containing a bare-prefix-slash literal (e.g. a Python source whose body assigns `x` to a string starting with the slash-prefix form) placed under `tests/fixtures/path_hardcoding/violation_slash.py` and scanned via `bin/cortex-check-path-hardcoding --root tests/fixtures/path_hardcoding --audit` exits non-zero and stderr names the file + line. **Phase**: Phase 1.

3. **Detection patterns — bare-literal Path/os.path.join args**: The gate flags any source occurrence matching the regex `\b(Path|os\.path\.join)\(\s*["'](lifecycle|backlog|research|requirements)["']`. Acceptance: a fixture file containing `Path("lifecycle") / "x"` placed under `tests/fixtures/path_hardcoding/violation_bare.py` and scanned via `--audit` exits non-zero and stderr names the file + line. **Phase**: Phase 1.

4. **Scan-scope inclusion**: The gate scans Python files (`*.py`) under `cortex_command/`, plus the executable scripts `bin/cortex-*`, `hooks/cortex-*`, and `claude/hooks/cortex-*`. Acceptance: `bin/cortex-check-path-hardcoding --audit` reads files from all four scan roots (verified by running against a tree where each root has a violation fixture; all four are flagged). **Phase**: Phase 1.

5. **Scan-scope exclusion (tests)**: The gate excludes any `tests/` subtree at any depth (matches both top-level `tests/` and `cortex_command/**/tests/`). Acceptance: a fixture violation placed under `cortex_command/init/tests/test_fixture_excluded.py` does NOT cause `--audit` to exit non-zero (verified via fixture test with the file present but allowlist empty). **Phase**: Phase 1.

6. **Allowlist file and schema**: `bin/.path-hardcoding-allowlist.md` exists as a markdown file with a 6-column table: `file | line_pattern | category | rationale | lifecycle_id | added_date`. The `category` field is constrained to a closed enum: `archive-rewriter`, `docstring-narrative`, `migration-script`. The `rationale` field requires ≥30 characters after trim and rejects the forbidden-literal substrings (case-insensitive): `internal`, `misc`, `tbd`, `n/a`, `pending`, `temporary`. Acceptance: a unit test in `tests/test_check_path_hardcoding.py` exercises each schema constraint (unknown category → reject; rationale <30 chars → reject; forbidden literal → reject; valid row → accept) and passes. **Phase**: Phase 1.

7. **Allowlist suppresses matching violations**: A violation whose `(file, line_pattern)` pair matches a row in the allowlist does not cause the gate to fail. `line_pattern` is matched as a regex against the offending line. Acceptance: a fixture violation in `tests/fixtures/path_hardcoding/violation_slash.py` PLUS a corresponding allowlist row at `tests/fixtures/path_hardcoding/.path-hardcoding-allowlist.md` causes `--audit --root tests/fixtures/path_hardcoding` to exit 0. **Phase**: Phase 1.

8. **Fail-open on missing allowlist**: If `bin/.path-hardcoding-allowlist.md` is absent at the resolved scan root, the gate runs with zero allowlisted exceptions (strict mode) — it does NOT fail-closed. Acceptance: `bin/cortex-check-path-hardcoding --audit --root tests/fixtures/path_hardcoding_no_allowlist` (a fixture root with no allowlist file and no violations) exits 0; the same fixture root with one violation file exits non-zero. **Phase**: Phase 1.

9. **Two-mode operation — `--staged`**: With `--staged`, the gate restricts scanning to files in `git diff --cached --name-only --diff-filter=ACMR` whose paths fall under the scan-scope roots. Acceptance: a unit test stages a violation file via `git update-index --add --cacheinfo`, runs the gate in `--staged` mode, and asserts non-zero exit. **Phase**: Phase 1.

10. **Two-mode operation — `--audit`**: With `--audit`, the gate scans every file matching the scan-scope rules under the repo root (or `--root <path>` when given). Acceptance: `just check-path-hardcoding-audit` exits 0 on the current repo after the Phase 2 sweep lands (i.e., once `daytime_pipeline.py` is refactored, `cortex-check-prescriptive-prose:43` is fixed, and the initial allowlist seeded). **Phase**: Phase 2.

11. **Pre-commit wiring**: `.githooks/pre-commit` invokes the gate as Phase 1.9 (between prescriptive-prose Phase 1.85 and short-circuit Phase 2). The trigger pattern matches any staged path under `cortex_command/**/*.py`, `bin/cortex-*`, `hooks/cortex-*`, `claude/hooks/cortex-*`, or `bin/.path-hardcoding-allowlist.md`. Acceptance: `grep -F 'check-path-hardcoding' .githooks/pre-commit` returns ≥1 match AND `grep -nE 'Phase 1\.9' .githooks/pre-commit` returns ≥1 match. **Phase**: Phase 2.

12. **Justfile recipes**: `justfile` defines `check-path-hardcoding *args` (invokes `bin/cortex-check-path-hardcoding --staged {{args}}`) and `check-path-hardcoding-audit` (invokes `bin/cortex-check-path-hardcoding --audit`), placed near the existing parity-recipe block (around line 343–361). Acceptance: `just --list 2>&1 | grep -E 'check-path-hardcoding(-audit)?$'` returns 2 lines. **Phase**: Phase 2.

13. **Drift cleanup — `daytime_pipeline.py`**: Lines 220, 223, 224, 225, 226, 243, and 391 of `cortex_command/overnight/daytime_pipeline.py` are refactored from `cwd / "cortex" / f"lifecycle/{feature}/X"` style to `cwd / Path("cortex/lifecycle") / feature / "X"` style, so each literal is self-contained and the bare `"lifecycle/..."` prefix is eliminated. Acceptance: `grep -nE '"lifecycle/' cortex_command/overnight/daytime_pipeline.py` returns zero matches. **Phase**: Phase 2.

14. **#202 straggler fix — prescriptive-prose glob**: `bin/cortex-check-prescriptive-prose:43` is updated from `"backlog/*.md"` to `"cortex/backlog/*.md"`. Acceptance: `grep -nE '"backlog/\*\.md"' bin/cortex-check-prescriptive-prose` returns zero matches AND `grep -nE '"cortex/backlog/\*\.md"' bin/cortex-check-prescriptive-prose` returns ≥1 match. **Phase**: Phase 2.

15. **Initial allowlist entries**: `bin/.path-hardcoding-allowlist.md` ships with rows covering the legitimate `bin/cortex-archive-rewrite-paths` cases (lines 65, 66, 69, 203) under categories `archive-rewriter` (lines 65/66/69) and `docstring-narrative` (line 203). Acceptance: `bin/cortex-check-path-hardcoding --audit` exits 0 on the post-sweep repo. **Phase**: Phase 2.

16. **Parity-linter recognition**: After landing, `bin/cortex-check-path-hardcoding` is recognized as wired by `bin/cortex-check-parity` (in-scope references in `justfile` + `.githooks/pre-commit` satisfy the existing wiring-detection logic without needing a `bin/.parity-exceptions.md` row). Acceptance: `just check-parity --staged` exits 0 on the PR's staged tree. **Phase**: Phase 2.

17. **Pre-commit ordering**: The new Phase 1.9 runs AFTER Phase 1.85 (prescriptive-prose) and BEFORE Phase 2 (short-circuit decision). Acceptance: in `.githooks/pre-commit`, the line numbers satisfy `line("Phase 1.85") < line("Phase 1.9") < line("Phase 2 —")`. **Phase**: Phase 2.

18. **Stdlib-only implementation**: `bin/cortex-check-path-hardcoding` uses only the Python standard library — no third-party imports. Acceptance: `grep -nE '^(import|from) ' bin/cortex-check-path-hardcoding | grep -vE '^.*: (import|from) (argparse|os|re|subprocess|sys|pathlib|dataclasses|datetime)' ` returns zero matches (i.e., every import is from the stdlib whitelist of modules used by sibling gates). **Phase**: Phase 1.

19. **Tests pass under `just test`**: `tests/test_check_path_hardcoding.py` exists and all its tests pass. Acceptance: `just test 2>&1 | grep -E 'test_check_path_hardcoding'` returns the test file's results and overall `just test` exit code is 0. **Phase**: Phase 1.

## Non-Requirements

- **Does NOT scan markdown files** (`*.md`). Skill prose, docstrings-in-docs, and other narrative mentions of `lifecycle/` / `backlog/` / etc. are intentionally out of scope. Drift in those venues is narrative, not code-path; the prescriptive-prose gate already covers skill prose discipline.
- **Does NOT enforce use of the upward-walking helper from #201**. The gate flags bare-prefix literals; it has no opinion on whether the replacement uses #201's helper or `Path("cortex/lifecycle")` directly. Coupling to #201's API surface would be fragile and is not required for drift prevention.
- **Does NOT use AST-based scanning**. Regex scan on source text is sufficient for realistic regression vectors (slash-prefix literals in any context). AST precision is not worth the LOC and dependency cost; false-positive surface is handled via allowlist.
- **Does NOT scan `tests/` subtrees**. Tests legitimately embed violation strings as fixtures; allowlisting test fixtures would balloon the allowlist with no production-drift protection gain.
- **Does NOT migrate or update any existing `bin/.parity-exceptions.md` rows**. The new allowlist is a separate file with a separate schema. No shared state with sibling gates.

## Edge Cases

- **Empty allowlist**: gate runs in strict mode (every match is a violation). Exit 0 only when zero violations are found.
- **Allowlist row with regex metacharacters in `line_pattern`**: the `line_pattern` cell is treated as a regex. Unescaped `.` matches any character; this is documented in the allowlist file's header comment. Authors who want a literal-match should escape regex metacharacters or use `re.escape`-style writing.
- **Violation on a multi-line string**: the gate scans line-by-line. A bare-prefix appearing on line N of a multi-line string literal is flagged at line N (not the line where the triple-quote opens). This matches sibling-gate behavior (`cortex-check-parity` line-numbers the same way).
- **File renamed/deleted in staged diff**: `--staged` mode filters via `git diff --cached --name-only --diff-filter=ACMR` (Added/Copied/Modified/Renamed). Deletions (`D`) are not scanned — a deleted file cannot reintroduce drift.
- **Concurrent edits to the allowlist**: the allowlist is a flat markdown file with no locking. Concurrent contributor edits resolve via normal git-merge mechanics; row ordering is not load-bearing (gate iterates the table as a set).
- **`--root <path>` with relative vs absolute**: the gate resolves `--root` via `Path(...).resolve()` so both forms work. This matches `cortex-check-events-registry`'s `--root` behavior.
- **Allowlist row pointing to a file outside scan scope**: such rows are valid but inert — they suppress nothing because the file is never scanned. The gate does not warn about inert rows in v1; an `--audit`-side hygiene check is a possible follow-up but not in scope.
- **Pre-commit triggered on allowlist-only change**: editing `bin/.path-hardcoding-allowlist.md` without changing scan-target files still triggers the gate (the trigger pattern includes the allowlist file). This is intentional: an allowlist edit that breaks schema is itself a regression worth catching at commit time.
- **`--staged` when there are no staged files in scan scope**: gate exits 0 immediately (no violations possible).

## Changes to Existing Behavior

- **ADDED**: `.githooks/pre-commit` gains Phase 1.9 — a fourth gate (after parity, shim, telemetry-call, events-registry, prescriptive-prose) that may block commits. Authors will see a new failure mode if they introduce bare-prefix path literals.
- **MODIFIED**: `cortex_command/overnight/daytime_pipeline.py` line block (220–391) — path construction style changes from `cwd / "cortex" / f"lifecycle/{x}/y"` to `cwd / Path("cortex/lifecycle") / x / "y"`. Functional behavior is byte-identical: same resolved paths, same `.mkdir`/`.read`/`.write` outcomes.
- **MODIFIED**: `bin/cortex-check-prescriptive-prose:43` glob from `"backlog/*.md"` to `"cortex/backlog/*.md"`. Restores the gate's scan of backlog ticket bodies (silently broken since #202 relocated `backlog/` to `cortex/backlog/`).
- **ADDED**: `just check-path-hardcoding` and `just check-path-hardcoding-audit` recipes available to contributors.

## Technical Constraints

- **Pattern fidelity to project.md two-mode gate precedent**: project.md mandates that pre-commit critical-path gates pair `--staged` with `--audit`; #203 inherits this. The `--staged` mode must not perform any time-based or repo-wide check that doesn't directly key off staged paths.
- **Fail-open posture matches `bin/.parity-exceptions.md` precedent**: per project.md, fail-mode is a per-gate decision; this gate's allowlist is opt-in for exceptions (not a registry of expected entries), so fail-open is the correct posture. Document the choice in the gate's docstring.
- **Stdlib-only**: matches sibling gates (`cortex-check-parity`, `cortex-check-events-registry`, `cortex-check-prescriptive-prose`). No `uv`/`pip`-installed dependencies.
- **`cortex-log-invocation` shim**: `bin/cortex-*` scripts ship with the `cortex-log-invocation` shim in their first 50 lines (enforced by `bin/cortex-invocation-report --check-shims` at pre-commit Phase 1.6). The new script must include this shim.
- **Plugin mirror via build**: `bin/cortex-check-path-hardcoding` is a top-level source that the dual-source build mirror replicates into `plugins/cortex-core/bin/`. Verified by the existing `.githooks/pre-commit` Phase 2–4 drift loop; nothing additional needed in spec scope.

## Open Decisions

None. All design decisions were resolvable at spec time using research findings and existing project precedents.
