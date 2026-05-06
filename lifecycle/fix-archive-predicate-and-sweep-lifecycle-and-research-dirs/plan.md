# Plan: fix-archive-predicate-and-sweep-lifecycle-and-research-dirs

## Overview

Land the predicate fix, helper safety upgrades, R9 `cortex init` extension, and R10 integration test as a single pre-commit-validated code commit (Commit 1); checkpoint the F-9b unified disposition manifest and R13 preconditions as Commit 2 so subsequent executors can diff against a fixed prior commit; then run the F-9c lifecycle sweep (Commit 3) and F-10 research sweep (Commit 4) as separate bulk-data commits gated by externally-verifiable sha256 / merge-base / cli.py:268 re-validations. Final task replays the R10 integration test to convert sweep-anxiety into a CI gate.

## Tasks

### Task 1: Replace justfile:212 archive predicate

- **Files**: `justfile`
- **What**: Replace the JSON-only `grep -q '"feature_complete"' "$events_log"` predicate at line 212 with the JSON+YAML alternation regex from R1, and add an immediately-preceding comment naming both event formats.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current line 212 reads: `grep -q '"feature_complete"' "$events_log" || continue`
  - Replacement: `grep -qE '"event":[[:space:]]*"feature_complete"|^[[:space:]]*event:[[:space:]]*feature_complete[[:space:]]*$' "$events_log" || continue`
  - Comment on the line above (line 211 region) names both formats — e.g., `# Match both NDJSON-form ("event": "feature_complete") and YAML-block-form (event: feature_complete) entries.`
  - Recipe surrounds at lines 190–223 (Pass 1: build candidate slug list); do not touch any other line.
  - macOS BSD `grep -E` portability constraint per spec: use `[[:space:]]*` and `^...$` anchors; do not introduce `\b`.
- **Verification**: `grep -nE '"event":\[\[:space:\]\]\*"feature_complete"\|\^\[\[:space:\]\]\*event:\[\[:space:\]\]\*feature_complete\[\[:space:\]\]\*\$' justfile | wc -l | tr -d ' '` = `1` AND output line begins with `212:` — pass if both true. Then `sed -n '211p' justfile | grep -q 'feature_complete'` — pass if exit 0 (preceding comment names both formats by mentioning the token).
- **Status**: [ ] pending

### Task 2: Extend `bin/cortex-archive-rewrite-paths` with `--exclude-dir`, slug validation, and `research/archive` exclusion; wire `--exclude-dir` through `just lifecycle-archive`

- **Files**: `bin/cortex-archive-rewrite-paths`, `justfile`
- **What**: Add an argparse `--exclude-dir` repeatable flag (R2) that normalizes values to root-relative `Path` objects and merges into `EXCLUDED_REL_PREFIXES` at runtime; add slug-shape validation (R3) that exits 2 before any file walk; extend the static `EXCLUDED_REL_PREFIXES` tuple with `Path("research") / "archive"` (R4); add a `--exclude-dir` repeatable parameter to the `lifecycle-archive` recipe so the consolidated set from R7 reaches the helper invocation at line 276.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Argparse signature lives at `bin/cortex-archive-rewrite-paths:164–189`; add a `parser.add_argument("--exclude-dir", action="append", default=[], dest="exclude_dir", ...)` entry.
  - Normalization rules (R2): trailing slash stripped, leading `./` stripped, absolute paths resolved relative to `--root`, out-of-root paths exit 2 with stderr matching `out-of-root`. Implement as a private helper `_normalize_exclude_dir(value: str, root: Path) -> Path`.
  - Runtime merge: after `_parse_args` returns, normalize each `--exclude-dir` value via the new helper and merge with `EXCLUDED_REL_PREFIXES` into a per-call exclude tuple; thread the merged tuple through `_iter_markdown_files` (currently reads the module-level constant — change to accept the tuple as a parameter, default = `EXCLUDED_REL_PREFIXES`).
  - Slug validation (R3): `re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug)`; on miss, write `cortex-archive-rewrite-paths: invalid slug: {slug}` to stderr and `return 2` BEFORE any `_iter_markdown_files` invocation. Validation runs against every value in `args.slug`.
  - Static tuple extension (R4): change line 64–69 to include `Path("research") / "archive"` as a fifth element. Boundary semantics docstring at lines 14–19 already covers it.
  - `EXCLUDED_DIR_NAMES` constant (line 60) is name-only; not modified.
  - Atomic-write contract at lines 131–136 is unchanged; argparse-only addition.
  - Stdout NDJSON contract at lines 201–206 unchanged; `--exclude-dir` does not change output schema.
  - `justfile:276` currently calls `rewrite_json=$(bin/cortex-archive-rewrite-paths --slug "$slug")`. Modify the recipe to accept and forward `--exclude-dir` values. Pattern: parse `--exclude-dir <path>` repeatable arg into a `exclude_dir_args=()` bash array (alongside the existing `--dry-run` and `--from-file` parsing in the head of the recipe), and pass `"${exclude_dir_args[@]}"` to the helper invocation at line 276 and to the dry-run preview's `grep -rlE` at line 247–253 (the dry-run pattern walks `*.md` directly via grep — same `--exclude-dir=` flag forwarding so its preview matches the helper's actual exclusions).
  - Auto-mirror: pre-commit hook at `.githooks/pre-commit` regenerates `plugins/cortex-core/bin/cortex-archive-rewrite-paths` from canonical `bin/cortex-archive-rewrite-paths` automatically on commit. Do not edit the mirror manually.
  - Wiring co-location: this task ships both the helper change (canonical) and the recipe change that consumes the new flag, so `bin/cortex-check-parity` does not emit W003 on the post-commit-1 state.
- **Verification**:
  - Helper acceptance (R2 happy): `python3 bin/cortex-archive-rewrite-paths --slug foo --exclude-dir research/repo-spring-cleaning --exclude-dir ./research/opus-4-7-harness-adaptation/ --dry-run --root .` exits 0 and stdout NDJSON shows `rewritten_files` containing zero paths under either excluded dir — pass if `python3 -c "import json,sys; o=json.load(sys.stdin); paths=o.get('rewritten_files',[]); sys.exit(0 if all(not (p.startswith('research/repo-spring-cleaning/') or p.startswith('research/opus-4-7-harness-adaptation/')) for p in paths) else 1)" < <(...)` returns 0.
  - Helper acceptance (R2 reject): `python3 bin/cortex-archive-rewrite-paths --slug foo --exclude-dir /tmp/outside --dry-run --root .` exits 2 AND stderr contains substring `out-of-root` — pass if both true.
  - Helper acceptance (R3): `python3 bin/cortex-archive-rewrite-paths --slug ../etc --dry-run --root .` exits 2 AND stderr contains substring `invalid slug` — pass if both true.
  - Helper acceptance (R4): `grep -nE 'research[/]archive' bin/cortex-archive-rewrite-paths` returns ≥ 1 match within the `EXCLUDED_REL_PREFIXES` tuple (lines 64–69 region) — pass if grep exit 0 with line number in that region.
  - Recipe forwarding: `just lifecycle-archive --dry-run --exclude-dir research/repo-spring-cleaning` exits 0 and the `rewrite candidates:` section omits `research/repo-spring-cleaning/...` paths — pass if `! just lifecycle-archive --dry-run --exclude-dir research/repo-spring-cleaning | grep -q 'research/repo-spring-cleaning/'`.
- **Status**: [ ] pending

### Task 3: Extend `tests/test_archive_rewrite_paths.py` with `--exclude-dir` and slug-validation cases

- **Files**: `tests/test_archive_rewrite_paths.py`
- **What**: Add pytest cases covering R2's three normalization variants (trailing slash, leading `./`, absolute), the R2 out-of-root rejection (exit 2 + stderr `out-of-root`), the R3 slug-shape rejection (exit 2 + stderr `invalid slug`, no file opens), and the R4 `research/archive` exclusion (a citation under `research/archive/<slug>/` is not rewritten by default).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - File is currently ~14978 bytes; cases follow the existing tmp_path + repo-fixture pattern.
  - For R3 "no file opens" assertion: monkey-patch `cortex_archive_rewrite_paths._iter_markdown_files` (or `pathlib.Path.open` at module scope) to raise; assert the test's `subprocess.run` still exits 2 because validation runs before any walk.
  - For R4 exclusion test: create a `research/archive/<slug>/note.md` containing `lifecycle/<slug>/spec.md`; run helper with `--slug <slug>`; assert the file is NOT in `rewritten_files`.
  - Helper runs as a subprocess in existing tests (`subprocess.run([sys.executable, str(HELPER_PATH), ...])`) — follow the same pattern.
- **Verification**: `pytest tests/test_archive_rewrite_paths.py -q` exits 0 — pass if all tests pass. Then `pytest tests/test_archive_rewrite_paths.py -q --collect-only | grep -cE '(exclude_dir|invalid_slug|research_archive)'` ≥ `5` (three normalization cases + reject + slug + research-archive) — pass if count ≥ 5.
- **Status**: [ ] pending

### Task 4: Extend `cortex_command/init/handler.py` to register `research/` (R9 implementation)

- **Files**: `cortex_command/init/handler.py`
- **What**: In `_run`'s register branch, derive `research_target = str(repo_root / "research") + "/"` directly after the existing `lifecycle_target = scaffold.check_symlink_safety(repo_root)` call (no `check_symlink_safety` for research — cortex does not scaffold `research/`); add a second `settings_merge.register(repo_root, research_target, home=home)` call after the existing register; in the `--unregister` early-branch, add a third `settings_merge.unregister(resolved_path, str(resolved_path / "research") + "/", home=home)` call.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `_run` body lives at lines 114–199; register call at line 197.
  - Step 2 (symlink-safety gate) at line 149 → derive `research_target` immediately below it.
  - Step 7 (register call) at line 197 → add second register call below it.
  - `--unregister` early-branch at lines 123–139; legacy_target_path + wide_target_path are at lines 125–126; add `research_target_path = str(resolved_path / "research") + "/"` and a third `settings_merge.unregister(resolved_path, research_target_path, home=home)` after line 138.
  - Two-register ordering invariant (R9 acceptance): lifecycle FIRST, research SECOND. Don't reorder.
  - Independence (R9): the two register calls run sequentially; if research register fails after lifecycle succeeds, half-registered state persists. `cortex init --update` recovers idempotently per existing pattern at handler.py:18–19.
  - Marker-decline + `--update` paths at lines 157–189 do not change — register/unregister calls are at the tail of `_run`.
- **Verification**: `python3 -c "import ast; tree=ast.parse(open('cortex_command/init/handler.py').read()); calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='register']; assert len(calls)==2, len(calls); print('OK')"` prints `OK` — pass if exit 0. Then `grep -c "settings_merge.unregister" cortex_command/init/handler.py` = `3` — pass if count = 3 (legacy lifecycle/sessions, wide lifecycle/, plus new research/).
- **Status**: [ ] pending

### Task 5: Extend `cortex_command/init/tests/test_settings_merge.py` with R9 dual-registration coverage

- **Files**: `cortex_command/init/tests/test_settings_merge.py`
- **What**: Add 8 dual-registration test cases covering R9's enumerated behaviors: (a) happy-path register-creates-settings (both entries appear); (b) sibling-key preservation (other JSON keys untouched); (c) idempotency (running register twice yields one of each entry); (d) order preservation (`[lifecycle/, research/]` order, not reversed); (e) malformed-sandbox refusal (existing R14 gate still rejects); (f) unregister-removes both entries; (g) unregister-idempotent (pre-R9 install missing the `research/` entry unregisters cleanly); (h) partial-failure recovery (`--update` adds the missing `research/` entry on a half-registered settings).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - Test file follows pytest tmp_path fixture pattern; existing tests use `home: Path` keyword to point `~/.claude/settings.local.json` writes at the tmp dir.
  - Use the existing `_invoke(args, home, repo)` helper pattern (or equivalent) where each test calls the handler with synthetic `args = argparse.Namespace(...)`.
  - For (h): seed `~/.claude/settings.local.json` with a half-registered `[lifecycle/]` allowWrite, run `cortex init --update`, assert `[lifecycle/, research/]` after.
  - For (e): existing malformed-sandbox fixture remains; assert dual-registration still refuses with the same error.
  - For (g): seed `~/.claude/settings.local.json` with only `[lifecycle/]`; run `cortex init --unregister`; assert allowWrite is empty (or absent) and exit 0.
  - Wikilinks-style comment headings (`# (a) happy-path ...`) for greppability.
- **Verification**: `pytest cortex_command/init/tests/test_settings_merge.py -q -k 'dual_registration'` exits 0 — pass if all dual-registration tests pass. Then `pytest cortex_command/init/tests/test_settings_merge.py -q --collect-only -k 'dual_registration' | grep -c '::test_'` ≥ `8` — pass if ≥ 8 dual-reg test functions exist.
- **Status**: [ ] pending

### Task 6: Add `tests/test_lifecycle_references_resolve.py` integration test + sentinel fixture

- **Files**: `tests/test_lifecycle_references_resolve.py`, `tests/fixtures/lifecycle_references/broken-citation.md`
- **What**: Implement R10's integration test that enumerates every git-tracked `*.md` via `git ls-files '*.md'`, applies the five citation-form regexes from spec §"Slug-and-citation grammar", asserts each extracted slug resolves to either `lifecycle/<slug>/` or `lifecycle/archive/<slug>/`. Add a parametrized negative-case variant that runs the same extraction over `tests/fixtures/lifecycle_references/broken-citation.md` and asserts the test detects the deliberately-broken slug. Add coverage assertions: `total_resolved >= 50`, plus `>= 1` match per form across the five forms.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Five citation-form regexes are defined in spec.md §"Slug-and-citation grammar" (the `<slug>` grammar `re.fullmatch(r'[a-z0-9][a-z0-9-]*', slug)` plus four wikilink/path-form regexes). The test must implement the five forms verbatim; do not paraphrase or simplify them. The bare-slug `lifecycle_slug:` form is parsed from YAML frontmatter — non-empty scalar string only; lists or non-string scalars must fail with `malformed lifecycle_slug:` naming the file path.
  - Walker contract: git-tracked only via `subprocess.run(["git", "ls-files", "*.md"], capture_output=True, text=True, check=True).stdout.splitlines()` — no separate exclusion list, no filesystem walk.
  - Resolution check: for each extracted `slug`, assert `Path(f"lifecycle/{slug}").is_dir() or Path(f"lifecycle/archive/{slug}").is_dir()`.
  - Coverage assertions: `assert total_resolved >= 50, f"resolved only {total_resolved}"`; for `form, count in per_form.items(): assert count >= 1, f"no matches for form {form}"`.
  - Negative-case fixture content at `tests/fixtures/lifecycle_references/broken-citation.md`: a markdown body containing exactly one slash-form citation `lifecycle/this-slug-does-not-exist/research.md`. The parametrized variant runs the extraction over the fixture path (NOT via `git ls-files`) and asserts the test's resolution logic detects the broken slug (test fails with a message naming `broken-citation.md:<line>:this-slug-does-not-exist`).
  - The fixture is added to `git ls-files` after Task 7's commit; the main test must skip the fixture path (filter: `if "tests/fixtures/lifecycle_references/" in path: continue`) so the fixture's deliberately-broken citation does not cause the main test to fail.
  - Per spec edge case "lifecycle_slug field is a list or non-string scalar": if any backlog file's `lifecycle_slug:` is a YAML list or non-string scalar, the test fails with `malformed lifecycle_slug:` naming the file path.
- **Verification**: `pytest tests/test_lifecycle_references_resolve.py -q` exits 0 on the post-Task-7 commit — pass if exit 0 AND pytest report includes the line `total_resolved >= 50` (or test asserts pass) AND the negative-case parametrized variant runs and reports the broken-citation detection. Then `grep -q 'this-slug-does-not-exist' tests/fixtures/lifecycle_references/broken-citation.md` — pass if exit 0 (fixture present and contains the sentinel).
- **Status**: [ ] pending

### Task 7: Stage Tasks 1–6 and create Commit 1 via `/cortex-core:commit`

- **Files**: `justfile`, `bin/cortex-archive-rewrite-paths`, `plugins/cortex-core/bin/cortex-archive-rewrite-paths` (auto-regenerated mirror), `tests/test_archive_rewrite_paths.py`, `cortex_command/init/handler.py`, `cortex_command/init/tests/test_settings_merge.py`, `tests/test_lifecycle_references_resolve.py`, `tests/fixtures/lifecycle_references/broken-citation.md`
- **What**: Stage all files modified or created by Tasks 1–6 plus the auto-regenerated `plugins/cortex-core/bin/cortex-archive-rewrite-paths` mirror, then invoke `/cortex-core:commit` to produce Commit 1 with a message naming all four spec requirements landed (R1 predicate fix, R2/R3/R4 helper upgrades, R9 init extension, R10 integration test).
- **Depends on**: [1, 2, 3, 4, 5, 6]
- **Complexity**: simple
- **Context**:
  - The pre-commit hook at `.githooks/pre-commit` regenerates the plugin mirror from canonical `bin/cortex-archive-rewrite-paths`; if the hook is properly enabled (`just setup-githooks`), the mirror is staged automatically on `git add`.
  - Use `/cortex-core:commit` skill — never `git commit` manually per project convention.
  - Commit message body should reference R1, R2, R3, R4, R9, R10, the four ticket reqs that this commit closes; no MUST/CRITICAL escalation language is introduced (post-Opus 4.7 policy).
  - This commit is bisect-friendly: every test passes against this single commit (R10 test passes because all `lifecycle/<slug>` references are still pointing at unmoved top-level dirs).
- **Verification**: `git log --oneline HEAD~1..HEAD` shows exactly 1 new commit — pass if `wc -l` = 1. Then `git show --stat HEAD | grep -cE '(justfile|cortex-archive-rewrite-paths|test_archive_rewrite_paths\.py|init/handler\.py|test_settings_merge\.py|test_lifecycle_references_resolve\.py|broken-citation\.md)'` ≥ `7` — pass if count ≥ 7 distinct file paths.
- **Status**: [ ] pending

### Task 8: Generate disposition manifest, preconditions.json, backlog frontmatter; create Commit 2

- **Files**: `lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/disposition.md`, `lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/preconditions.json`, `backlog/169-fix-archive-predicate-and-sweep-lifecycle-and-research-dirs.md`
- **What**: Build the unified disposition manifest at `disposition.md` (frontmatter `manifest_sha256: <sha256>`, body markdown table partitioned into lifecycle dirs and research dirs); record #166 + #168 commit SHAs and the recording timestamp in `preconditions.json` per R13's schema; update `backlog/169-*.md` frontmatter `blocked-by: [166, 168]`. Stage all three and create Commit 2 via `/cortex-core:commit`.
- **Depends on**: [7]
- **Complexity**: complex
- **Context**:
  - **Disposition manifest body schema** (R5): markdown table with header `| slug | partition | predicate-hit | backlog-ref | cross-refs | recommended-action |`. `partition` ∈ `{lifecycle, research}`. `predicate-hit` ∈ `{json, yaml, none}` for lifecycle rows; `n/a` for research rows. `backlog-ref` cites the originating ticket number (or `none` for `feat-a/`-style detritus). `cross-refs` records live `lifecycle/<slug>` citations elsewhere. `recommended-action` ∈ `{archive-via-recipe, archive-manual, delete, keep-toplevel}`.
  - **Lifecycle partition discovery**: `for d in lifecycle/*/; do basename "$d"; done` filtered against the predicate (run in-line: `grep -qE '"event":[[:space:]]*"feature_complete"|^[[:space:]]*event:[[:space:]]*feature_complete[[:space:]]*$' "$d/events.log" 2>/dev/null && echo "$d json|yaml"`). Cross-check via `git worktree list` to skip active-worktree slugs (per `justfile:198–209` semantics).
  - **Research partition discovery**: `for d in research/*/; do basename "$d"; done`. Excluded: `research/repo-spring-cleaning` (alive epic #165 discovery), `research/opus-4-7-harness-adaptation` (alive epic #82). All others: `recommended-action: archive-via-recipe` (or `archive-manual` if not predicate-eligible — research/ has no predicate; all rows are `archive-manual` style git mv).
  - **Manual-archive lifecycle rows** (named in spec R6): `add-playwright-htmx-test-patterns-to-dev-toolchain`, `define-evaluation-rubric-update-lifecycle-spec-template-create-dashboard-context-md`, `run-claude-api-migrate-to-opus-4-7-on-throwaway-branch-and-report-diff`, `clean-up-active-sessionjson-when-overnight-session-transitions-to-phasecomplete`. Recommended-action: `archive-manual` for each; cross-refs column cites the surviving live citations.
  - **Delete row**: `feat-a/` (lifecycle partition) — recommended-action: `delete`.
  - **manifest_sha256 derivation**: `manifest_sha256` is the sha256 of the manifest body content (everything AFTER the closing `---` of frontmatter, including the table heading and body rows, with no leading/trailing whitespace normalization beyond what the writer emits). Compute via `sha256sum` (or `shasum -a 256` on macOS) of the body-only slice.
  - **preconditions.json schema** (R13 verbatim): `{"prereq_commits": {"166": "<sha>", "168": "<sha>"}, "recorded_at": "<ISO 8601>"}`.
  - **SHA derivation (deterministic via events.log blame)**: critical-review confirmed `git log --grep='#NNN'` is unreliable in this repo (returns the same planning-consolidation commit `c019e97` for both #166 and #168). The robust derivation reads the sibling lifecycle's events.log directly:
    1. For ticket #N, read `backlog/N-*.md`'s `lifecycle_slug:` frontmatter field (e.g., `lifecycle_slug: rewrite-readme-migrate-content-to-docs-setupmd-...`).
    2. Locate the first `feature_complete` event line in `lifecycle/<sibling-slug>/events.log` using the same predicate Task 1 uses (matches both NDJSON and YAML-block forms): `grep -nE '"event":[[:space:]]*"feature_complete"|^[[:space:]]*event:[[:space:]]*feature_complete[[:space:]]*$' lifecycle/<sibling-slug>/events.log | head -1 | cut -d: -f1` → captures the line number `<lnum>`.
    3. Run `git blame -L <lnum>,<lnum> --porcelain lifecycle/<sibling-slug>/events.log | head -1 | cut -d' ' -f1` to retrieve the SHA of the commit that added that line.
    This is fully automated (no operator step), deterministic (single canonical source per ticket), and correctly returns the feature_complete commit's SHA. Repeat for each ticket; record both SHAs in `preconditions.json` along with `recorded_at` (ISO 8601 UTC).
  - **Why not `git log --grep`**: the grep heuristic returns any commit subject mentioning `#NNN` — including planning, audit, consolidation, and forward-reference commits. The blame-based path queries the events.log line that the lifecycle skill itself writes at Complete phase, so the SHA is provably the feature_complete commit. The events.log file is checked in per project convention; `bin/cortex-archive-rewrite-paths` does not touch `.log` files (only `*.md`), so blame is stable across this lifecycle's own commits.
  - **Backlog frontmatter update**: `cortex-update-item 169-fix-archive-predicate-and-sweep-lifecycle-and-research-dirs blocked-by='[166, 168]'` (the helper accepts JSON-array values). Confirm by re-reading the file: `grep -A2 '^blocked-by:' backlog/169-fix-archive-predicate-and-sweep-lifecycle-and-research-dirs.md` shows the new list.
  - **Commit 2 structure**: stage `lifecycle/.../disposition.md`, `lifecycle/.../preconditions.json`, `backlog/169-*.md`, and any auto-rebuilt `backlog/index.{json,md}` (per the existing `just backlog-index` pre-commit hook); commit via `/cortex-core:commit`.
  - **Sequencing precondition**: this task aborts when ANY of the following holds:
    1. `backlog/166-*.md` has no `lifecycle_slug:` frontmatter field, OR the named dir does not exist.
    2. `lifecycle/<166-sibling-slug>/events.log` contains NO `feature_complete` event matching either NDJSON or YAML-block form (predicate identical to Task 1's).
    3. Same checks for `backlog/168-*.md` and its sibling lifecycle.
    4. The blame-derived SHA is not an ancestor of HEAD (`git merge-base --is-ancestor <sha> HEAD` exit ≠ 0).

    Any abort: stop with stderr message naming the failing condition; the operator completes the sibling lifecycle (run `/cortex-core:lifecycle <sibling-slug>` through the Complete phase, which writes the feature_complete event) and re-runs this task. The blame-derived SHA approach has no false-positive failure mode — if events.log has a feature_complete event, the SHA is definitionally the commit that wrote it.
- **Verification**:
  - `python3 -c "import json; o=json.load(open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/preconditions.json')); assert set(o['prereq_commits'].keys())=={'166','168'} and all(len(v)>=7 and set(v)<=set('0123456789abcdef') for v in o['prereq_commits'].values()) and 'recorded_at' in o; print('OK')"` prints `OK` — pass if exit 0.
  - `for sha in $(python3 -c "import json; o=json.load(open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/preconditions.json')); print('\n'.join(o['prereq_commits'].values()))"); do git merge-base --is-ancestor "$sha" HEAD; done` — pass if every loop iteration exits 0 (each recorded SHA is ancestor of HEAD).
  - `python3 -c "import re; data=open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/disposition.md').read(); m=re.search(r'^manifest_sha256:\s*([0-9a-f]{64})\s*$', data, re.MULTILINE); assert m, 'no manifest_sha256 frontmatter'; body=data.split('---',2)[2]; import hashlib; got=hashlib.sha256(body.encode()).hexdigest(); assert got==m.group(1), f'sha mismatch: stored {m.group(1)} computed {got}'; print('OK')"` prints `OK` — pass if exit 0 (frontmatter sha256 matches body content).
  - `grep -A2 '^blocked-by:' backlog/169-fix-archive-predicate-and-sweep-lifecycle-and-research-dirs.md | grep -E '166|168' | wc -l | tr -d ' '` ≥ `2` — pass if both ticket numbers appear.
  - `git log --oneline HEAD~1..HEAD` shows exactly 1 new commit AND `git show --stat HEAD | grep -E '(disposition\.md|preconditions\.json|169-.*\.md)'` returns ≥ 3 file paths — pass if both true.
- **Status**: [ ] pending

### Task 9: F-9c lifecycle sweep — re-validate, execute, write events.log; create Commit 3

- **Files**: `lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log`, `lifecycle/archive/<slug>/` (multiple — every predicate-eligible + 4 manual-archive slugs), and every `*.md` rewritten by `bin/cortex-archive-rewrite-paths`
- **What**: Verify R5 (dry-run sha256 + manifest body sha256 + lifecycle-partition set equality), R12 (`cortex_command/cli.py:268` lacks `"see docs/mcp-contract.md."`), R13 (#166/#168 SHAs ancestors of HEAD); on all-pass, run `just lifecycle-archive` for predicate-eligible dirs; perform `git mv lifecycle/<slug>/ lifecycle/archive/<slug>/ && bin/cortex-archive-rewrite-paths --slug <slug> --exclude-dir <consolidated-set>` for each of the 4 manual-archive dirs; `rm -rf lifecycle/feat-a/`. Append events.log entries with `dry_run_stdout_sha256`, `manifest_body_sha256`, `dry_run_match: true`, `cli_py_268_content: "<verbatim line>"`, `cli_py_268_updated: true`, `prereq_commits: {"166": "<sha>", "168": "<sha>"}`, `prereq_commits_ancestor_check: {"166": 0, "168": 0}`, `prereq_commits_present: true`. Stage everything and create Commit 3 via `/cortex-core:commit`.
- **Depends on**: [8]
- **Complexity**: complex
- **Context**:
  - **Pre-execution preflight (R5)**:
    1. `dry_run_output=$(just lifecycle-archive --dry-run)`; `dry_run_stdout_sha256=$(printf '%s' "$dry_run_output" | shasum -a 256 | cut -d' ' -f1)`.
    2. Read `disposition.md` body (everything after closing `---` of frontmatter), compute `manifest_body_sha256`; compare to stored `manifest_sha256` frontmatter — must match.
    3. Extract candidate slugs from `dry_run_output`'s `archive candidates:` block (everything between `archive candidates:` and `rewrite candidates:`, one slug per line, sans `lifecycle/` prefix and trailing `/`).
    4. Extract lifecycle-partition slugs from disposition.md body via Python (parse markdown table, filter `partition == 'lifecycle'` AND `recommended-action == 'archive-via-recipe'`).
    5. Assert the two sets are equal. On divergence: abort with stderr message naming the differing slugs; operator must refresh the manifest in Task 8 and re-commit before retrying.
  - **Pre-execution preflight (R12)**:
    - Read full `cli.py` content from HEAD via `git show HEAD:cortex_command/cli.py`. Capture line 268's content separately as `cli_py_268_content` for the events.log record (`git show HEAD:cortex_command/cli.py | sed -n '268p'`).
    - File-wide substring check: `git show HEAD:cortex_command/cli.py | grep -qv 'see docs/mcp-contract\.md\.'` — assert exit 0 (substring absent from the entire file, not just line 268). On miss: abort with stderr message naming R12 precondition; operator must land #166 before retrying. (Searching the full file rather than only line 268 is intentional: a concurrent commit that inserts or removes a line above 268 would silently shift the target string and defeat a line-number-pinned check.)
  - **Pre-execution preflight (R13)**:
    - Read `prereq_commits` from `preconditions.json`.
    - For each (`ticket`, `sha`) pair, run `git merge-base --is-ancestor "$sha" HEAD`; record exit code.
    - Assert all exit codes are 0. On non-ancestor at Task 9 (pre-Commit-3): abort with stderr message naming the ticket(s) whose SHAs are not ancestors of HEAD; operator must refresh `preconditions.json` (likely #166 or #168 was rebased) and re-commit Commit 2 before retrying. **On non-ancestor at Task 10 (post-Commit-3)**: abort with stderr message instructing the operator to (a) `git revert HEAD` (or `git reset --hard HEAD~1`) to undo Commit 3 first, (b) refresh `preconditions.json`, (c) re-commit Commit 2, (d) replay from Task 9. Skipping step (a) leaves Commits 3 and 4 chained on top of an invalidated preconditions baseline.
  - **Execution sequence** (post-preflight):
    1. `just lifecycle-archive --exclude-dir research/repo-spring-cleaning --exclude-dir research/opus-4-7-harness-adaptation` (consumes the consolidated set from R7; the recipe forwards to the helper at line 276 per Task 2's wiring). The recipe's per-slug loop is internally idempotent on partial completion (the candidate-slug list is rebuilt from `lifecycle/*/events.log` glob; already-moved slugs no longer match).
    2. For each of the 4 manual-archive slugs: `test -d "lifecycle/archive/$slug"` — if exit 0 (already moved), skip this slug; otherwise `git mv lifecycle/<slug>/ lifecycle/archive/<slug>/` followed by `bin/cortex-archive-rewrite-paths --slug <slug> --exclude-dir research/repo-spring-cleaning --exclude-dir research/opus-4-7-harness-adaptation`. The `test -d` guard makes the loop idempotent on partial completion (resuming after a crash skips already-moved slugs).
    3. `test -d lifecycle/feat-a/` — if exit 0, `rm -rf lifecycle/feat-a/`; otherwise skip (idempotent on retry).
    4. **Partial-completion recovery (operator action, not automated)**: if Task 9 crashes mid-loop and the working tree has both `lifecycle/<slug>/` and `lifecycle/archive/<slug>/` for unmoved/moved subsets, do NOT trigger the R5/R7 "refresh manifest" recovery — that would legitimize partial state. Instead, either (a) re-run Task 9 from the top (the idempotency guards above resume from the last successful move) OR (b) `git restore --staged --worktree lifecycle/` to revert all in-progress moves before re-running R5.
  - **Consolidated --exclude-dir set construction**: F-9c uses two named live dirs ONLY (`research/repo-spring-cleaning` and `research/opus-4-7-harness-adaptation`); the broader research-partition set from R7 is reserved for F-10 (where the research-archive set is the actual moves being made). For F-9c's lifecycle sweep, citations inside the F-10-archive-bound research dirs are NOT yet archived — they are still live; rewriting them in-place is desired (their citations should track lifecycle/<slug> → lifecycle/archive/<slug> moves). Only the two epic-discovery dirs are excluded so their original-state record is preserved for #165/#82 audit trails.
  - **events.log append**: Single JSON object per executor invocation; field order matches the spec's R5/R12/R13 acceptance signal field names verbatim:

    ```json
    {"ts": "<ISO 8601>", "event": "f9c_executor", "feature": "fix-archive-predicate-and-sweep-lifecycle-and-research-dirs", "dry_run_stdout_sha256": "<hex>", "manifest_body_sha256": "<hex>", "dry_run_match": true, "cli_py_268_content": "<verbatim line>", "cli_py_268_updated": true, "prereq_commits": {"166": "<sha>", "168": "<sha>"}, "prereq_commits_ancestor_check": {"166": 0, "168": 0}, "prereq_commits_present": true, "exclude_dir_args": ["research/repo-spring-cleaning", "research/opus-4-7-harness-adaptation"]}
    ```

  - **Commit 3 staging**: `git add lifecycle/archive/`, `git add lifecycle/<slug>` (for the staged moves), `git add lifecycle/.../events.log`, `git add` for every `*.md` rewritten by the helper (the recipe's manifest already records these in `lifecycle/archive/_manifest.jsonl` — read it to enumerate rewritten files for staging). `rm -rf lifecycle/feat-a/` is then committed as a deletion.
  - **Cleanup invariant**: post-Commit-3, `lifecycle/feat-a/` does not exist in the working tree or in HEAD; predicate-eligible top-level slugs no longer exist as `lifecycle/<slug>/` (moved to archive); 4 manual-archive slugs same.
- **Verification**:
  - `test ! -d lifecycle/feat-a/` exit 0 — pass if dir absent.
  - `for slug in add-playwright-htmx-test-patterns-to-dev-toolchain define-evaluation-rubric-update-lifecycle-spec-template-create-dashboard-context-md run-claude-api-migrate-to-opus-4-7-on-throwaway-branch-and-report-diff clean-up-active-sessionjson-when-overnight-session-transitions-to-phasecomplete; do test -d "lifecycle/archive/$slug" || { echo "missing: $slug"; exit 1; }; done` — pass if exit 0 (all 4 manual-archive dirs at archive path).
  - `grep -c '"event": *"f9c_executor"' lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log` ≥ `1` — pass if ≥ 1 (events.log content cross-check).
  - `python3 -c "import json; line=[l for l in open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log') if '\"f9c_executor\"' in l][-1]; o=json.loads(line); assert o['dry_run_match'] is True and o['cli_py_268_updated'] is True and o['prereq_commits_present'] is True and o['prereq_commits_ancestor_check']=={'166':0,'168':0}; print('OK')"` prints `OK` — pass if exit 0 (events.log content cross-check).
  - **R5 dry-run sha256 re-derivation (automated, with rollback trap)**: run the following inside a subshell with a trap that guarantees rollback even on mid-step failure:

    ```bash
    ( trap 'git checkout - 2>/dev/null; git stash pop 2>/dev/null' EXIT INT TERM
      git stash --include-untracked && \
      git checkout HEAD~1 && \
      just lifecycle-archive --dry-run | shasum -a 256 | cut -d' ' -f1 )
    ```

    The printed hex must equal the `dry_run_stdout_sha256` field in the f9c_executor events.log entry. Pass if they match. The `trap ... EXIT` ensures `git checkout -` and `git stash pop` always run on subshell exit (success, failure, or signal), preventing the operator from being left on detached HEAD with stashed work after a mid-step failure.
  - **Manifest body sha256 re-derivation (automated)**: `python3 -c "import hashlib; d=open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/disposition.md').read(); body=d.split('---',2)[2]; print(hashlib.sha256(body.encode()).hexdigest())"` — the printed hex must equal (a) the `manifest_sha256` field in disposition.md frontmatter AND (b) the `manifest_body_sha256` field in the f9c_executor events.log entry. Both comparisons must pass.
  - **R12 cli.py substring re-derivation (automated, file-wide)**: `git show HEAD:cortex_command/cli.py | grep -qv 'see docs/mcp-contract\.md\.'` — pass if exit 0 (substring absent from the entire file, not just line 268; this matches the spec's actual safety property and is robust against line-number drift from concurrent edits above 268). Then cross-check that the line-268 content recorded in events.log matches what HEAD currently shows at line 268: `test "$(git show HEAD:cortex_command/cli.py | sed -n '268p')" = "$(python3 -c "import json; line=[l for l in open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log') if '\"f9c_executor\"' in l][-1]; print(json.loads(line)['cli_py_268_content'])")"` — pass if exit 0.
  - **R13 prereq SHA re-derivation (automated)**: `python3 -c "import json; o=json.load(open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/preconditions.json')); print(' '.join(o['prereq_commits'].values()))"` — for each printed sha, run `git merge-base --is-ancestor <sha> HEAD` and assert exit 0. Then assert the `prereq_commits` field in the f9c_executor events.log entry equals the preconditions.json values: `python3 -c "import json; pc=json.load(open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/preconditions.json'))['prereq_commits']; line=[l for l in open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log') if '\"f9c_executor\"' in l][-1]; el=json.loads(line)['prereq_commits']; assert pc==el, f'mismatch: {pc} vs {el}'; print('OK')"` — pass if prints `OK`.
- **Status**: [ ] pending

### Task 10: F-10 research sweep — re-validate, execute, write events.log; create Commit 4

- **Files**: `research/archive/` (new directory), `research/archive/<slug>/` (multiple — every research-partition slug from manifest), `lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log`, `~/.claude/settings.local.json` precondition (read-only check; no mutation), every `*.md` rewritten by `bin/cortex-archive-rewrite-paths`
- **What**: Verify the R7 binding (research partition still equals manifest), R12, R13, and sandbox `allowWrite` precondition (research/ entry present); on all-pass, `mkdir research/archive/`, `git mv research/<slug>/ research/archive/<slug>/` for every manifest-listed research slug, and invoke `bin/cortex-archive-rewrite-paths --slug <slug>` per moved slug with the consolidated `--exclude-dir` set (research-partition-being-archived dirs excluded so their citations are preserved as historical record). Append events.log entries with `manifest_body_sha256`, `f10_research_set_match: true`, `exclude_dir_args` (sorted = manifest research partition + 2 named live), `cli_py_268_content`, `cli_py_268_updated: true`, `prereq_commits`, `prereq_commits_ancestor_check`. Stage everything and create Commit 4 via `/cortex-core:commit`.
- **Depends on**: [9]
- **Complexity**: complex
- **Context**:
  - **Pre-execution preflight (R7)**:
    1. Read manifest body, compute `manifest_body_sha256`; compare to `manifest_sha256` frontmatter — must match (catches manifest tampering between Commit 2 and now).
    2. Re-survey current `research/*/` dirs at top level (excluding `research/archive/` once it exists, but at this point it doesn't yet); construct current research-partition set.
    3. Extract manifest research-partition set from disposition.md.
    4. Assert sets are equal. On divergence: abort with stderr message instructing the operator to (a) `git revert HEAD` to undo Commit 3, (b) refresh the manifest, (c) re-commit Commit 2, (d) replay from Task 9 (per spec R7 binding rule: F-9c may need to be replayed if F-10's set diverged because of an interim research dir creation; skipping (a) leaves Commit 3's lifecycle sweep on top of an invalid manifest baseline).
  - **Pre-execution preflight (R12 + R13)**: identical to Task 9's preflight, EXCEPT R13's non-ancestor abort uses the post-Commit-3 recovery sequence (revert Commit 3 first, then refresh preconditions.json, re-commit Commit 2, replay from Task 9).
  - **Pre-execution preflight (sandbox allowWrite for research/)**: read `~/.claude/settings.local.json` (or `$HOME/.claude/settings.local.json`); assert `sandbox.filesystem.allowWrite` array contains the absolute path of `research/` (with trailing slash, per R9 normalization). On absent: abort with stderr message instructing the operator to run `cortex init --update` and retry. Do not silently re-run `cortex init` on the operator's behalf (per spec edge case).
  - **Consolidated --exclude-dir set construction (R7)**: take every research-partition slug from the manifest as `research/<slug>` (post-archive these become `research/archive/<slug>` but the helper walks the pre-move repo state at invocation time, so we exclude the pre-archive paths to preserve the citations inside dirs that ARE about to be archived); add the two named live dirs `research/repo-spring-cleaning` and `research/opus-4-7-harness-adaptation`. Result is sorted-set-equal to: `<manifest research partition (pre-move paths)> ∪ {research/repo-spring-cleaning, research/opus-4-7-harness-adaptation}`.
  - **Execution sequence** (post-preflight):
    1. `mkdir -p research/archive/` (idempotent via `-p`).
    2. For each research-partition slug in the manifest: `test -d "research/archive/$slug"` — if exit 0 (already moved), skip; otherwise `git mv research/<slug>/ research/archive/<slug>/`. The `test -d` guard makes the loop idempotent on partial completion.
    3. For each moved slug: `bin/cortex-archive-rewrite-paths --slug <slug> --exclude-dir <consolidated>`. The helper's regex patterns at lines 105–121 only match `lifecycle/<slug>`, not `research/<slug>` — citations to `research/<slug>` paths in other tracked `*.md` files are NOT rewritten by this helper. Per spec R8 acceptance, the requirement is only the `mkdir + git mv` move; the helper invocation is included for events.log audit-trail completeness (records `rewritten_files: []` per slug). See Scope Boundaries for the documented `research/<slug>` citation gap.
    4. **Partial-completion recovery (operator action)**: if Task 10 crashes mid-loop with some slugs at `research/<slug>/` and others at `research/archive/<slug>/`, do NOT trigger the R7 "refresh manifest" recovery — that would legitimize partial state. Instead, either (a) re-run Task 10 from the top (the idempotency guards above resume from the last successful move) OR (b) `git restore --staged --worktree research/` to revert all in-progress moves before re-running R7's preflight.
  - **events.log append**:

    ```json
    {"ts": "<ISO 8601>", "event": "f10_executor", "feature": "fix-archive-predicate-and-sweep-lifecycle-and-research-dirs", "manifest_body_sha256": "<hex>", "f10_research_set_match": true, "cli_py_268_content": "<verbatim line>", "cli_py_268_updated": true, "prereq_commits": {"166": "<sha>", "168": "<sha>"}, "prereq_commits_ancestor_check": {"166": 0, "168": 0}, "exclude_dir_args": ["<sorted consolidated set>"], "sandbox_research_registered": true}
    ```

  - **Commit 4 staging**: `git add research/archive/`, `git add research/<slug>` (for the staged moves), `git add lifecycle/.../events.log`, plus any rewritten `*.md` files (likely zero, but stage anything the helper touched).
  - **Cleanup invariant**: post-Commit-4, `research/archive/` exists; manifest-listed research slugs no longer exist at `research/<slug>/`; `research/repo-spring-cleaning/` and `research/opus-4-7-harness-adaptation/` remain at top level.
- **Verification**:
  - `test -d research/archive/` exit 0 — pass if dir present.
  - `ls research/archive/ | wc -l | tr -d ' '` ≥ `25` — pass if count ≥ 25 (per R8 acceptance).
  - `test -d research/repo-spring-cleaning/ && test -d research/opus-4-7-harness-adaptation/` exit 0 — pass if both dirs present at top level.
  - `grep -c '"event": *"f10_executor"' lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log` ≥ `1` — pass if ≥ 1 (events.log content cross-check).
  - `python3 -c "import json; line=[l for l in open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log') if '\"f10_executor\"' in l][-1]; o=json.loads(line); assert o['f10_research_set_match'] is True and o['cli_py_268_updated'] is True and o['sandbox_research_registered'] is True and o['prereq_commits_ancestor_check']=={'166':0,'168':0}; print('OK')"` prints `OK` — pass if exit 0 (events.log content cross-check).
  - **Manifest body sha256 re-derivation (automated)**: `python3 -c "import hashlib; d=open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/disposition.md').read(); body=d.split('---',2)[2]; print(hashlib.sha256(body.encode()).hexdigest())"` — the printed hex must equal (a) the `manifest_sha256` field in disposition.md frontmatter AND (b) the `manifest_body_sha256` field in the f10_executor events.log entry. Both comparisons must pass.
  - **R12 cli.py substring re-derivation (automated, file-wide)**: `git show HEAD:cortex_command/cli.py | grep -qv 'see docs/mcp-contract\.md\.'` — pass if exit 0 (substring absent from the entire file; matches the spec's safety property and is robust against line-number drift). Then cross-check that line 268's content recorded in events.log matches what HEAD currently shows at line 268: `test "$(git show HEAD:cortex_command/cli.py | sed -n '268p')" = "$(python3 -c "import json; line=[l for l in open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log') if '\"f10_executor\"' in l][-1]; print(json.loads(line)['cli_py_268_content'])")"` — pass if exit 0.
  - **R13 prereq SHA re-derivation (automated)**: `python3 -c "import json; o=json.load(open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/preconditions.json')); print(' '.join(o['prereq_commits'].values()))"` — for each printed sha, run `git merge-base --is-ancestor <sha> HEAD` and assert exit 0. Then assert the `prereq_commits` field in the f10_executor events.log entry equals the preconditions.json values: `python3 -c "import json; pc=json.load(open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/preconditions.json'))['prereq_commits']; line=[l for l in open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log') if '\"f10_executor\"' in l][-1]; el=json.loads(line)['prereq_commits']; assert pc==el, f'mismatch: {pc} vs {el}'; print('OK')"` — pass if prints `OK`.
  - **R7 research-partition set re-derivation (automated)**: parse the disposition.md table body to extract all rows where partition column equals `"research"` — collect their slugs as `research/<slug>` paths. Then compute: sorted re-derived set must equal `sorted(events.log f10_executor exclude_dir_args) minus ["research/repo-spring-cleaning", "research/opus-4-7-harness-adaptation"]`. Assert sorted equality: `python3 -c "import json; line=[l for l in open('lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log') if '\"f10_executor\"' in l][-1]; excl=sorted(json.loads(line)['exclude_dir_args']); assert 'research/repo-spring-cleaning' in excl and 'research/opus-4-7-harness-adaptation' in excl; print('OK')"` — pass if prints `OK` (sorted exclude_dir_args contains both named live dirs). For the research-partition set equality portion, parse disposition.md rows (partition=research) into `research/<slug>` paths and assert sorted equality against `excl` minus the two named live dirs.
- **Status**: [ ] pending

### Task 11: Run R10 integration test + R11 canary; record final verification

- **Files**: `lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log` (append final verification record)
- **What**: After all four commits land, run `pytest tests/test_lifecycle_references_resolve.py` and assert it passes with `total_resolved >= 50` and `>= 1` match per form across all five citation forms; run R11 canary content-grep against `backlog/029-add-playwright-mcp-for-dashboard-visual-evaluation.md`; append a `feature_complete` event to events.log on success. No new commit (this is verification of already-committed state).
- **Depends on**: [10]
- **Complexity**: simple
- **Context**:
  - **R10 test invocation**: `pytest tests/test_lifecycle_references_resolve.py -v 2>&1 | tee /tmp/r10-output.txt`; assert exit 0 AND tee output includes both `total_resolved` and the per-form counters (≥ 1 per form). Per spec R10 acceptance, the test must pass on the post-Task-10 state (every `lifecycle/<slug>` reference resolves to either `lifecycle/<slug>/` or `lifecycle/archive/<slug>/`).
  - **R11 canary**: `grep -q 'lifecycle/archive/add-playwright-htmx-test-patterns-to-dev-toolchain' backlog/029-add-playwright-mcp-for-dashboard-visual-evaluation.md` exit 0 — pass if the rewrite recipe successfully updated the citation in backlog #029 from `lifecycle/archive/add-playwright-htmx-test-patterns-to-dev-toolchain` to `lifecycle/archive/add-playwright-htmx-test-patterns-to-dev-toolchain` during Task 9's manual-archive rewrite step.
  - **events.log final record**: append `{"ts": "<ISO 8601>", "event": "feature_complete", "feature": "fix-archive-predicate-and-sweep-lifecycle-and-research-dirs", "tasks_total": 11, "rework_cycles": 0}` (per the lifecycle-archive predicate's expected schema). This event makes the lifecycle dir itself archive-eligible for a future sweep run.
  - The events.log append is a metadata-only edit; per spec edge case, it does not need a separate commit. The lifecycle's eventual feature_complete commit (Complete phase) will pick it up.
  - This task does NOT itself create a commit; it appends to events.log in working tree state, to be picked up by the Complete-phase commit.
- **Verification**:
  - `pytest tests/test_lifecycle_references_resolve.py -q` exit 0 — pass if all assertions hold AND coverage assertions (`total_resolved >= 50`, ≥ 1 per form) pass.
  - `grep -q 'lifecycle/archive/add-playwright-htmx-test-patterns-to-dev-toolchain' backlog/029-add-playwright-mcp-for-dashboard-visual-evaluation.md` exit 0 — pass if grep finds the rewritten citation (R11 content-grep canary).
  - `grep -c '"event": *"feature_complete"' lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/events.log` ≥ `1` — pass if event appended.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification rests on three load-bearing gates:

1. **Externally-verifiable executor records (R5/R7/R12/R13)**: every Tasks 9–10 events.log entry pairs each precondition assertion (manifest sha256, dry-run sha256, cli.py:268 substring, prereq SHAs ancestor check) with a captured artifact (hex, verbatim line, exit code) that a reviewer re-derives from the relevant commit. No gate accepts boolean-only attestation.

2. **R10 integration test (Task 11)**: walks every git-tracked `*.md` and asserts every `lifecycle/<slug>` reference (across five citation forms) resolves to either `lifecycle/<slug>/` or `lifecycle/archive/<slug>/`. Negative-case sentinel fixture proves the test detects deliberately-broken citations. Coverage assertions (`total_resolved >= 50`, ≥ 1 per form) prevent regex-bug false-passes. This is the load-bearing gate that converts sweep-anxiety into a CI gate for all future archive runs.

3. **R11 content-grep canary (Task 11)**: a documented quick-check spot-check that backlog #029's load-bearing citation was rewritten during Task 9. Supplements R10; not a substitute for it.

The 4-commit split is itself a verification mechanism: Commit 2's manifest is the read-against artifact for Commits 3 and 4's R5/R7 preflight diffs; merging the manifest into a sweep commit defeats external verifiability.

## Veto Surface

- **Heavyweight rewind on R7 / R12 / R13 abort post-Commit-3**: any of three preflight gates failing at Task 10 (R7 manifest divergence, R12 cli.py substring regression, R13 prereq-SHA non-ancestor) requires the same recovery: `git revert HEAD` to undo Commit 3, refresh the manifest or preconditions.json, re-commit Commit 2, replay from Task 9. The plan documents this for all three failure modes (Task 9 R12/R13 abort messages, Task 10 R7 abort message, the pre-execution preflight bullets). Alternative: a partial sweep semantic (move only the slugs still satisfying the manifest, emit a warning) — rejected because it would leave the external-verifiability invariant ambiguous (events.log records the original manifest sha256 but the sweep no longer matches).
- **Task 9's --exclude-dir scope** (the 2 named live dirs only, NOT the broader research-partition set): per spec R7, the consolidated set with research-partition slugs is reserved for F-10. F-9c only protects the 2 alive epic dirs. Alternative: extend Task 9 to use the full F-10 consolidated set, preserving research-partition citations across both sweeps. This trades simpler audit (2 named excludes) for symmetric protection.
- **Task 8's #166/#168 SHA discovery (resolved post-critical-review)**: the original `git log --grep='#NNN'` heuristic was rejected — critical review confirmed it returned the same wrong commit (`c019e97 Consolidate #166+#167 ...`) for both tickets in the current repo. Replaced with deterministic events.log blame-based derivation: read each ticket's `lifecycle_slug:` from its backlog file, locate the `feature_complete` event line in the sibling's events.log, `git blame -L <line>,<line>` to retrieve the SHA. Fully automated, deterministic, and provably returns the feature_complete commit. Alternative considered and rejected: operator-supplied SHAs via env vars or manual `preconditions.json` edit — would break autonomous overnight execution which is cortex-command's core feature; the blame approach is automated AND correct.
- **Task 10's `bin/cortex-archive-rewrite-paths --slug <research-slug>` invocation per moved research dir**: this invocation is functionally a no-op for `research/<slug>` paths (the helper only rewrites `lifecycle/<slug>` patterns). Plan keeps the invocation for events.log audit-trail completeness per spec R7 acceptance. Alternative: skip the helper invocation in Task 10 and document the limitation in events.log via a `helper_skipped: true` field. User may prefer this if events.log noise is a concern.

## Scope Boundaries

Per spec § Non-Requirements, all out: DR-2 visibility cleanup (gitignore-hide / `.cortex/` relocation); README rewrite (#166); doc reorg (#166); code/script junk deletion (#168); modifications to other `cortex-archive-*` bin/ utilities; predicate change in any tool other than `justfile:212`; backfill of historical events.log files to YAML format; CLAUDE.md content past 100 lines; symlink-safety gate for `research/`; bare-slug wikilinks `[[<slug>]]` without `lifecycle/` prefix; auto-migration of `research/` registration on plain `cortex init`.

**Acknowledged gap — `research/<slug>` citation breakage post-F-10**: F-10 moves ~30 research dirs to `research/archive/<slug>/` via `git mv` only. `bin/cortex-archive-rewrite-paths` matches `lifecycle/<slug>` patterns ONLY (helper lines 105–121); citations to `research/<slug>` paths in tracked `*.md` files are NOT rewritten. Critical review identified ~111 backlog `discovery_source: research/<slug>` frontmatter fields, ~30 in-flight lifecycle artifacts citing swept research slugs (including forward-operational escalation directives in `lifecycle/tighten-1b-plan-agent-prompt-*/spec.md:90` and similar), `docs/sdk.md:9`'s hyperlink, `docs/setup.md:388`'s prose citation, plus cross-citations inside surviving research dirs. All become broken paths post-F-10. Per spec R8 acceptance, the requirement is only `mkdir + git mv`; rewriting `research/<slug>` citations is not in scope of this lifecycle. Closing the gap requires either (a) extending the rewrite helper to match `research/<slug>` patterns OR (b) a follow-on ticket to bulk-rewrite citations after the sweep. R10's integration test does NOT catch this — it only validates `lifecycle/<slug>` resolution. Spec edge case 82's claim that "R10's integration test catches" body-cited archived slugs applies only to `lifecycle/` citations, not `research/` citations. Operator should be aware that `/cortex-core:refine` Discovery Bootstrap loads `discovery_source:` paths as agent context and will silently fail to load research from swept slugs until citations are rewritten.
