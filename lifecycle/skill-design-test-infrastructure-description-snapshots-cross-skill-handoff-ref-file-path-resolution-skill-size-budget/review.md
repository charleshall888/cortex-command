# Review: skill-design-test-infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget)

## Stage 1: Spec Compliance

### Requirement 1: Trigger-phrase fixture covers four primary skills
- **Expected**: `tests/fixtures/skill_trigger_phrases.yaml` lists `lifecycle`, `refine`, `critical-review`, `discovery`, each with `must_contain` array of ≥1 phrase.
- **Actual**: Fixture present with all four skills; counts are 4/4/4/4 phrases. Acceptance one-liner exits 0 (`Req1 PASS`).
- **Verdict**: PASS
- **Notes**: Phrases are sourced from current canonical SKILL.md descriptions; substring presence verified by Test #1.

### Requirement 2: Test #1 passes against current canonical SKILL.md descriptions
- **Expected**: `uv run pytest tests/test_skill_descriptions.py -q` exits 0.
- **Actual**: Both tests in `test_skill_descriptions.py` pass (canonical + regression). Test parametrizes by iterating over `(skill, phrase)` pairs from the YAML; substring search is case-sensitive over the parsed `description` frontmatter field.
- **Verdict**: PASS

### Requirement 3: Test #1 fails on simulated regression via fixture
- **Expected**: `tests/fixtures/skill_design/skills/regression-fixture/SKILL.md` + `regression_skill_trigger_phrases.yaml` exist; one declared phrase is absent; test wraps the substring-check in `pytest.raises(AssertionError)` and exits 0 under `pytest -k regression`.
- **Actual**: Both fixture files present; YAML declares `"fixture present phrase"` (present in description) and `"fixture missing phrase"` (deliberately absent). `test_regression_fixture_detects_missing_phrase` uses `pytest.raises(AssertionError, match=r"fixture missing phrase")` so the failure-detection path is pinned. Acceptance run exits 0.
- **Verdict**: PASS

### Requirement 4: Handoff schema fixture (per plan deviation: `discovery_source` only)
- **Expected (plan-revised)**: `tests/fixtures/skill_handoff_schema.yaml` lists exactly `discovery_source` with `producer: discovery` and `consumers: [lifecycle, refine]`. (Plan removed `lifecycle_slug` because of 31+ Python attribute references that already provide loud-fail coverage.)
- **Actual**: Fixture matches the plan-revised schema exactly. The set of field names is `{'discovery_source'}`; producer + consumers are correct.
- **Verdict**: PASS
- **Notes**: Internal consistency confirmed: fixture, test (3 pairs derived: discovery, lifecycle, refine), and module docstring all reference `discovery_source` as the sole compound-token in scope. Spec deviation is in-scope per the review prompt.

### Requirement 5: Test #2 (handoff schema name-presence) passes against current SKILL.md files
- **Expected**: Parametrized over each `(field, skill)` pair; literal token search across `skills/<skill>/SKILL.md` OR `skills/<skill>/references/*.md`; aggregate AssertionError; exits 0.
- **Actual**: `test_canonical_skill_handoff_fields_present` passes; `_field_present_in_skill` checks SKILL.md first then iterates `references/*.md`; aggregate-finding pattern matches the spec convention.
- **Verdict**: PASS

### Requirement 6: Test #2 docstring records scope limitations (four verbatim phrases)
- **Expected**: Four verbatim phrases each grep-count exactly 1 in `tests/test_skill_handoff.py`. (Spec phrasing of (c)/(d) was updated by the plan to reflect the narrowed `discovery_source`-only scope.)
- **Actual**: All four plan-revised phrases grep-count to exactly 1:
  - `does NOT catch semantic drift` → 1
  - `Do not expand fixture YAML to encode value-shape rules` → 1
  - `Scope limited to SKILL.md-prose-mediated handoff fields with no Python-test coverage — currently the compound token discovery_source` → 1
  - `Python-mediated handoff fields (e.g., lifecycle_slug, complexity, criticality, areas read by cortex_command/) are out of scope for this test — coverage relies on existing Python tests` → 1
- **Verdict**: PASS
- **Notes**: Plan-revised phrasing of (c)/(d) is internally consistent with the narrowed fixture scope.

### Requirement 7: Test #2 fails on simulated rename via fixture
- **Expected**: Fixture pair under `tests/fixtures/skill_design/handoff_rename/`; consumer omits the field name; regression test exits 0 under `pytest -k regression`.
- **Actual**: `skill_handoff_schema.yaml` declares `synthetic_renamed_field` (producer: producer-fixture, consumer: consumer-fixture); `consumer-fixture/SKILL.md` deliberately omits the token. Test uses `pytest.raises(AssertionError, match=r"synthetic_renamed_field")`. Acceptance run exits 0.
- **Verdict**: PASS

### Requirement 8: Test #3 extends `test_lifecycle_references_resolve.py` with `file_line_citation` form
- **Expected**: New regex form added; per-form coverage assertion; `grep -c "file_line_citation" tests/test_lifecycle_references_resolve.py` ≥ 2.
- **Actual**: Form added at `FORM_REGEXES["file_line_citation"]`; per-form coverage gate present (`required_forms` tuple includes `file_line_citation`); grep count = 32 (well above the threshold).
- **Verdict**: PASS

### Requirement 9: Test #3 path-resolution rule and traversal safety
- **Expected**: Top-level prefix list resolves repo-relative; otherwise relative to citing-file directory; `is_relative_to(REPO_ROOT)` + reject `..` segments; line-count check; traversal failure produces literal `outside repo`.
- **Actual**: `TOP_LEVEL_PREFIXES` matches the spec list exactly (10 entries). `_resolve_file_line_citation` rejects `..` segments with literal `outside repo`, then performs `Path.resolve()` and `is_relative_to(REPO_ROOT)` containment check. Line-count check uses `max(cited_line, cited_lend)`. Path-traversal fixture exists and the regression test passes with `match=r"outside repo"`.
- **Verdict**: PASS

### Requirement 10: Test #3 passes against current state
- **Expected**: `uv run pytest tests/test_lifecycle_references_resolve.py -q` exits 0.
- **Actual**: 4 tests pass. Note: prior 26 stale `<file>:<line>` citations were repaired in commit 94f58ba as part of Task 4 to keep the live-tree gate green.
- **Verdict**: PASS

### Requirement 11: Test #3 fails on simulated stale citation via fixture
- **Expected**: `tests/fixtures/lifecycle_references/stale_file_line_citation.md` cites past actual line count; test exits 0 under `pytest -k stale_citation`.
- **Actual**: Fixture cites `tests/fixtures/lifecycle_references/broken-citation.md:9999` (well past actual line count). `test_stale_citation_file_line_regression` uses `pytest.raises(AssertionError, match=r"line .*beyond|exceeds line count|stale_file_line_citation\.md")`. Acceptance run exits 0.
- **Verdict**: PASS

### Requirement 12: Test #4 size-budget rule
- **Expected**: Enumerate canonical and plugin SKILL.md files; assert ≤500 lines unless valid marker present; exits 0.
- **Actual**: `test_canonical_and_plugin_skills_within_size_budget` enumerates union of `enumerate_canonical_skills() + enumerate_plugin_skills()` (with byte-content dedup); test passes against current state.
- **Verdict**: PASS

### Requirement 13: Test #4 marker syntax and validation
- **Expected**: Marker regex `<!--\s*size-budget-exception:\s*(?P<reason>.{30,}?),\s*lifecycle-id=(?P<lid>\d+),\s*date=(?P<date>\d{4}-\d{2}-\d{2})\s*-->`; invalid marker triggers error containing literal `invalid size-budget-exception marker` and the file path.
- **Actual**: `MARKER_REGEX` matches the spec verbatim. `MARKER_PREFIX_REGEX` detects malformed markers; if a prefix occurrence is not covered by a valid match, an error is emitted with the literal substring `invalid size-budget-exception marker` and the file path. `tests/fixtures/skill_size_budget/invalid-marker/SKILL.md` exercises the path; regression test passes with `match=r"invalid size-budget-exception marker"`.
- **Verdict**: PASS

### Requirement 14: Test #4 fails on simulated cap breach with actionable failure message
- **Expected**: `tests/fixtures/skill_size_budget/over-cap-no-marker/SKILL.md` is 501 lines, no marker; failure message contains (a) file path, (b) line count vs. cap, (c) `extract to references/`, (d) `<!-- size-budget-exception:`.
- **Actual**: Fixture file is exactly 501 lines (verified via `wc -l`). Cap-breach error message contains all four required tokens (`501 lines exceeds cap of 500`, file path, both remediation hints). Regression test passes with `match=r"over-cap-no-marker.*501.*500"`. The plan-deviation boundary fixture (`boundary-29-char-reason/SKILL.md`) exists and behaves correctly: its marker (29-char rationale) is rejected by `MARKER_REGEX` so the file falls through to cap-breach as designed; regression test asserts the cap-breach line specifically.
- **Verdict**: PASS

### Requirement 15: Shared helpers in `tests/conftest.py` (no new bin/ tool)
- **Expected**: Helpers in `tests/conftest.py` (or sibling `_skill_helpers.py`); `bin/cortex-check-skill-design` does NOT exist.
- **Actual**: `repo_root`, `enumerate_skills`, `enumerate_canonical_skills`, `enumerate_plugin_skills`, `parse_skill_frontmatter` all defined in `tests/conftest.py`. `bin/cortex-check-skill-design` does not exist.
- **Verdict**: PASS

### Requirement 16: Justfile recipe `test-skill-design`
- **Expected**: New recipe with body `.venv/bin/pytest tests/test_skill_descriptions.py tests/test_skill_handoff.py tests/test_skill_size_budget.py tests/test_lifecycle_references_resolve.py -q`; `just --list | grep -c "test-skill-design"` ≥ 1; `just test-skill-design` exits 0.
- **Actual**: Recipe at `justfile:403-404` matches the spec body verbatim. `just --list | grep -c test-skill-design` = 1. `just test-skill-design` exits 0 (13 tests pass).
- **Verdict**: PASS

### Requirement 17: Justfile aggregator wiring
- **Expected**: New line `run_test "test-skill-design" just test-skill-design` in `test-skills` aggregator; `grep -c "test-skill-design" justfile` ≥ 2.
- **Actual**: Wired at `justfile:461`; grep count = 2.
- **Verdict**: PASS

### Requirement 18: No new allowlist file
- **Expected**: `tests/.skill-design-exceptions.md` does NOT exist.
- **Actual**: File does not exist.
- **Verdict**: PASS

### Requirement 19: Tests pass on aggregate `just test`
- **Expected**: Four new/extended tests collected by `pytest tests/` and pass.
- **Actual**: Isolated run `uv run pytest tests/test_skill_descriptions.py tests/test_skill_handoff.py tests/test_skill_size_budget.py tests/test_lifecycle_references_resolve.py -q` exits 0 with 13 passed.
- **Verdict**: PASS
- **Notes**: Aggregate `just test` was not invoked in this read-only review (per the review prompt's scope), but the spec's substantive acceptance criterion (the four tests pass) is satisfied.

### Requirement 20: Path-traversal safety also applied in test #2 if needed
- **Expected**: Either no path is constructed from fixture content, OR a traversal-safety check is present.
- **Actual**: `tests/test_skill_handoff.py` reads only fixed `skills/<name>/SKILL.md` and `skills/<name>/references/*.md` glob results; no path is constructed from fixture content. Module docstring documents this trivial-satisfaction explicitly.
- **Verdict**: PASS

### Requirement 21: #178 dependency hard-enforced
- **Expected**: `backlog/178-*.md` has `status: complete` at PR-open time.
- **Actual**: `grep -E "^status:" backlog/178-apply-skill-creator-lens-improvements-tocs-descriptions-oq3-frontmatter.md` returns `status: complete`.
- **Verdict**: PASS
- **Notes**: Trigger-phrase corpus is substring-present in canonical SKILL.md descriptions on the same commit (transitively verified by Test #1's pass).

## Requirements Drift
**State**: none
**Findings**:
- Task 6 added the `SKILL.md size cap` bullet to `requirements/project.md` Architectural Constraints (line 30), so the new behavior is captured in the requirements doc. No other implementation behavior exceeds what `requirements/project.md` documents — the four tests are CI gates that defend behaviors already implied by the existing `SKILL.md-to-bin parity enforcement` and `Sandbox preflight gate` constraints (drift gates over canonical surfaces).
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Helper names (`repo_root`, `enumerate_skills`, `enumerate_canonical_skills`, `enumerate_plugin_skills`, `parse_skill_frontmatter`) match the spec/plan exactly. Test function naming consistently uses `test_<scenario>` and `test_regression_<...>` to satisfy `pytest -k regression` selection. Fixture directory names mirror their test purpose (`skill_design/`, `skill_size_budget/`, `lifecycle_references/`).
- **Error handling**: Errors are aggregated into single multi-line `AssertionError` messages per the `tests/test_lifecycle_references_resolve.py` and `tests/test_check_parity.py` precedent. No fail-fast behavior. YAML loads use `yaml.safe_load` and re-raise with the offending fixture path (`_load_fixture` in both Tests #1 and #2). Resolved-path containment uses `Path.is_relative_to(REPO_ROOT)` with a Python <3.9 `AttributeError` fallback.
- **Test coverage**: All plan verification steps were executed. Each of the four tests has a canonical-pass test plus at least one regression-variant test that exercises the failure-detection path. Test #4 has three regression variants (over-cap, invalid-marker, boundary-29-char) plus a sanity-check that proves the fixtures are enumerable via the generic helper. Drift remediation across 26 stale citations (commit 94f58ba) was required to keep Test #3 green and is appropriately scoped to the live-tree corpus.
- **Pattern consistency**: Tests follow the project's existing aggregation idiom (`tests/test_check_parity.py`, `tests/test_lifecycle_references_resolve.py`). All four regression-variant tests use `pytest.raises(AssertionError, match=<regex>)` (verified — `match=` is present on every `pytest.raises(AssertionError, ...)` call across the four test files). The `enumerate_skills` helper's `dedupe_by_content: bool = False` flag works as designed: passes through to a SHA-256 dedup over file bytes when set; the canonical wrapper passes False, the plugin wrapper passes True. The boundary-29-char-reason fixture correctly probes the regex boundary — the marker is rejected and the file falls through to the cap-breach path (not double-counted as both an invalid-marker error and a cap-breach error against the same span — both errors are emitted, but the regression test pins the cap-breach message specifically). Task 6's `requirements/project.md` bullet matches the verbatim text from the plan.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
