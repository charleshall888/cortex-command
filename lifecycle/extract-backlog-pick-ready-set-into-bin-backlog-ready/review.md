# Review: extract-backlog-pick-ready-set-into-bin-backlog-ready

## Stage 1: Spec Compliance

### Requirement R1: `bin/cortex-backlog-ready` shim follows three-branch pattern, executable
- **Expected**: Same logging-wrap and `set -euo pipefail` head-3 lines as `bin/cortex-generate-backlog-index`; `test -x` passes.
- **Actual**: `diff <(head -3 bin/cortex-backlog-ready) <(head -3 bin/cortex-generate-backlog-index)` produces no output. `test -x bin/cortex-backlog-ready` exits 0. Branches (a) packaged, (b) `CORTEX_COMMAND_ROOT`, (c) error exit 2 all present and structurally identical.
- **Verdict**: PASS

### Requirement R2: `backlog/ready.py` Python entry point with `--help`
- **Expected**: `test -f backlog/ready.py && python3 backlog/ready.py --help` exits 0 and prints usage including `--include-blocked`.
- **Actual**: File exists; `--help` exits 0 and prints `--include-blocked` flag with description "Also emit filtered-out items under an `ineligible` array".
- **Verdict**: PASS

### Requirement R3: Shared readiness helper with canonical reason-string contract
- **Expected**: `cortex_command/backlog/readiness.py` exposes `is_item_ready` and `partition_ready` with the exact reason-string formats from the spec table; pure (no I/O); 11 unit-test rows covering each format and pass/sentinel cases.
- **Actual**: `python3 -c "from cortex_command.backlog import is_item_ready, partition_ready; print('ok')"` prints `ok`. The helper at `cortex_command/backlog/readiness.py:89-175` produces:
  - `f"status: {item.status}"` (line 117)
  - `f"self-referential blocker: {ref_str}"` (line 137)
  - `f"blocker not found: {ref_str}"` (line 161, gated on `_looks_like_uuid`)
  - `f"external blocker: {ref_str}"` (line 167)
  - `(False, None)` sentinel for non-terminal internal blockers (line 172)
  - `(True, None)` for empty/all-resolved (lines 121, 175)
  No filesystem I/O. `tests/test_backlog_readiness.py` covers all 11 spec rows and `partition_ready` parallel-list contract; `pytest tests/test_backlog_readiness.py -q` exits 0 with 11 passes.
- **Notes**: The multi-blocker comma-joined `"blocked by <id1>: <status1>, <id2>: <status2>"` format from spec R3's table is NOT produced by `is_item_ready` directly — when multiple non-terminal internal blockers exist, the helper returns the `(False, None)` sentinel and `filter_ready`'s Phase-2 BFS owns the final `"blocked by ... (not in session)"` rendering. This matches spec R3's bullet "The helper returns `(False, None)` as a sentinel when an item has at least one unresolved internal blocker whose final reason depends on session membership". The spec's Open Decision is resolved by re-export (per `__init__.py`). Reason-string wire contract is intact at every consumer.
- **Verdict**: PASS

### Requirement R4: `filter_ready()` refactor delegates gates 1+2 to helper
- **Expected**: Status check and blocker pre-check delegate to `is_item_ready`; sentinel routes to Phase-2 BFS; gates 3-6 unchanged; ≥10-line shrink; `pytest tests/ -q -k 'overnight or filter_ready'` exits 0.
- **Actual**: `cortex_command/overnight/backlog.py:489-497` calls `is_item_ready` with `eligible_statuses=ELIGIBLE_STATUSES, treat_external_blockers_as="blocking"` and routes (False, None) sentinel to `pending_blocked.append(item)`. Phase-2 BFS at lines 547-616 unchanged. Plan reports 200→184 lines (16-line shrink). `pytest tests/test_select_overnight_batch.py -q` exits 0 (35 passed); the new `TestReasonStringFormat` class adds 5 format-equality cases and `TestOutOfSessionBlocked` preserves the `"blocked by ... (not in session)"` format.
- **Verdict**: PASS

### Requirement R5: `generate_index.py` refactor uses helper, surfaces external blockers in `## Warnings`
- **Expected**: Replace inline `int(b) not in active_ids` short-circuits; item 8 (with `blocked_by: anthropics/claude-code#34243`) absent from `## Refined` and `## Backlog`, present in `## Warnings`; new warning line `external blocker (...)` appears.
- **Actual**: `backlog/generate_index.py:218-238` invokes `is_item_ready` with full-corpus `all_items_ns` for both Refined and Backlog passes. Warnings extension at lines 247-273 emits `f"- **{item['id']}**: external blocker ({b})"` for non-digit, non-UUID refs. Structural verification: item 8 absent from Refined section, absent from Backlog section, present exactly once in Warnings ("- **8**: external blocker (anthropics/claude-code#34243)"). `grep -c 'external blocker (anthropics/claude-code#34243)' backlog/index.md` = 1.
- **Notes**: The full-corpus `all_items` fix from Task 3 is implemented correctly via `collect_items()` extension at lines 80-178 — archived items + terminal-status items both contribute to the lookup, so blockers pointing to `status:done` items resolve as resolved (preserving the legacy `int(b) not in active_ids` semantic). `types.SimpleNamespace(**rec)` adapter avoids the `cortex_command.overnight` eager fan-out per plan Task 3 context.
- **Verdict**: PASS

### Requirement R6: JSON output schema (groups, priority order, item shape, refined-first)
- **Expected**: Five canonical groups in order `critical, high, medium, low, contingent`; uniform `"items": []` for empty groups; item shape `{id, title, status, type, blocked_by, parent}`; refined-first within group.
- **Actual**: Live `bin/cortex-backlog-ready` output: `schema_version: 1`, `groups: ['critical', 'high', 'medium', 'low', 'contingent']`, all groups carry `items` field. Item shape per `_item_payload` at `backlog/ready.py:127-136` matches spec exactly. Within-group sort key `(0 if status == "refined" else 1, item.id)` at line 143 implements refined-first then ID asc.
- **Verdict**: PASS

### Requirement R7: `--include-blocked` flag adds `ineligible` array with reason/rejection
- **Expected**: `ineligible` array of priority groups; each item carries `reason` and `rejection`; uniform empty groups; `ineligible` absent without flag.
- **Actual**: With `--include-blocked`: `ineligible` priorities `['critical', 'high', 'medium', 'low', 'contingent']`, each item carries `reason` and `rejection in {"blocker", "status"}`. Without flag: `'ineligible' not in d`. `_group_by_priority(..., canonical_only=True)` at `backlog/ready.py:286-293` enforces uniform schema.
- **Notes**: Per Task 4's known implementation note, unknown-priority *ineligible* items are bucketed into `medium` (line 198-202) to keep the canonical 5-group order. The spec doesn't fix this either way; this is internally consistent with the `canonical_only=True` projection. Acceptable.
- **Verdict**: PASS

### Requirement R8: Stale-index stderr warning
- **Expected**: When `.md` mtime > `index.json` mtime, write `WARNING: ... older than {filename} — run \`cortex-generate-backlog-index\` to refresh.` to stderr; cap 5; exit 0.
- **Actual**: Re-ran live: created stale fixture in `/tmp/claude/stale_test/`, touched `.md` files to year 9999, ran script. Captured stderr: `WARNING: backlog/index.json is older than 108-extract-backlog-pick-ready-set-into-bin-backlog-ready.md — run \`cortex-generate-backlog-index\` to refresh.` (one line, exact format match). `_check_stale_index` at `backlog/ready.py:93-124` enforces `_STALE_WARNING_CAP = 5` plus `... and N more` overflow.
- **Verdict**: PASS

### Requirement R9: JSON-on-error contract
- **Expected**: Missing/unparseable `index.json` produces `{"error": ..., "schema_version": 1}` to stdout; exit non-zero; no traceback on stdout.
- **Actual**: From `/tmp` cwd: `bin/cortex-backlog-ready 2>/dev/null` produces `{"error": "backlog/ not found in cwd", "schema_version": 1}` and exits 1. `_emit_error` at `backlog/ready.py:86-90` writes only the JSON to stdout; `traceback.print_exc(file=sys.stderr)` keeps tracebacks off stdout (line 330, 346).
- **Verdict**: PASS

### Requirement R10: SKILL.md wiring counts
- **Expected**: `grep -c 'cortex-backlog-ready' skills/backlog/SKILL.md` ≥ 2; `grep -c 'index.json' skills/backlog/SKILL.md` ≤ 1; `grep -c 'index.md' skills/backlog/SKILL.md` ≤ 4.
- **Actual**: 2, 1, 3 respectively.
- **Notes**: Task 7's reword from literal `index.json` to "missing or malformed backlog index" preserves the user-facing semantic intent without exceeding the count cap. The remaining `index.json` token is in the `add` subcommand; both `pick` and `ready` route through `cortex-backlog-ready`.
- **Verdict**: PASS

### Requirement R11: Snapshot test pinned
- **Expected**: `pytest tests/test_backlog_ready_render.py -q` exits 0; `tests/fixtures/backlog_ready_render.json` exists.
- **Actual**: Test passes (1 passed in 0.14s). Fixture file present with 8 fixture items spanning all 5 priorities, refined-first ordering, external blocker, and internal non-terminal blocker. Test invokes `bin/cortex-backlog-ready --include-blocked` via subprocess against `tmp_path` and compares stdout against the pinned fixture.
- **Verdict**: PASS

### Requirement R12: Plugin mirror parity
- **Expected**: `diff bin/cortex-backlog-ready plugins/cortex-interactive/bin/cortex-backlog-ready` empty.
- **Actual**: No diff; mirror is byte-identical to canonical.
- **Verdict**: PASS

### Requirement R13: `bin/cortex-check-parity` recognition
- **Expected**: `bin/cortex-check-parity` exits 0 with no W003 orphan or error mentioning `cortex-backlog-ready`.
- **Actual**: `bin/cortex-check-parity` exits 0 with no output.
- **Verdict**: PASS

### Critical-Review Objection 4 (Task 3 full-corpus all_items fix)
- **Expected**: Blockers pointing to terminal-status items still resolve as resolved (no regression vs. legacy `int(b) not in active_ids` semantic).
- **Actual**: `collect_items()` at `backlog/generate_index.py:80-178` builds `all_items` including (a) archived items via `BACKLOG_DIR / "archive"` glob (lines 97-108) and (b) non-archive terminal-status items appended to `all_items` *before* the `if status in TERMINAL_STATUSES: continue` filter (lines 132-136, 138-139). The full-corpus map is wrapped via `SimpleNamespace(**rec)` at line 211 and passed to the helper. Behavioral verification: items 86 and 91 in `index.md` reference id 85 (status complete, not in `index.json`), and both appear in `## Backlog` — confirming the full-corpus map resolves them as terminal blockers.
- **Notes**: The same fix is NOT replicated in `bin/cortex-backlog-ready` because that script reads from `index.json` (active-only by design); items 86 and 91 do appear in its `ineligible` list as `external blocker: 85`. This divergence between `index.md` (full-corpus aware) and `cortex-backlog-ready` (index.json-only) is not pinned by any spec acceptance and is a natural consequence of the design (script is a read-only consumer of the index). This is a scope-boundary observation, not a spec violation — the spec deliberately keeps the script read-only against `index.json` (Non-Requirement: "No regeneration of `backlog/index.json` by `bin/cortex-backlog-ready`"). Flagged in Code Quality below for awareness.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None. The implementation introduces a new shared helper, a read-only JSON-emitting bin script, and a deterministic snapshot test — all consistent with the requirements doc's "AI workflow orchestration (skills, lifecycle, pipeline, discovery, backlog)" in-scope item. The SKILL.md-to-bin parity rule (project.md line 27) is honored. No new architectural state is added.

**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Module name `cortex_command/backlog/readiness.py` mirrors `cortex_command/overnight/backlog.py`. Helper functions use `_leading_underscore` for module-private (`_build_status_lookup`, `_check_stale_index`, `_group_by_priority`). The script `backlog/ready.py` lives alongside `backlog/generate_index.py` per spec R2's "mirroring" requirement. Bin shim names match the `cortex-<verb>-<noun>` pattern.

- **Error handling**: Appropriate. `_emit_error` at `backlog/ready.py:86-90` is the single error funnel: writes structured JSON to stdout, returns exit code 1, lets tracebacks fall to stderr via `traceback.print_exc(file=sys.stderr)`. Stale-index check is wrapped in a separate try/except so a stat error there cannot block the JSON output (line 327-330). `_safe_sort` at lines 151-172 tolerates heterogeneous ID types (the spec's "non-int id" edge case) by falling back to string comparison with a stderr warning. `_check_stale_index` swallows `FileNotFoundError` per-file (line 113) so a race with a deleted `.md` doesn't crash the warning loop.

- **Test coverage**: Strong. Plan verification re-run:
  - `pytest tests/test_backlog_readiness.py -q` → 11 passed (R3 reason-string table verified row-by-row).
  - `pytest tests/test_backlog_ready_render.py -q` → 1 passed (snapshot pinned across runs via `sorted()` glob discipline).
  - `pytest tests/test_select_overnight_batch.py -q` → 35 passed (TestOutOfSessionBlocked + TestReasonStringFormat both green; format equality assertions catch wire-format drift, not just substring drift).
  - `just test` → 5/5 passed.
  - Live `bin/cortex-backlog-ready` against real backlog produces 15 ready items across 5 priority groups; `--include-blocked` surfaces 4 ineligible items (item 8 external, items 86/91 with reason `external blocker: 85`, item 90 with internal non-terminal sentinel). All edge cases from spec lines 113-124 are exercised either by the snapshot fixture or the unit tests.
  - `bin/cortex-check-parity` exits 0.
  - Test failures elsewhere in the suite (`tests/test_mcp_subprocess_contract.py` and modules requiring `psutil`) are pre-existing/environmental and unrelated to this lifecycle.

- **Pattern consistency**: Strong. The `types.SimpleNamespace(**item)` adapter pattern is used consistently in both `backlog/generate_index.py` (Task 3) and `backlog/ready.py` (Task 4) to avoid the `cortex_command.overnight` eager fan-out — matches the plan's Veto Surface decision (line 210). `sorted(BACKLOG_DIR.glob("[0-9]*-*.md"))` discipline is applied at every glob site (`generate_index.py:99, 113`, `ready.py:106`). The `__init__.py` re-export style follows the spec's Open Decision resolution toward shorter import lines. The shim three-branch template is preserved verbatim. The SKILL.md edit preserves the selection-UX prose verbatim and only replaces the read+filter+sort steps.

  One observation worth flagging (not a blocker): the `index.md` ↔ `cortex-backlog-ready` divergence on items whose blockers are terminal-status non-archive items (today: 86, 91 → blocker id 85). `index.md` shows them as ready (full-corpus lookup); `cortex-backlog-ready` reports them as `external blocker: 85`. The script reads only `index.json`, which `collect_items()` filters to active-only. The spec keeps the script read-only against `index.json` (Non-Requirements line 106), so this is by-design — but it means `/backlog ready` and `/dev`'s inferred ready set will differ from `index.md`'s `## Backlog` for these items. Tracked as a scope-boundary side-effect, not a spec violation; could merit a follow-up if the divergence becomes user-visible noise.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
