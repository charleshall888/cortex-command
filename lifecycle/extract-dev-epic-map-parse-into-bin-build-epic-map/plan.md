# Plan: extract-dev-epic-map-parse-into-bin-build-epic-map

## Overview

Land a freestanding `bin/cortex-build-epic-map` (bash wrapper → `backlog/build_epic_map.py`) that consumes `backlog/index.json` and emits a deterministic epic→children JSON map per spec Requirements 1–8 and 11–12, then rewrite `skills/dev/SKILL.md` Step 3b (preserving 3a and 3c untouched) to invoke the script and consume its output per Requirement 9. Fixtures and tests are landed alongside the implementation; the plugin mirror is regenerated via `just build-plugin` and verified against the pre-commit drift hook (Requirement 10).

## Tasks

### Task 1: Create test fixtures for build_epic_map
- **Files**:
  - `tests/fixtures/build_epic_map/multi_epic.json`
  - `tests/fixtures/build_epic_map/wide_shape.json`
  - `tests/fixtures/build_epic_map/no_epics.json`
  - `tests/fixtures/build_epic_map/malformed_json.json`
  - `tests/fixtures/build_epic_map/v2_schema.json`
- **What**: Produce minimal `index.json`-shaped fixtures that exercise the four normalization rules, multi-epic detection, the four-field child shape, malformed JSON, and schema_version mismatch. Each fixture is a **bare JSON array of item objects** — matching exactly what `backlog/generate_index.py:148-150`'s `generate_json()` emits (`return json.dumps(items, indent=2, ensure_ascii=False)` on a plain Python list, with no envelope object and no `version` key). Each item dict carries `id`, `title`, `status`, `priority`, `type`, `parent`, `spec`, `schema_version` etc. The empty-active-items edge case is covered in Task 4 via `no_epics.json` (zero items with `type: epic` and `{}` output) and a `tmp_path`-based inline fixture — no dedicated `empty.json` fixture is needed.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Real shape reference: live `backlog/index.json` opens with `[` (a top-level JSON array). `backlog/generate_index.py:148-150`'s `generate_json()` confirms: `return json.dumps(items, indent=2, ensure_ascii=False)` on a plain Python list. Per `backlog/generate_index.py:131` each item dict carries `id` (int), `title`, `status`, `priority`, `type`, `parent` (str|null), `spec` (str|null), `schema_version` ("1"). Fixtures must be bare JSON arrays of these item dicts — not wrapping objects.
  - `multi_epic.json`: two `type: epic` items (ids 100, 101) with varied statuses (in_progress, refined, blocked); 5–6 children with `parent` values covering all four normalization paths — `null`, `"100"` (quoted str matches), `100` (bare int matches), `"58f9eb72-1234-5678-90ab-cdef01234567"` (UUID skip), `"abc-123"` (UUID-shaped skip), `"101"` (matches second epic). Include at least one non-epic non-child item.
  - `wide_shape.json`: one epic (id 100), one child whose `spec` is a non-empty string, one whose `spec` is `null`, one whose `spec` is missing, one whose `spec` is `""`. Used by Requirement 5's keys-only assertion and the `spec`-passthrough cases in Requirement 11.
  - `no_epics.json`: items present but none with `type: epic` — exercises the empty-output edge case. Because both "no active items" and "no epics detected" produce identical output (`{"schema_version":"1","epics":{}}`), this fixture covers both edge cases.
  - `malformed_json.json`: literal text `not json` (or any non-JSON bytes).
  - `v2_schema.json`: at least one active item with `schema_version: "2"` to trigger the hard-error path (Requirement 7).
  - Hand-write rather than copy-from-real `index.json`; fixtures must remain stable when the live index churns.
- **Verification**: `python3 -c 'import json,glob; [json.load(open(p)) for p in glob.glob("tests/fixtures/build_epic_map/*.json") if "malformed" not in p]'` exit code = 0 — pass if all non-malformed fixtures parse as JSON.
- **Status**: [ ] pending

### Task 2: Implement `backlog/build_epic_map.py`
- **Files**: `backlog/build_epic_map.py`
- **What**: Implement the parent-field normalizer, epic auto-detection, schema-version validation, and JSON emitter. Module is importable as `cortex_command.backlog.build_epic_map` (the existing package layout maps `backlog/*.py` to `cortex_command.backlog.*`) and runnable as `python3 backlog/build_epic_map.py [INDEX_PATH]`.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Follow the layout pattern of `backlog/update_item.py:23-37`: stdlib-only top imports, `_PROJECT_ROOT = Path(__file__).resolve().parent.parent`, `sys.path.insert(0, str(_PROJECT_ROOT))`, then `from cortex_command.common import ...` only if needed (for this script, none required — pure stdlib).
  - Public surface:
    - `def normalize_parent(value: Any) -> int | None` — implements the four-step normalization (null/missing → None; strip surrounding `"` or `'`; if hyphen present after strip → None; else attempt `int()` and return result; on `ValueError` return None). Pure function, unit-testable.
    - `def build_epic_map(items: list[dict], strict_schema: bool = True) -> dict` — auto-detects `type: epic` items, builds `{epic_id_str: {"children": [{"id", "title", "status", "spec"}]}}` with children sorted by `id` ascending and epics in integer-id-ascending order. Validates `schema_version` per item (raise `SchemaVersionError` on mismatch when `strict_schema=True`). `spec` field copied verbatim — `None`/missing both serialize to JSON `null`.
    - `def main(argv: list[str] | None = None) -> int` — argparse with positional `index_path` (default `backlog/index.json`); reads file; the parsed JSON is a `list[dict]` directly (no envelope unwrap — see "Active-items access" below); on `FileNotFoundError` write a stderr line including the path and return 1; on `json.JSONDecodeError` write a stderr line naming the error and return 1; on `SchemaVersionError` write `cortex-build-epic-map: unsupported schema_version "<v>" — expected "1"` to stderr and return 2; on success print the envelope per the Sorting contract below and return 0. The `if __name__ == "__main__":` block calls `sys.exit(main())`.
  - Custom exception class `SchemaVersionError(Exception)` defined in-module with attribute `value` carrying the offending value's `repr` for the error message.
  - Sorting contract (Requirement 6 — "epics are sorted by integer-id ascending in the JSON object's serialization order"): use `sort_keys=False` and explicitly construct deterministic ordering at every level so `json.dumps` preserves it. (Python 3.7+ dict preserves insertion order; `sort_keys=True` would re-sort to lexicographic order, which violates integer-id ascending for width-mixed keys like `"9"` vs `"100"`.)
    - **Outer envelope**: build as `{"schema_version": "1", "epics": <epics_map>}` with keys in this exact order (insertion order suffices).
    - **Epics map**: insert keys in integer-ascending order — `for epic_id in sorted(epic_ids, key=int): result[str(epic_id)] = {...}`.
    - **Per-child dict**: insert fields in lexicographic order to satisfy Requirement 5's `keys | sort | join(",")` assertion (`id`, `spec`, `status`, `title`).
    - **Children list**: `sorted(children, key=lambda c: c["id"])` (integer ascending).
    - Emit with `json.dumps(result, indent=2, sort_keys=False, ensure_ascii=False)`.
  - Children sort: explicit `sorted(children, key=lambda c: c["id"])` inside `build_epic_map`.
  - Schema validation logic: iterate active items; treat `schema_version` `None` or missing as `"1"`; raise `SchemaVersionError` on any other value (including int `1`, list, dict — strict string `"1"` match only). The `wide_shape.json` and `multi_epic.json` fixtures carry `schema_version: "1"` on every item; `v2_schema.json` carries `"2"` on at least one item.
  - Active-items access: `backlog/index.json` is a **bare JSON array** of item dicts. `backlog/generate_index.py:148-150`'s `generate_json()` confirms — it returns `json.dumps(items, ...)` on a plain Python list with no wrapping object. Parse with `items = json.loads(text)`; iterate `items` directly. There is no top-level key to dereference. (The plan's earlier draft incorrectly cited `generate_index.py:154-227`, which is the markdown emitter `generate_md`, not the JSON producer.)
  - Pure-stdlib imports only: `json`, `argparse`, `sys`, `pathlib.Path`. No `claude/common.py`.
  - Module docstring summarizes purpose and exit codes; an `--help` line ending mentions `index.json` (Requirement 2's substring assertion).
- **Verification**: `python3 -c 'from cortex_command.backlog.build_epic_map import main, build_epic_map, normalize_parent'` exit code = 0 — pass if all three symbols are importable.
- **Status**: [ ] pending

### Task 3: Create `bin/cortex-build-epic-map` wrapper
- **Files**: `bin/cortex-build-epic-map`
- **What**: Bash wrapper following the established `bin/cortex-*` dispatch convention — log invocation, dual-branch dispatch (packaged then `CORTEX_COMMAND_ROOT` fallback), exit-2 not-found message. Set executable bit.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Pattern reference: `bin/cortex-generate-backlog-index` (read in research as the canonical 17-line wrapper). Mirror its structure exactly, substituting `cortex_command.backlog.build_epic_map` and `$CORTEX_COMMAND_ROOT/backlog/build_epic_map.py`.
  - First non-shebang line: `"$(dirname "$0")/cortex-log-invocation" "$0" "$@" || true` (fail-open observability shim per `docs/observability.md`).
  - Options: `set -euo pipefail` after the log shim.
  - Branch (a): `python3 -c "import cortex_command.backlog.build_epic_map" 2>/dev/null` → `exec python3 -m cortex_command.backlog.build_epic_map "$@"`.
  - Branch (b): `[ -n "${CORTEX_COMMAND_ROOT:-}" ] && grep -q '^name = "cortex-command"' "$CORTEX_COMMAND_ROOT/pyproject.toml" 2>/dev/null` → `exec python3 "$CORTEX_COMMAND_ROOT/backlog/build_epic_map.py" "$@"`.
  - Branch (c): exit-2 message: `echo "cortex-command CLI not found — run 'cortex setup' or point CORTEX_COMMAND_ROOT at a cortex-command checkout" >&2 ; exit 2`.
  - After writing, set executable bit: must end up `-rwxr-xr-x` and tracked as such by git (`git update-index --chmod=+x bin/cortex-build-epic-map` if filemode tracking does not auto-set; verify with `git ls-files -s bin/cortex-build-epic-map` showing mode `100755`).
- **Verification**: `head -1 bin/cortex-build-epic-map | grep -c '^#!/bin/bash'` = 1 AND `test -x bin/cortex-build-epic-map` exit 0 AND `grep -c 'cortex_command.backlog.build_epic_map' bin/cortex-build-epic-map` ≥ 1 — all three must pass.
- **Status**: [ ] pending

### Task 4: Write `tests/test_build_epic_map.py`
- **Files**: `tests/test_build_epic_map.py`
- **What**: pytest covering normalize_parent unit cases, end-to-end subprocess invocations against fixtures, schema-version validation, malformed-input handling, `spec`-field passthrough cases, and exit-code branching per Requirement 11.
- **Depends on**: [1, 2, 3]
- **Complexity**: complex
- **Context**:
  - Pattern reference: `tests/test_check_parity.py` and `tests/test_archive_rewrite_paths.py` for the subprocess-invoke + parse-stdout pattern. Use `subprocess.run([str(REPO_ROOT / "bin" / "cortex-build-epic-map"), str(fixture_path)], capture_output=True, text=True)`. Resolve `REPO_ROOT` via `Path(__file__).resolve().parent.parent`.
  - Test functions (≥8 per Requirement 11's collect-only count):
    - `test_parent_normalization_null_missing` — calls `normalize_parent(None)` and the missing case via dict `.get("parent")` → both return `None`.
    - `test_parent_normalization_quote_strip` — `normalize_parent('"103"')` and `normalize_parent("'103'")` both return `103`.
    - `test_parent_normalization_uuid_skip` — `normalize_parent("58f9eb72-1234-5678-90ab-cdef01234567")` returns `None`; `normalize_parent("abc-123")` returns `None`.
    - `test_parent_normalization_integer_match` — `normalize_parent("103")` returns `103`; `normalize_parent(103)` returns `103`; `normalize_parent("abc")` returns `None`.
    - `test_multi_epic_subprocess` — invoke `bin/cortex-build-epic-map tests/fixtures/build_epic_map/multi_epic.json`; assert exit 0, parse stdout JSON, assert epic keys are `"100","101"` (sorted), children IDs match expected sorted ordering, `schema_version` is `"1"`.
    - `test_wide_shape_keys_only` — invoke against `wide_shape.json`; assert each child's keys (sorted) equal `["id", "spec", "status", "title"]` (Requirement 5).
    - `test_spec_passthrough` — within `wide_shape.json` results, assert that `spec: null`, missing, `""`, and a non-empty string each round-trip to the expected JSON value (Requirement 11c). May be folded into `test_wide_shape_keys_only` or split into individual cases — splitting yields a higher `--collect-only` count.
    - `test_no_epics_emits_empty_map` — invoke against `no_epics.json`; assert exit 0, stdout JSON `epics` is `{}`. This fixture has items present but none with `type: epic`, so it covers the "no epics detected" edge case. The empty-active-items edge case (zero items in the array) produces the same output `{"schema_version":"1","epics":{}}` and is verified inline via `tmp_path`: write a minimal valid index JSON with an empty `items` array to a temp file and invoke the wrapper against it, asserting exit 0 and `epics == {}`.
    - `test_malformed_json_exits_1` — invoke against `malformed_json.json`; assert exit 1, stderr non-empty.
    - `test_missing_path_exits_1` — invoke against `/nonexistent/path/index.json`; assert exit 1, stderr contains the path substring.
    - `test_schema_v2_exits_2` — invoke against `v2_schema.json`; assert exit 2, stderr matches regex `cortex-build-epic-map: unsupported schema_version "[^"]*" — expected "1"`, stdout empty.
    - `test_deterministic_output` — invoke twice against `multi_epic.json`; assert stdout bytes identical (sha256 or direct equality).
    - `test_width_mixed_epic_ordering` — width-mixed ordering coverage (Requirement 6's "integer-id ascending"). Build a `tmp_path` fixture as a bare JSON array containing two epic items with IDs `9` and `100` (and a child for each). Invoke the wrapper; parse stdout JSON; assert `list(parsed["epics"].keys()) == ["9", "100"]` (integer-ascending order, NOT lexicographic which would yield `["100", "9"]`). This test fails under any `sort_keys=True` implementation and is the regression guard for the Sorting contract in Task 2.
  - Use `pytest`'s `subprocess.run(..., timeout=10)` to avoid hangs.
  - For the `--help` substring check (Requirement 2), add `test_help_mentions_index_json` invoking `python3 -m cortex_command.backlog.build_epic_map --help` and asserting `"index.json" in result.stdout`. Module-level argparse description or epilog must include the substring.
- **Verification**: `pytest tests/test_build_epic_map.py -v` exit code = 0 — pass if all tests pass; AND `pytest tests/test_build_epic_map.py --collect-only -q | grep -c '::test_'` ≥ 8.
- **Status**: [ ] pending

### Task 5: Rewrite `skills/dev/SKILL.md` Step 3b
- **Files**: `skills/dev/SKILL.md`
- **What**: Replace the inline four-step parent-field normalization narrative (currently `SKILL.md:151-167`) with a script-invocation block that satisfies Requirement 9 (a)–(g): inline `cortex-build-epic-map` reference, output schema description, Ready intersection prose, missing-index fallback preservation, exit-1 and exit-2 handling. Step 3a (`SKILL.md:135-141`) and Step 3c (from `SKILL.md:168` onward) MUST NOT be edited.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Region to edit: lines 151–167 inclusive of the current SKILL.md (the "Epic detection and child map construction" preamble + the four-step list). The leading line `**Epic detection and child map construction** (must complete before any output is rendered):` may be retained or rephrased; the four-step numbered list is replaced.
  - Replacement-prose checklist (mapping to Requirement 9 sub-clauses, all must appear within the rewritten 3b region):
    - **9a** Inline-code reference: `` `cortex-build-epic-map` `` appears at least once.
    - **9b** Output schema description: name the four per-child fields (`id`, `title`, `status`, `spec`) and the envelope `{"schema_version": "1", "epics": {...}}`; mention that `spec` non-null indicates a refined child (Step 3c reads this directly).
    - **9c** Ready intersection prose: explicitly state that the agent intersects the script's emitted `epics` keys with the IDs in the Ready section (already extracted at `SKILL.md:143-149`), and only Ready-set epics are passed to Step 3c. Include the literal phrase "Ready set" or "Ready section" so the verification grep matches.
    - **9d** Fallback preservation: include a sentence equivalent to "If `index.json` is missing after Step 3a ran, warn and fall back to reading `index.md`." The grep target is `'fall back to .*index.md'`.
    - **9e** Exit-code prose: explicit handling for exit 1 ("missing or malformed `index.json`" → warn and fall back to `index.md` table columns) and exit 2 ("`schema_version` mismatch" → report mismatch and halt triage). The grep target is `'exit (code )?(1|2)'` and `'schema_version'`.
    - **9f** Step 3a (`SKILL.md:135-141`) bytes-unchanged.
    - **9g** Step 3c (`SKILL.md:168` onward) bytes-unchanged. Specifically, the `[refined]` indicator branch at current line 184 keys off `spec:` field — Requirement 5's choice of `spec` as the field name preserves this, so no Step 3c text edit is needed.
  - The diff scope must be a single contiguous edit inside the Step 3b region. Do NOT touch any line in the Step 3a (135–141) or Step 3c (168–end) regions.
  - Suggested replacement-prose shape (the implementer may adjust phrasing as long as all 9a–9e signals are present):
    1. One-paragraph script invocation + intent.
    2. Four-line schema description (envelope + four per-child fields).
    3. Two-line Ready intersection step (the script emits ALL detected epics; Step 3b filters to the Ready set before passing to 3c).
    4. Two-line fallback prose (exit 1 → warn + read `index.md` table columns).
    5. Three-line exit-code handling block (one line per exit code 1, 2; one line on the rationale: silent fallback masks the schema-bump signal).
- **Verification**: ALL THREE must pass:
  - **(a) Parity gate**: `bin/cortex-check-parity` exit code = 0 — SKILL.md-to-bin wiring accepted, no orphan/drift warnings (Requirement 9h).
  - **(b) Step 3a unchanged (Requirement 9f)**: `git diff -U0 -- skills/dev/SKILL.md | python3 -c "import re,sys; d=sys.stdin.read(); hunks=re.findall(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', d, re.MULTILINE); bad=[(s,c) for s,c in hunks if int(s) <= 141 and (int(s) + (int(c) if c else 1) - 1) >= 135]; sys.exit(1 if bad else 0)"` exit 0 — no diff hunks intersect lines 135–141.
  - **(c) Step 3c unchanged (Requirement 9g)**: `git diff -U0 -- skills/dev/SKILL.md | python3 -c "import re,sys; d=sys.stdin.read(); hunks=re.findall(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', d, re.MULTILINE); bad=[(s,c) for s,c in hunks if (int(s) + (int(c) if c else 1) - 1) >= 168]; sys.exit(1 if bad else 0)"` exit 0 — no diff hunks reach line 168 or beyond.

  (Hunk-range checks parse the `@@ -N,M +N,M @@` headers and assert no hunk touches the protected line ranges. Pure-stdlib Python; no external tools.)
- **Status**: [ ] pending

### Task 6: Regenerate plugin mirror via `just build-plugin`
- **Files**: `plugins/cortex-interactive/bin/cortex-build-epic-map`
- **What**: Run `just build-plugin` to regenerate the plugin tree; the mirror directory is auto-populated by the existing rsync recipe (`--include='cortex-*' --exclude='*'`). No hand-edits.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - `justfile` `build-plugin` recipe runs the rsync sync for each build-output plugin (`cortex-interactive`, `cortex-overnight-integration`). Per research §"Plugin mirroring", new `bin/cortex-*` scripts are auto-picked up — no recipe change needed.
  - After `just build-plugin`, the file `plugins/cortex-interactive/bin/cortex-build-epic-map` should exist, be executable, and be byte-identical to `bin/cortex-build-epic-map`. The pre-commit drift hook (installed via `just setup-githooks`) will block the commit if the mirror differs after a fresh build.
  - Verify before staging: `cmp bin/cortex-build-epic-map plugins/cortex-interactive/bin/cortex-build-epic-map`.
  - Stage the mirror file alongside the canonical wrapper.
- **Verification**: `cmp bin/cortex-build-epic-map plugins/cortex-interactive/bin/cortex-build-epic-map` exit code = 0 — pass if files are byte-identical.
- **Status**: [ ] pending

### Task 7: End-to-end live integration check
- **Files**: (no edits — runs against the working tree)
- **What**: Smoke-test the full chain (wrapper → packaged-Python branch → live `backlog/index.json`) and confirm exit-0 with non-empty JSON output. Sanity-check the parity gate, the test suite, and the drift hook all pass.
- **Depends on**: [4, 5, 6]
- **Complexity**: simple
- **Context**:
  - Live invocation: `bin/cortex-build-epic-map backlog/index.json` from repo root. Expected: exit 0, stdout begins with `{`, contains `"schema_version": "1"`, `epics` map with keys for actual epics in the live index.
  - `pytest tests/test_build_epic_map.py` exit 0.
  - `bin/cortex-check-parity` exit 0 (no W003 orphan, no E002 drift).
  - `just build-plugin && git diff --exit-code -- plugins/cortex-interactive/bin/` exit 0 (drift hook simulation).
  - This task is the gate for declaring implementation complete; if any verification fails, the corresponding upstream task is reopened.
- **Verification**: `bin/cortex-build-epic-map backlog/index.json | jq -r '.schema_version'` returns the literal string `1` AND `pytest tests/test_build_epic_map.py` exit 0 AND `bin/cortex-check-parity` exit 0 AND `just build-plugin && git diff --exit-code -- plugins/cortex-interactive/bin/` exit 0 — all four must pass.
- **Status**: [ ] pending

## Verification Strategy

End-to-end correctness is verified by Task 7's live integration check, which composes (a) the live `backlog/index.json` invocation, (b) the pytest suite, (c) the parity gate, and (d) the drift-hook simulation. Each upstream task carries a narrower verification step (file-keys, importability, executable bit, schema version). If Task 7 fails, the failure pinpoints which upstream surface regressed:

- Wrapper or packaging issue → Task 3 (executable bit, dispatch branch).
- Python implementation issue → Task 2 (normalize/build_epic_map symbol).
- Test suite issue → Task 4 (fixtures vs. assertions).
- SKILL.md wiring or out-of-region edit → Task 5 (parity grep + line-region diff checks).
- Plugin drift issue → Task 6 (`just build-plugin` invocation).

The sha256-determinism assertion (Requirement 6) and the `--collect-only` test count (Requirement 11) are subsumed by Task 4's pytest run. Task 1 lands five named fixtures; the empty-active-items edge case is covered in Task 4 via `no_epics.json` (same output path) and an inline `tmp_path` fixture.

## Veto Surface

- **`spec` field name vs. `refined` boolean** (Task 2 / Task 5). Spec Requirement 5 chose to ship the raw `spec` string (matching `index.json`'s field name) rather than a `refined: bool` derived flag. This decision is locked by the spec to avoid Step 3c text edits. Re-litigating it would re-open Step 3c's invariant; flagged here only for traceability.
- **Single-call vs. per-epic invocation** (architectural). Per research §Tradeoffs Alt C, the script auto-detects all epics in one call rather than accepting `--epic-ids`. If overnight or a future caller needs per-epic invocation later, `--epic-ids` is reserved as a backwards-compatible flag (Non-Requirement). No action now.
- **Tests-as-subprocess vs. tests-via-import** (Task 4). The plan mixes unit tests on `normalize_parent` (direct import) with end-to-end tests via subprocess (`bin/cortex-build-epic-map`). Spec Requirement 11 names both. If reviewers prefer a single mode, consolidating to subprocess loses tight feedback on the normalizer; recommend keeping both.

## Scope Boundaries

Excluded per spec Non-Requirements (recap for the implementer):

- No Step 3c decision-tree extraction. Step 3c stays inline.
- No `--epic-ids` filter flag. Auto-detection only.
- No `--out FILE` flag. Stdout only.
- No `bin/.parity-exceptions.md` entry. Wired via SKILL.md.
- No centralization into `cortex_command/common.py`. Lives in `backlog/build_epic_map.py`.
- No edits to `skills/dev/SKILL.md` Step 3a (lines 135–141) or Step 3c (line 168 onward).
- No new fields in the per-child output beyond `id`, `title`, `status`, `spec`.
- No migration logic for `schema_version: "2"` or beyond. Hard-error and stop.
- No diagnostic prose in SKILL.md about why specific children are dropped (UUID-era parent, integer mismatch). Diagnostic vocabulary lives in `backlog/build_epic_map.py` source comments only.
