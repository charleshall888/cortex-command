# Specification: Ship DR-5 SKILL.md-to-bin parity linter with zero existing violations

> **Epic background**: this spec implements DR-5 from epic [`research/extract-scripts-from-agent-tool-sequences/research.md`](../../research/extract-scripts-from-agent-tool-sequences/research.md). Adjacent extractions (105–111), runtime adoption telemetry (DR-7, ticket 113), and the deferred `bin/overnight-schedule` rename are NOT in this spec's scope.

> **Critical review applied 2026-04-27**: This revision narrows the linter's scope (drop W004 hidden-via-abstraction), tightens classification rules (define inverse-of-R4 to exclude hook/plugin tokens), strengthens allowlist schema (drop `experimental` category, forbid weak rationale literals, add W005 allowlist-superfluous warning), and disambiguates `--staged` semantics. See `events.log` `critical_review` and `critical-review-residue.json` for source findings.

## Problem Statement

Five of nine current `bin/cortex-*` scripts are under-adopted because two failure modes go uncaught: (a) **day-one missing reference** — a script ships without ever being mentioned in a SKILL.md/docs body; (b) **drift** — a SKILL.md references a script name that no longer exists (e.g., `git-sync-rebase.sh` survived after the rename to `cortex-git-sync-rebase`). Without enforcement, the cost of writing tooling exceeds the benefit because agents and developers never discover what already exists. This ticket ships a static parity linter (`bin/cortex-check-parity`) that fails commits introducing either failure mode, plus retrofits the current set of violations so the first run is green.

## Requirements

1. **Linter ships at `bin/cortex-check-parity`**: Acceptance — `test -x bin/cortex-check-parity && bin/cortex-check-parity --self-test` exits 0 with stdout containing "self-test passed".

2. **Stdlib-only Python implementation**: Acceptance — `head -1 bin/cortex-check-parity` matches `^#!/usr/bin/env python3$`; `grep -E "^(import|from) " bin/cortex-check-parity | grep -vE "^(import|from) (argparse|json|os|pathlib|re|subprocess|sys|typing|dataclasses|enum)" | wc -l` outputs `0`.

3. **Two failure modes detected**: Acceptance — running `bin/cortex-check-parity --self-test` runs in-process fixtures that exercise each mode (drift, orphan) and exits 0 only if both classifications produce expected output. Self-test fixtures are inline in the script.

4. **Wiring rule** (defines what counts as a SKILL.md → bin reference): A `bin/cortex-foo` is **wired** if any of these signals appear in any in-scope file:
   - **(a) Path-qualified mention**: literal `bin/cortex-foo` token anywhere in the file (any context).
   - **(b) Bare-token mention in code context**: `cortex-foo` appears inside a backtick code span (`` `cortex-foo` ``) or fenced code block (``` ```...``` ```).
   - **(c) Allowlist entry**: a passing row in `bin/.parity-exceptions.md` (R8).
   
   Acceptance — covered by R12's pytest fixtures.

5. **Bin-reference candidate rule** (defines which scanned tokens are checked against the deployed `bin/` set): A regex match `cortex-[a-z][a-z0-9-]*` in scope is a candidate for E002/W003 evaluation **only if** all of the following hold:
   - **(a) Not path-qualified to a non-bin path**: the immediately preceding context is not `hooks/`, `plugins/`, `claude/hooks/`, `.claude/hooks/`, or any `*/hooks/` path. Tokens in those contexts are hook script names — explicitly excluded.
   - **(b) Not suffixed with `.sh`**: tokens like `cortex-validate-commit.sh` are hook scripts — explicitly excluded.
   - **(c) Not a known plugin name**: the closed plugin list `{cortex-interactive, cortex-overnight-integration, cortex-pr-review, cortex-ui-extras, cortex-dev-extras, android-dev-extras}` (sourced from `justfile` `BUILD_OUTPUT_PLUGINS` + `HAND_MAINTAINED_PLUGINS`) is excluded.
   - **(d) Not the linter binary itself** (`cortex-check-parity` referenced inside the linter source).
   
   Tokens passing (a)-(d) are then classified per R4. This rule is the **inverse of R4** — it defines the universe of candidates the linter inspects, distinguishing bin-script references from hook/plugin/non-bin tokens. Acceptance — pytest fixtures `tests/fixtures/parity/exclude-hook-suffix/`, `exclude-plugin-name/`, `exclude-hook-path/` reference tokens matching the regex but failing R5(a)-(d), and the linter exits 0 (no violations).

6. **README enumeration tables alone do NOT wire**: a `cortex-foo` token in a flat-enumeration markdown table inside an in-scope file (e.g., `CLAUDE.md` future inventory tables) does not satisfy R4(b)'s "code-span" condition unless the same file's body section also references the token in narrative prose. Acceptance — pytest fixture `tests/fixtures/parity/invalid-readme-table-only/` has a script referenced only in a flat enumeration markdown table (no narrative body), and the linter exits 1 reporting orphan. Note: a code-span mention IN A TABLE CELL (not flat enumeration) still wires per R4(b); R6 narrows only against flat enumeration patterns.

7. **Scan scope**: Linter scans top-level `skills/**/*.md`, `CLAUDE.md`, `requirements/**/*.md`, `docs/**/*.md`, `tests/**/*.py`, `tests/**/*.sh`, `hooks/cortex-*.sh`, `claude/hooks/cortex-*.sh`, and the `justfile`. Plugin-tree mirrors (`plugins/*/`) are NOT scanned. Acceptance — `bin/cortex-check-parity --print-scan-paths` outputs exactly these globs (sorted).

8. **Allowlist row schema**: Each row in `bin/.parity-exceptions.md` must be a markdown table row with five columns:
   - `script`: matches `^cortex-[a-z][a-z0-9-]*$` (or `^[a-z][a-z0-9-]*$` for un-prefixed scripts; only `overnight-schedule` qualifies today).
   - `category`: closed enum from `{maintainer-only-tool, library-internal, deprecated-pending-removal}`. The `experimental` category is intentionally absent — experimentation should produce a real category before allowlisting.
   - `rationale`: free text, ≥30 characters after whitespace trim, AND must not be one of the literals `internal`, `misc`, `tbd`, `n/a`, `pending`, `temporary` (case-insensitive, after trim).
   - `lifecycle_id`: backlog ID (numeric or kebab-slug) or lifecycle slug. Existence is not validated by the linter — that adds I/O cost; reviewers verify during PR.
   - `added_date`: ISO date `YYYY-MM-DD`.
   
   Rows failing validation produce `bin/.parity-exceptions.md:LN:1: E001 invalid allowlist entry: <reason>`. Acceptance — pytest fixture `tests/fixtures/parity/invalid-allowlist-row/` exercises each failure (empty rationale, bad category, forbidden rationale literal `'internal'`, rationale <30 chars, missing date, bad date format) and produces one E001 per malformed row.

9. **Output format and codes**: Default plain text, one violation per line, format `path:line:col: <code> <message>`. Codes:
   - `E001` (allowlist row invalid)
   - `E002` (drift — referenced not deployed)
   - `W003` (orphan — deployed not referenced)
   - `W005` (allowlist-superfluous — script is allowlisted AND has a wiring signal in scope, so the row is now redundant)
   
   `--json` flag emits a JSON array of `{path, line, col, code, message}` objects. Acceptance — `bin/cortex-check-parity --self-test --json | python3 -c 'import sys,json; json.load(sys.stdin)'` exits 0.

10. **Exit codes**: 0 = clean (or only warnings in `--lenient` mode); 1 = any error (E001, E002) or any warning in default mode (W003, W005); 2 = internal error (file unreadable, scan path missing, allowlist file unparseable). `--lenient` downgrades W003 and W005 from exit-1 to warnings (still printed; exit 0 if only warnings remain). Acceptance — `bin/cortex-check-parity --self-test` exit code = 0; running against a fixture with only orphan violations exits 1 by default and 0 with `--lenient`.

11. **Justfile recipe**: `just check-parity *args` invokes `python3 bin/cortex-check-parity {{args}}`. Acceptance — `grep -E '^check-parity \*args:$' justfile` produces exactly one match.

12. **Pytest test suite**: A test file at `tests/test_check_parity.py` parametrizes over fixture directories at `tests/fixtures/parity/{valid-*, invalid-*, exclude-*}/`. Each fixture contains a minimal `bin/`, in-scope files, optional `bin/.parity-exceptions.md`. Acceptance — `uv run pytest tests/test_check_parity.py -q` exits 0 and reports ≥10 fixtures: valid-path-qualified, valid-code-span, valid-fenced-code, valid-allowlist, invalid-readme-table-only, invalid-drift, invalid-allowlist-row, invalid-allowlist-superfluous, exclude-hook-suffix, exclude-plugin-name, exclude-hook-path. Fixtures live in `tests/fixtures/parity/` which is NOT in the production scan scope (R7 includes `tests/**/*.py` and `tests/**/*.sh` but not arbitrary fixture markdown).

13. **Pre-commit hook integration**: `.githooks/pre-commit` runs the linter as a new "Phase 1.5" between the existing plugin classification (Phase 1) and staged-files decision (Phase 2). Trigger condition: any staged path matches `^(skills/|bin/cortex-|justfile$|bin/\.parity-exceptions\.md$|CLAUDE\.md$|requirements/|tests/|hooks/cortex-|claude/hooks/cortex-)`. The hook calls `just check-parity --staged`. **`--staged` semantics**: deployed set is read from the working-tree filesystem (`bin/` directory contents — staging state irrelevant for executable presence); referenced set is read from `git diff --cached --name-only --diff-filter=ACMRD` plus the file contents at the staged blob. On non-zero exit the hook prints the linter output and exits 1, blocking the commit. **Phase handoff note**: R7 delegates plugin-mirror drift to existing Phase 4 (drift detection runs after Phase 3 build-plugin). Phase 4 runs only when Phase 3 ran (Phase 2 BUILD_NEEDED triggered). On commits whose staged paths fall under R13's parity trigger but NOT Phase 2's BUILD_NEEDED trigger (e.g., changes only to `requirements/` or `bin/.parity-exceptions.md`), Phase 4 is intentionally skipped — non-build-relevant changes cannot introduce plugin-tree drift, so the absent Phase 4 has nothing to catch. Acceptance — staging a file containing a drift violation and running `git commit -m "test"` exits 1 with the linter's E002 violation output visible; staging an unrelated change (e.g., `README.md`) does not trigger the linter; staging only `requirements/foo.md` triggers Phase 1.5 but not Phase 3 or Phase 4.

14. **Day-one allowlist contents**: `bin/.parity-exceptions.md` ships with exactly one entry on day one:

    | script | category | rationale | lifecycle_id | added_date |
    | --- | --- | --- | --- | --- |
    | `cortex-archive-sample-select` | `maintainer-only-tool` | Lifecycle archive sampling — invoked manually by the maintainer when archiving a session; no agent flow references it and no wiring path is appropriate today. | `102` | `2026-04-27` |
    
    Acceptance — running `bin/cortex-check-parity` against current HEAD AFTER all R15 retrofits are applied exits 0.

15. **Retrofits applied in this ticket** (so first run is green):
    - **R15.1**: Rename `bin/validate-spec` → `bin/cortex-validate-spec`. Update `justfile:331` to invoke renamed binary. Acceptance — `test -x bin/cortex-validate-spec && ! test -e bin/validate-spec` and `grep -F 'bin/cortex-validate-spec' justfile` outputs ≥1 line.
    - **R15.2**: `skills/morning-review/references/walkthrough.md` — replace 5 occurrences of bare `git-sync-rebase.sh` with `cortex-git-sync-rebase` (lines ~564, 610, 611, 612, 614). Acceptance — `grep -c 'git-sync-rebase\.sh' skills/morning-review/references/walkthrough.md` outputs `0`.
    - **R15.3**: `skills/lifecycle/references/complete.md` — drop the dead `~/.local/bin/generate-backlog-index` failover step from both fallback chains (lines 44 and 68 in current HEAD). Retain canonical `cortex-generate-backlog-index` lines (43 and 67). Acceptance — `grep -c '~/\.local/bin/generate-backlog-index' skills/lifecycle/references/complete.md` outputs `0`.
    - **R15.4**: `skills/dev/SKILL.md:137` — rewrite the parenthetical removing the `~/.local/bin/generate-backlog-index` mention and the stale "do NOT use uv run" guidance. Acceptance — `grep -c '~/\.local/bin' skills/dev/SKILL.md` outputs `0`.
    - **R15.5**: `skills/evolve/SKILL.md:54` — replace `bin/git-sync-rebase.sh` with `bin/cortex-git-sync-rebase`. Acceptance — `grep -c 'git-sync-rebase\.sh' skills/evolve/SKILL.md` outputs `0`.
    - **R15.6**: `requirements/pipeline.md:148` — replace `bin/git-sync-rebase.sh` with `bin/cortex-git-sync-rebase`; drop any `~/.local/bin/` deployment annotation. Acceptance — `grep -c 'git-sync-rebase\.sh' requirements/pipeline.md` outputs `0`.
    - **R15.7**: `tests/test_git_sync_rebase.py` — update body references to point at `bin/cortex-git-sync-rebase`. Acceptance — `grep -c "bin/git-sync-rebase\.sh\|'git-sync-rebase\.sh'" tests/test_git_sync_rebase.py` outputs `0`.
    - **R15.8**: `bin/.parity-exceptions.md` — created with the day-one entry per R14 plus a header explaining the schema (R8) and a guidance line: "Adding an entry is a small architectural decision. Reviewers: confirm `category` enum is correct and `rationale` is specific (not 'internal' or 'misc' — those literals are linter-rejected). The W005 warning surfaces when an allowlisted script also has a wiring signal in scope; prune those rows."

16. **Empirical first-run-green dry-run** (gates the commit on day one): During implementation (per Plan), after the linter and all R15 retrofits are written but BEFORE the day-one commit, run `bin/cortex-check-parity` against HEAD and confirm it exits 0. If any unaccounted violations surface, the spec must be amended (do not silently add allowlist entries to make it green). The day-one commit happens with a human in the room — `R16` is enforced by human review of the diff, not by automation. After day one, the linter runs as a normal pre-commit gate per R13; future drift is prevented by R13, not by re-running R16. Acceptance — the implementation includes this dry-run as a documented step in plan.md and a test `tests/test_check_parity_first_run_green.sh` that runs the linter against the actual repo and exits 0.

17. **Markdown reference detection**: stdlib regex with R5's exclusion rules. The R5(a)-(d) candidate filter is the structural fix for hook/plugin/non-bin tokens that appear in code spans. No PyPI dep is anticipated; if the dry-run reveals genuine prose-vs-code-span ambiguity (vs. R5-resolvable cases), escalate to `markdown-it-py`. Acceptance — R16's dry-run exits 0 on the existing repo with stdlib-only AND R5 exclusions applied OR plan.md documents the escalation if it triggers.

18. **Self-test inline fixtures**: `--self-test` exercises in-process fixtures for each violation class (E001 invalid allowlist row, E002 drift, W003 orphan, W005 allowlist-superfluous), the four valid wiring patterns from R4, and the four R5 exclusion patterns. Acceptance — `bin/cortex-check-parity --self-test --verbose` prints "PASS" lines for each named case and exits 0.

## Non-Requirements

- The linter does NOT detect **hidden-via-abstraction** (Python module path mentioned without canonical CLI shim). Static module-path → shim-name mapping requires either parsing each `bin/cortex-*` shim's bash body or maintaining a hand-curated table; the latter is rot-prone, the former adds complexity. Per critical review: the actual abstraction shape in this repo is `python3 backlog/X.py` (because `cortex_command/backlog/` is not a real Python package — files live at `backlog/X.py`), and `complete.md`'s defense-in-depth fallback chain (R15.3) deliberately preserves these as legitimate fallbacks. Detection would require re-litigating that design. Defer to a future ticket if the abstraction problem becomes real.
- The linter does NOT enforce a `cortex-` naming prefix on new bin/ scripts. Today's prefix convention is structural in the build glob, not a lint-checked policy.
- The linter does NOT detect `git commit --no-verify` bypass or audit the overnight runner's commit path. That gap belongs to a separate observability ticket.
- The linter does NOT parse the `justfile` to resolve transitive `just <recipe>` invocations. Per research §Adversarial F7, the empirical premise was false: justfile recipes parallel-implement via `python3 backlog/X.py` rather than transitively wrapping `bin/cortex-*`.
- The linter does NOT scan plugin-tree mirrors at `plugins/*/`. The dual-source pre-commit hook (`.githooks/pre-commit` Phase 4) handles canonical→mirror drift when Phase 3 runs.
- The linter does NOT rename `bin/overnight-schedule` to `cortex-overnight-schedule`. Defer to a separate ticket. The day-one allowlist treats `overnight-schedule` as wired via `skills/overnight/SKILL.md:234,237,318` (path-qualified token in fenced code blocks — counts as wiring under R4(b) extended to non-prefixed scripts).
- The linter does NOT track allowlist size, growth rate, or row age. No `--audit-allowlist` recipe. Observability is a future enhancement; the W005 warning is the only automated rot signal.
- The linter does NOT runtime-track invocation counts. That is DR-7 / ticket 113.
- The linter does NOT propose or auto-apply fixes. It reports violations only.
- The pytest tests for the linter do NOT run network calls or invoke external binaries beyond the linter itself.

## Edge Cases

- **Allowlisted script gets re-wired in a SKILL.md body**: emit W005 (allowlist-superfluous). The row is now redundant; reviewers prune it. Default exit code = 1 unless `--lenient`. (Revised from prior spec — the linter now flags this rather than ignoring it.)
- **Half-staged rename (R15.1)**: developer stages `bin/cortex-validate-spec` (new) but forgets to stage the deletion of `bin/validate-spec` (old). Working-tree state has both files present; linter sees both as deployed. Un-prefixed `validate-spec` is not in the day-one allowlist, so it's W003 (orphan). Pre-commit hook blocks until the deletion is staged. **Resolution**: developer runs `git add -u bin/` to stage the deletion alongside the new binary.
- **Stale-base worktree (overnight runner concern)**: a worktree branched from main BEFORE the R15.1 rename retrofit lands still has `bin/validate-spec` (un-prefixed) deployed. After R15.1 ships to main, every parity-triggering commit in that stale-base worktree fails Phase 1.5 (un-prefixed validate-spec deployed but not allowlisted). **Mitigation**: worktrees rebase on main before commit (existing overnight-runner protocol per `cortex-git-sync-rebase`). If a worktree commit pre-dates the rebase, the hook blocks; the runner can either rebase the worktree or `--no-verify` the bypass (acknowledged as out of scope per Non-Requirements). Document in operational runbook.
- **Hook-script tokens in code spans**: `cortex-validate-commit.sh` (or any `cortex-*.sh`) appearing in a code span is excluded from candidate evaluation by R5(b). No false positive.
- **Plugin-name tokens in code spans**: `cortex-pr-review` (or any name in the closed plugin list) in a code span is excluded by R5(c). The plugin list is hardcoded in the linter; updating the list requires editing the linter source — intentional friction to prevent the closed list from drifting.
- **Fixture file inside `tests/fixtures/parity/`**: scan scope includes `tests/**/*.py` and `tests/**/*.sh` only (not arbitrary fixture markdown), so fixture markdown does not contaminate the production scan.
- **Renamed script (R15.1) generates orphan during interim staging**: the rename is applied as a single commit with R1; the working-tree state at commit time is consistent.
- **Allowlist file deletion**: missing `bin/.parity-exceptions.md` is a valid state (allowlist treated as empty); linter exits 0 if no other violations and prints an informational note.
- **Allowlist file present but malformed**: exit 2 with `bin/.parity-exceptions.md: E000 unparseable allowlist`. Hook blocks commits.
- **A bin script with no executable bit**: treated as not-deployed.
- **Symlinks in `bin/`**: deployed set is `os.scandir(bin/)` filtered to files (regular or symlink) with execute bit.
- **Multiple references to the same script**: any single in-scope reference satisfies wiring.
- **Prose-only mention of `cortex-foo`** (no code span, no fenced code, no path qualifier): does NOT count as wiring per R4. Prose mentions of script names are common in narrative explanation and the rule treats them as no-op.
- **A `cortex-*` token appearing only in a YAML frontmatter `description:` field** (e.g., `skills/lifecycle/SKILL.md:3`'s `bin/cortex-*` glob): the path-qualified glob matches R4(a)'s "literal `bin/cortex-foo` token" only if the glob expands to a specific name. A glob `bin/cortex-*` does NOT count as wiring any specific script. Tokens inside backtick spans within frontmatter ARE recognized by R4(b). This is an explicit clarification — frontmatter is in-scope for R4(b) but globs are not literal references.

## Changes to Existing Behavior

- **ADDED**: `bin/cortex-check-parity` (new linter), `bin/.parity-exceptions.md` (new allowlist), `tests/test_check_parity.py` + `tests/fixtures/parity/` (new tests), `just check-parity *args` recipe (new), Phase 1.5 in `.githooks/pre-commit` (new).
- **RENAMED**: `bin/validate-spec` → `bin/cortex-validate-spec`. Newly enters `plugins/cortex-interactive/bin/` via `--include='cortex-*'` mirror at next `just build-plugin` run.
- **MODIFIED (retrofit)**: `skills/morning-review/references/walkthrough.md`, `skills/lifecycle/references/complete.md`, `skills/dev/SKILL.md`, `skills/evolve/SKILL.md`, `requirements/pipeline.md`, `tests/test_git_sync_rebase.py`, `justfile` (recipe at line 331; new check-parity recipe).
- **REMOVED**: dead `~/.local/bin/generate-backlog-index` references in `complete.md` (lines 44, 68); stale `~/.local/bin/` parenthetical in `dev/SKILL.md:137`; original `bin/validate-spec`.

## Technical Constraints

- Python 3 stdlib-only — no `uv run --script`, no PyPI deps (R2). Threshold for upgrading to `markdown-it-py` is documented in R17.
- Pre-commit hook latency: not formally bounded by requirements/. Empirical target: linter completes in <500ms on current repo size.
- Pre-commit hook bypass via `--no-verify` is acknowledged (per `.githooks/pre-commit:18`) and out of scope.
- Drift between top-level and `plugins/cortex-interactive/bin/` is the responsibility of the existing dual-source hook (Phase 4). Parity linter must not duplicate that check. Phase 4 runs only when Phase 3 (build-plugin) ran; on commits where R13 fires Phase 1.5 but Phase 2's BUILD_NEEDED trigger is not met, Phase 4 is intentionally skipped. Non-build-relevant changes cannot introduce plugin-tree drift.
- Renamed `bin/cortex-validate-spec` newly matches `--include='cortex-*'`. The retrofit commit relies on existing pre-commit Phase 3 to regenerate `plugins/cortex-interactive/bin/cortex-validate-spec`.
- Allowlist row schema (R8) is enforced at linter load time. The schema is the linter's source of truth; the markdown file is the human-editable surface.
- Plugin name list in R5(c) is hardcoded in the linter source (sourced from `justfile` `BUILD_OUTPUT_PLUGINS` + `HAND_MAINTAINED_PLUGINS`). Adding a new plugin requires editing the linter — intentional friction.
- Overnight-runner exposure: agents running unattended could in principle silently inflate the allowlist to bypass the gate. R16 is a day-one human-attended gate only; future allowlist additions are post-hoc auditable via `git log bin/.parity-exceptions.md`. A standing observability surface (audit recipe, growth-rate alarm) is a future enhancement.

## Open Decisions

None at spec time.
