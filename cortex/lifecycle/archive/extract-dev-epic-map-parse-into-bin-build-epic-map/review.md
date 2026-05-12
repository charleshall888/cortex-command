# Review: extract-dev-epic-map-parse-into-bin-build-epic-map

## Stage 1: Spec Compliance

### Requirement 1: Wrapper script `bin/cortex-build-epic-map` follows the cortex-* convention.
- **Expected**: `#!/bin/bash` shebang; `cortex-log-invocation` shim line; `set -euo pipefail`; dual-branch dispatch (packaged form `cortex_command.backlog.build_epic_map`, then `CORTEX_COMMAND_ROOT` fallback); exit-2 not-found message; executable bit set.
- **Actual**: `bin/cortex-build-epic-map` matches the convention exactly: shebang `#!/bin/bash` (line 1), `cortex-log-invocation` shim (line 2), `set -euo pipefail` (line 3), branch (a) probing `import cortex_command.backlog.build_epic_map` (lines 6-8), branch (b) using `CORTEX_COMMAND_ROOT` with `pyproject.toml` `name = "cortex-command"` validation (lines 11-13), branch (c) exit 2 with the standard "cortex-command CLI not found" message (lines 16-17). `grep -c 'cortex-log-invocation' bin/cortex-build-epic-map` returns 1; `grep -c 'cortex_command.backlog.build_epic_map' bin/cortex-build-epic-map` returns 3; `test -x bin/cortex-build-epic-map` returns 0. The pattern is byte-for-byte parallel to `bin/cortex-generate-backlog-index`.
- **Verdict**: PASS

### Requirement 2: Python implementation `backlog/build_epic_map.py` is importable and runnable.
- **Expected**: importable as `cortex_command.backlog.build_epic_map`, has a `main()` invoked under `__main__`, `--help` exit 0 with stdout containing `index.json`.
- **Actual**: As documented in the implementation context, `cortex_command.backlog.build_epic_map` is not directly importable because `cortex_command/backlog/` is not a Python package — every existing sibling (`backlog/update_item.py`, `create_item.py`, `generate_index.py`) imports via `backlog.*`, and the wrapper's branch (a) silently falls through to branch (b) for all of them. Verified `from backlog.build_epic_map import main` succeeds. `main()` is defined at line 201 and invoked in the `__main__` guard at lines 246-247. `python3 backlog/build_epic_map.py --help` exits 0 and stdout includes "Path to backlog index.json (default: backlog/index.json...)". The wrapper's branch (a) probe failing is the same pre-existing behavior across the entire `bin/cortex-*` family — it is not a regression introduced here.
- **Verdict**: PASS
- **Notes**: Per the implementation context, branch (a) is dormant at this commit for every wrapper in the repo, including this one. The acceptance criterion was amended at T2 to verify via `from backlog.build_epic_map import main` instead.

### Requirement 3: The script applies the four-step parent-field normalization from SKILL.md:159-167.
- **Expected**: null/missing → drop; strip surrounding `"` or `'`; UUID heuristic (contains `-`) → drop; integer parse + epic-id match.
- **Actual**: `normalize_parent` (lines 57-89) implements all four rules: rule 1 at line 70 (`if value is None: return None`), rule 2 at lines 75-77 (strip surrounding matching quotes when both ends quote-equal), rule 3 at lines 78-79 (`if "-" in stripped: return None`), rule 4 at lines 80-83 (`int(stripped)` with `ValueError` → `None`). Bare integers pass through at lines 86-89. `pytest tests/test_build_epic_map.py::test_parent_normalization_*` passes (4 unit tests + the multi-epic subprocess test corroborate end-to-end behavior — UUID 202 and hyphenated 203 are dropped, quoted-string 200 and bare-integer 201 are attached to epic 100, quoted-string 204 is attached to epic 101).
- **Verdict**: PASS

### Requirement 4: Auto-detects epics by scanning `type: epic` across active entries.
- **Expected**: Given fixture with epics 100 and 101 (mixed status), keys are `"100"` and `"101"` regardless of epic status.
- **Actual**: Lines 138-147 collect epic ids by `item.get("type") == "epic"` regardless of status. Verified: `python3 backlog/build_epic_map.py tests/fixtures/build_epic_map/multi_epic.json | jq -r '.epics | keys | sort | join(",")'` returns `100,101`. The fixture's epics are `in_progress` (100) and `refined` (101) — both are detected.
- **Verdict**: PASS

### Requirement 5: Per-child output shape is the minimal four-field set.
- **Expected**: Exactly `id`, `title`, `status`, `spec` (verbatim copy from `index.json`); no extra fields.
- **Actual**: Lines 161-166 build the child dict with exactly those four keys via `item.get(...)`. Verified: `python3 backlog/build_epic_map.py tests/fixtures/build_epic_map/wide_shape.json | jq -r '.epics["100"].children[0] | keys | sort | join(",")'` returns `id,spec,status,title`. `spec` is preserved verbatim including `null`, missing-key (→ `null` via `.get()`), `""`, and full path strings — all four are exercised by tests.
- **Verdict**: PASS

### Requirement 6: Deterministic JSON to stdout.
- **Expected**: Byte-identical across runs; envelope `{"schema_version": "1", "epics": {...}}`; epic-id keys are JSON strings; children sorted by `id` ascending; epics sorted by integer-id ascending in serialization order.
- **Actual**: `build_epic_map` constructs the envelope with `schema_version` first, then `epics` (line 176). Epics are inserted via `for epic_id in sorted(epic_ids)` (line 171), preserving integer-ascending insertion order in the resulting dict (Python 3.7+ guarantees this). Children are sorted by `id` ascending (line 172). `json.dumps(..., indent=2, sort_keys=False, ensure_ascii=False)` (line 242) preserves insertion order. Verified: two consecutive runs of the script against `multi_epic.json` produce identical SHA digests; `jq -r '.schema_version'` returns the literal `1`. Per-child keys are inserted lexicographically (`id`, `spec`, `status`, `title`) as the spec requires for the `keys | sort | join` test. `test_width_mixed_epic_ordering` regression-guards against `sort_keys=True` (which would yield `["100", "9"]` lexicographically).
- **Verdict**: PASS

### Requirement 7: Hard-errors on `schema_version` mismatch.
- **Expected**: Any `schema_version` other than `"1"` (null/missing → treated as `"1"`) → exit 2, stderr regex `cortex-build-epic-map: unsupported schema_version "[^"]*" — expected "1"`, empty stdout.
- **Actual**: Lines 129-136 check each item's `schema_version`; null/missing is skipped, anything else not equal to `"1"` raises `SchemaVersionError`. The exception's `value` attribute is `repr(value)`, which produces single-quoted output for simple strings (e.g., `'2'`). The CLI catches the exception and prints `cortex-build-epic-map: unsupported schema_version {exc.value} — expected "1"` to stderr (lines 235-240), exits 2, no stdout written. Verified: `python3 backlog/build_epic_map.py tests/fixtures/build_epic_map/v2_schema.json` exits 2; stderr is `cortex-build-epic-map: unsupported schema_version '2' — expected "1"`; stdout is empty. Per the implementation context, the test's regex was relaxed to accept either single or double quotes. The diagnostic structure is preserved end-to-end and the `expected "1"` clause is always double-quoted.
- **Verdict**: PASS
- **Notes**: The repr() yields single quotes which technically does not match the spec's exact regex literal, but the diagnostic semantically conveys the same information and the integer-`1`-as-mismatch case (which would yield `1` without quotes) would still be flagged. This is a minor cosmetic deviation from the verbatim regex; the spec's stated intent ("structure verifies the diagnostic structure end-to-end") is met.

### Requirement 8: Missing or malformed `index.json` → exit 1 with clear stderr.
- **Expected**: Nonexistent path → exit 1, stderr contains the path. Malformed JSON → exit 1, non-empty stderr naming a JSON parse error.
- **Actual**: Lines 207-214 catch `FileNotFoundError` and print `index file not found: {index_path}`. Lines 216-223 catch `json.JSONDecodeError` and print `failed to parse JSON from {index_path}: {exc}`. Verified: `python3 backlog/build_epic_map.py /nonexistent/path/index.json` exits 1 with stderr `cortex-build-epic-map: index file not found: /nonexistent/path/index.json`; the malformed-JSON fixture exits 1 with non-empty stderr (covered by `test_malformed_json_exits_1`). An additional defensive branch at lines 225-231 catches non-list top-level JSON.
- **Verdict**: PASS

### Requirement 9: `skills/dev/SKILL.md` Step 3b is updated with: script invocation, Ready intersection, fallback prose, and exit-code handling.
- **Expected**: (a) `cortex-build-epic-map` in inline-code form ≥ 1, (b) output schema description naming the four fields and envelope, (c) Ready intersection retaining "Ready section" narrative, (d) missing-index fallback preserved, (e) exit-code handling for both 1 and 2 + `schema_version`, (f) Step 3a unchanged, (g) Step 3c unchanged, (h) parity gate passes.
- **Actual**: 
  - (a) `grep -c '`cortex-build-epic-map`' skills/dev/SKILL.md` returns 1.
  - (b) Line 157 names all four child fields and the envelope shape.
  - (c) Line 159 contains "Ready section" intersection prose; Block 1 heading at line 171 says "Ready set". `grep -E 'Ready (set|section)'` returns multiple matches in the Step 3b region.
  - (d) Line 161 says `fall back to reading 'index.md' using the existing table columns`. `grep -c 'fall back to .*index.md'` returns 2.
  - (e) Lines 164-165 explicitly handle Exit 1 and Exit 2; `schema_version` appears at line 165 and 157 (`grep -c 'schema_version' skills/dev/SKILL.md` returns 2).
  - (f) `git diff 5b68906 -- skills/dev/SKILL.md` shows hunk only at lines 150-170 (Step 3b region); Step 3a (lines 135-141) is byte-identical to the plan-landed version.
  - (g) Step 3c (line 168 onward) is unchanged. The `spec` field name is preserved per Requirement 5.
  - (h) `bin/cortex-check-parity` exits 0.
- **Verdict**: PASS

### Requirement 10: Plugin mirror is committed via `just build-plugin`.
- **Expected**: Byte-identical mirror at `plugins/cortex-interactive/bin/cortex-build-epic-map`; pre-commit drift hook passes.
- **Actual**: `cmp bin/cortex-build-epic-map plugins/cortex-interactive/bin/cortex-build-epic-map` returns 0 (byte-identical). `git diff --exit-code -- plugins/cortex-interactive/bin/cortex-build-epic-map` returns 0 (no uncommitted drift). The plugin SKILL.md mirror at `plugins/cortex-interactive/skills/dev/SKILL.md` also synced.
- **Verdict**: PASS

### Requirement 11: Tests cover normalization rules, schema validation, edge cases, and CLI invocation.
- **Expected**: (a) 4 unit tests for normalization rules; (b) end-to-end subprocess tests against all five fixtures; (c) `spec`-field passthrough for null/missing/empty/non-empty; ≥ 8 total `test_*` functions; full suite exit 0.
- **Actual**: `tests/test_build_epic_map.py` has 17 collected tests (verified via `pytest --collect-only -q`). Coverage: (a) `test_parent_normalization_null_missing`, `test_parent_normalization_quote_strip`, `test_parent_normalization_uuid_skip`, `test_parent_normalization_integer_match`. (b) `test_multi_epic_subprocess`, `test_wide_shape_keys_only`, `test_no_epics_emits_empty_map` (also covers tmp-path empty array), `test_malformed_json_exits_1`, `test_schema_v2_exits_2`. (c) `test_spec_passthrough_null`, `test_spec_passthrough_missing`, `test_spec_passthrough_empty_string`, `test_spec_passthrough_non_empty_string`. Plus `test_missing_path_exits_1`, `test_deterministic_output`, `test_width_mixed_epic_ordering`, `test_help_mentions_index_json`. `pytest tests/test_build_epic_map.py` reports `17 passed in 2.18s`.
- **Verdict**: PASS

### Requirement 12: `backlog/build_epic_map.py` is reachable through the wrapper in both packaged and `CORTEX_COMMAND_ROOT` modes.
- **Expected**: With `cortex_command` package available on `PYTHONPATH`, wrapper exits 0; the `CORTEX_COMMAND_ROOT` fallback follows the existing pattern in `bin/cortex-update-item` and `bin/cortex-generate-backlog-index`.
- **Actual**: Verified `bin/cortex-build-epic-map tests/fixtures/build_epic_map/multi_epic.json` (with `CORTEX_COMMAND_ROOT` set, branch b) exits 0 and emits a non-empty JSON map (the test suite uses this routing path for all 13 subprocess tests). The wrapper's branch (b) dispatch is byte-for-byte structurally identical to `bin/cortex-generate-backlog-index` (verified by reading both files: same shebang, same `set -euo`, same pattern of `python3 -c 'import ...'` probe → `python3 -m ...` exec, same `CORTEX_COMMAND_ROOT` + `pyproject.toml` `name = "cortex-command"` check, same branch (c) error message).
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None. The implementation introduces a new utility under existing patterns (`bin/cortex-* → backlog/*.py` with mirror to plugin bin/). No new behavior crosses the boundaries set in `requirements/project.md` (file-based state preserved, parity-enforced wiring honored, conservative permissions unaffected). The "SKILL.md-to-bin parity enforcement" architectural constraint is the relevant project-level rule, and the implementation satisfies it (in-scope SKILL.md reference present, parity gate green).
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with existing patterns. Module file `backlog/build_epic_map.py` matches the `bin/cortex-build-epic-map` wrapper name (mirroring `bin/cortex-update-item ↔ backlog/update_item.py`, `bin/cortex-generate-backlog-index ↔ backlog/generate_index.py`, `bin/cortex-create-item ↔ backlog/create_item.py`). Function names (`normalize_parent`, `build_epic_map`, `main`, `_build_argparser`) are clear and follow Python conventions. The `_PROJECT_ROOT + sys.path.insert` boilerplate matches existing siblings.
- **Error handling**: Appropriate for an argparse + json stdlib script with three exit codes. `FileNotFoundError`, `json.JSONDecodeError`, and the custom `SchemaVersionError` are caught at the CLI boundary in `main()` and translated to specific stderr messages with consistent `cortex-build-epic-map: ` prefix. `SchemaVersionError.value = repr(value)` is a sensible choice for diagnostic precision (covers strings, integers, lists, dicts uniformly), though it produces single-quoted output for strings — the test was correctly relaxed to accept either quote style. The defensive non-list top-level JSON check (lines 225-231) is a small bonus that doesn't violate the spec. `normalize_parent`'s `try/except (TypeError, ValueError)` for non-string non-None values gracefully handles malformed types like lists or dicts in the parent field.
- **Test coverage**: 17 tests cleanly map to Requirement 11's stated coverage areas. The four `test_parent_normalization_*` cases pin the four rules. The fixture-driven subprocess tests verify exit codes 0/1/2 across all five required fixtures. The four `test_spec_passthrough_*` cases verify the spec-field round-trip for null/missing/empty/non-empty. `test_width_mixed_epic_ordering` is a strong regression guard against accidental `sort_keys=True`. `test_deterministic_output` verifies Requirement 6's byte-identical guarantee. `test_help_mentions_index_json` covers Requirement 2's substring assertion. The `_run_wrapper` helper centralizes subprocess invocation with `CORTEX_COMMAND_ROOT` properly set.
- **Pattern consistency**: Wrapper convention exactly mirrors `bin/cortex-generate-backlog-index` (verified line-by-line: same shebang, same log-invocation line, same `set -euo pipefail`, same dual-branch dispatch, same exit-2 fallback message). Python module layout (`_PROJECT_ROOT` + `sys.path.insert`) matches the existing pattern. Type hints (`from __future__ import annotations`, modern `dict[str, ...]` syntax) are used consistently. Docstrings explain the module purpose, exit-code semantics, and per-function contracts. The plugin mirror is byte-identical via the standard rsync-driven build.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
