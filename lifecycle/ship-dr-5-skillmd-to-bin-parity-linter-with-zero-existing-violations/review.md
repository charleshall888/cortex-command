# Review: ship-dr-5-skillmd-to-bin-parity-linter-with-zero-existing-violations

## Stage 1: Spec Compliance

### Requirement 1: Linter ships at `bin/cortex-check-parity`
- **Expected**: `test -x bin/cortex-check-parity && bin/cortex-check-parity --self-test` exits 0 with stdout containing "self-test passed".
- **Actual**: File present, executable bit set. Running `python3 bin/cortex-check-parity --self-test` exits 0 and prints `self-test passed` after 15 PASS lines (with `--verbose`).
- **Verdict**: PASS

### Requirement 2: Stdlib-only Python implementation
- **Expected**: `^#!/usr/bin/env python3$` shebang; non-stdlib import grep returns 0.
- **Actual**: First line is `#!/usr/bin/env python3`; the import grep against the allowlist `{argparse, json, os, pathlib, re, subprocess, sys, typing, dataclasses, enum}` returns `0`. Imports actually used: `argparse`, `json`, `os`, `re`, `subprocess`, `sys`, `dataclasses`, `enum`, `pathlib`, `typing.Iterable`.
- **Verdict**: PASS

### Requirement 3: Two failure modes detected
- **Expected**: `--self-test` exercises drift and orphan modes; both classifications produce expected output.
- **Actual**: `SELF_TEST_CASES` includes `invalid-drift` (E002 candidate-set check) and `invalid-orphan` (W003 wiring-set negative check), plus `invalid-allowlist-row` (E001) and `invalid-allowlist-superfluous` (W005). All four emit PASS in `--verbose` mode.
- **Verdict**: PASS

### Requirement 4: Wiring rule (R4 a/b/c)
- **Expected**: Path-qualified `bin/cortex-foo` (a), backtick or fenced code mention (b), or passing allowlist row (c) constitute wiring.
- **Actual**: `collect_wiring_signals` invokes `_collect_path_qualified_tokens` (R4(a) via `PATH_QUALIFIED_RE = bin/(cortex-…)`), `_collect_inline_code_tokens` (R4(b) inline), and `_collect_fenced_code_tokens` (R4(b) fenced). Allowlist (R4(c)) is applied at the lint level — allowlisted tokens are skipped during W003 emission. Self-test cases `valid-path-qualified`, `valid-code-span`, `valid-fenced-code`, `valid-allowlist` all pass; pytest fixture `valid-table-cell-with-narrative` exercises the R6/R4(b) boundary.
- **Verdict**: PASS

### Requirement 5: Bin-reference candidate rule (R5 a/b/c/d, plus amended e + c-extension)
- **Expected**: Exclusion of (a) hook/plugin path-qualified tokens, (b) `.sh`-suffixed tokens, (c) closed plugin names, (d) self-reference. Spec amendments approved mid-implement: (e) leading-dot file/marker tokens; (c)-extension reserved non-bin names `{cortex-command, cortex-overnight}`.
- **Actual**: `NON_BIN_PATH_PREFIX_RE` strips R5(a) contiguous path-qualified tokens before scan. `.sh` suffix excluded in both `_collect_inline_code_tokens` and `_collect_fenced_code_tokens` (R5(b)). `PLUGIN_NAMES` frozenset (6 names matching justfile `BUILD_OUTPUT_PLUGINS` + `HAND_MAINTAINED_PLUGINS`) excluded (R5(c)). `SELF_REFERENCE = "cortex-check-parity"` excluded from candidate set only (R5(d) — fixed in commit 91510f3 to keep wiring set intact). R5(e) leading-dot rule applied in both inline and fenced paths. `RESERVED_NON_BIN_NAMES = {cortex-command, cortex-overnight}` excluded (R5(c) extension). All seven exclusion self-tests pass (`exclude-hook-suffix`, `exclude-plugin-name`, `exclude-hook-path`, `exclude-self-reference`, `exclude-leading-dot`, `exclude-reserved-non-bin-name`, plus the pytest `exclude-*` fixtures). The `plugin-list-matches-justfile` self-test enforces drift detection between `PLUGIN_NAMES` and the justfile arrays.
- **Verdict**: PASS

### Requirement 6: README enumeration tables alone do NOT wire
- **Expected**: Flat-enumeration table cell with no narrative body mention does not satisfy R4(b); table cell with narrative elsewhere DOES wire.
- **Actual**: `_table_only_tokens` groups contiguous markdown table blocks, identifies columns where ≥2 rows contain only `cortex-X` tokens (no non-token cells), then subtracts any token that has a narrative mention (path-qualified or inline-code) outside the table region. The fixture `invalid-readme-table-only` correctly emits 2× W003 for both `cortex-foo` and `cortex-bar`; the fixture `valid-table-cell-with-narrative` correctly produces zero violations.
- **Verdict**: PASS

### Requirement 7: Scan scope
- **Expected**: Top-level `skills/**/*.md`, `CLAUDE.md`, `requirements/**/*.md`, `docs/**/*.md`, `tests/**/*.py`, `tests/**/*.sh`, `hooks/cortex-*.sh`, `claude/hooks/cortex-*.sh`, `justfile`. Plugin trees excluded.
- **Actual**: `SCAN_GLOBS` enumerates exactly these 9 globs. `--print-scan-paths` outputs them sorted. `plugins/*/` is not included.
- **Verdict**: PASS

### Requirement 8: Allowlist row schema
- **Expected**: 5-column markdown table; closed category enum `{maintainer-only-tool, library-internal, deprecated-pending-removal}` (no `experimental`); rationale ≥30 chars and not in `{internal, misc, tbd, n/a, pending, temporary}`; date `YYYY-MM-DD`.
- **Actual**: `parse_allowlist` enforces all five constraints. `ALLOWED_CATEGORIES` matches the spec; `experimental` is correctly absent. `FORBIDDEN_RATIONALE_LITERALS` matches. `DATE_RE` is `^\d{4}-\d{2}-\d{2}$`. The `invalid-allowlist-row` pytest fixture and self-test case both exercise all six failure modes (empty rationale, bad category, forbidden literal, too short, missing date, malformed date) and produce 6× E001.
- **Verdict**: PASS

### Requirement 9: Output format and codes
- **Expected**: `path:line:col: <code> <message>` plain text; `--json` emits parseable array; codes E001/E002/W003/W005.
- **Actual**: `Violation.format_text()` produces the exact format. `emit(..., as_json=True)` prints `json.dumps([v.to_dict() for v in errors+warnings])`. All four codes are emitted in the lint pipeline. `python3 bin/cortex-check-parity --self-test --json | python3 -c 'import sys,json; json.load(sys.stdin)'` exits 0.
- **Verdict**: PASS

### Requirement 10: Exit codes
- **Expected**: 0 = clean (or only-warnings + lenient); 1 = any error or any warning in default mode; 2 = internal error.
- **Actual**: `determine_exit` returns 1 if errors present, else 1 if warnings present and not lenient, else 0. `RuntimeError` from allowlist read produces exit 2 with `E000 unparseable allowlist` on stderr. Empirically verified with a temp fixture: orphan-only repo exits 1 by default and 0 with `--lenient`.
- **Verdict**: PASS

### Requirement 11: Justfile recipe
- **Expected**: `^check-parity \*args:$` matches exactly once; body invokes `python3 bin/cortex-check-parity {{args}}`.
- **Actual**: `justfile:334` reads `check-parity *args:`; line 335 reads `    python3 bin/cortex-check-parity {{args}}`. Recipe is placed adjacent to `validate-spec` per plan.
- **Verdict**: PASS

### Requirement 12: Pytest test suite
- **Expected**: `tests/test_check_parity.py` parametrizes over `tests/fixtures/parity/{valid-*, invalid-*, exclude-*}/`; reports ≥10 fixtures.
- **Actual**: 12 fixture directories exist (5 valid + 4 invalid + 3 exclude). `python3 -m pytest tests/test_check_parity.py -q` reports `12 passed in 0.91s`. Harness asserts exit 0 + empty array for valid/exclude, exit 1 + matching expected.json codes for invalid. `tests/fixtures/parity/` is correctly outside R7's production scan scope.
- **Verdict**: PASS

### Requirement 13: Pre-commit hook integration (`--staged` semantics)
- **Expected**: Phase 1.5 runs between Phase 1 and Phase 2; trigger regex matches the spec set; deployed set from working-tree, referenced set from working-tree scan WITH staged blobs OVERLAID (not REPLACED).
- **Actual**: `.githooks/pre-commit` lines 70-90 implement Phase 1.5 with the case-pattern matcher covering exactly the spec triggers (`skills/`, `bin/cortex-`, `justfile`, `bin/.parity-exceptions.md`, `CLAUDE.md`, `requirements/`, `tests/`, `hooks/cortex-`, `claude/hooks/cortex-`). Header comment updated to "Five phases" reflecting the new structure. Commit `e29c46e` correctly fixes the `--staged` corpus to overlay staged blobs on top of the working-tree scan rather than replace it: `staged_overlay` dict captures staged in-scope files; `gather_scan_files(root)` walks the working tree; for each path, the staged overlay (if present) is preferred; staged-only paths (new additions) are appended last. This matches R13's "plus blob contents at the staged version" intent — stage-only-out-of-scope-file commits no longer falsely emit W003 against every deployed cortex-* script.
- **Verdict**: PASS

### Requirement 14: Day-one allowlist contents
- **Expected**: Exactly one entry for `cortex-archive-sample-select` with category `maintainer-only-tool`, rationale describing lifecycle archive sampling, lifecycle 102, date 2026-04-27.
- **Actual**: `bin/.parity-exceptions.md` contains exactly the spec-mandated row. The schema-explanation header and the R15.8 reviewer-guidance line are both present. Running `bin/cortex-check-parity` against current HEAD exits 0.
- **Verdict**: PASS

### Requirement 15: Retrofits applied (15.1–15.8)
- **Expected**: Rename `bin/validate-spec` → `bin/cortex-validate-spec`; replace `git-sync-rebase.sh` and `~/.local/bin/...` references in 5 files; ship the day-one allowlist.
- **Actual**:
  - 15.1: `bin/cortex-validate-spec` executable, `bin/validate-spec` absent, `justfile:331` invokes the renamed binary.
  - 15.2: `grep -c 'git-sync-rebase\.sh' skills/morning-review/references/walkthrough.md` = 0; cortex-git-sync-rebase mentioned 5 times.
  - 15.3: `grep -c '~/\.local/bin/generate-backlog-index' skills/lifecycle/references/complete.md` = 0; canonical mentions = 2.
  - 15.4: `grep -c '~/\.local/bin' skills/dev/SKILL.md` = 0.
  - 15.5: `grep -c 'git-sync-rebase\.sh' skills/evolve/SKILL.md` = 0; canonical mention ≥ 1.
  - 15.6: `grep -c 'git-sync-rebase\.sh' requirements/pipeline.md` = 0.
  - 15.7: `grep -cE "bin/git-sync-rebase\\.sh|'git-sync-rebase\\.sh'" tests/test_git_sync_rebase.py` = 0.
  - 15.8: Allowlist file shipped with header and guidance line per spec.
- **Verdict**: PASS

### Requirement 16: Empirical first-run-green dry-run
- **Expected**: Documented dry-run step + `tests/test_check_parity_first_run_green.sh` that runs the linter against the actual repo and exits 0.
- **Actual**: Script exists, executable, runs `python3 bin/cortex-check-parity` from `git rev-parse --show-toplevel`. Empirically: `bash tests/test_check_parity_first_run_green.sh` exits 0 from repo root.
- **Verdict**: PASS

### Requirement 17: Markdown reference detection (stdlib regex with R5 exclusions)
- **Expected**: Stdlib regex; R16 dry-run exits 0 with R5 exclusions applied; no PyPI escalation needed.
- **Actual**: `re` module only; R5 exclusions (a-d, plus amendments e and c-extension) implemented; R16 dry-run is green. No `markdown-it-py` escalation triggered.
- **Verdict**: PASS

### Requirement 18: Self-test inline fixtures
- **Expected**: `--self-test` exercises E001/E002/W003/W005, the four R4 valid wiring patterns, and the four R5 exclusion patterns. `--verbose` prints PASS lines and exits 0.
- **Actual**: 15 cases enumerated in `SELF_TEST_CASES`: 4 valid (path-qualified, code-span, fenced-code, allowlist), 6 exclude (hook-suffix, plugin-name, hook-path, self-reference, leading-dot, reserved-non-bin-name), 4 invalid (allowlist-row, drift, orphan, allowlist-superfluous), and 1 drift-detection case (`plugin-list-matches-justfile`). The two extra exclude cases beyond spec (R5(e) and R5(c)-extension) are scope amendments accepted mid-implement. `--verbose` prints PASS lines for all 15; exit 0.
- **Verdict**: PASS

## Requirements Drift

**State**: detected

**Findings**:
- The implementation introduces a new enforcement surface (`bin/cortex-check-parity` SKILL.md-to-bin parity linter, day-one allowlist `bin/.parity-exceptions.md`, pre-commit Phase 1.5) that is not currently enumerated in `requirements/project.md`'s scope or quality-attribute discussion. The linter is a static gate that participates in the agentic-layer's discoverability/enforcement contract and embodies the project's "complexity must earn its place" philosophy by failing commits that ship under-adopted scripts. The closed plugin list in R5(c) (and the reserved non-bin name list added as R5(c)-extension) is hardcoded in the linter source as intentional friction — that design decision is unstated in project.md.
- Two semantic deviations from the verbatim spec landed during implement and are acknowledged in events.log as `scope_amendment`: (i) R5(e) leading-dot exclusion to handle file/marker names like `.cortex-init` and `.cortex-update.lock`; (ii) R5(c) extension via `RESERVED_NON_BIN_NAMES = {cortex-command, cortex-overnight}` for project/MCP-server identifiers that appear in fenced code blocks but are not bin scripts. These are amendments to spec R5, not project-level requirements drift, but they imply the rule "scripts in `bin/` follow `cortex-*` naming with no `.`-prefix and not aliasing the project name or MCP server name" — that naming convention is not documented in project.md.
- The W003 self-orphan fix (commit 91510f3) and `--staged` overlay fix (commit e29c46e) are corrections, not deviations. Both align the implementation with R4's intent (linter must see `bin/cortex-check-parity` in justfile as wiring) and R13's intent ("plus blob contents at the staged version" → overlay, not replace). No project-requirements impact.

**Update needed**: `requirements/project.md`

## Suggested Requirements Update

**File**: `requirements/project.md`

**Section**: `## Architectural Constraints`

**Content**:
```
- **SKILL.md-to-bin parity enforcement**: `bin/cortex-*` scripts must be wired through an in-scope SKILL.md / requirements / docs / hooks / justfile / tests reference (see `bin/cortex-check-parity` for the static gate). Drift between deployed scripts and references is a pre-commit-blocking failure mode. Allowlist exceptions live at `bin/.parity-exceptions.md` with closed-enum categories and ≥30-char rationales. The closed plugin list in the linter is intentional friction — adding a plugin or reserved name requires editing the linter source.
```

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. The new binary follows the `cortex-*` prefix convention used by every other in-scope shim. The renamed `bin/cortex-validate-spec` brings the previous outlier (`bin/validate-spec`) into the convention. Python identifiers are snake_case; module-level constants are SCREAMING_SNAKE; dataclass field names mirror allowlist column names. Self-test case names use kebab-case matching the fixture-directory naming, which is symmetric with the pytest matrix and aids cross-reference.

- **Error handling**: Appropriate. Allowlist parsing returns `(rows, violations)` rather than raising, allowing the linter to report many bad rows in a single pass. `load_allowlist` raises `RuntimeError` only on filesystem read failure, which `main()` catches and converts to exit 2 with E000 — matching the spec's "unparseable allowlist" edge case. `_read_staged_blob` swallows `CalledProcessError`, `FileNotFoundError`, and `UnicodeDecodeError`, returning `None` to let the corpus skip binaries cleanly. `gather_deployed` skips entries whose `stat()` raises `OSError` (handles broken symlinks). The `plugin-list-matches-justfile` self-test gracefully no-ops outside a repo (`Path("justfile").is_file()` check) — correct fixture-cwd behavior.

- **Test coverage**: All plan-mandated verification surfaces pass. Self-test 15 cases all PASS in `--verbose`. Pytest matrix 12/12 PASS in 0.91s. R16 dry-run script exits 0 from repo root. The `--staged` overlay fix (e29c46e) was empirically validated by the implementer per the commit message — comment-only edits to `bin/.parity-exceptions.md` no longer false-positive every deployed script as W003. The W003 self-orphan fix (91510f3) is covered by the inline self-test case `exclude-self-reference`'s wiring-set assertion (`bin/cortex-check-parity` in `\`bin/cortex-check-parity\`` MUST remain wired). Test coverage is unusually deep for a stdlib-only tool: 4 verification surfaces (self-test, pytest, R16 script, pre-commit hook) with documented redundancy boundaries in `plan.md`'s Verification Strategy section.

- **Pattern consistency**: The justfile recipe is a 1:1 shape match for the adjacent `validate-spec` recipe. The pre-commit Phase 1.5 block follows the existing phase-numbering convention and uses the same case-pattern bash idiom that Phases 2 and 4 use. Fixture-directory layout matches the pre-existing `tests/fixtures/` pattern and is symmetric with the self-test case names (each pytest fixture has a self-test counterpart). The `.parity-exceptions.md` schema-explanation header reuses the markdown-table-with-prose-prefix pattern already used elsewhere in the repo. The `Violation` and `AllowlistRow` `@dataclass(frozen=True)` shape is idiomatic stdlib Python for this kind of value object. The amended R5(e) and R5(c)-extension rules are implemented symmetrically across `_collect_inline_code_tokens` and `_collect_fenced_code_tokens`, avoiding asymmetric coverage gaps.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
