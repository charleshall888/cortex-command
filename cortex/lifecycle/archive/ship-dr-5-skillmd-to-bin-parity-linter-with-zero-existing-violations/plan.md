# Plan: ship-dr-5-skillmd-to-bin-parity-linter-with-zero-existing-violations

## Overview

Build the linter as a single stdlib-only Python file with inline self-test fixtures, ship the day-one allowlist, exercise correctness via a pytest fixture matrix, retrofit the existing in-scope violations so the first run is green, then wire enforcement via a justfile recipe and a new pre-commit Phase 1.5. Retrofits run independently of linter delivery (no compile-time coupling), enabling parallel execution; the R16 dry-run and pre-commit wiring fan in once both halves complete.

## Tasks

### Task 1: Implement the parity linter
- **Files**: `bin/cortex-check-parity` (NEW; executable bit set)
- **What**: Single-file Python 3 stdlib-only CLI that scans in-scope files (R7), classifies `cortex-*` tokens against R5 candidate filter, applies R4 wiring rules, validates the allowlist (R8), emits violations with codes E001/E002/W003/W005 (R9), supports flags `--self-test`, `--json`, `--lenient`, `--staged`, `--print-scan-paths`, `--verbose`, and exits per R10.
- **Sizing note**: Targets ~30-60 min — exceeds the standard 15-min budget. The artifact is a single executable file; splitting (e.g., into "core" + "self-test wrapper") would produce a non-functional partial binary across commits and break the verification surface. The `complex` tier scales the implement-phase turn budget accordingly.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Imports limited to `argparse`, `json`, `os`, `pathlib`, `re`, `subprocess`, `sys`, `typing`, `dataclasses`, `enum` (R2 acceptance grep).
  - Wiring rule (R4): `cortex-foo` is wired if (a) literal `bin/cortex-foo` token present, (b) `` `cortex-foo` `` backtick code span or fenced code block mention, or (c) passing allowlist row. **Open spec question (see "Open Spec Questions" section below)**: R4(b)'s fenced-code-block matching may need tightening to "command-head only" to prevent example transcripts from spuriously wiring orphans. Until resolved, implement the spec verbatim.
  - Candidate filter (R5): regex `cortex-[a-z][a-z0-9-]*` excludes tokens (a) preceded by `hooks/`, `plugins/`, `claude/hooks/`, `.claude/hooks/`, or any `*/hooks/` path; (b) suffixed with `.sh`; (c) in the closed plugin list `{cortex-interactive, cortex-overnight-integration, cortex-pr-review, cortex-ui-extras, cortex-dev-extras, android-dev-extras}` — hardcoded constant; (d) literal self-reference `cortex-check-parity` inside the linter source.
  - **R5(a) operationalization**: "preceded by" means the path qualifier is **contiguous** to the token — implement as regex `(?:hooks/|plugins/|claude/hooks/|\.claude/hooks/|/hooks/)cortex-[a-z][a-z0-9-]*`. Whitespace between qualifier and token does NOT trigger exclusion (narrative prose like "the hooks/ directory contains cortex-foo" is NOT excluded by R5(a) — it falls through to R5(c)/(d) and then the wiring-rule check). Fixture `exclude-hook-path` already covers the contiguous case; no narrative-prose fixture is needed because R5(a) does not match it.
  - **R6 operationalization** ("flat enumeration markdown table"): a markdown table column containing token `cortex-X` is "flat enumeration" iff (i) the column has ≥2 rows where the cell's content (after stripping whitespace and backticks) matches `cortex-[a-z][a-z0-9-]*`, AND (ii) the same file has no narrative-prose mention of `cortex-X` (path-qualified or backtick code span) outside the table. When both hold, the table cell does NOT wire (R6 narrows R4(b)). When (i) fails (cell contains narrative content) OR (ii) fails (narrative mention exists elsewhere in file), R4(b) fires normally and the cell DOES wire. The `invalid-readme-table-only` fixture covers (i)+(ii) holding; add a positive `valid-table-cell-with-narrative` fixture to Task 4 covering the (ii)-fails branch.
  - Scan scope (R7): hardcoded globs `skills/**/*.md`, `CLAUDE.md`, `requirements/**/*.md`, `docs/**/*.md`, `tests/**/*.py`, `tests/**/*.sh`, `hooks/cortex-*.sh`, `claude/hooks/cortex-*.sh`, `justfile`. Plugin-tree mirrors NOT scanned.
  - Allowlist parsing (R8): markdown table at `bin/.parity-exceptions.md` — 5 columns (`script`, `category`, `rationale`, `lifecycle_id`, `added_date`), validation: script regex match, category in closed enum `{maintainer-only-tool, library-internal, deprecated-pending-removal}`, rationale ≥30 chars after trim AND not in forbidden literal set `{internal, misc, tbd, n/a, pending, temporary}` (case-insensitive), date matches `^\d{4}-\d{2}-\d{2}$`. Each malformed row → one E001.
  - W005 "allowlist-superfluous": if a script is allowlisted AND has any wiring signal (R4 a/b) in scope, emit W005.
  - Operates on `os.getcwd()`. Tests/pre-commit invoke from repo root (or fixture root for tests via `cwd=`).
  - `--staged` semantics (R13): deployed set from working-tree `bin/`; referenced set from `git diff --cached --name-only --diff-filter=ACMRD` plus blob contents at the staged version.
  - Self-test (R18): inline fixtures exercise E001 (invalid allowlist row), E002 (drift), W003 (orphan), W005 (allowlist-superfluous), the four R4 valid wiring patterns, and the four R5 exclusion patterns. `--verbose` prints `PASS <case-name>` per case.
  - **R5(c) drift-detection self-test case**: include a `--self-test` case `plugin-list-matches-justfile` that opens `justfile` from the repo root, parses the literal Bash arrays `BUILD_OUTPUT_PLUGINS=(...)` and `HAND_MAINTAINED_PLUGINS=(...)`, asserts the union equals the linter's hardcoded R5(c) constant. On mismatch, fail with a diff message. This makes silent drift between justfile and linter constant a self-test failure rather than a future runtime bug. The check skips gracefully (PASS, no-op) when run from outside a repo (e.g., a fixture cwd) — checked via `Path("justfile").is_file()`.
  - Read `bin/cortex-validate-spec` (post-Task 7 path) only as a stylistic reference for stdlib-only CLI structure — do not copy classification logic.
- **Verification**: `python3 bin/cortex-check-parity --self-test` exits 0 with `self-test passed` in stdout — pass if exit 0; AND `head -1 bin/cortex-check-parity` matches `^#!/usr/bin/env python3$`; AND `grep -E "^(import|from) " bin/cortex-check-parity | grep -vE "^(import|from) (argparse|json|os|pathlib|re|subprocess|sys|typing|dataclasses|enum)" | wc -l` outputs `0`.
- **Status**: [x] complete

### Task 2: Add `check-parity` justfile recipe
- **Files**: `justfile`
- **What**: New recipe `check-parity *args:` with body `python3 bin/cortex-check-parity {{args}}`, placed adjacent to the existing `validate-spec` recipe (currently `justfile:331`).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Mirror the `validate-spec` recipe shape at `justfile:331`. Both R13 pre-commit invocation and ad-hoc developer invocation route through this recipe. After Task 7 lands, `validate-spec` becomes `cortex-validate-spec`; place `check-parity` below it.
- **Verification**: `grep -cE '^check-parity \*args:$' justfile` outputs `1` — pass if count = 1.
- **Status**: [x] complete

### Task 3: Create day-one allowlist file
- **Files**: `bin/.parity-exceptions.md` (NEW)
- **What**: Markdown file with a header explaining the R8 schema, the R15.8 reviewer-guidance line, and exactly one allowlist row for `cortex-archive-sample-select` per R14.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Header: short prose explaining R8 columns and that the linter parses this file at load time. Include the verbatim guidance line from R15.8: "Adding an entry is a small architectural decision. Reviewers: confirm `category` enum is correct and `rationale` is specific (not 'internal' or 'misc' — those literals are linter-rejected). The W005 warning surfaces when an allowlisted script also has a wiring signal in scope; prune those rows."
  - Single row (R14):
    | script | category | rationale | lifecycle_id | added_date |
    | --- | --- | --- | --- | --- |
    | `cortex-archive-sample-select` | `maintainer-only-tool` | Lifecycle archive sampling — invoked manually by the maintainer when archiving a session; no agent flow references it and no wiring path is appropriate today. | `102` | `2026-04-27` |
- **Verification**: `python3 bin/cortex-check-parity --print-scan-paths >/dev/null` exits 0 (file parses cleanly under R8) AND `grep -cF 'cortex-archive-sample-select' bin/.parity-exceptions.md` outputs `1` — pass if both hold.
- **Status**: [x] complete

### Task 4: Pytest harness + valid wiring fixtures
- **Files**: `tests/test_check_parity.py` (NEW), `tests/fixtures/parity/valid-path-qualified/` (NEW dir, ~3 files), `tests/fixtures/parity/valid-code-span/` (NEW dir, ~3 files), `tests/fixtures/parity/valid-fenced-code/` (NEW dir, ~3 files), `tests/fixtures/parity/valid-allowlist/` (NEW dir, ~3 files), `tests/fixtures/parity/valid-table-cell-with-narrative/` (NEW dir, ~3 files — covers R6 boundary: table cell mention DOES wire when narrative mention exists elsewhere in the file)
- **What**: Pytest module that parametrizes over `tests/fixtures/parity/*/` directories. Each fixture is a self-contained mini-repo with a minimal `bin/cortex-foo` shim, an in-scope file (e.g., `skills/example/SKILL.md`) demonstrating the wiring pattern, and optionally `bin/.parity-exceptions.md`. Test asserts exit 0 for `valid-*` and parses `--json` output to confirm zero violations.
- **Sizing note**: File count (~13) exceeds the 5-file budget. Each fixture dir is ≤3 small leaf files (≤20 lines each); total payload is ~200 lines of mechanical scaffolding once the harness pattern is established. Splitting into one task per fixture would produce 11 fixture tasks for a single logical block of work — judged worse for plan ergonomics than the file-count departure.
- **Depends on**: [1, 2]
- **Complexity**: complex
- **Context**:
  - Harness pattern: follow `tests/test_archive_rewrite_paths.py` shape. Locate linter via `REPO_ROOT / "bin" / "cortex-check-parity"`. Invoke with `subprocess.run([sys.executable, str(SCRIPT), "--json"], cwd=str(fixture), capture_output=True, text=True)`.
  - Parametrize with `pytest.mark.parametrize("fixture", sorted(FIXTURES_ROOT.iterdir()), ids=lambda p: p.name)`.
  - Assertion logic keyed on fixture-name prefix: `valid-*` → exit 0, empty JSON array. `invalid-*` → exit 1, JSON contains expected code (Task 5 extends). `exclude-*` → exit 0 (Task 6 extends).
- **Verification**: `uv run pytest tests/test_check_parity.py -k valid -q` exits 0 AND reports `5 passed` — pass if both hold.
- **Status**: [x] complete

### Task 5: Invalid (violation-producing) fixtures
- **Files**: `tests/fixtures/parity/invalid-readme-table-only/` (NEW dir, ~3 files), `tests/fixtures/parity/invalid-drift/` (NEW dir, ~3 files), `tests/fixtures/parity/invalid-allowlist-row/` (NEW dir, ~3 files), `tests/fixtures/parity/invalid-allowlist-superfluous/` (NEW dir, ~3 files)
- **What**: Four fixtures each producing a specific violation code: W003 (orphan via flat README enumeration only — R6), E002 (drift — referenced not deployed), E001 ×6 (six malformed allowlist rows), W005 (allowlist-superfluous).
- **Sizing note**: File count (~12) exceeds the 5-file budget — same rationale as Task 4 (mechanical fixture scaffolding once the Task-4 pattern is established).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - `invalid-readme-table-only`: bin contains `cortex-foo` shim; in-scope file is a flat enumeration markdown table only with no narrative body mention. Linter must emit W003 (orphan) per R6.
  - `invalid-drift`: bin is empty (or contains a different script); in-scope SKILL.md mentions `bin/cortex-foo` (path-qualified). Linter must emit E002.
  - `invalid-allowlist-row`: allowlist file contains 6 malformed rows — empty rationale, bad category (e.g., `experimental`), forbidden rationale literal `internal`, rationale <30 chars, missing date, malformed date `2026/01/01`. Linter emits 6× E001.
  - `invalid-allowlist-superfluous`: allowlist contains valid row for `cortex-foo`; in-scope SKILL.md ALSO has `bin/cortex-foo` path-qualified mention. Linter emits W005.
  - Test harness assertion (already in Task 4): `invalid-*` → exit 1 + JSON contains expected code(s) + expected count.
- **Verification**: `uv run pytest tests/test_check_parity.py -k invalid -q` exits 0 AND reports `4 passed` — pass if both hold.
- **Status**: [x] complete

### Task 6: R5 exclusion fixtures
- **Files**: `tests/fixtures/parity/exclude-hook-suffix/` (NEW dir, ~2 files), `tests/fixtures/parity/exclude-plugin-name/` (NEW dir, ~2 files), `tests/fixtures/parity/exclude-hook-path/` (NEW dir, ~2 files)
- **What**: Three fixtures each containing a `cortex-*`-shaped token that R5 must exclude from candidate evaluation. No `bin/cortex-foo` is deployed in any of them — without R5 each would be E002, with R5 each is clean.
- **Sizing note**: File count (~6) exceeds the 5-file budget by 1 — same rationale as Task 4.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - `exclude-hook-suffix`: SKILL.md mentions `cortex-foo.sh` in a code span (R5(b)).
  - `exclude-plugin-name`: SKILL.md mentions `cortex-pr-review` in a code span (R5(c) — closed plugin list).
  - `exclude-hook-path`: SKILL.md mentions `hooks/cortex-foo` (R5(a) — non-bin path qualifier).
  - Bin/ directory is empty in each fixture (no false positives via path-qualified token matching).
- **Verification**: `uv run pytest tests/test_check_parity.py -k exclude -q` exits 0 AND reports `3 passed` — pass if both hold.
- **Status**: [x] complete

### Task 7: Rename `bin/validate-spec` → `bin/cortex-validate-spec`
- **Files**: `bin/validate-spec` (DELETE), `bin/cortex-validate-spec` (NEW — same contents), `justfile`
- **What**: `git mv bin/validate-spec bin/cortex-validate-spec`; update `justfile:331` from `python3 bin/validate-spec {{args}}` to `python3 bin/cortex-validate-spec {{args}}`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Caller enumeration (in scan scope per R7): `justfile:331` is the only in-scope reference. Out-of-scope references in `research/`, `lifecycle/archive/`, `backlog/`, and the current ticket's `lifecycle/.../research.md` and `spec.md` are intentionally excluded from R7 — the linter does not scan them, so no retrofit is required.
  - Renamed binary newly matches `--include='cortex-*'` in the build-plugin filter; `plugins/cortex-interactive/bin/cortex-validate-spec` is regenerated by `.githooks/pre-commit` Phase 3 on next commit that triggers a build.
- **Verification**: `test -x bin/cortex-validate-spec && ! test -e bin/validate-spec` exits 0 AND `grep -cF 'bin/cortex-validate-spec' justfile` outputs ≥`1` — pass if both hold.
- **Status**: [x] complete

### Task 8: Retrofit `walkthrough.md` (5 occurrences)
- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Replace 5 occurrences of the bare token `git-sync-rebase.sh` with `cortex-git-sync-rebase`. Lines ~564, 610, 611, 612, 614 in current HEAD; locate by content-search rather than line number.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Per R5(b), the `.sh` suffix would silently exclude the token from candidate evaluation; the rename achieves both correctness (matches deployed `bin/cortex-git-sync-rebase`) and discoverability. Use `Edit` with `replace_all=true` on the literal string.
- **Verification**: `grep -c 'git-sync-rebase\.sh' skills/morning-review/references/walkthrough.md` outputs `0` AND `grep -cF 'cortex-git-sync-rebase' skills/morning-review/references/walkthrough.md` ≥ `5` — pass if both hold.
- **Status**: [x] complete

### Task 9: Retrofit `complete.md` (drop dead `~/.local/bin/` failover lines)
- **Files**: `skills/lifecycle/references/complete.md`
- **What**: Remove the `~/.local/bin/generate-backlog-index` failover lines from both fallback chains (current HEAD lines 44 and 68). Retain the canonical `cortex-generate-backlog-index` lines (43 and 67).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Each fallback chain has a canonical-then-stale-failover pair; drop only the stale failover. Verify the canonical line remains intact after each removal.
- **Verification**: `grep -c '~/\.local/bin/generate-backlog-index' skills/lifecycle/references/complete.md` outputs `0` AND `grep -c 'cortex-generate-backlog-index' skills/lifecycle/references/complete.md` ≥ `2` — pass if both hold.
- **Status**: [x] complete

### Task 10: Retrofit `dev/SKILL.md` and `evolve/SKILL.md`
- **Files**: `skills/dev/SKILL.md`, `skills/evolve/SKILL.md`
- **What**: In `dev/SKILL.md` (around line 137), rewrite the parenthetical removing the `~/.local/bin/generate-backlog-index` mention and the stale "do NOT use uv run" guidance. In `evolve/SKILL.md` (around line 54), replace `bin/git-sync-rebase.sh` with `bin/cortex-git-sync-rebase`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Read both files first; the `dev/SKILL.md` rewrite may shorten or omit the parenthetical entirely depending on what survives once the dead references are dropped. Locate the line by content-search, not line number.
- **Verification**: `grep -c '~/\.local/bin' skills/dev/SKILL.md` outputs `0` AND `grep -c 'git-sync-rebase\.sh' skills/evolve/SKILL.md` outputs `0` AND `grep -cF 'bin/cortex-git-sync-rebase' skills/evolve/SKILL.md` ≥ `1` — pass if all three hold.
- **Status**: [x] complete

### Task 11: Retrofit `pipeline.md` and `test_git_sync_rebase.py`
- **Files**: `requirements/pipeline.md`, `tests/test_git_sync_rebase.py`
- **What**: In `pipeline.md` (around line 148), replace `bin/git-sync-rebase.sh` with `bin/cortex-git-sync-rebase`; drop any `~/.local/bin/` deployment annotation. In `test_git_sync_rebase.py`, update body references — likely a `SCRIPT_PATH = REPO_ROOT / "bin" / "git-sync-rebase.sh"` line and any subprocess args — to point at `bin/cortex-git-sync-rebase`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The actual binary already exists as `bin/cortex-git-sync-rebase` (renamed in a prior epic). This task aligns the test file and the requirements doc to match deployed reality. Read `tests/test_git_sync_rebase.py` to enumerate all occurrences before editing.
- **Verification**: `grep -c 'git-sync-rebase\.sh' requirements/pipeline.md` outputs `0` AND `grep -cE "bin/git-sync-rebase\\.sh|'git-sync-rebase\\.sh'" tests/test_git_sync_rebase.py` outputs `0` AND `uv run pytest tests/test_git_sync_rebase.py -q` exits 0 — pass if all three hold.
- **Status**: [x] complete

### Task 12: First-run-green dry-run script (R16, documentary gate)
- **Files**: `tests/test_check_parity_first_run_green.sh` (NEW; executable bit set)
- **What**: Shell script that runs `python3 bin/cortex-check-parity` from repo root and propagates exit. Per spec R16, this is **human-attended on day one only** — enforced by the maintainer reading the diff at commit time, not by automation. The script exists so the day-zero check is mechanically reproducible (re-runnable in CI or local-dev), not as a perpetual safety net. After day zero, Task 13's pre-commit hook is the enforcement surface; this script becomes a strict subset of that hook.
- **Depends on**: [1, 3, 7, 8, 9, 10, 11]
- **Complexity**: simple
- **Context**:
  - Shell shape: `#!/usr/bin/env bash`, `set -euo pipefail`, `cd "$(git rev-parse --show-toplevel)"`, `python3 bin/cortex-check-parity` — exit code propagates.
  - **Honest framing**: spec R16 explicitly states the gate is human-attended ("the day-one commit happens with a human in the room"). The plan does not strengthen that into automation — doing so would expand scope beyond the approved spec. The implementer running Task 12 must, on a non-zero exit, surface the violation to the human operator and **stop** — adding rows to `bin/.parity-exceptions.md` to clear the gate is prohibited unless the spec is amended first. Because the on-disk artifact is identical in both cases, this is a discipline rule for the implementer, not a tooling guarantee.
  - **Failure-mode acknowledgement**: if Task 12's exit-0 reflects a silently-extended allowlist rather than a clean baseline, Task 13 will lock that corrupted baseline in. The mitigation is process (maintainer reviews the day-zero commit diff, including any allowlist row additions), not automation. See "Open Spec Questions" below for whether to revisit this.
- **Verification**: `bash tests/test_check_parity_first_run_green.sh` exits 0 — pass if exit 0. **Maintainer judgment** required at commit time: confirm `bin/.parity-exceptions.md` contains exactly the single row from Task 3 (no additions during implementation).
- **Status**: [x] complete

### Task 13: Wire pre-commit Phase 1.5
- **Files**: `.githooks/pre-commit`
- **What**: Insert a new "Phase 1.5" block between Phase 1 (classification guard) and Phase 2 (build-needed decision). On staged-paths matching the parity trigger pattern, invoke `just check-parity --staged` and propagate non-zero exit. Update the header comment block from "four phases" to "five phases".
- **Depends on**: [1, 2, 12]
- **Complexity**: simple
- **Context**:
  - Existing pre-commit shape: Phase 1 (validate plugin.json + classification), Phase 2 (build-needed decision via staged paths), Phase 3 (`just build-plugin`), Phase 4 (drift detection). Insert Phase 1.5 above Phase 2's staged-paths block.
  - Trigger regex (R13): `^(skills/|bin/cortex-|justfile$|bin/\.parity-exceptions\.md$|CLAUDE\.md$|requirements/|tests/|hooks/cortex-|claude/hooks/cortex-)`. Implement via a `git diff --cached --name-only --diff-filter=ACMRD` loop with shell pattern matching.
  - On match → `just check-parity --staged`. On non-zero exit → print stdout/stderr + `exit 1`. On no match → fall through to Phase 2.
  - `--staged` semantics handled by the linter (Task 1): deployed set from working-tree `bin/`, referenced set from `git diff --cached` blob contents at staged version.
  - Phase 4 is intentionally skipped on parity-only commits (e.g., changes only to `requirements/` or `bin/.parity-exceptions.md`) where Phase 2 BUILD_NEEDED does not fire — non-build-relevant changes cannot introduce plugin-tree drift.
- **Verification**:
  - Static: `grep -c 'just check-parity --staged' .githooks/pre-commit` outputs `1` AND `grep -cE '^# Phase 1\.5' .githooks/pre-commit` ≥ `1` — pass if both hold.
  - **Runtime smoke (positive)**: with a clean working tree, stage a temporary fake-skill file demonstrating a real E002 violation: `printf '# fake skill\n\nReferences \\`bin/cortex-this-script-does-not-exist\\`.\n' > skills/_smoke-test.md && git add skills/_smoke-test.md`; run `bash .githooks/pre-commit` → expected exit 1 with `E002` in stdout; cleanup `git restore --staged skills/_smoke-test.md && rm skills/_smoke-test.md`. Pass if pre-commit exits 1 with E002 visible.
  - **Runtime smoke (negative — no violation)**: with a clean working tree, stage a comment-only edit to `bin/.parity-exceptions.md` (e.g., `printf '\n<!-- smoke test -->\n' >> bin/.parity-exceptions.md && git add bin/.parity-exceptions.md`); run `bash .githooks/pre-commit` → expected exit 0 (parity check fires on the staged path, finds no violations); cleanup `git restore bin/.parity-exceptions.md`. Pass if pre-commit exits 0.
  - Together these prove (1) the trigger regex fires correctly, (2) the linter is actually invoked with `--staged`, and (3) both the failure path and pass path work. Trivial `bin/.parity-exceptions.md`-only staging (which produces zero `cortex-*` token deltas) is insufficient — replaced by the positive E002 smoke above.
- **Status**: [x] complete

## Verification Strategy

The plan ships four verification surfaces. They are **complementary, not redundant** — each is canonical for a different failure class. The previous draft framed three as "independent surfaces"; that framing was inaccurate (Task 12 is a strict subset of Task 13 after day zero, and the inline self-test partially overlaps with the pytest matrix). Honest accounting:

1. **Inline self-test** (Task 1, `--self-test`) — **canonical for**: classification logic regressions (R4 wiring rule changes, R5 candidate filter changes, R8 schema changes). Runs in-process against inline fixture data. Fast (<100ms), runs as part of the linter's own correctness check. The R5(c) plugin-list drift case lives here.
2. **Pytest fixture matrix** (Tasks 4–6) — **canonical for**: integration behavior the self-test cannot exercise — glob-resolution from a non-repo cwd, allowlist file-read I/O, JSON output schema, exit-code propagation, R6 boundary cases (the `valid-table-cell-with-narrative` and `invalid-readme-table-only` pair). Tasks 4–6 ship 12 file-system fixtures.
3. **R16 first-run-green dry-run** (Task 12) — **canonical for**: day-zero state only. Verifies the load-bearing spec claim that the day-one allowlist contains exactly one entry and every other `cortex-*` script is wired through R7 scope. After day zero, this script is a strict subset of Task 13's hook check; it persists as a re-runnable mechanical sanity check, not a perpetual gate.
4. **Pre-commit Phase 1.5 hook** (Task 13) — **canonical for**: ongoing enforcement against new commits. Both runtime smokes in Task 13's verification (positive E002 path + negative no-violation path) exercise this surface end-to-end.

**Redundancy is acknowledged**: self-test and pytest matrix both enumerate E001/E002/W003/W005 plus the R4/R5 patterns. The self-test is the **source of truth for classification logic**; pytest matrix exists for the surfaces above (cwd, I/O, output formatting). Future rule changes should land in self-test first; pytest fixtures only need updating if a new fixture-format surface is exposed (e.g., a new exit code, a new output channel).

After all tasks complete:
- `just check-parity` from repo root → exits 0.
- `uv run pytest tests/test_check_parity.py -q` → all pass (12 fixtures: 5 valid + 4 invalid + 3 exclude).
- `bash tests/test_check_parity_first_run_green.sh` → exits 0 (R16 day-zero gate).
- Both Task 13 runtime smokes pass per the procedure in Task 13's verification block.

## Veto Surface

- **R7 scan-scope split between top-level and plugin trees**: scope is `skills/**/*.md` (top-level only) — `plugins/*/skills/**/*.md` is excluded. Drift between top-level and plugin mirrors is delegated to the existing dual-source pre-commit Phase 4. If a future change makes the plugin-tree mirrors authoritative for any subset of skills, R7 must be revised.
- **Closed plugin name list hardcoded in linter source (R5(c))**: adding a new plugin requires editing `bin/cortex-check-parity`. Intentional friction per spec Technical Constraints. Drift detection is now load-bearing — Task 1 includes a self-test case (`plugin-list-matches-justfile`) that fails when the constant disagrees with `justfile` `BUILD_OUTPUT_PLUGINS` + `HAND_MAINTAINED_PLUGINS`. The day-one constant is `{cortex-interactive, cortex-overnight-integration, cortex-pr-review, cortex-ui-extras, cortex-dev-extras, android-dev-extras}` — verify against justfile at implementation time.
- **`overnight-schedule` un-prefixed wiring assumption (Non-Requirement #3)**: the spec assumes `overnight-schedule` is wired via path-qualified mentions in `skills/overnight/SKILL.md`. If the R16 dry-run surfaces `overnight-schedule` as an orphan, **stop and ask the user** — do not add an allowlist row. The fix may be (a) the wiring assumption is wrong and the SKILL.md needs a path-qualified mention, (b) the script should be renamed `cortex-overnight-schedule`, or (c) an allowlist row is genuinely warranted. The choice belongs to the user, not the implementer.
- **`--no-verify` and overnight-runner bypass acknowledged out of scope**: enforcement is best-effort against `git commit` interactive use; bypass paths are documented as a Non-Requirement. The user may wish to revisit this trade-off — observability for bypass detection belongs to a future ticket but could in principle be in-scope here.
- **Pre-commit Phase 1.5 latency budget (~500ms target, not formally bounded)**: Technical Constraints note an empirical target only. If the linter's first-run scan exceeds the target on the current repo, the user may want to defer pre-commit wiring to a follow-up while keeping the justfile recipe and tests.
- **Half-staged rename edge case (Spec edge case 3) — corrected description**: the spec's framing assumes `git mv` followed by partial unstaging leaves both files in the working tree; this is **wrong** for standard git semantics. After `git mv bin/validate-spec bin/cortex-validate-spec`, the working-tree disk state has only the prefixed file regardless of staging actions on the index. Per Task 1's `--staged` rule "deployed = working-tree bin/", the deployed set agrees with the staged justfile reference and the hook passes — the un-prefixed deletion never lands as a problem. The genuine half-staged risk is a different shape: a developer manually `cp`-s the file then forgets to `git rm` the original. That edge case is rare and resolved by `git status` review at commit time. The veto here is informational only — flag if the user wants spec amendment for accuracy.
- **R4(b) fenced-code-block matching is permissive — see "Open Spec Questions"**.
- **Allowlist rationale validation (R8) is structural, not semantic**: R8 enforces ≥30 chars + closed-set blocklist. It cannot constrain semantic quality; an LLM-generated rationale satisfying the structural rule still passes. This is acknowledged at spec time; the day-one human-attended commit gate is the only quality check. Future ticket could add `--audit-allowlist` for periodic review.

## Commit-Landing Order

Task dependencies (`Depends on:` fields) describe execution order, not commit-landing order. For a pre-commit hook (Task 13), the distinction is load-bearing — the hook becomes active the moment its file lands on disk. Required commit ordering:

1. **Commit A (or atomic landing of Tasks 1–12)**: ships `bin/cortex-check-parity`, the justfile recipe, the day-one allowlist, the pytest harness + fixtures, the rename, and all retrofits. Run `bash tests/test_check_parity_first_run_green.sh` BEFORE committing — the maintainer attends to this output.
2. **Commit B**: ships Task 13 (`.githooks/pre-commit` Phase 1.5 wiring). This commit's pre-commit hook fires on itself; the staged blob view sees only the hook change (no `cortex-*` token deltas in staged content), so it exits 0 cleanly.

**Atomic alternative** (single commit landing Tasks 1–13): also valid — the staged blob view is self-consistent (linter + allowlist + retrofits + hook all together). Choose the split-commit form if the implementer wants the R16 dry-run as a separate review checkpoint; choose the atomic form if all artifacts are co-reviewable.

**Anti-pattern (do not do this)**: landing Task 13 in a feature branch ahead of Tasks 1–12 will activate Phase 1.5 against subsequent retrofit commits, blocking them with the violations the retrofits are supposed to fix.

## Open Spec Questions

The critical review surfaced one question the orchestrator cannot self-resolve — it requires user input because it would amend the approved spec:

- **R4(b) fenced-code-block matching scope**: the spec says `cortex-foo` is wired by appearance "inside a backtick code span ... or fenced code block". The reviewer's concern: a SKILL.md containing an example transcript with a deprecated `cortex-old-name` reference satisfies R4(b) and prevents E002 even when the script is genuinely orphaned. Three options:
  - **(a) Implement spec verbatim** — accept that fenced-code-block mentions wire any token. False-negative risk is bounded; the maintainer can convert genuinely-orphaned scripts to the allowlist or remove the example.
  - **(b) Tighten R4(b) to require the token appear as a "command head"** — first non-comment word on a line inside fenced code blocks, OR inside a backtick code span. Backticks anywhere still wire (low false-negative risk); fenced blocks only wire when they look like a command invocation. Spec amendment required.
  - **(c) Defer to a future ticket** — implement (a) now, file a follow-up if false negatives surface in practice.

The plan currently implements **(a)** to honor the approved spec. This is the only Ask in the critical review feedback cycle.

## Scope Boundaries

Per spec Non-Requirements:
- No "hidden-via-abstraction" detection (Python module path → CLI shim mapping).
- No `cortex-*` naming-prefix enforcement on new bin scripts.
- No `--no-verify` bypass detection or overnight-runner audit.
- No transitive `just <recipe>` resolution in justfile parsing.
- No scanning of `plugins/*/` mirrors (Phase 4 owns canonical→mirror drift).
- No rename of `bin/overnight-schedule` (deferred to a future ticket).
- No allowlist size/growth/age tracking, no `--audit-allowlist` recipe.
- No runtime invocation tracking (DR-7 / ticket 113).
- No fix proposals or auto-apply — report-only.
- No external network calls or external binary dependencies in the pytest suite beyond the linter itself.
