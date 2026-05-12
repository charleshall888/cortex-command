# Review: promote-refine-references-clarify-criticmd-to-canonical-with-schema-aware-migration

## Stage 1: Spec Compliance

### Requirement 1: Lifecycle copy is deleted
- **Expected**: `test ! -f skills/lifecycle/references/clarify-critic.md` exits 0.
- **Actual**: File absent; binary check exits 0 (`R1 PASS`). Deletion appears as a `D` entry in commit `058eceb`.
- **Verdict**: PASS

### Requirement 2: Plugin mirror auto-pruned
- **Expected**: `test ! -f plugins/cortex-core/skills/lifecycle/references/clarify-critic.md` exits 0.
- **Actual**: File absent (`R2 PASS`). Same-commit deletion alongside the canonical (R13).
- **Verdict**: PASS

### Requirement 3: §3a reference rewired
- **Expected**: `grep -c '\.\./refine/references/clarify-critic\.md' skills/lifecycle/references/clarify.md` = 1.
- **Actual**: grep returns 1 (matches the trailing `../refine/...` substring inside the actual `../../refine/...` path). The implementation correctly uses `../../refine/references/clarify-critic.md` because `skills/lifecycle/references/clarify.md` is one directory deeper than `skills/refine/SKILL.md`, so two `..` levels are needed to reach `skills/`. The spec's prose example showed `../refine/...` which would not actually resolve correctly from this depth — implementation chose the functionally-correct path. The §3a section at line 53 uses the rewired reference at line 55.
- **Verdict**: PASS

### Requirement 4: schema_version field present in canonical markdown
- **Expected**: `grep -c 'schema_version'` ≥ 3, with occurrences in (a) required-fields prose, (b) JSONL example, (c) legacy-tolerance prose.
- **Actual**: 6 occurrences — line 132 (prose), 137 (required-fields), 164/165 (legacy-tolerance for minimal v1 + v1+dismissals), 175 (JSONL example), 181 (YAML structural breakdown). Phrased as SHOULD on producer side per OQ3.
- **Verdict**: PASS

### Requirement 5: Reader-side legacy-tolerance helper in Python
- **Expected**: `_normalize_clarify_critic_event(evt: dict) -> dict` exists in test file with ≥2 references.
- **Actual**: Defined at lines 193-227 of `tests/test_clarify_critic_alignment_integration.py`. grep returns 4 occurrences (definition + 3 call sites: `check_invariant`, replay test, mention in docstring). All three normalizations implemented exactly per spec: `schema_version` defaults to 1; `parent_epic_loaded` defaults to False; bare-string findings wrapped per-element with hybrid-list support; raises TypeError on non-str-non-dict items.
- **Verdict**: PASS

### Requirement 6: check_invariant calls the normalizer
- **Expected**: `check_invariant(_normalize_clarify_critic_event(evt))` exits 0 for the v1 fixture.
- **Actual**: `check_invariant` itself calls `_normalize_clarify_critic_event` internally at line 238 before invariant evaluation. Acceptance command exits 0 (`R6 PASS`).
- **Verdict**: PASS

### Requirement 7: Replay test fixture pinned to test-owned location
- **Expected**: `tests/fixtures/clarify_critic_v1.json` exists; `.provenance` sibling exists with `define-output-floors` source annotation.
- **Actual**: Both files present; provenance is a single-line markdown comment matching the spec form: `Source: lifecycle/archive/define-output-floors-for-interactive-approval-and-overnight-compaction/events.log:2 — pre-feature v1 clarify_critic event (bare-string findings, no parent_epic_loaded, no dismissals).`
- **Verdict**: PASS

### Requirement 8: Replay test exists and passes
- **Expected**: `pytest tests/test_clarify_critic_alignment_integration.py::test_clarify_critic_v1_replay_invariant -x` exits 0; asserts (a) schema_version==1, (b) parent_epic_loaded is False, (c) findings are dicts with text+origin str, (d) every origin=="primary", (e) check_invariant True.
- **Actual**: Test at lines 531-568. All five assertions present and matching spec wording. `uv run pytest` reports 1 passed in 0.01s. Test name carries `_v1_` per Adversarial mitigation #4.
- **Verdict**: PASS

### Requirement 9: JSONL-emission requirement + JSONL example block
- **Expected**: ≥1 JSONL/single-line-JSON mention; `## Event Logging` section contains a single-line JSON `clarify_critic` example.
- **Actual**: 7 grep matches for JSONL/single-line-JSON. Acceptance regex `python3 -c "..."` exits 0 — the inline single-line JSON example at line 175 in `## Event Logging` is detected by the section-anchored regex. The YAML structural breakdown is retained as a documentation aid below the JSONL primary example, per spec.
- **Verdict**: PASS

### Requirement 10: v1.5 intermediate shape acknowledged
- **Expected**: legacy-tolerance prose enumerates `minimal v1`, `v1+dismissals`, and `YAML-block` shapes.
- **Actual**: All three terms present (lines 164-166). Each shape is described by behavioral effect (bare-string findings, no parent_epic_loaded, dismissals presence, multi-line YAML on disk), not by version label.
- **Verdict**: PASS

### Requirement 11: No change to cortex_command/overnight/events.py
- **Expected**: `git show --name-status 058eceb -- cortex_command/overnight/events.py` returns no output.
- **Actual**: Empty output (no entry in the migration commit's name-status diff for that file).
- **Verdict**: PASS

### Requirement 12: Tests pass
- **Expected**: `pytest tests/test_clarify_critic_alignment_integration.py -x` exits 0; all existing tests continue to pass.
- **Actual**: 8 passed in 0.37s. The original 6 tests + 2 new tests (replay invariant + post-migration JSONL) all green.
- **Verdict**: PASS

### Requirement 13: Migration commit deletes both canonical and mirror in same commit
- **Expected**: `git show --name-status --format= HEAD -- 'skills/lifecycle/references/clarify-critic.md' 'plugins/cortex-core/skills/lifecycle/references/clarify-critic.md' | grep -c '^D'` = 2.
- **Actual**: Returns 2 (commit `058eceb` deletes both in the same commit).
- **Verdict**: PASS

### Requirement 14: Producer-side JSONL emission check
- **Expected**: `test_post_migration_clarify_critic_events_are_jsonl` exists in test file; reads cutoff from `tests/fixtures/jsonl_emission_cutoff.txt`; walks active `lifecycle/*/events.log` excluding `archive`; asserts post-cutoff events are JSONL; pytest exits 0.
- **Actual**: Test at lines 593-671. Cutoff fixture present (`2026-05-06T23:39:47Z`). Active-only walk via `glob("*/events.log")` with archive-path exclusion. Both JSONL and YAML-block parsing via regex line-scan (with rationale comment about why yaml.safe_load_all is unsuitable). Includes a positive-control assertion to prevent silent parse-skip regressions. `uv run pytest` reports 1 passed in 0.01s.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Python helper names follow project conventions (`_normalize_clarify_critic_event` private-leading-underscore for module helpers, snake_case throughout). Test names carry the schema-version anchor (`_v1_`) per spec Edge Cases. Fixture filename pattern `clarify_critic_v1.json` mirrors test name. Provenance file uses `.provenance` suffix consistent with test-fixture annotation patterns. Cutoff fixture filename `jsonl_emission_cutoff.txt` is descriptive and self-documenting.
- **Error handling**: Normalizer raises `TypeError` with offending-type identification on non-str-non-dict findings (per spec Edge Cases — fail loudly rather than silently produce malformed output). Empty `findings` defaults via `evt.get("findings", [])` returns empty list trivially. Cutoff parser normalizes `Z` to `+00:00` for `datetime.fromisoformat` compatibility. R14 test isolates per-file failures into a violations list and raises a single AssertionError with all offending paths, line numbers, and timestamps — better debug surface than per-file fail-fast.
- **Test coverage**: All 14 acceptance commands pass on first run. New tests are additive; existing 6 tests continue to pass and exercise `check_invariant` directly with synthetic dicts (no normalizer dependency). The R14 test includes a positive-control assertion that prevents the "trivially passes by detecting nothing" failure mode (silent parse-skip regression). Test docstrings carry forward references to spec requirements (`R8`, `R14`) and adversarial mitigations.
- **Pattern consistency**: JSONL example block follows the structural pattern of `skills/lifecycle/references/plan.md:138`'s `plan_comparison` v2 example (single-line JSON primary, structural breakdown as documentation aid). Cross-skill `..` reference at §3a matches the established 5-instance pattern in `skills/refine/SKILL.md` (note: depth-adjusted — `../../refine/...` from `skills/lifecycle/references/` correctly resolves to `skills/refine/references/`, equivalent navigation to `../lifecycle/...` from `skills/refine/SKILL.md`). Plugin mirror is identical to canonical (auto-rebuilt by pre-commit hook Phase 3). Live-doc reference in `docs/internals/sdk.md` updated to point at the new canonical home.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
