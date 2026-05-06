# Specification: Skill-design test infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget)

## Problem Statement

Cortex's skill-design surface has four documented regression modes that the existing test suite does not catch: (1) silent edits drop trigger phrases from SKILL.md descriptions and break routing for users who say those phrases; (2) refactors rename cross-skill handoff fields (e.g., `discovery_source` → `research_source`) and silently decouple producers from consumers; (3) line-anchored `<file>:<line>` citations in lifecycle artifacts go stale when target files grow above the cited line; (4) SKILL.md files grow organically past Anthropic's documented 500-line guidance with no CI signal. Three new pytest test files plus a focused extension of the existing `tests/test_lifecycle_references_resolve.py` create four CI-time drift gates that pattern-match `bin/cortex-check-parity`'s SKILL.md-to-bin parity model — closing the named regression modes at near-zero per-PR cost. The work is the audit's "Test gaps (new class)" section (`research/vertical-planning/audit.md:282-290`) absorbing items 1, 2, 4, 5; item 3 (description false-positive tests) is sanctioned-but-deferred.

## Requirements

1. **Trigger-phrase fixture (test #1) covers four primary skills**: `tests/fixtures/skill_trigger_phrases.yaml` is created with at least one curated trigger phrase per skill for `lifecycle`, `refine`, `critical-review`, and `discovery`, sourced from those skills' post-#178 SKILL.md descriptions. Schema (top-level mapping):
    ```yaml
    skills:
      lifecycle:
        must_contain: ["start a lifecycle", "lifecycle research/specify/plan/implement/review/complete", ...]
      refine:
        must_contain: ["refine backlog item", "prepare for overnight", ...]
      critical-review:
        must_contain: ["critical review", "pressure test", ...]
      discovery:
        must_contain: ["discover this", "decompose into backlog", ...]
    ```
    Acceptance: `python3 -c "import yaml; d = yaml.safe_load(open('tests/fixtures/skill_trigger_phrases.yaml')); assert set(d['skills'].keys()) >= {'lifecycle','refine','critical-review','discovery'}; assert all(len(d['skills'][s]['must_contain']) >= 1 for s in ['lifecycle','refine','critical-review','discovery'])"` exits 0.

2. **Test #1 passes against current canonical SKILL.md descriptions**: `tests/test_skill_descriptions.py` parametrizes over each `(skill, phrase)` pair in `skill_trigger_phrases.yaml` and asserts each phrase appears as a substring (case-sensitive) in the corresponding canonical `skills/<skill>/SKILL.md` `description` frontmatter field. Acceptance: `uv run pytest tests/test_skill_descriptions.py -q` exits 0.

3. **Test #1 fails on simulated regression via fixture (no canonical-source edits)**: a synthetic fixture skill at `tests/fixtures/skill_design/skills/regression-fixture/SKILL.md` exists with a fixture-only trigger-phrase corpus declared in `tests/fixtures/skill_design/regression_skill_trigger_phrases.yaml` where one declared phrase is deliberately absent from the fixture skill's description. `tests/test_skill_descriptions.py` includes a parametrized variant that runs against the regression fixture and asserts that the test logic flags the missing phrase with output naming both the fixture skill name and the dropped phrase. Acceptance: `uv run pytest tests/test_skill_descriptions.py -k regression -q` — the regression-variant test must demonstrate the failure-detection path runs (e.g., via `pytest.raises(AssertionError)` wrapping or via expected-fail markers) and exits 0.

4. **Handoff schema fixture (test #2) enumerates SKILL.md-prose-mediated handoff fields only**: `tests/fixtures/skill_handoff_schema.yaml` is created listing exactly these two cross-skill handoff field names with `producer` and `consumers` arrays naming the canonical skills (under `skills/`) where the literal field-name token MUST appear in `skills/<skill>/SKILL.md` OR `skills/<skill>/references/*.md`: `discovery_source` (producer: discovery; consumers: lifecycle, refine), `lifecycle_slug` (producer: lifecycle; consumers: overnight, refine). These are the compound-token, SKILL.md-prose-mediated handoffs where substring presence reliably reflects the contract. Schema:
    ```yaml
    handoff_fields:
      - name: discovery_source
        producer: discovery
        consumers: [lifecycle, refine]
      - name: lifecycle_slug
        producer: lifecycle
        consumers: [overnight, refine]
    ```
    Acceptance: `python3 -c "import yaml; d = yaml.safe_load(open('tests/fixtures/skill_handoff_schema.yaml')); fields = {h['name'] for h in d['handoff_fields']}; assert fields == {'discovery_source','lifecycle_slug'}"` exits 0 (exact set, not subset — additions require an explicit spec change to justify the added field meets the substring-presence-is-meaningful criterion).

    **Empirical pre-audit (informs the (field, skill) pair selection)**:
    - `discovery_source`: present in `discovery/SKILL.md` (1) and `discovery/references/*.md` (4); `lifecycle/SKILL.md` (3); `refine/SKILL.md` (2). All asserted (field, skill) pairs satisfied.
    - `lifecycle_slug`: present in `lifecycle/SKILL.md` (2); `refine/SKILL.md` (1) and `refine/references/*.md` (2); `overnight/SKILL.md` (1). All asserted (field, skill) pairs satisfied.

    **Out-of-scope handoff fields and rationale (informs test #2's documented limitations)**:
    - `complexity`, `criticality`, `areas`: actual consumers are Python code in `cortex_command/` (overnight scheduler / dispatcher), not `skills/overnight/SKILL.md`. Empirical scan: zero occurrences in `skills/overnight/SKILL.md`. Substring-presence in SKILL.md tests the wrong surface for these fields. Also: high prose-occurrence in lifecycle/refine SKILL.md (7-26 mentions each) makes substring-rename detection unreliable. Coverage for these field renames is implicit via existing Python tests that exercise `cortex_command/`; if explicit name-presence coverage is desired, file a follow-up ticket scoping a separate Python-consumer test.
    - `research`, `spec`: these are pointer fields (paths to artifact filenames) with extremely high prose-occurrence (research=42-150 mentions per skill; spec=27-92 per skill) due to the skills' own vocabulary about the research/spec lifecycle phases. Test #3 (citation resolver) covers artifact-existence regressions for the artifacts these fields point to.
    - `lifecycle_phase`: empirical scan shows zero occurrences in any consumer SKILL.md (only producer `lifecycle/SKILL.md` mentions it). No SKILL.md-prose consumer to assert against. Out of scope.

5. **Test #2 (handoff schema name-presence) passes against current SKILL.md files**: `tests/test_skill_handoff.py` parametrizes over each `(field, skill)` pair derived from `skill_handoff_schema.yaml` (one assertion per producer plus one per consumer per field) and asserts the literal field-name token appears at least once in `skills/<skill>/SKILL.md` OR in `skills/<skill>/references/*.md`. Acceptance: `uv run pytest tests/test_skill_handoff.py -q` exits 0.

6. **Test #2 docstring records scope limitations**: `tests/test_skill_handoff.py` module docstring contains four verbatim phrases acknowledging the test's bounded scope: (a) `does NOT catch semantic drift` (value-shape drift while name stays stable); (b) `Do not expand fixture YAML to encode value-shape rules` (anti-expansion guidance for the 3-way drift trap); (c) `Scope limited to SKILL.md-prose-mediated handoff fields only — compound tokens like discovery_source and lifecycle_slug` (positive scope statement); (d) `Python-mediated handoff fields (e.g., complexity, criticality, areas read by cortex_command/) are out of scope for this test — coverage relies on existing Python tests` (explicit negative-scope statement). Acceptance: each of the four verbatim phrases is grep-able with count exactly 1 in `tests/test_skill_handoff.py`.

7. **Test #2 fails on simulated rename via fixture (no canonical-source edits)**: a synthetic fixture at `tests/fixtures/skill_design/handoff_rename/` contains (a) a fixture handoff schema YAML naming a field expected in a fixture consumer, and (b) a fixture consumer SKILL.md that omits the field name. `tests/test_skill_handoff.py` includes a parametrized variant that runs against the fixture and demonstrates the failure-detection path with output naming both the field name and the fixture consumer. Acceptance: `uv run pytest tests/test_skill_handoff.py -k regression -q` exits 0 with the regression variant exercising the failure-detection logic.

8. **Test #3 extends `tests/test_lifecycle_references_resolve.py` with `<file>:<line>` form**: a new regex form named `file_line_citation` is added to the test's `FORM_REGEXES` mapping. The pattern matches `<path>.<ext>:<line>(-<lend>)?` where `<ext>` is one of `md`, `py`, `sh`, `toml`, `yaml`, `yml`, `json`. The form gets a per-form coverage assertion (`assert per_form_resolved['file_line_citation'] >= 1`) and contributes to the `total_resolved` count. Acceptance: `grep -c "file_line_citation" tests/test_lifecycle_references_resolve.py` returns at least 2.

9. **Test #3 path-resolution rule and traversal safety**: when matched, the citation form (a) resolves cited paths repo-relative if they start with one of `skills/`, `lifecycle/`, `plugins/`, `bin/`, `tests/`, `cortex_command/`, `docs/`, `requirements/`, `research/`, `backlog/`; otherwise resolves relative to the citing file's directory; (b) checks that the final resolved path satisfies `Path.is_relative_to(REPO_ROOT)` AND contains no `..` segments after resolution; (c) opens the file and asserts `line_count >= cited_line` (or `>= cited_lend` for range form). Citations failing the traversal-safety check produce an error containing the literal string `outside repo`. Acceptance: a test fixture under `tests/fixtures/lifecycle_references/` containing `../../etc/passwd:1` causes the test to fail with an error containing `outside repo`.

10. **Test #3 passes against current state**: `uv run pytest tests/test_lifecycle_references_resolve.py -q` exits 0.

11. **Test #3 fails on simulated stale citation via fixture (no canonical-source edits)**: a fixture lifecycle artifact at `tests/fixtures/lifecycle_references/stale_file_line_citation.md` contains a `<file>:<line>` citation that points past the cited file's actual line count. `tests/test_lifecycle_references_resolve.py` includes the fixture in its parametrized scope (alongside the existing `broken-citation.md` fixture pattern) and demonstrates the failure-detection path with output naming both citing file and cited target. Acceptance: `uv run pytest tests/test_lifecycle_references_resolve.py -k stale_citation -q` exits 0 with the regression variant exercising the failure-detection logic.

12. **Test #4 size-budget rule**: `tests/test_skill_size_budget.py` enumerates all canonical `skills/*/SKILL.md` files AND all `plugins/*/skills/*/SKILL.md` files (per the user's "all hand-maintained SKILL.md" scope decision). For each enumerated file, it asserts: `line_count <= 500` UNLESS the file contains at least one valid size-budget exception marker. Acceptance: `uv run pytest tests/test_skill_size_budget.py -q` exits 0.

13. **Test #4 marker syntax and validation**: a valid size-budget exception marker matches the regex `<!--\s*size-budget-exception:\s*(?P<reason>.{30,}?),\s*lifecycle-id=(?P<lid>\d+),\s*date=(?P<date>\d{4}-\d{2}-\d{2})\s*-->` (rationale ≥30 characters, lifecycle-id is a positive integer, date is YYYY-MM-DD). A file containing a marker that fails this regex causes the test to fail with an error containing the literal string `invalid size-budget-exception marker` and the file path. Acceptance: a test fixture file (a temporary copy under `tests/fixtures/skill_size_budget/`) with `<!-- size-budget-exception: too short -->` in its body causes the test to flag the marker as invalid.

14. **Test #4 fails on simulated cap breach with actionable failure message**: a fixture SKILL.md file with 501 lines and no marker causes `test_skill_size_budget.py` (regression variant) to flag the breach with an error message that contains: (a) the file path, (b) the literal numeric line count vs. cap, AND (c) BOTH remediation hints — the literal substring `extract to references/` AND the literal substring `<!-- size-budget-exception:` (the marker template prefix). Acceptance: `tests/fixtures/skill_size_budget/over-cap-no-marker/SKILL.md` (a 501-line synthetic SKILL.md) causes the regression-variant test to assert the failure-message string contains all four required tokens.

15. **Shared helpers in `tests/conftest.py`** (no new `bin/` tool): common helpers — canonical-skill enumerator, plugin-skill enumerator, SKILL.md frontmatter+description parser, REPO_ROOT resolver — live in `tests/conftest.py` (or a sibling `tests/_skill_helpers.py` imported by `conftest.py`). Acceptance: `test ! -e bin/cortex-check-skill-design && echo PASS || echo FAIL` returns `PASS`.

16. **Justfile recipe `test-skill-design`**: a new recipe is appended to the justfile that runs the four tests as a unit. Recipe body: `.venv/bin/pytest tests/test_skill_descriptions.py tests/test_skill_handoff.py tests/test_skill_size_budget.py tests/test_lifecycle_references_resolve.py -q`. Acceptance: `just --list 2>&1 | grep -c "test-skill-design"` returns at least 1 AND `just test-skill-design` exits 0.

17. **Justfile aggregator wiring**: the `test-skills` aggregator recipe (currently around line 435 of `justfile`) gets a new line `run_test "test-skill-design" just test-skill-design`. Acceptance: `grep -c "test-skill-design" justfile` returns at least 2.

18. **No new allowlist file**: `tests/.skill-design-exceptions.md` is NOT created on day 1. Test #4 uses in-file `<!-- size-budget-exception: ... -->` markers exclusively. Test #1 trigger-phrase corpus updates land via standard PR review. Acceptance: `test ! -e tests/.skill-design-exceptions.md && echo PASS || echo FAIL` returns `PASS`.

19. **Tests pass on aggregate `just test`**: all four tests are collected by `pytest tests/` and pass. Acceptance: `just test` produces no failures attributable to the four new/extended tests (verified by `uv run pytest tests/test_skill_descriptions.py tests/test_skill_handoff.py tests/test_skill_size_budget.py tests/test_lifecycle_references_resolve.py -q` exits 0).

20. **Path-traversal safety also applied in test #2 if needed**: if `tests/test_skill_handoff.py` resolves any path derived from fixture content (e.g., to find `references/*.md`), it must use `is_relative_to(REPO_ROOT)` and reject `..` segments. The simpler implementation reads only fixed `skills/<name>/SKILL.md` and `skills/<name>/references/*.md` glob results — in which case this requirement is trivially satisfied. Acceptance: source review confirms either (a) no path is constructed from fixture content, OR (b) path-traversal safety check is present.

21. **#178 dependency hard-enforced**: `#181` implementation cannot begin until backlog item `#178` has `status: complete` (or equivalent terminal state). The trigger-phrase corpus in `tests/fixtures/skill_trigger_phrases.yaml` (Requirement #1) is authored as the LAST sub-task of #181 implementation, sourced from the actual post-#178 SKILL.md description text on the main branch at corpus-authoring time. No pre-#178 fallback corpus is permitted. Acceptance: at the time of #181 PR open, `cortex-update-item 178-* --get status` (or equivalent inspection) returns `complete`, AND the trigger phrases in the fixture are substring-present in the canonical SKILL.md descriptions on the same commit.

## Non-Requirements

- **Test #2 does NOT catch semantic drift.** It catches field-name presence/rename only. If both producer and consumer rename a field together, or if the value-shape contract drifts while names stay stable, the test passes silently. This limitation is documented in the test docstring with anti-expansion guidance.
- **Test #2 covers SKILL.md-prose-mediated handoff fields only** (compound tokens: `discovery_source`, `lifecycle_slug`). Python-mediated handoff fields (`complexity`, `criticality`, `areas` — actually consumed by `cortex_command/` overnight scheduler), pointer fields (`research`, `spec` — covered transitively by test #3's artifact-existence check), and producer-only fields (`lifecycle_phase` — no SKILL.md consumer) are explicitly out of scope. The audit's named regression mode (`discovery_source → research_source` rename) IS covered. Renames of out-of-scope fields are covered by other test surfaces (Python imports break loudly; explicit Python-consumer name-rename testing would be a separate follow-up ticket if the implicit coverage proves insufficient).
- **Test #1 covers ONLY the four primary skills** (lifecycle, refine, critical-review, discovery). Other 9 canonical skills (overnight, dev, research, refine[sic — wait this is in the four], morning-review, requirements, backlog, pr, commit, diagnose) are not in the trigger-phrase corpus on day 1.
  > Note: the four primary skills are exactly those the audit's `research/vertical-planning/audit.md:282-290` flagged for description fixes; #178 is the rewriter ticket that #181 blocks on.
- **Test #3 does NOT scan `skills/**/*.md` for citations.** Empirical scan found 6/8 hits in skills/ are fake worked-example prose; only 2 are real (sibling-file pointers in `skills/discovery/references/`). Test #3 instead extends `tests/test_lifecycle_references_resolve.py` (which already operates on the lifecycle and research artifact tree where the audit's real example lives). The lifecycle resolver's existing scope (`lifecycle/` and `research/`) is preserved unless the implementer determines that adding `skills/**/*.md` to the scan corpus is incidentally required to satisfy the per-form coverage gate; in that case the path-traversal safety check applies to the expanded scope identically.
- **No description false-positive tests** ("given input X, skill Y should NOT trigger") — sanctioned-but-deferred sibling concern from audit's "Test gaps (new class)" item 3, explicitly out of #181 scope.
- **No live skill execution in any test.** All four checks are static (markdown read, regex match, line count, YAML compare). No subprocess invocation of any skill or `bin/cortex-*` tool.
- **No new `bin/cortex-check-skill-design` CLI tool.** Pure-pytest only; helpers in `tests/conftest.py`. The four checks do not need pre-commit / external invocation outside `pytest` since `just test` already runs them.
- **No `tests/.skill-design-exceptions.md` allowlist file.** In-file markers only for test #4; trigger-phrase fixture diffs and handoff-schema fixture diffs are the review surface for tests #1 and #2.
- **No vertical-planning structure for the test files.** Conventional pytest layout (sibling files in `tests/`). Vertical-planning adoption (parent epic Stream F = ticket #182) targets `plan.md`/`spec.md` artifact templates only.
- **No CHANGELOG entry / commit-message convention required for fixture updates.** Standard PR review process applies. The Adversarial-flagged risk that fixture-update PRs become mechanical bypass is accepted by the user.
- **No pre-extraction of `skills/diagnose/SKILL.md`.** #181 lands with cap=500. `diagnose` (currently 489 lines) stays under the cap; the next content-additive PR triggers test #4 — that is the test's intended behavior, not a defect to pre-empt.
- **No exception markers pre-applied to any SKILL.md on day 1.** No SKILL.md gets a `<!-- size-budget-exception: ... -->` marker as part of #181.
- **No `bin/cortex-check-parity` modification.** All work happens in `tests/` and `justfile`.
- **No documentation file updates.** Per CLAUDE.md "NEVER proactively create documentation files"; test docstrings are the sole documentation surface.
- **No 600-line cap, no per-skill caps, no growth-rate budget.** Uniform 500 with in-file marker.
- **No snapshot-style test for full SKILL.md descriptions.** Substring presence is the actual contract; full-snapshot fails on legitimate prose tweaks (high false-positive rate).
- **No AST-based markdown parsing.** Stdlib regex over raw markdown text only (matches `bin/cortex-check-parity` and `tests/test_lifecycle_references_resolve.py` precedent).

## Edge Cases

- **#178 has not yet landed**: #181's `blocked-by: [178]` is hard-enforced — implementation cannot begin until #178 ships and the post-#178 SKILL.md descriptions are committed to main (see Requirement #21). The pre-#178 fallback contemplated in earlier draft prose (audit-recommended phrasings) is rejected; corpus is sourced exclusively from the actual post-#178 file content at the time of corpus authoring.
- **`diagnose` SKILL.md grows post-#181**: the next content-additive PR to `diagnose` (currently 489 lines) hits the cap. Test #4 fires with a clear extraction recommendation. Author's choice: extract to `references/` (the test's intended remediation) OR add an in-file size-budget-exception marker with rationale, lifecycle-id, and date. Both paths are documented in the test's failure message.
- **Plugin SKILL.md content profile differs from cortex-core**: non-mirrored plugins (cortex-overnight, cortex-ui-extras, cortex-pr-review, android-dev-extras, cortex-dev-extras) have hand-maintained SKILL.md files. Same in-file marker mechanism applies. If pattern emerges that a specific plugin needs uniform higher cap, file a follow-up ticket; do not pre-create a per-plugin override mechanism.
- **Trigger-phrase substring collision**: a phrase like `lifecycle` appears in many non-lifecycle skill descriptions. Test asserts substring presence in the named skill's description, not absence elsewhere — collisions are not a failure mode for #181's tests. (False-positive prevention is the deferred audit item 3.)
- **Citation regex matches inside fenced code blocks in `lifecycle/**` artifacts**: if false-positives appear, the implementer adds a `<!-- citation: ignore -->` suppression marker convention matching the existing `<!-- callgraph: ignore -->` pattern. Implementation can defer adding this until at least one false positive is observed.
- **Path-traversal in cited paths**: a markdown prose `../../etc/passwd:1` matches the regex. Mitigation per requirement #9: resolve to absolute, check `is_relative_to(REPO_ROOT)`, reject `..` segments.
- **Symlinks in skill paths**: SKILL.md symlinks could double-count or trick line-count reads. Mitigation: SKILL.md enumerator helpers in `conftest.py` use `Path.resolve()` consistently and deduplicate by absolute resolved path.
- **YAML fixture is empty or malformed**: `yaml.safe_load` on a malformed fixture raises `yaml.YAMLError`. The test should catch and fail with a message naming which fixture file failed to parse.
- **Field name appears only inside a fenced code block in a SKILL.md**: test #2 asserts substring presence anywhere in the SKILL.md (and `references/*.md`). Code-block-only mentions count as presence — this is acceptable since the contract is "the name is mentioned somewhere," and a refactor that renames the field would also rename it inside code-block examples.
- **Producer skill's only mention of a field is in a `references/` file, not the SKILL.md itself**: per requirement #5, the test searches `skills/<skill>/SKILL.md` AND `skills/<skill>/references/*.md`. References are in scope; presence in either location satisfies the contract.
- **Test runtime**: line-count and citation-resolution operations are O(N_files × N_lines) reads. With ~13 canonical SKILL.md files plus ~8-15 plugin SKILL.md files plus the lifecycle-resolver's existing corpus, total work is small (<1s). If runtime becomes an issue (e.g., test scope expands), the test moves to CI-only and out of pre-commit.
- **`just` is not installed**: tests run under `pytest` directly (the four tests are pure pytest, no shell-out to `just`). The justfile recipe is a convenience wrapper, not a dependency.

## Changes to Existing Behavior

- **MODIFIED**: `tests/test_lifecycle_references_resolve.py` gains the `file_line_citation` regex form, a per-form coverage assertion, the path-traversal safety check, and corresponding fixture support. Existing five regex forms unchanged. Existing `total_resolved` coverage gate updated to include the new form's contribution.
- **MODIFIED**: `justfile` `test-skills` aggregator gains `run_test "test-skill-design" just test-skill-design`.
- **ADDED**: new `test-skill-design` recipe in `justfile`.
- **ADDED**: three new pytest test files (`tests/test_skill_descriptions.py`, `tests/test_skill_handoff.py`, `tests/test_skill_size_budget.py`).
- **ADDED**: two new fixture YAML files (`tests/fixtures/skill_trigger_phrases.yaml`, `tests/fixtures/skill_handoff_schema.yaml`).
- **ADDED**: shared SKILL.md helpers in `tests/conftest.py` (or a sibling `tests/_skill_helpers.py` imported by conftest).
- **ADDED**: in-file marker convention `<!-- size-budget-exception: <reason ≥30 chars>, lifecycle-id=<NNN>, date=<YYYY-MM-DD> -->` for SKILL.md files. No SKILL.md gets a marker on day 1.
- **ADDED**: small fixture additions under `tests/fixtures/lifecycle_references/` to exercise the path-traversal safety check (e.g., a deliberate `../../etc/passwd:1` test fixture marked as expected-to-fail) and `tests/fixtures/skill_size_budget/` (e.g., a 501-line synthetic SKILL.md fixture for the breach-detection acceptance test).

## Technical Constraints

- **Stdlib-only Python.** PyYAML is permitted (already a transitive test-suite dep). No new third-party deps. Specifically excluded: markdown AST libraries (mistune, markdown-it-py); snapshot frameworks (syrupy, pytest-snapshot); markdown link checkers (md-link-checker, linkcheckmd, mkdocs-linkcheck).
- **Errors aggregated and emitted as a single multi-line `AssertionError`** matching `tests/test_lifecycle_references_resolve.py` and `tests/test_check_parity.py` convention. No fail-fast on first finding.
- **Pytest exit-code semantics suffice** (0 clean / 1 fail / 2 internal). No `--json` mode (these are pytest tests, not CLI tools).
- **Test failure messages include actionable remediation hint**: cap-breach error suggests "extract to references/ or add `<!-- size-budget-exception: ... -->` marker"; trigger-phrase miss names skill and dropped phrase; citation-drift names citing file and cited target with line counts; field-rename names field and consumer.
- **All four tests target canonical sources only by default.** Test #4 explicitly extends to non-mirrored plugins per requirement #12.
- **Skill enumeration via filesystem glob**: `pathlib.Path("skills").glob("*/SKILL.md")` and `pathlib.Path("plugins").glob("*/skills/*/SKILL.md")`. No runtime registry; no closed-set allowlist with self-test.
- **Fixture YAML uses `yaml.safe_load`** (not `yaml.load`) to prevent object-injection.
- **No git dependency at test runtime.** REPO_ROOT discovery via `pathlib.Path(__file__).resolve().parent.parent` (or equivalent); the existing `tests/test_lifecycle_references_resolve.py` use of `git ls-files` is preserved unchanged in the existing forms but the new `file_line_citation` form may use either approach as long as untracked fixtures under `tests/fixtures/lifecycle_references/` are reachable for the negative-case acceptance test (#9).
- **No modifications outside `tests/` and `justfile`.** No edits to `bin/`, `claude/hooks/`, `cortex_command/`, `skills/`, `plugins/`, `requirements/`, `docs/`. (Earlier draft contained an interactive-edit-revert carve-out for verification acceptance criteria; that path is removed in favor of fixture-based regression detection per requirements #3, #7, #11, #14.)
- **Pre-commit hook integration**: tests run as part of the existing `just test` invocation. No new pre-commit hook entries; no changes to `claude/hooks/cortex-pre-commit.sh`.
- **Tests run in <1 second total.** If implementation surprises this budget (e.g., glob expansion explodes), the implementer must justify the runtime in a Plan-phase note; runtime budget is not a deferred concern.

## Open Decisions

(none — all decisions resolved at spec time)
