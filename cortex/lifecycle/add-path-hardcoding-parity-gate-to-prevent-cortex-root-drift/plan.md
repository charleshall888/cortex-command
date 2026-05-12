# Plan: add-path-hardcoding-parity-gate-to-prevent-cortex-root-drift

## Overview

Cleanup-then-deploy ordering: refactor the two empirically-surfaced pre-relocation drift sites first (`daytime_pipeline.py` + `cortex-check-prescriptive-prose`), then deploy the new gate (`bin/cortex-check-path-hardcoding`) plus its allowlist and pre-commit wiring as a single commit. This ordering is load-bearing — the gate's first activation runs against its own commit's staged tree, so any pre-existing drift must already be cleaned (or allowlisted) before deployment lands. The gate is a regex scanner, stdlib-only, mirroring the `bin/cortex-check-events-registry` two-mode (`--staged` / `--audit`) precedent and the `bin/.parity-exceptions.md` allowlist authoring discipline.

## Outline

### Phase 1: Cleanup (tasks: 1, 2)
**Goal**: Eliminate the two pre-existing drift sites empirically surfaced by the spec, so the post-cleanup tree is internally clean before the gate activates.
**Checkpoint**: `grep -nE '"lifecycle/' cortex_command/overnight/daytime_pipeline.py` returns zero matches; `grep -nE '"cortex/backlog/\*\.md"' bin/cortex-check-prescriptive-prose` returns ≥1 match.

### Phase 2: Gate deployment (tasks: 3, 4, 5, 6)
**Goal**: Land the gate, its allowlist, pre-commit wiring, justfile recipes, and the test suite; then verify the integrated system on the whole-repo audit.
**Checkpoint**: `just check-path-hardcoding-audit` exits 0; `just check-parity --staged` exits 0; `just test` exits 0.

## Tasks

### Task 1: Refactor daytime_pipeline.py path literals
- **Files**: `cortex_command/overnight/daytime_pipeline.py`
- **What**: Replace 7 instances of `cwd / "cortex" / f"lifecycle/{feature}/X"` style with `cwd / Path("cortex/lifecycle") / feature / "X"` style so each literal is self-contained and no bare-prefix `"lifecycle/..."` segment remains.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Affected lines: 220, 223, 224, 225, 226, 243, 391. Current shapes include `cwd / "cortex" / f"lifecycle/{feature}/plan.md"`, `cwd / "cortex" / f"lifecycle/{feature}/daytime-state.json"`, `cwd / "cortex" / f"lifecycle/{feature}/events.log"`, `cwd / "cortex" / f"lifecycle/{feature}"`, `cwd / "cortex" / f"lifecycle/{feature}/pipeline-events.log"`, `(cwd / "cortex" / f"lifecycle/{feature}/deferred")`, `cwd / "cortex" / f"lifecycle/{feature}/deferred"`. Use canonical-anchor form: `cwd / Path("cortex/lifecycle") / feature / "plan.md"`, etc. `Path` is already imported in this module — verify the import is present before editing; if not, add a `from pathlib import Path` import to the module's existing imports. Resolved path output must be byte-identical to the pre-refactor result; this is a stylistic refactor, not a semantic change.
- **Verification**: `grep -cE '"lifecycle/' cortex_command/overnight/daytime_pipeline.py` returns 0 — pass if count is 0.
- **Status**: [x] completed

### Task 2: Fix prescriptive-prose backlog glob
- **Files**: `bin/cortex-check-prescriptive-prose`
- **What**: Update the stale `"backlog/*.md"` glob at line 43 (inside `SCAN_GLOBS`) to `"cortex/backlog/*.md"` so the prescriptive-prose gate scans the post-#202 backlog directory rather than the (now-empty) pre-relocation path. Also update the matching docstring example at line 20 referencing `backlog/195-*.md` to `cortex/backlog/195-*.md` for consistency.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Both changes are inside `bin/cortex-check-prescriptive-prose`. SCAN_GLOBS is a tuple near the top of the file. The docstring example is in the module's leading comment. No other call sites reference the old glob path.
- **Verification**: `grep -cE '"backlog/\*\.md"' bin/cortex-check-prescriptive-prose` returns 0 AND `grep -cE '"cortex/backlog/\*\.md"' bin/cortex-check-prescriptive-prose` returns ≥ 1.
- **Status**: [x] completed

### Task 3: Allowlist file with schema and initial entries
- **Files**: `bin/.path-hardcoding-allowlist.md`
- **What**: Create the allowlist markdown file with a leading prose section (purpose, fail-open posture, schema description, closed-enum category list, forbidden-literal block, and authoring guidance), then the 6-column markdown table seeded with rows for the legitimate `bin/cortex-archive-rewrite-paths` violations.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Mirror `bin/.parity-exceptions.md`'s shape and tone. Table columns: `file | line_pattern | category | rationale | lifecycle_id | added_date`. Closed-enum categories: `archive-rewriter`, `docstring-narrative`, `migration-script`. Rationale: ≥30 chars after trim; reject case-insensitive substrings `internal`, `misc`, `tbd`, `n/a`, `pending`, `temporary`. `line_pattern` is a regex (or exact substring) matched against the offending line — document that authors who want literal-match should escape regex metacharacters. Initial seed rows (4 total): `bin/cortex-archive-rewrite-paths` line 65 (`Path("lifecycle") / "archive"` — `archive-rewriter`), line 66 (`Path("lifecycle") / "sessions"` — `archive-rewriter`), line 69 (`Path("research") / "archive"` — `archive-rewriter`), line 203 (`"lifecycle/sessions/, retros/). ..."` — `docstring-narrative`). `lifecycle_id`: `203`. `added_date`: `2026-05-12`.
- **Verification**: `test -f bin/.path-hardcoding-allowlist.md` exits 0 AND `grep -cE '\| `archive-rewriter` \|' bin/.path-hardcoding-allowlist.md` ≥ 3 AND `grep -cE '\| `docstring-narrative` \|' bin/.path-hardcoding-allowlist.md` ≥ 1.
- **Status**: [x] completed

### Task 4: Gate script with three modes + pre-commit and justfile wiring
- **Files**: `bin/cortex-check-path-hardcoding`, `.githooks/pre-commit`, `justfile`
- **What**: Build the regex-based gate script (`bin/cortex-check-path-hardcoding`) supporting `--staged`, `--audit`, and `--root <path>` modes, with scan-scope walker including `cortex_command/**/*.py`, `bin/cortex-*`, `hooks/cortex-*`, `claude/hooks/cortex-*` and excluding `**/tests/**` at any depth. Mark the script executable (`chmod +x`). Wire the gate into the justfile (recipes `check-path-hardcoding *args` and `check-path-hardcoding-audit`, placed near the existing parity recipes around line 343–361). Add Phase 1.9 to `.githooks/pre-commit` between the prescriptive-prose Phase 1.85 and the short-circuit Phase 2, with trigger pattern matching staged paths under `cortex_command/**/*.py`, `bin/cortex-*`, `hooks/cortex-*`, `claude/hooks/cortex-*`, or the allowlist file `bin/.path-hardcoding-allowlist.md`.
- **Depends on**: [1, 2, 3]
- **Complexity**: complex
- **Context**: Mirror `bin/cortex-check-events-registry`'s CLI shape (argparse with mutually exclusive `--staged`/`--audit` mode flags and an optional `--root <path>` override). Stdlib-only — argparse, dataclasses, os, re, subprocess, sys, pathlib. Include the `cortex-log-invocation` shim line in the first 50 lines exactly as written in sibling scripts (canonical form at `bin/cortex-check-events-registry` line 27 — copy verbatim, do not paraphrase). Detection regex patterns are constructed via string concatenation so the gate's own source never contains a contiguous `"lifecycle/`-shape literal (avoids self-match on scan). Define a `_PREFIXES` tuple constant holding the four prefix names, then build two `re.compile`'d patterns at module scope — one for the slash-prefix form (quote + prefix + slash) and one for the bare-literal form inside `Path(...)` or `os.path.join(...)` calls. Compose the prefix alternation via `"|".join(_PREFIXES)` so the literal `"lifecycle/"` substring never appears as source text. Allowlist parser mirrors the events-registry parser: read the markdown table after the header separator row, parse each row's six cells, validate the category enum and the rationale length + forbidden-literal block, return a list of `AllowlistRow` dataclass instances. Fail-open on missing allowlist file (matches `bin/.parity-exceptions.md` precedent). Scan-scope walker: enumerate files under the four scan roots, exclude any path containing a `tests/` segment at any depth, scan only `*.py` for `cortex_command/` and any file matching `cortex-*` for the bin/hooks roots. `--staged` mode filters via `git diff --cached --name-only --diff-filter=ACMR` intersected with the scan-scope walker output. Output format: `path:line: PH001 bare-prefix path literal — replace with Path("cortex/<prefix>") or allowlist if intentional`. Stderr writes diagnostics; stdout is empty on pass. Pre-commit Phase 1.9 follows the existing phase template: read trigger pattern from a `while IFS= read -r f` loop with `case` statement, set a `path_hardcoding_triggered` flag, then `if ! just check-path-hardcoding` block matching Phase 1.8's shape. Justfile recipes follow the established two-mode pattern: `check-path-hardcoding *args: bin/cortex-check-path-hardcoding --staged {{args}}` and `check-path-hardcoding-audit: bin/cortex-check-path-hardcoding --audit`. The dual-source plugin mirror (`plugins/cortex-core/bin/cortex-check-path-hardcoding`) is generated by `just build-plugin`; the implementer must run `just build-plugin` after writing the script and stage the generated mirror file (otherwise `.githooks/pre-commit` Phase 4's drift loop fails the commit with a clear "stage the regenerated plugin files" diagnostic).
- **Verification**: `test -x bin/cortex-check-path-hardcoding` exits 0 AND `bin/cortex-check-path-hardcoding --help` exits 0 AND `bin/cortex-check-path-hardcoding --audit` exits 0 against the cleaned + allowlisted tree AND `grep -nE 'Phase 1\.9' .githooks/pre-commit` returns ≥1 match AND `just --list 2>&1 | grep -cE 'check-path-hardcoding(-audit)?$'` returns 2.
- **Status**: [x] completed

### Task 5: Test suite with fixtures
- **Files**: `tests/test_check_path_hardcoding.py`, `tests/fixtures/path_hardcoding/.path-hardcoding-allowlist.md`, `tests/fixtures/path_hardcoding/violation_slash.py`, `tests/fixtures/path_hardcoding/violation_bare.py`, `tests/fixtures/path_hardcoding/cortex_command/init/tests/test_fixture_excluded.py`
- **What**: Unit + integration tests covering every spec requirement. Tests exercise the gate via subprocess invocation with `--root <fixture-dir>` so each test uses a controlled tree. Fixtures intentionally embed violation strings (allowed because they live under `tests/`, which is out of production scan scope).
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: Mirror `tests/test_check_events_registry.py` and `tests/test_check_parity.py` structure (pytest, subprocess-based fixtures, tmp_path-style isolation where needed). Test coverage targets:
  - **Detection** — slash-prefix pattern matches (`"lifecycle/x"`, `f"backlog/{x}"`, `Path("research/y")`, `os.path.join("requirements", "z")`); bare-literal pattern matches (`Path("lifecycle")`, `os.path.join("backlog", "x")`).
  - **Scope inclusion** — fixtures placed under each of `cortex_command/`, `bin/cortex-*`, `hooks/cortex-*`, `claude/hooks/cortex-*` are all flagged.
  - **Scope exclusion** — fixture at `tests/fixtures/path_hardcoding/cortex_command/init/tests/test_fixture_excluded.py` is NOT flagged even though it contains a violation (verifies `**/tests/**` exclusion).
  - **Allowlist schema** — unit tests for the parser: unknown category rejected, rationale <30 chars rejected, each forbidden literal (`internal`, `misc`, `tbd`, `n/a`, `pending`, `temporary`) rejected case-insensitive, valid row accepted.
  - **Allowlist suppression** — a violation matched by an allowlist row produces exit 0; the same violation without the matching row produces non-zero.
  - **Fail-open on missing allowlist** — at test time, rename the fixture allowlist file to a temp sibling (e.g., via `tmp_path` copy of the fixture tree without the allowlist), invoke the gate against that root, and assert it runs in strict mode (exits 0 with zero violations present; exits non-zero with one violation present). Avoids a second top-level fixture directory.
  - **`--staged` mode** — stage a violation file via `git update-index --add --cacheinfo` in a tmp git repo fixture; assert non-zero exit and that an unstaged violation file is NOT scanned.
  - **`--audit` mode** — scans every in-scope file under `--root`.
  - **`--root <path>` resolution** — both relative and absolute paths resolve correctly via `Path(...).resolve()`.
  - **Line-number reporting** — a violation on line N of a multi-line string is reported at line N.
  - **Deletion handling** — `--staged` with a `D` filter (deleted file) does not scan the deleted path.
  - **Empty staged set** — `--staged` with no in-scope staged files exits 0 immediately.
  Each test invokes `subprocess.run([str(REPO_ROOT / "bin/cortex-check-path-hardcoding"), <mode>, "--root", str(fixture_dir)], capture_output=True, text=True)` and asserts on `returncode`, `stdout`, `stderr`. Resolve `REPO_ROOT` via the same `_repo_root()` helper sibling test files use (`Path(__file__).resolve().parents[1]`). Fixture files for the gate test are committed (not generated at test time) because they contain the bare-prefix violation strings that the gate is designed to flag — generating them at test time would mean the test file itself contains those strings, which is fine under tests/ exclusion but slightly cleaner to keep as committed fixtures.
- **Verification**: `just test 2>&1 | grep -E 'test_check_path_hardcoding'` returns the test file's results AND `just test` overall exit code is 0.
- **Status**: [ ] pending

### Task 6: Whole-repo audit verification
- **Files**: (no files modified — verification-only task)
- **What**: Run the integrated audit pass against the whole repo after Phase 1 + Phase 2 land: full-repo `--audit` of the new gate must report zero violations on the cleaned + allowlisted tree, the existing parity linter must continue to pass (the new gate recognized as wired through `justfile` + `.githooks/pre-commit` in-scope references), and the test suite must remain green.
- **Depends on**: [4, 5]
- **Complexity**: simple
- **Context**: This task surfaces any wiring-recognition gap or allowlist miss that the per-task verifications didn't catch in isolation. If `just check-parity --staged` flags the new gate as W003 (orphan), inspect `bin/cortex-check-parity`'s wiring-detection logic — most likely the justfile recipe + pre-commit reference satisfy the existing in-scope scan, but if not, add a `bin/.parity-exceptions.md` row with category `maintainer-only-tool` and a ≥30-char rationale citing #203's lifecycle.
- **Verification**: `just check-path-hardcoding-audit && just check-parity --staged && just test` — pass if all three commands exit 0.
- **Status**: [ ] pending

## Risks

- **Gate's own source self-match**: The gate's regex patterns reference the four prefix names. Task 4 specifies string-concatenation construction of the regex literals (e.g., `re.compile(r'["\']\\s*(?:' + "|".join(_PREFIXES) + r')/')`) so the gate's source text never contains a contiguous `"lifecycle/` substring that would self-match on scan. If the implementer writes the regex as a single string literal, the gate flags itself on its own commit. Fallback: allowlist `bin/cortex-check-path-hardcoding` itself with a new `gate-source` category — but the string-concatenation form is cleaner and avoids extending the closed-enum category list.
- **Pre-commit ordering on the deploy commit**: Phase 1.9 activates on the same commit that introduces it (git reads the staged `.githooks/pre-commit`). Task 4 lands the gate, its wiring, the allowlist, AND the (already-clean) cleanup state from Tasks 1–2 in a tree the gate scans against. If Task 1 or Task 2 is incomplete at Task 4's commit time, Task 4's commit fails — by design.
- **Parity-linter wiring recognition**: `bin/cortex-check-parity` scans for in-scope references to `bin/cortex-*` scripts. The new gate's references appear in `justfile` and `.githooks/pre-commit` — both are in-scope per the existing parity-trigger pattern. Task 6's verification confirms this; if it surfaces W003, the fix is a `bin/.parity-exceptions.md` row, not a re-wiring.
- **Test-fixture commit shape**: `tests/fixtures/path_hardcoding/*` files intentionally contain bare-prefix violations. They live under `tests/` (excluded from production scan) so the gate ignores them, but a future contributor might accidentally move them into a production scan root. Naming the directory `tests/fixtures/path_hardcoding/` and keeping all fixture content under it makes the intent visually self-documenting; no special enforcement needed beyond the scan exclusion.
- **`**/tests/**` exclusion depth**: The exclusion must match `cortex_command/init/tests/` (a tests/ subtree under a production source root), not just the top-level `tests/`. Task 4's scan-scope walker must implement this as "any path segment equal to `tests`" rather than "top-level prefix `tests/`". Task 5's fixture at `tests/fixtures/path_hardcoding/cortex_command/init/tests/test_fixture_excluded.py` verifies this empirically.

## Acceptance

After all six tasks land, the post-commit repo state satisfies three integrated checks: (1) `just check-path-hardcoding-audit` exits 0 against the whole repo, confirming no bare-prefix `lifecycle/`/`backlog/`/`research/`/`requirements/` literals remain outside the documented allowlist; (2) `just check-parity --staged` exits 0, confirming the new gate is recognized as wired without a parity-exceptions row; (3) any future commit that introduces a bare-prefix path literal in a scanned source tree fails at pre-commit with a `PH001` diagnostic pointing at the file and line — verified by spot-checking with a temporary throwaway commit before this feature is closed.
