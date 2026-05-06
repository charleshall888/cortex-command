# Specification: Extract /refine resolution into bin/cortex-resolve-backlog-item with bailout

## Problem Statement

`/refine` Step 1 today resolves fuzzy input (numeric ID, kebab-slug, title phrase, or ad-hoc topic) into a backlog item via agent-side prose: the agent runs ad-hoc Glob/Grep/Read calls and applies `slugify()` rules manually from `skills/refine/SKILL.md:31`. This is non-deterministic in a load-bearing way (the agent can fingerprint the slugify rules incorrectly, producing a wrong `lifecycle-slug`), and consumes 3–4 tool calls on every invocation. Extracting the deterministic resolution into a `bin/cortex-resolve-backlog-item` script with a bailout-on-ambiguity exit contract gives `/refine` a guaranteed-correct happy path while preserving today's inline disambiguation flow on the unhappy path. Beneficiaries: every `/refine` invocation (correctness + small latency win); every future skill that needs the same resolution (reusable infrastructure).

## Requirements

1. **Script exists at canonical path with executable bit.**
   - Acceptance: `test -x bin/cortex-resolve-backlog-item && echo OK` exits 0 and prints `OK`.

2. **Script shebang is `#!/usr/bin/env python3` (self-contained Python, no `uv run` dependency).**
   - Acceptance: `head -1 bin/cortex-resolve-backlog-item` outputs `#!/usr/bin/env python3`.

3. **Script does NOT import the `cortex_command` package** (avoids `cortex_command/__init__.py:13-15` install_guard blast radius during overnight sessions).
   - Acceptance: `grep -E "^(from|import) cortex_command" bin/cortex-resolve-backlog-item` returns no matches (exit 1).

4. **Script contains the cortex-log-invocation shim line within its first 50 lines** (enforced by `.githooks/pre-commit` Phase 1.6 via `bin/cortex-invocation-report --check-shims`).
   - Acceptance: `bin/cortex-invocation-report --check-shims` exits 0 with `bin/cortex-resolve-backlog-item` not flagged.

5. **Script implements `slugify()` locally** (re-implementing the 5-line body of `cortex_command/common.py:slugify` at L76-81; see Technical Constraints for why local re-implementation is required). A drift test asserts behavioral equivalence between the local re-implementation and the canonical function over BOTH (a) corpus equivalence — every title in `backlog/[0-9]*-*.md` is run through both implementations and outputs must match exactly — AND (b) the following 10 named adversarial cases: empty input `""`, all-special-chars `"!!!"`, pure underscores `"___"`, pure slashes `"///"`, leading-hyphens-after-strip `"---foo"`, embedded slash `"a/b"`, embedded underscore `"a_b"`, Unicode `"café"`, backtick-bearing title ``"Make `just setup` additive"``, parenthesis-bearing title `"Define rubric (spike)"`. Each adversarial case is a separately-named test so future maintainers can grow the inventory by failure mode.
   - Acceptance: `pytest tests/test_resolve_backlog_item.py -k drift -v` exits 0 with at least 11 cases (≥10 named adversarial + ≥1 corpus equivalence iteration).

6. **Numeric input matches by filename prefix `^NNN-`, NOT by `id:` frontmatter field** (98 of 148 backlog items lack `id:`; filename prefix is the only correct strategy).
   - Acceptance: `pytest tests/test_resolve_backlog_item.py -k numeric -v` exits 0 covering at least: input `109` resolves to `109-extract-...md`; input `999` (nonexistent) bails with no-match.

7. **Kebab-slug input matches the filename slug after stripping `NNN-` prefix and `.md` suffix.**
   - Acceptance: `pytest tests/test_resolve_backlog_item.py -k kebab -v` exits 0 covering at least: input `extract-refine-resolution-into-bin-resolve-backlog-item-with-bailout` resolves to ticket 109; input `does-not-exist` bails with no-match.

8. **Title-phrase input matches if EITHER predicate fires:**
   - **Predicate A** (raw substring): `lower(input)` is a substring of `lower(title)` from frontmatter.
   - **Predicate B** (slugified substring): `slugify(input)` is a substring of `slugify(title)`.

   The candidate set is the **set-theoretic union** of the two predicates' results, deduplicated by filename. n=1 → resolve; n>1 → ambiguous bail; n=0 → no-match bail. Both sides are normalized symmetrically (input and title are lowercased for predicate A; both are slugified for predicate B). Internal whitespace in the input is preserved before predicate A; predicate B's slugify normalizes it. The predicate is documented as a one-paragraph summary in `clarify.md` §1 AND in the script's `--help` for completeness — the spec is the source of truth.
   - Acceptance: `pytest tests/test_resolve_backlog_item.py -k title_phrase -v` exits 0 covering at least: (a) `uniquely_identifies` — phrase resolves to one item; (b) `extract_multiple` — `extract` matches multiple items, exits 2; (c) `nonsense_no_match` — input matching zero items exits 3; (d) `axis_predicate_a_only` — input `"4.7"` (against tickets containing literal `"4.7"`) matches via raw substring but not slugified; (e) `axis_predicate_b_only` — input `"backlog-pick"` against ticket 108 (`"Extract /backlog pick ready-set into bin/backlog-ready"`) matches via slugified-substring but not raw; (f) `axis_mixed_case` — input `"GPG"` against title containing `"GPG"` matches via case-folded predicate A; (g) `axis_whitespace` — input `"create  skill"` (double space) matches a title `"Create skill"` via predicate B (slugify collapses whitespace).

9. **Exit codes form a 5-class surface: 0/2/3/64/70.**
   - `0`: unambiguous match. JSON object printed on stdout. Stderr empty (or quiet log).
   - `2`: ambiguous match (n > 1). Stdout empty. Stderr lists up to 5 candidates as `<filename>\t<title>` lines plus a one-line "ambiguous: <count> matches" header. If n > 5, append `... (<count - 5> more)`.
   - `3`: no match (n = 0). Stdout empty. Stderr prints `no match for '<input>'`.
   - `64`: usage error (missing or malformed argument; e.g., empty/whitespace input). Stdout empty. Stderr prints usage.
   - `70`: internal software/IO error (BSD sysexits.h `EX_SOFTWARE`) — malformed YAML frontmatter, missing/empty backlog directory, file-permission failures, or other unexpected runtime exception. Stdout empty. Stderr prints a diagnostic message naming the affected file or path.
   - Acceptance: `pytest tests/test_resolve_backlog_item.py -k exit_codes -v` exits 0 covering all five codes via subprocess.

10. **Stdout JSON schema on exit 0 is exactly the closed set `{filename, backlog_filename_slug, title, lifecycle_slug}` — no `frontmatter` field, no body.**
    - Acceptance: `bin/cortex-resolve-backlog-item 109 | python3 -c "import json,sys; d=json.load(sys.stdin); assert set(d.keys()) == {'filename','backlog_filename_slug','title','lifecycle_slug'}, d.keys()"` exits 0.

11. **`lifecycle_slug` follows the same fallback chain as `cortex_command.overnight.backlog.BacklogItem.resolve_slug()`**: `lifecycle_slug` frontmatter → spec/research dirname → `slugify(title)`.
    - Acceptance: `pytest tests/test_resolve_backlog_item.py -k lifecycle_slug -v` exits 0 covering all three branches with explicit fixtures.

12. **`skills/refine/SKILL.md` Step 1 invokes the script AND documents the per-exit-code agent action.** The Step 1 prose must include: (a) the `cortex-resolve-backlog-item <input>` invocation; (b) for exit 0 — parse stdout JSON and proceed to Step 2; (c) for exit 2 — read stderr candidates and ask the user to disambiguate; (d) for exit 3 — switch to Context B (ad-hoc topic) per `clarify.md` §1; (e) for exit 64 or 70 — halt and surface the stderr diagnostic to the user; do NOT fall through to disambiguation prose (these are bugs, not user-input ambiguity).
    - Acceptance: `grep -c 'cortex-resolve-backlog-item' skills/refine/SKILL.md` ≥ 1 AND `python3 -c "import re,sys; t=open('skills/refine/SKILL.md').read(); m=re.search(r'## Step 1.*?(?=## Step 2)', t, re.S); body=m.group(0) if m else ''; codes=[c for c in ['0','2','3','64','70'] if re.search(rf'(exit[^a-z]*{c}\b|code[^a-z]*{c}\b|\\\\b{c}\\\\b.*(stderr|stdout|halt|disambig|Context B|JSON))', body, re.I)]; sys.exit(0 if len(codes) >= 5 else 1)"` exits 0 (verifies all five codes are mentioned in Step 1).

13. **`skills/refine/references/clarify.md` §1 is rewritten to encode the per-exit-code branching as the canonical specification.** Section §1 contains: (a) the script invocation; (b) the JSON-on-exit-0 parse instruction with the four field names; (c) per-exit-code prose for each of {2 ambiguous, 3 no-match, 64 usage-error, 70 internal-error} matching the SKILL.md Step 1 actions in Requirement 12; (d) the Context-A-vs-Context-B distinction; (e) a one-paragraph summary of the title-phrase predicate from Requirement 8. Slugify rule details (the four regex transformations) are removed — they live in the script source.
    - Acceptance: `grep -q 'cortex-resolve-backlog-item' skills/refine/references/clarify.md` exits 0 AND between `### 1. Resolve Input` and the next `###` header ALL of the following are present: `0`, `2`, `3`, `64`, `70`, `Context A`, `Context B`, `slugify(input)` AND the literal regex pattern `[_/]` is absent (slugify rule details removed). No line-count cap applies.

14. **Plugin mirror at `plugins/cortex-interactive/bin/cortex-resolve-backlog-item` matches the canonical source byte-for-byte after `just build-plugin`.**
    - Acceptance: `just build-plugin && diff -q bin/cortex-resolve-backlog-item plugins/cortex-interactive/bin/cortex-resolve-backlog-item` exits 0 with no output.

15. **Pre-commit dual-source drift check passes.**
    - Acceptance: `.githooks/pre-commit` (run via `git commit` or directly) exits 0 with the new files staged.

16. **Parity gate (`bin/cortex-check-parity`) passes; new script is wired via in-scope SKILL.md reference, NOT via the parity-allowlist exception file** (`bin/.parity-exceptions.md`). This is distinct from the Claude harness `permissions.allow` allowlist addressed in Open Decisions; "allowlist" in this requirement refers exclusively to the parity-gate exception file.
    - Acceptance: `bin/cortex-check-parity` exits 0 AND `grep -c 'cortex-resolve-backlog-item' bin/.parity-exceptions.md` = 0.

17. **Project-level committed `.claude/settings.json` permits the new script's invocation by bare name** via a per-script `permissions.allow` row. The committed file (NOT `.claude/settings.local.json`, which is gitignored at the user-global level) gets a `Bash(cortex-resolve-backlog-item *)` entry under `permissions.allow`. If the file does not yet have a `permissions.allow` block, this requirement establishes one. Per-script (not wildcard) — every future `bin/cortex-*` script adds its own row, mirroring the parity-gate's per-script accountability.
   - Acceptance: `git ls-files .claude/settings.json` outputs that path (confirms file is committed) AND `python3 -c "import json; d=json.load(open('.claude/settings.json')); allow=d.get('permissions',{}).get('allow',[]); assert any('cortex-resolve-backlog-item' in p for p in allow), [p for p in allow if 'cortex-resolve' in p]"` exits 0.

18. **Tests cover Requirements 5–11 conditions plus failure modes via the established `tests/test_archive_rewrite_paths.py` pattern (importlib in-process for unit tests, subprocess for CLI exit-code/JSON contract).**
    - Acceptance: `pytest tests/test_resolve_backlog_item.py -v` exits 0 with ≥30 passing test cases (covering: 11 drift cases per R5; numeric/kebab/title-phrase axis tests per R6/R7/R8; 5 exit-code subprocess tests per R9; JSON schema test per R10; 3 lifecycle_slug fallback branches per R11; plus the edge cases enumerated in the Edge Cases section — `missing_title`, `empty_after_slugify`, `empty_title_slugify`).

## Non-Requirements

- **Does NOT add runtime adoption telemetry** for happy-path-rate observation. Ticket 103 is `status: complete` and provides `cortex-log-invocation` JSONL telemetry; this script consumes that infrastructure (via the shim line) but does not emit additional metrics.
- **Does NOT modify `bin/cortex-update-item`** or its `_find_item()` helper. The new resolver is a sibling, not a refactor of existing resolution.
- **Does NOT extend the JSON schema with frontmatter or body content.** Downstream `/refine` phases that need additional fields read the file themselves.
- **Does NOT introduce a `cortex_command/backlog/` Python package.** The bash dispatchers' branch-(a) reference (`python3 -m cortex_command.backlog.update_item`) remains aspirational.
- **Does NOT alter the disambiguation prose in `clarify.md` §1 step 2/3** — only §1 step 1's matching rules. The Context-A/Context-B distinction stays intact.
- **Does NOT support glob or regex input patterns.** Numeric, kebab-slug, and title-phrase only.
- **Does NOT write any files.** Read-only resolution.

## Edge Cases

- **Backlog item edited concurrently mid-resolve**: `cortex_command/common.py:atomic_write()` (L366-407) uses tempfile + `os.replace`, so reads see either pre-or-post snapshot, never torn writes. Resolver returns whichever snapshot it observed; agent's downstream Read of the file gets the freshest version. **Document** in script docstring; no defensive locking needed.
- **Invocation during overnight session**: Resolver does not import `cortex_command` package, so `install_guard.check_in_flight_install()` is not triggered. Behavior identical in daytime and overnight contexts.
- **Multi-match title phrase (e.g., `extract`)**: Bails with exit 2 listing up to 5 candidates on stderr. Today, 25 titles contain "overnight," 14 "lifecycle," 10 "extract" — multi-match is a frequent path, not a corner case.
- **Sequel-item shadowing (e.g., "Create skill X" exists, then "Create skill X v2" is added)**: Substring-match logic surfaces both as candidates → exit 2 → user disambiguates. Eliminates today's silent first-match-wins behavior in `update_item.py:_find_item:156-160`.
- **Empty or whitespace-only input**: Exit 64 (usage). Stderr usage string.
- **Input matches more than 5 items**: Stderr shows the first 5 alphabetically by filename + a `... (N more)` footer line. Exit 2.
- **Backlog item with malformed YAML frontmatter**: Resolver raises `yaml.YAMLError` → caught at top level → exit 70 (EX_SOFTWARE). Stderr prints `<filename>: failed to parse frontmatter`. Distinct from ambiguous/no-match.
- **Backlog directory missing or empty**: Exit 70. Stderr prints `backlog directory not found at <path>` or `backlog directory contains no NNN-*.md items`.
- **Numeric input with leading zeros (e.g., `009`)**: Matches filenames starting with `009-` exactly; does not auto-strip leading zeros. Documented in `--help`.
- **UUID-form input (e.g., `c5cf3e45-...`)**: Out of scope per Non-Requirements (UUID matching exists in `update_item.py:_find_item` but is not part of `/refine` Step 1's documented surface). Treated as title-phrase input — likely no-match.
- **Filename with no `title:` field**: Resolver synthesizes a fallback title from the filename (strip `NNN-` prefix and `.md` suffix) for predicate B's slugify-vs-slugify comparison only. Predicate A is skipped (no raw title to match against). The synthesized title is also used as the `title` field in the JSON output on resolve. Documented in `--help` and tested via `pytest tests/test_resolve_backlog_item.py -k missing_title -v`.
- **Title-phrase input slugifies to empty string** (e.g., input `"!!!"` or `"___"`): both predicates degenerate. Predicate A: empty `lower(input)` is a substring of every title — would match all 148 items. Predicate B: empty slugified input is a substring of every slugified title — same. Resolver detects empty-after-slugify input and returns exit 64 (usage error) with stderr `input '<input>' resolves to empty after normalization; provide more characters`.
- **Backlog item title slugifies to empty** (e.g., title is all special characters): item is excluded from predicate B comparison and only matchable via predicate A. Falls under R5's named adversarial case `"!!!"`.

## Changes to Existing Behavior

- **MODIFIED**: `skills/refine/SKILL.md` Step 1 (L22-35) — was prose-only inline tool-call sequence; now invokes the script first with explicit per-exit-code branching prose (per Requirement 12).
- **MODIFIED**: `skills/refine/references/clarify.md` §1 (L7-23) — rewritten to encode the per-exit-code contract as the canonical specification (per Requirement 13); slugify rule details removed; title-phrase predicate documented as one-paragraph summary.
- **ADDED**: `bin/cortex-resolve-backlog-item` (top-level canonical, plugin mirror auto-built).
- **ADDED**: `tests/test_resolve_backlog_item.py`.
- **ADDED**: `Bash(cortex-resolve-backlog-item *)` row in committed `.claude/settings.json` under `permissions.allow` (establishes the `permissions.allow` block in the committed project settings if it does not yet exist).

## Technical Constraints

- **SKILL.md-to-bin parity** (`requirements/project.md:27`): the script MUST be referenced from an in-scope file (Requirement 12 satisfies this via `skills/refine/SKILL.md`). Allowlist exception is not used.
- **cortex-log-invocation shim** (`requirements/observability.md:53-59`, `.githooks/pre-commit:93-115`): mandatory in first 50 lines (Requirement 4).
- **Dual-source mirror via `just build-plugin`** (CLAUDE.md, `justfile:475-507`): rsync `--include='cortex-*'` auto-mirrors any new `bin/cortex-*`; pre-commit Phase 4 fails on drift; the script + plugin mirror must land in one commit (Requirements 14, 15).
- **install_guard blast radius** (`cortex_command/__init__.py:13-15`, `install_guard.py:184-202`): the script MUST NOT import `cortex_command.*` or it will spuriously fail with `InstallInFlightError` during overnight sessions, which the agent would misread as ambiguous-match. Local re-implementation of `slugify` + drift test mitigates (Requirements 3, 5).
- **Atomic-write read-snapshot semantics** (`cortex_command/common.py:atomic_write` L366-407): reads see either pre-or-post snapshot, never torn writes. No locking needed; document in script docstring.
- **Exit code 64** follows BSD `sysexits.h` `EX_USAGE` (universally recognized for usage errors); 2 and 3 follow the dev.to/InfoQ "1–2 user errors, 3–125 app-specific" convention. Exit code 70 (`EX_SOFTWARE`) signals frontmatter/IO errors distinguishable from ambiguous/no-match.
- **stdout = JSON only on exit 0; stderr = human-readable prose for everything else** (Anthropic Claude Code hooks contract: stdout JSON parsed only on exit 0; exit 2 surfaces stderr to model). Never mix JSON and prose on the same stream.
- **Test pattern** follows `tests/test_archive_rewrite_paths.py`: `importlib.machinery.SourceFileLoader` for in-process unit tests + subprocess for CLI exit-code/JSON contract.
- **Existing `update_item.py:_find_item()` is not modified** — its first-match-wins behavior is load-bearing for callers that pass exact slugs/UUIDs. The new resolver is a sibling implementation, not a refactor.

## Open Decisions

None. The Claude harness permission-registration question raised by critical review was resolved in favor of committing the row to project-level `.claude/settings.json` (per Requirement 17) — chosen for portability across clones, durability through editor/machine changes, and pattern establishment for future `bin/cortex-*` scripts. Extending `cortex init` to manage `permissions.allow` is deferred to a separate ticket; this spec lands one explicit row in the committed file.
