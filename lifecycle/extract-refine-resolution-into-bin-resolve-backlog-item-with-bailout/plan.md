# Plan: extract-refine-resolution-into-bin-resolve-backlog-item-with-bailout

## Overview

Land Approach A' from `research.md` §Tradeoffs: a self-contained `bin/cortex-resolve-backlog-item` Python script with a locally re-implemented `slugify` (drift-tested against canonical), a 5-class exit-code surface (0/2/3/64/70), and a closed-set JSON contract on stdout. `skills/refine/SKILL.md` Step 1 and `skills/refine/references/clarify.md` §1 are rewritten to encode the per-exit-code branching as the canonical specification, with slugify regex details removed from prose. Plugin mirror auto-builds via `just build-plugin`; a project-committed `.claude/settings.json` `permissions.allow` row registers the script for bare-name invocation.

## Tasks

### Task 1: Implement `bin/cortex-resolve-backlog-item` core script
- **Files**: `bin/cortex-resolve-backlog-item`
- **What**: Self-contained Python 3 script that resolves a fuzzy input (numeric / kebab-slug / title-phrase) against `backlog/[0-9]*-*.md` and prints the closed-set JSON object on stdout (exit 0) or a candidate-list / no-match / usage / software-error diagnostic on stderr (exit 2/3/64/70). No `cortex_command` package import.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **Shebang**: `#!/usr/bin/env python3` (Requirement 2; precedent `bin/cortex-archive-rewrite-paths:1`).
  - **cortex-log-invocation shim** (line ≤50, Requirement 4): copy the verbatim one-liner from `bin/cortex-archive-rewrite-paths:46` (`import os, subprocess, sys; subprocess.run([os.path.join(os.path.dirname(os.path.realpath(__file__)), "cortex-log-invocation"), sys.argv[0], *sys.argv[1:]], check=False)`) immediately after the module docstring.
  - **Local `slugify`** (Requirement 5): re-implement the 5-line body of `cortex_command/common.py:slugify` (L76-81) in-script. Comment cites the canonical source path. No `from cortex_command.*` import.
  - **Frontmatter parser**: stdlib `yaml` (already used by `backlog/update_item.py:_parse_frontmatter` pattern). Read `title:` and `lifecycle_slug:` keys only — do NOT load body content.
  - **Argparse**: single positional argument `input` (the fuzzy string). `--help` documents per-exit-code semantics, the title-phrase predicate, leading-zero numeric handling, and atomic-read-snapshot semantics from spec Edge Cases. No additional flags.
  - **Resolution functions** (private, prefixed `_`):
    - `_resolve_numeric(input: str, items: list[Path]) -> list[Path]` — match by `^NNN-` filename prefix (Requirement 6). Verify input is `re.fullmatch(r"\d+", input)`.
    - `_resolve_kebab(input: str, items: list[Path]) -> list[Path]` — match `input` against `path.stem` after stripping `^\d+-` prefix (Requirement 7).
    - `_resolve_title_phrase(input: str, items: list[(Path, dict)]) -> list[Path]` — set-theoretic union of predicate A (`lower(input) in lower(title)`) and predicate B (`slugify(input) in slugify(title)`), deduped by filename. Whitespace preserved before predicate A; predicate B's slugify normalizes (Requirement 8).
  - **Dispatch**: try numeric, then kebab, then title-phrase. Each strategy that returns 1 → exit 0 with JSON; n>1 → exit 2 with candidates; n=0 → fall through to next strategy. After all three exhaust, exit 3 (no-match).
  - **Empty/whitespace input**: exit 64 with usage prose (Edge Cases — `empty_after_slugify`).
  - **JSON schema** (Requirement 10, exit 0 only): exactly `{"filename": str, "backlog_filename_slug": str, "title": str, "lifecycle_slug": str}`. No `frontmatter` key, no body. Computed: `filename = path.name`, `backlog_filename_slug = path.stem`, `title = frontmatter["title"]` or filename-derived fallback (Edge Cases — `missing_title`), `lifecycle_slug = frontmatter.get("lifecycle_slug") or slugify(title)` — mirroring `cortex_command/overnight/backlog.py:BacklogItem.resolve_slug` L100-115 fallback (Requirement 11). Spec/research dirname check is the second-tier fallback.
  - **Candidate list** (exit 2): write up to 5 `<filename>\t<title>` lines + a header `ambiguous: <count> matches` to stderr; if count > 5, append `... (<count - 5> more)` (Requirement 9).
  - **Software-error catch-all** (exit 70): top-level `try/except Exception` writes `<file>: failed to parse frontmatter` or `backlog directory not found at <path>` / `... contains no NNN-*.md items` to stderr per spec Edge Cases.
  - **Backlog dir resolution**: `Path(__file__).resolve().parent.parent / "backlog"` (matches `bin/cortex-archive-rewrite-paths` repo-root walking pattern). Override via `CORTEX_BACKLOG_DIR` env var for tests.
  - **Executable bit** (Requirement 1): `chmod +x bin/cortex-resolve-backlog-item` after creation.
- **Verification**: `test -x bin/cortex-resolve-backlog-item && head -1 bin/cortex-resolve-backlog-item | grep -qx '#!/usr/bin/env python3' && ! grep -E '^(from|import) cortex_command' bin/cortex-resolve-backlog-item && bin/cortex-invocation-report --check-shims` — pass if exit 0 (combines R1, R2, R3, R4 acceptance).
- **Status**: [x] completed

### Task 2: Add `tests/test_resolve_backlog_item.py`
- **Files**: `tests/test_resolve_backlog_item.py`
- **What**: ≥30 pytest cases covering Requirements 5–11 plus edge cases. Pattern follows `tests/test_archive_rewrite_paths.py` (importlib `SourceFileLoader` for in-process unit tests; subprocess for CLI exit-code/JSON contract).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - **Loader pattern**: copy the `_load_module()` helper from `tests/test_archive_rewrite_paths.py:37-54` and adapt the path to `bin/cortex-resolve-backlog-item`. Use it for unit-level access to `slugify`, `_resolve_numeric`, `_resolve_kebab`, `_resolve_title_phrase`.
  - **Subprocess pattern**: copy from `tests/test_archive_rewrite_paths.py:320-349`. Use a per-test `tmp_path / "backlog"` fixture and pass `env={"CORTEX_BACKLOG_DIR": str(tmp_path / "backlog"), **os.environ}`.
  - **Required test classes / function names** (the `-k drift|numeric|kebab|title_phrase|exit_codes|lifecycle_slug` pytest selectors in the spec must match — implement them as test-name substrings):
    - `test_drift_corpus_equivalence` — iterate every `title:` from `backlog/[0-9]*-*.md` (use the real backlog dir, not the fixture) and assert local `slugify(title) == cortex_command.common.slugify(title)`. Uses a `pytest.importorskip("cortex_command.common")` guard so the test skips cleanly when the package is unavailable. Counts as ≥1 of the 11 R5 cases (one parametrized case with N>=1 ids).
    - 10 named adversarial drift tests (one `def test_drift_adversarial_<label>` each per R5): `empty`, `all_special_chars`, `pure_underscores`, `pure_slashes`, `leading_hyphens_after_strip`, `embedded_slash`, `embedded_underscore`, `unicode_cafe`, `backtick_just_setup`, `parenthesis_spike`. Each asserts behavioral equivalence on its specific input.
    - `test_numeric_resolves_109`, `test_numeric_999_no_match` (R6).
    - `test_kebab_resolves_extract_refine`, `test_kebab_does_not_exist_no_match` (R7).
    - `test_title_phrase_uniquely_identifies`, `test_title_phrase_extract_multiple_ambiguous`, `test_title_phrase_nonsense_no_match`, `test_title_phrase_axis_predicate_a_only`, `test_title_phrase_axis_predicate_b_only`, `test_title_phrase_axis_mixed_case`, `test_title_phrase_axis_whitespace` (R8 — fixture titles tailored to each axis).
    - `test_exit_codes_zero_unambiguous`, `test_exit_codes_two_ambiguous`, `test_exit_codes_three_no_match`, `test_exit_codes_64_empty_input`, `test_exit_codes_70_malformed_frontmatter` (R9 — subprocess).
    - `test_json_schema_closed_set` (R10 — subprocess; assert `set(d.keys()) == {"filename","backlog_filename_slug","title","lifecycle_slug"}`).
    - `test_lifecycle_slug_frontmatter_wins`, `test_lifecycle_slug_dirname_fallback`, `test_lifecycle_slug_slugify_fallback` (R11 — three fixture variants).
    - `test_edge_missing_title` (Edge Cases — synthesized title when frontmatter lacks `title:`).
    - `test_edge_empty_after_slugify` (Edge Cases — input `"!!!"` → exit 64).
    - `test_edge_empty_title_slugify` (Edge Cases — fixture item whose title is all special chars; only matchable via predicate A).
  - **Total**: ≥1 corpus + 10 adversarial + 2 numeric + 2 kebab + 7 title-phrase + 5 exit-code + 1 JSON schema + 3 lifecycle_slug + 3 edge = 34 cases ≥ 30 (R18).
  - **Frontmatter fixture format**: minimal YAML — `---\ntitle: <T>\n---\n`. Fixtures are written by tests via `tmp_path.write_text()` (no on-disk fixture files).
- **Verification**: `pytest tests/test_resolve_backlog_item.py -v` — pass if exit 0 with ≥30 reported test cases (R18 acceptance).
- **Status**: [x] completed

### Task 3: Wire script into `skills/refine/SKILL.md` Step 1
- **Files**: `skills/refine/SKILL.md`
- **What**: Replace today's prose-only fuzzy-input flow at L22-35 with a `cortex-resolve-backlog-item <input>` invocation followed by per-exit-code branching prose covering all 5 codes (0, 2, 3, 64, 70).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - **Anchor**: existing Step 1 spans L22-35 per `research.md` §Today's `/refine` Step 1.
  - **Required prose elements** (all five codes per Requirement 12):
    - exit `0` → parse stdout JSON, proceed to Step 2 (downstream phases use the four named fields directly).
    - exit `2` → read stderr `<filename>\t<title>` candidate lines, ask user to disambiguate, then re-invoke or treat the user's choice as the resolved item.
    - exit `3` → switch to Context B (ad-hoc topic) per `clarify.md` §1.
    - exit `64` → halt and surface stderr usage diagnostic to user; do NOT fall through to disambiguation.
    - exit `70` → halt and surface stderr software-error diagnostic to user; do NOT fall through.
  - **Reference pattern**: existing `bin/cortex-*` invocation prose in other skills (e.g., grep for `cortex-update-item` callers in `skills/`).
  - **Caller enumeration**: this is the only file that invokes the script; no other skills call it today. `plugins/cortex-interactive/skills/refine/SKILL.md` is the auto-built mirror — do NOT edit it directly (Task 6 regenerates it).
- **Verification**: `grep -c 'cortex-resolve-backlog-item' skills/refine/SKILL.md` ≥ 1 AND the Requirement 12 regex `python3 -c "import re,sys; t=open('skills/refine/SKILL.md').read(); m=re.search(r'## Step 1.*?(?=## Step 2)', t, re.S); body=m.group(0) if m else ''; codes=[c for c in ['0','2','3','64','70'] if re.search(rf'(exit[^a-z]*{c}\b|code[^a-z]*{c}\b|\\b{c}\\b.*(stderr|stdout|halt|disambig|Context B|JSON))', body, re.I)]; sys.exit(0 if len(codes) >= 5 else 1)"` exits 0.
- **Status**: [x] completed

### Task 4: Rewrite `skills/refine/references/clarify.md` §1
- **Files**: `skills/refine/references/clarify.md`
- **What**: Encode the per-exit-code branching as the canonical specification (mirrors Task 3's SKILL.md prose). Remove the four slugify regex transformations from prose — they live in the script source. Document the title-phrase predicate as a one-paragraph summary.
- **Depends on**: [1, 3]
- **Complexity**: simple
- **Context**:
  - **Anchor**: existing §1 spans L7-23 per `research.md` §Today's `/refine` Step 1.
  - **Required content** (Requirement 13):
    - the script invocation;
    - JSON-on-exit-0 parse instruction citing `filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`;
    - per-exit-code prose for each of {2 ambiguous, 3 no-match, 64 usage-error, 70 internal-error} matching SKILL.md Step 1 wording;
    - Context A (resolved backlog item) vs Context B (ad-hoc topic) distinction (preserved from current §1);
    - one-paragraph summary of the title-phrase predicate (predicate A union predicate B; both sides normalized symmetrically).
  - **Required deletions**: any line containing the literal regex `[_/]` — the four slugify regex transformations move to the script source.
  - **Caller enumeration**: this is the only `clarify.md` instance — `plugins/cortex-interactive/skills/refine/references/clarify.md` is the auto-built mirror (Task 6).
- **Verification**: `grep -q 'cortex-resolve-backlog-item' skills/refine/references/clarify.md` exits 0 AND `python3 -c "import re,sys; t=open('skills/refine/references/clarify.md').read(); m=re.search(r'### 1\. Resolve Input.*?(?=\n###\s)', t, re.S); body=m.group(0) if m else ''; req=['0','2','3','64','70','Context A','Context B','slugify(input)']; missing=[r for r in req if r not in body]; bad='[_/]' in body; sys.exit(0 if not missing and not bad else 1)"` exits 0 (Requirement 13 acceptance).
- **Status**: [x] completed

### Task 5: Add committed `.claude/settings.json` `permissions.allow` row for the new script
- **Files**: `.claude/settings.json`
- **What**: Insert a `Bash(cortex-resolve-backlog-item *)` entry under `permissions.allow` in the project-level committed settings file. Establish the `permissions.allow` block if absent.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - File is already committed per `git ls-files .claude/settings.json`.
  - Use stdlib `json` to read, mutate, and write back with `indent=2` to preserve diff readability.
  - Per-script (not wildcard) — every future `bin/cortex-*` adds its own row, mirroring the parity-gate's per-script accountability (Requirement 17).
  - Do NOT touch `.claude/settings.local.json` — that file is gitignored at the user-global level and out of scope.
  - Existing pattern reference: `.claude/settings.local.json:179` shows `Bash(python3 -m cortex_command.*)` row; format the new entry the same way.
- **Verification**: `python3 -c "import json; d=json.load(open('.claude/settings.json')); allow=d.get('permissions',{}).get('allow',[]); assert any('cortex-resolve-backlog-item' in p for p in allow), [p for p in allow if 'cortex-resolve' in p]"` exits 0 (Requirement 17 acceptance).
- **Status**: [x] completed

### Task 6: Build plugin mirror and verify dual-source parity
- **Files**: `plugins/cortex-interactive/bin/cortex-resolve-backlog-item`, `plugins/cortex-interactive/skills/refine/SKILL.md`, `plugins/cortex-interactive/skills/refine/references/clarify.md` (all auto-generated by `just build-plugin`)
- **What**: Run `just build-plugin` to rsync-mirror canonical sources into the plugin tree, then assert byte-for-byte parity for the new script and the parity gate passes without an allowlist exception.
- **Depends on**: [1, 3, 4]
- **Complexity**: simple
- **Context**:
  - `justfile:475-507` rsync glob `--include='cortex-*'` auto-mirrors any new `bin/cortex-*` (no manifest edit; per `research.md` §Dual-source / parity enforcement).
  - `.githooks/pre-commit` Phase 4 fails on drift — running the build explicitly here catches problems before commit (Requirement 15).
  - Parity gate (`bin/cortex-check-parity`) is wired through Task 3's SKILL.md reference, NOT through `bin/.parity-exceptions.md` (Requirement 16).
- **Verification**: `just build-plugin && diff -q bin/cortex-resolve-backlog-item plugins/cortex-interactive/bin/cortex-resolve-backlog-item && bin/cortex-check-parity && [ "$(grep -c 'cortex-resolve-backlog-item' bin/.parity-exceptions.md)" = "0" ]` — pass if exit 0 (combines R14, R15, R16 acceptance).
- **Status**: [x] completed

## Verification Strategy

End-to-end verification after all tasks complete:

1. `pytest tests/test_resolve_backlog_item.py -v` — confirms ≥30 cases pass (R5–R11, R18).
2. `bin/cortex-resolve-backlog-item 109 | python3 -c "import json,sys; d=json.load(sys.stdin); assert set(d.keys()) == {'filename','backlog_filename_slug','title','lifecycle_slug'}"` — confirms the JSON contract on a real ticket (R10).
3. `bin/cortex-resolve-backlog-item extract-refine` (multi-match input) — confirms exit 2 + stderr candidate list on a real-corpus ambiguous case (R9).
4. `bin/cortex-check-parity && bin/cortex-invocation-report --check-shims` — confirms parity-gate and shim-gate pass with the new script in place (R4, R16).
5. `git diff --stat plugins/cortex-interactive/bin/ plugins/cortex-interactive/skills/refine/` shows the auto-mirrored changes; `.githooks/pre-commit` passes when staging (R14, R15).
6. Manual smoke: invoke `/refine 109` in a fresh session — agent should print the parsed JSON and proceed without ad-hoc Glob/Grep/Read calls. Interactive/session-dependent: covered in Implement-phase commit smoke.

## Veto Surface

- **Approach A' over Approach B**: research recommended A' (root-level structure with self-contained `bin/` script) over B (`cortex_command/backlog/` package) to avoid `install_guard.check_in_flight_install` blast radius during overnight sessions. The plan implements A'. If the user wants to reconsider B (with a runtime carve-out for the resolver), the plan needs a different Task 1 design.
- **Per-script `permissions.allow` row vs wildcard**: Task 5 lands one explicit `Bash(cortex-resolve-backlog-item *)` row, establishing the per-script-accountability pattern. A `Bash(cortex-* *)` wildcard would shorten future tickets but conflicts with the spec's chosen pattern (Requirement 17 prose) and makes the security surface harder to audit.
- **Local `slugify` re-implementation + drift test vs canonical import**: Task 1 re-implements the 5-line `slugify` body locally to avoid `cortex_command/__init__.py:13-15` install_guard import side effects. The drift test (Task 2) is the safety net. If the user prefers tighter coupling, Task 1 changes to a `sys.path` injection + `from cortex_command.common import slugify` (after verifying that submodule imports trigger `__init__.py`'s install_guard call, per `research.md` §Approach A' Verification).
- **5-class exit-code surface (0/2/3/64/70) vs 2-class (0/1)**: spec Requirement 9 locked in the 5-class surface; the adversarial agent argued for 0/1 in research §Open Questions §1. The plan implements 5-class. Reverting would simplify SKILL.md prose at the cost of losing the 64/70 distinction the spec preserved.

## Scope Boundaries

Explicitly excluded (maps to spec §Non-Requirements):

- **Runtime adoption telemetry** for happy-path-rate observation — ticket 103 owns this; this script consumes the cortex-log-invocation shim only.
- **Modifications to `bin/cortex-update-item` or `backlog/update_item.py:_find_item`** — first-match-wins behavior is load-bearing for write callers; the new resolver is a sibling.
- **`frontmatter` field in JSON output** — spec Requirement 10 closed-set excludes it. Downstream `/refine` phases that need additional fields read the file directly.
- **`cortex_command/backlog/` Python package** — bash dispatchers' branch-(a) reference remains aspirational; not materialized by this ticket.
- **Disambiguation-prose changes in `clarify.md` §1 step 2/3** — only step 1's matching rules are rewritten. Context-A/Context-B distinction stays intact.
- **Glob / regex input patterns** — numeric, kebab-slug, and title-phrase only.
- **UUID-form input** — out of scope per spec Edge Cases; treated as title-phrase input.
- **`cortex init` extension to manage `permissions.allow`** — deferred to a separate ticket per spec §Open Decisions.
- **File writes by the resolver** — read-only resolution.
