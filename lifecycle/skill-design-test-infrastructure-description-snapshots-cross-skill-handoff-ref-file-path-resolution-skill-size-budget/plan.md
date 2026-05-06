# Plan: skill-design-test-infrastructure-description-snapshots-cross-skill-handoff-ref-file-path-resolution-skill-size-budget

## Overview

Three new pytest test files (`test_skill_descriptions.py`, `test_skill_handoff.py`, `test_skill_size_budget.py`) plus a focused extension of the existing `tests/test_lifecycle_references_resolve.py` create four CI-time drift gates for cortex's skill-design surface. Shared helpers live in `tests/conftest.py`; declarative fixture YAMLs hold trigger-phrase and handoff schemas; per-test regression fixtures prove each gate detects its named failure mode without modifying canonical sources. Wiring lands via a new `test-skill-design` justfile recipe added to the existing `test-skills` aggregator.

## Tasks

### Task 1: Shared SKILL.md helpers in tests/conftest.py
- **Files**: `tests/conftest.py`
- **What**: Add four shared helpers used by tests 1, 2, and 4: canonical-skill enumerator, plugin-skill enumerator, SKILL.md frontmatter+description parser, REPO_ROOT resolver.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - REPO_ROOT discovery: `pathlib.Path(__file__).resolve().parent.parent` from `tests/conftest.py`.
  - **Required helper signatures (exact names — verification depends on these)**:
    - `repo_root() -> pathlib.Path`
    - `enumerate_skills(root: pathlib.Path, glob_pattern: str) -> list[pathlib.Path]` — generic enumerator accepting any root and glob; deduplicates by `Path.resolve()` for symlink safety. Used directly by Task 5's regression-variant which points it at `tests/fixtures/skill_size_budget/`.
    - `enumerate_canonical_skills() -> list[pathlib.Path]` — wraps `enumerate_skills(repo_root() / "skills", "*/SKILL.md")`.
    - `enumerate_plugin_skills() -> list[pathlib.Path]` — wraps `enumerate_skills(repo_root() / "plugins", "*/skills/*/SKILL.md")`.
    - `parse_skill_frontmatter(skill_path: pathlib.Path) -> dict` — uses stdlib `yaml.safe_load` over the `---`-delimited block at the top of SKILL.md; returns `{}` for skills with no frontmatter.
  - **Plugin-mirror dedup**: the cortex-core plugin's SKILL.md files are byte-identical regular-file copies (not symlinks) of canonical. `Path.resolve()` won't dedup them. The generic `enumerate_skills` helper accepts an optional `dedupe_by_content: bool = False` flag; `enumerate_plugin_skills()` passes `dedupe_by_content=True` to remove byte-identical duplicates against the canonical set, preventing dual failure messages on cap breaches. Implementation: hash each file's bytes via `hashlib.sha256`, dedup by hash when the flag is set. The regression-variant test from Task 5 calls the generic `enumerate_skills` directly with `dedupe_by_content=False`.
  - Pattern reference: `tests/test_check_parity.py` for stdlib parsing convention; `tests/test_lifecycle_references_resolve.py` for REPO_ROOT discovery convention.
- **Verification**: behavioral smoke test — `uv run python3 -c "import sys; sys.path.insert(0, 'tests'); from conftest import repo_root, enumerate_skills, enumerate_canonical_skills, enumerate_plugin_skills, parse_skill_frontmatter; assert callable(repo_root) and callable(enumerate_skills) and callable(enumerate_canonical_skills) and callable(enumerate_plugin_skills) and callable(parse_skill_frontmatter); skills = enumerate_canonical_skills(); assert len(skills) >= 10; fm = parse_skill_frontmatter(skills[0]); assert 'name' in fm or 'description' in fm; print('PASS')"` exits 0 with `PASS` printed — pass if exit 0.
- **Status**: [ ] pending

### Task 2: Test #1 — trigger-phrase corpus + canonical assertion + regression fixture
- **Files**:
  - `tests/fixtures/skill_trigger_phrases.yaml` (NEW)
  - `tests/test_skill_descriptions.py` (NEW)
  - `tests/fixtures/skill_design/skills/regression-fixture/SKILL.md` (NEW)
  - `tests/fixtures/skill_design/regression_skill_trigger_phrases.yaml` (NEW)
- **What**: Create the trigger-phrase fixture YAML covering lifecycle/refine/critical-review/discovery skills (sourced from current canonical SKILL.md descriptions on this branch — #178 is `status: complete`), the parametrized canonical-skill assertion test, and a regression-fixture variant that proves the failure-detection path works on a synthetic SKILL.md missing a declared phrase.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Fixture schema (per spec Req 1):
    ```yaml
    skills:
      lifecycle:
        must_contain: ["start a lifecycle", ...]
      refine:
        must_contain: ["refine backlog item", "prepare for overnight", ...]
      critical-review:
        must_contain: ["critical review", "pressure test", ...]
      discovery:
        must_contain: ["discover this", "decompose into backlog", ...]
    ```
  - Test parametrizes over each `(skill, phrase)` pair from the YAML and asserts the phrase is a case-sensitive substring of the canonical `skills/<skill>/SKILL.md` description frontmatter field.
  - Trigger phrase corpus authored as the LAST sub-task of this task per spec Req 21 — read each canonical SKILL.md description on `main` HEAD (or current branch HEAD post-#178) and select 3–5 high-signal phrases per skill. Phrases must already be substring-present.
  - Test uses helpers from Task 1 (`enumerate_canonical_skills`, `parse_skill_frontmatter`).
  - Regression-fixture variant: a separate `regression-fixture` skill at `tests/fixtures/skill_design/skills/regression-fixture/SKILL.md` with its own description, paired with `regression_skill_trigger_phrases.yaml` declaring a phrase deliberately absent from that fixture's description. The test loops the same assertion logic over the fixture pair wrapped in `pytest.raises(AssertionError, match=r"<dropped phrase from fixture YAML>")` — the `match=` regex ensures the AssertionError actually originates from the missing-phrase detection path, not from an unrelated bug raising AssertionError elsewhere. The test naming convention: include `_regression` in the test function name so `pytest -k regression` selects it.
  - Error message format (per spec Technical Constraints): on failure, name both the skill and the missing phrase. Aggregate findings into a single multi-line `AssertionError` (per `tests/test_lifecycle_references_resolve.py` precedent — no fail-fast).
  - Pattern reference: `tests/test_check_parity.py` for parametrize + AssertionError aggregation convention.
- **Verification**: `uv run pytest tests/test_skill_descriptions.py -q` — pass if exit 0 (covers both canonical and regression variants).
- **Status**: [ ] pending

### Task 3: Test #2 — handoff schema fixture + name-presence test + scope docstring + regression fixture
- **Files**:
  - `tests/fixtures/skill_handoff_schema.yaml` (NEW)
  - `tests/test_skill_handoff.py` (NEW)
  - `tests/fixtures/skill_design/handoff_rename/skill_handoff_schema.yaml` (NEW)
  - `tests/fixtures/skill_design/handoff_rename/skills/consumer-fixture/SKILL.md` (NEW)
- **What**: Create the handoff schema fixture (exactly one SKILL.md-prose-mediated field with no Python-test coverage: `discovery_source`), the parametrized name-presence test asserting each `(field, skill)` pair appears as a literal token in the producer or consumer's `SKILL.md` or `references/*.md`, and a regression fixture proving the rename-detection path works. **Plan deviation from spec Req 4**: spec listed two fields (`discovery_source`, `lifecycle_slug`); critical review surfaced empirical evidence that `lifecycle_slug` has 31+ Python attribute references in `tests/test_select_overnight_batch.py` and is also consumed by `cortex_command/overnight/` Python code — its rename break-loudly via Python tests. The same logic the spec applied to exclude `complexity`/`criticality`/`areas` ("Python imports break loudly") applies to `lifecycle_slug`. Narrowed to `discovery_source` only for consistency. Deviation logged in events.log.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Fixture schema (narrowed from spec Req 4):
    ```yaml
    handoff_fields:
      - name: discovery_source
        producer: discovery
        consumers: [lifecycle, refine]
    ```
  - Test parametrizes over each `(field, skill)` pair (one per producer + one per consumer per field — 3 pairs total: `(discovery_source, discovery)`, `(discovery_source, lifecycle)`, `(discovery_source, refine)`) and asserts the literal field-name token appears at least once in `skills/<skill>/SKILL.md` OR in any `skills/<skill>/references/*.md`. Search is plain substring (no regex), case-sensitive.
  - Module docstring **must** contain four verbatim phrases (per spec Req 6, adjusted for single-field scope) — check via `grep -c` in verification:
    1. `does NOT catch semantic drift`
    2. `Do not expand fixture YAML to encode value-shape rules`
    3. `Scope limited to SKILL.md-prose-mediated handoff fields with no Python-test coverage — currently the compound token discovery_source`
    4. `Python-mediated handoff fields (e.g., lifecycle_slug, complexity, criticality, areas read by cortex_command/) are out of scope for this test — coverage relies on existing Python tests`
  - Regression fixture: `tests/fixtures/skill_design/handoff_rename/skill_handoff_schema.yaml` declares a synthetic field expected in a synthetic consumer `tests/fixtures/skill_design/handoff_rename/skills/consumer-fixture/SKILL.md`; the consumer omits the field name. The regression-variant test points the same name-presence logic at the fixture pair, wrapped in `pytest.raises(AssertionError, match=r"<fixture field name>")` — the `match=` regex ensures the AssertionError originates from the missing-field-name detection path, not from an unrelated YAML-parse or path-resolution bug. Test name includes `_regression` for `pytest -k regression`.
  - Path-traversal safety (per spec Req 20): the simpler implementation reads only fixed `skills/<name>/SKILL.md` and `skills/<name>/references/*.md` glob results — no path is constructed from fixture content for the canonical test. For the regression fixture, the test enumerates the fixture's own subtree using a fixed path. Path-traversal safety check is trivially satisfied — document this in a one-line code comment in the test file.
  - Error message format: name both the field and the consumer-skill that's missing it. Aggregate findings.
- **Verification**: `uv run pytest tests/test_skill_handoff.py -q` — pass if exit 0; AND `for p in 'does NOT catch semantic drift' 'Do not expand fixture YAML to encode value-shape rules' 'Scope limited to SKILL.md-prose-mediated handoff fields only — compound tokens like discovery_source and lifecycle_slug' 'Python-mediated handoff fields (e.g., complexity, criticality, areas read by cortex_command/) are out of scope for this test — coverage relies on existing Python tests'; do test "$(grep -cF "$p" tests/test_skill_handoff.py)" -eq 1 || exit 1; done` exits 0 — pass if all four phrases appear exactly once.
- **Status**: [ ] pending

### Task 4: Test #3 — extend test_lifecycle_references_resolve.py with file_line_citation form
- **Files**:
  - `tests/test_lifecycle_references_resolve.py` (MODIFY)
  - `tests/fixtures/lifecycle_references/stale_file_line_citation.md` (NEW)
  - `tests/fixtures/lifecycle_references/path_traversal_fixture.md` (NEW)
- **What**: Add a `file_line_citation` regex form to the existing resolver test, with path-resolution rules (repo-relative for top-level dir prefixes; otherwise relative to citing file), traversal safety (`is_relative_to(REPO_ROOT)` + reject `..` segments), per-form coverage gate, and two regression fixtures (stale citation + path-traversal attempt).
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Existing file structure: `tests/test_lifecycle_references_resolve.py` has a `FORM_REGEXES` mapping (5 forms currently), a per-form coverage gate (`assert per_form_resolved[form] >= 1`), and a `total_resolved` aggregate gate. Read the file before editing to confirm the exact mapping name and gate locations.
  - New regex form `file_line_citation`: matches `<path>.<ext>:<line>(-<lend>)?` where `<ext>` ∈ {`md`, `py`, `sh`, `toml`, `yaml`, `yml`, `json`}. Add as a new entry in `FORM_REGEXES` (or whatever the existing mapping is named).
  - Path-resolution rules (per spec Req 9):
    - If cited path begins with one of `skills/`, `lifecycle/`, `plugins/`, `bin/`, `tests/`, `cortex_command/`, `docs/`, `requirements/`, `research/`, `backlog/` → resolve repo-relative (`REPO_ROOT / cited`).
    - Otherwise → resolve relative to the citing file's directory (`citing_file.parent / cited`).
  - Traversal safety (per spec Req 9):
    - After resolution, call `final_path.resolve()`, then check `final_path.is_relative_to(REPO_ROOT)` AND `'..' not in cited.split('/')` (raw cited path must not contain `..` segments — even one `..` rejects).
    - On safety failure, emit error containing literal substring `outside repo` (verbatim).
  - Line-count check: `len(open(final_path).readlines()) >= cited_line` (or `>= cited_lend` for range form).
  - Per-form coverage gate: `assert per_form_resolved['file_line_citation'] >= 1` — at least one real `file_line_citation` must resolve in the live corpus, defending against regex-bug false-pass.
  - Stale citation regression fixture: `tests/fixtures/lifecycle_references/stale_file_line_citation.md` cites a real file at a line number past its actual line count. Wrap the test logic in a `_regression` test that points the resolver at this fixture and asserts via `pytest.raises(AssertionError, match=r"line .*beyond|exceeds line count|stale_file_line_citation\.md")` — the `match=` regex ensures the AssertionError originates from the line-count-exceeded detection path, not from regex-parse or path-resolution bugs. Existing `broken-citation.md` fixture is the precedent pattern.
  - Path-traversal regression fixture: `tests/fixtures/lifecycle_references/path_traversal_fixture.md` contains `../../etc/passwd:1`. The traversal-safety check must trigger; assertion error contains `outside repo`. The `_regression` test asserts via `pytest.raises(AssertionError, match=r"outside repo")` — `match=` ensures the failure originates specifically from the traversal-safety check, not from an incidental file-not-found error.
  - **Reading prerequisite**: implementer must read `tests/test_lifecycle_references_resolve.py` in full before editing — the existing `FORM_REGEXES` mapping name and the per-form coverage gate location are derived from current file structure, not pre-pinned in this plan. Plan to spend ~3 minutes on this read before opening the editor.
  - Caller enumeration: `tests/test_lifecycle_references_resolve.py` is a test file with no callers (test runners discover it). Modification is local.
- **Verification**: `uv run pytest tests/test_lifecycle_references_resolve.py -q` exits 0 (canonical + regression variants); AND `grep -c file_line_citation tests/test_lifecycle_references_resolve.py` returns ≥ 2 — pass if both conditions hold.
- **Status**: [ ] pending

### Task 5: Test #4 — size-budget enumerator, cap, marker regex, and regression fixtures
- **Files**:
  - `tests/test_skill_size_budget.py` (NEW)
  - `tests/fixtures/skill_size_budget/over-cap-no-marker/SKILL.md` (NEW, 501-line synthetic)
  - `tests/fixtures/skill_size_budget/invalid-marker/SKILL.md` (NEW, has malformed marker)
  - `tests/fixtures/skill_size_budget/boundary-29-char-reason/SKILL.md` (NEW, marker with 29-char rationale at the regex boundary)
- **What**: Enumerate canonical and plugin SKILL.md files; assert each ≤500 lines unless a valid `<!-- size-budget-exception: ... -->` marker is present; validate marker format (≥30-char rationale, lifecycle-id, YYYY-MM-DD); produce regression fixtures that prove the over-cap and invalid-marker failure paths.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Marker regex (per spec Req 13): `<!--\s*size-budget-exception:\s*(?P<reason>.{30,}?),\s*lifecycle-id=(?P<lid>\d+),\s*date=(?P<date>\d{4}-\d{2}-\d{2})\s*-->`
  - Failure messages (per spec Req 14): on cap breach AND no valid marker, the message must contain the file path, the literal numeric line count vs. cap, AND both remediation hint substrings: `extract to references/` AND `<!-- size-budget-exception:` (the marker template prefix). Single multi-line `AssertionError`.
  - Enumeration: helpers from Task 1 (`enumerate_canonical_skills` + `enumerate_plugin_skills`); union both lists.
  - Regression fixtures live OUTSIDE the canonical glob — fixtures are at `tests/fixtures/skill_size_budget/`, not in `skills/` or `plugins/`. The regression-variant test calls Task 1's generic `enumerate_skills(repo_root() / "tests/fixtures/skill_size_budget", "*/SKILL.md")` to enumerate fixture SKILL.md files. The over-cap-no-marker test asserts via `pytest.raises(AssertionError, match=r"over-cap-no-marker.*501.*500")` — `match=` ensures the AssertionError originates specifically from the cap-breach detection path with both the line count (501) and cap (500) in the message. The invalid-marker test asserts via `pytest.raises(AssertionError, match=r"invalid size-budget-exception marker")`.
  - **Boundary-condition fixtures**: in addition to the over-cap and invalid-marker fixtures, add `tests/fixtures/skill_size_budget/boundary-29-char-reason/SKILL.md` (marker present but rationale is exactly 29 characters — should be rejected) to probe the `.{30,}` regex boundary. A 30-char rationale should pass; 29 should fail. The `_regression` boundary test asserts the 29-char marker is treated as invalid and the file falls through to over-cap-without-valid-marker handling. Test name includes `_regression`.
  - `over-cap-no-marker/SKILL.md`: 501 lines, no marker → triggers cap breach with all 4 required failure-message tokens.
  - `invalid-marker/SKILL.md`: contains `<!-- size-budget-exception: too short -->` (rationale < 30 chars) → triggers invalid-marker error containing the literal string `invalid size-budget-exception marker` and the file path.
  - Synthetic SKILL.md fixtures only need a frontmatter block + enough body lines to hit 501 lines. Use a body line like `# filler line N` repeated.
  - Pattern reference: `tests/test_check_parity.py` for `Violation`-style aggregation if useful, though a simpler list-of-error-strings pattern suffices.
- **Verification**: `uv run pytest tests/test_skill_size_budget.py -q` exits 0 (canonical pass + regression variants demonstrating both failure paths) — pass if exit 0.
- **Status**: [ ] pending

### Task 6: Document SKILL.md size cap and marker convention in requirements/project.md
- **Files**: `requirements/project.md`
- **What**: Add one bullet to the Architectural Constraints section documenting the 500-line SKILL.md cap and the `<!-- size-budget-exception: ... -->` marker convention. Pattern-matches the existing "SKILL.md-to-bin parity enforcement" bullet (project.md:29). **Plan deviation from spec Non-Requirement** ("No documentation file updates"): critical review argued the marker convention is a contributor-facing authoring rule that needs a discoverability surface beyond test-failure-message recall, and that adding to an existing doc file is not "proactive doc creation" per CLAUDE.md. Empirical: `skills/diagnose/SKILL.md` is at 489/500 lines today — the next routine edit will trip the gate without a documented rule. Deviation logged in events.log.
- **Depends on**: [5]
- **Complexity**: trivial
- **Context**:
  - Insertion point: after the existing "SKILL.md-to-bin parity enforcement" bullet at `requirements/project.md:29` (use `grep -n "SKILL.md-to-bin parity enforcement" requirements/project.md` to confirm line at edit time).
  - New bullet text (verbatim — keeps prose terse and pattern-matched to siblings):
    > **SKILL.md size cap**: SKILL.md files are capped at 500 lines per Anthropic skill-authoring guidance (`tests/test_skill_size_budget.py` enforces). Exceptions land via in-file `<!-- size-budget-exception: <reason ≥30 chars>, lifecycle-id=<NNN>, date=<YYYY-MM-DD> -->` marker (modeled on `bin/.parity-exceptions.md` schema). Default remediation is extracting content to `skills/<name>/references/`; a marker is appropriate only when the SKILL.md inherently exceeds the cap (e.g., dense protocol surfaces with no extractable references).
  - Caller enumeration: `requirements/project.md` is read by `requirements/` consumers (refine, research, lifecycle skills) but no automated parser depends on the bullet's exact line number — additions are safe.
- **Verification**: `grep -F 'SKILL.md size cap' requirements/project.md` returns 1 line AND `grep -F 'size-budget-exception' requirements/project.md` returns 1 line — pass if both grep counts equal 1.
- **Status**: [ ] pending

### Task 7: Justfile recipe + test-skills aggregator wiring
- **Files**: `justfile`
- **What**: Append a new `test-skill-design` recipe that runs all four tests as a unit, and add a `run_test "test-skill-design" just test-skill-design` line to the existing `test-skills` aggregator recipe.
- **Depends on**: [2, 3, 4, 5]
- **Complexity**: simple
- **Context**:
  - New recipe body (per spec Req 16): `.venv/bin/pytest tests/test_skill_descriptions.py tests/test_skill_handoff.py tests/test_skill_size_budget.py tests/test_lifecycle_references_resolve.py -q`
  - **Locate the existing `test-skills` aggregator deterministically**: use `grep -n '^test-skills:' justfile` to get the recipe header line, then find the last `run_test` line in that recipe's body using `awk '/^test-skills:/{flag=1; next} flag && /^[a-z_-]+:/{flag=0} flag && /run_test/' justfile | tail -1`. Insert the new `run_test "test-skill-design" just test-skill-design` line immediately after the matched last `run_test` line. Do not rely on the literal line number from the spec.
  - Recipe naming follows the existing `test-*` naming convention in justfile.
  - Caller enumeration: justfile is the only caller of recipe names. No external code references this recipe by name.
- **Verification**: (a) `just --list 2>&1 | grep -E '^\s+test-skill-design\b'` returns 1 line — pass if recipe is listed. (b) `grep -E '^test-skill-design:' justfile` returns 1 line AND `grep -E 'run_test.*test-skill-design' justfile` returns 1 line — pass if exactly one recipe definition and one aggregator wiring line. (c) `just test-skill-design` exits 0 AND its output mentions all four target test files (verified via `just test-skill-design 2>&1 | grep -cE '(test_skill_descriptions|test_skill_handoff|test_skill_size_budget|test_lifecycle_references_resolve)\.py'` returns ≥ 4) — pass if recipe actually invokes all four targets.
- **Status**: [ ] pending

### Task 8: Final verification of negative-space requirements and isolated test-suite pass
- **Files**: none (read-only verification)
- **What**: Verify spec Req 18 (no allowlist file created), Req 21 (#178 dependency satisfied at PR-open time), Req 15 negative side (no bin/cortex-check-skill-design tool), the project.md doc paragraph from Task 6 is present, and that the four new/extended tests pass in isolation.
- **Depends on**: [6, 7]
- **Complexity**: trivial
- **Context**:
  - Req 18: `test ! -e tests/.skill-design-exceptions.md` — confirm no allowlist file exists.
  - Req 15 (negative side): `test ! -e bin/cortex-check-skill-design` — confirm no consolidated CLI tool was created.
  - Req 21: read `backlog/178-*.md` frontmatter `status` field; must be `complete`. Trigger phrases in `tests/fixtures/skill_trigger_phrases.yaml` are substring-present in canonical SKILL.md descriptions on the same commit (transitively verified by Task 2's pytest pass).
  - **Isolated test-suite pass**: run only the four new/extended tests, not `just test`, so a failure here is provably attributable to this plan's deliverable rather than to unrelated pre-existing test flakes.
  - **Aggregate `just test` pass is NOT part of this task's verification**: it is verified separately at PR-open time as a release-readiness signal, not as a per-plan correctness signal.
- **Verification**: chained AND of five conditions — `test ! -e tests/.skill-design-exceptions.md && test ! -e bin/cortex-check-skill-design && grep -E '^status:\s*complete' backlog/178-*.md && grep -F 'SKILL.md size cap' requirements/project.md && uv run pytest tests/test_skill_descriptions.py tests/test_skill_handoff.py tests/test_skill_size_budget.py tests/test_lifecycle_references_resolve.py -q` — pass if exit 0.
- **Status**: [ ] pending

## Verification Strategy

End-to-end the four gates run via `just test-skill-design` (Task 7), which is wired into `just test-skills` (Task 7) and reachable via `just test` (transitive). Each test passes against the current state of skills/ (Tasks 2, 3, 4, 5) and demonstrates its failure-detection path via a regression fixture using `pytest.raises(AssertionError, match=...)` to ensure failure-detection-path correctness (Tasks 2, 3, 4, 5). The marker convention is documented in `requirements/project.md` Architectural Constraints (Task 6) so contributors learn the rule before tripping it. Final isolated verification (Task 8) runs only the four new/extended tests so failures attribute provably to this plan's deliverable rather than unrelated suite flakes. Total new test code targets ≤300 lines per Adversarial mitigation #8 (research.md:263); no new bin/ tools, no allowlist file, one justfile recipe, one `requirements/project.md` paragraph addition.

## Veto Surface

- **Trigger-phrase corpus authoring is deferred to Task 2's last sub-step** (per spec Req 21). The user may want to review the corpus before it's committed; if so, plan can be revised to break Task 2 into "test scaffold" + "corpus authoring" tasks with an approval gate between them. Default plan keeps it as one task — the corpus is small (3–5 phrases × 4 skills = ~12–20 strings) and is reviewable in the PR diff alongside the test that consumes it.
- **Path-resolution prefix list in Task 4** (`skills/`, `lifecycle/`, `plugins/`, `bin/`, `tests/`, `cortex_command/`, `docs/`, `requirements/`, `research/`, `backlog/`) is taken verbatim from spec Req 9. If a future top-level directory is added, this list will need updating — that's a real but small maintenance cost. Alternative considered: detect repo-root prefix dynamically by checking which directories exist at REPO_ROOT. Rejected: adds runtime cost and ambiguity (fixture dirs at REPO_ROOT would qualify). User may want to reconsider.
- **Marker syntax inflexibility** (Task 5): the regex `<!-- size-budget-exception: <reason ≥30 chars>, lifecycle-id=<NNN>, date=<YYYY-MM-DD> -->` is strict. Whitespace flexibility is built in; field-order flexibility is not. If users dislike the rigidity, plan can be revised to allow optional fields or alternate orderings — but spec Req 13 ties down the exact regex.
- **Plugin-mirror dedup is now resolved in Task 1** (was a Veto item — moved to design): `enumerate_plugin_skills()` passes `dedupe_by_content=True` to the generic `enumerate_skills`, removing byte-identical SKILL.md files from the result so Test #4 produces single (not dual) failure messages on cap breaches. Alternative considered: prefix-exclude `plugins/cortex-core/`. Rejected because it would skip non-mirror plugin SKILL.md files in the same plugin directory if any are added in the future. Content-hash dedup is more permissive and self-correcting.

## Scope Boundaries

Maps directly to spec Non-Requirements:

- **No semantic drift detection in test #2** — name-presence only.
- **Test #2 narrowed to one field (`discovery_source`)** — **REVISED post-critical-review**: spec Req 4 listed two fields, but `lifecycle_slug` is loud-fail covered by 31+ Python attribute references in `tests/test_select_overnight_batch.py` and `cortex_command/overnight/`. Same logic the spec applied to exclude `complexity`/`criticality`/`areas` ("Python imports break loudly") applies to `lifecycle_slug`. Narrowed for consistency. Rationale logged in events.log.
- **Test #1 covers only 4 primary skills** (lifecycle, refine, critical-review, discovery) — other 9 canonical skills out of scope for the trigger-phrase corpus.
- **Test #3 does NOT scan `skills/**/*.md` for citations** — extends the existing lifecycle/research-scoped resolver only.
- **No description false-positive tests** — sanctioned-but-deferred per audit item 3.
- **No live skill execution** — all four tests are static (markdown reads, regex match, line count, YAML compare).
- **No new `bin/cortex-check-skill-design` CLI tool** — pure pytest only.
- **No `tests/.skill-design-exceptions.md` allowlist file** — in-file markers for test #4; YAML fixture diffs for tests #1 and #2.
- **No vertical-planning structure for the test files** — conventional pytest layout.
- **No CHANGELOG entry / commit-message convention required for fixture updates** — accepted Adversarial-flagged risk.
- **No pre-extraction of `skills/diagnose/SKILL.md`** — `diagnose` (currently 489 lines) stays under the cap; the next content-additive PR triggers test #4 — that's the test's intended behavior.
- **No exception markers pre-applied to any SKILL.md on day 1.**
- **No `bin/cortex-check-parity` modification.**
- ~~**No documentation file updates**~~ — **REVISED post-critical-review**: one bullet added to `requirements/project.md` Architectural Constraints (Task 6) documenting the SKILL.md size cap and marker convention. Critical review argued the marker convention is contributor-facing authoring affordance, and additions to existing docs are not "proactive doc creation" per CLAUDE.md. Rationale logged in events.log. Test docstrings remain the documentation surface for test internals.
- **No 600-line cap, no per-skill caps, no growth-rate budget** — uniform 500 with in-file marker.
- **No snapshot-style test** for full SKILL.md descriptions — substring presence is the actual contract.
- **No AST-based markdown parsing** — stdlib regex only.
