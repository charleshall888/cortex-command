# Review: backlog-index-surface-deferred-parked-state

## Stage 1: Spec Compliance

### Requirement 1: `deferred` tag is the recognized signal source, matched case-insensitively
- **Expected**: `_is_deferred` predicate does whole-element `.strip().lower() == "deferred"` match; `deferred-feature-work` must NOT fire; covered by case-variant test and negative whole-element test.
- **Actual**: `generate_index.py:74–76` implements `any(tag.strip().lower() == "deferred" for tag in item.get("tags", []))` — exact whole-element equality after normalization. Test class `TestDeferredFeatureWorkTagIsNotDeferred` (item `ITEM_E`, tags=["deferred-feature-work"]) pins the negative control with three assertions. Test class `TestCaseInsensitiveDeferred` (item `ITEM_D`, tags=["Deferred"]) pins the case-variant. Both classes exercise the live predicate through `generate_md`.
- **Verdict**: PASS

### Requirement 2: Status-cell annotation
- **Expected**: Deferred item's Status cell renders `<raw-status> (deferred)` (e.g. `backlog (deferred)`); full-row equality assertion required; control item has no suffix.
- **Actual**: `generate_index.py:235` sets `status_display = f"{item['status']} (deferred)" if _is_deferred(item) else item["status"]` and incorporates it into the row. `TestStatusCellAnnotation.test_deferred_item_row_contains_annotation` asserts full-row equality `"| 1 | Parked Feature | backlog (deferred) | medium | feature | — | — | — |" in md`. `test_control_item_row_has_no_deferred_suffix` asserts the control row full equality without suffix. `test_control_row_does_not_contain_deferred_suffix` adds an explicit negative assertion.
- **Verdict**: PASS

### Requirement 3: `index.json` is unchanged
- **Expected**: `generate_json` for a deferred-tagged item yields `record["status"] == "backlog"` and `"deferred" in record["tags"]`; no JSON field added, removed, or reshaped.
- **Actual**: `generate_json` (lines 215–217) is untouched — it serializes the item dict as-is. `TestGenerateJsonUnchanged` has two assertions: `records[0]["status"] == "backlog"` and `"deferred" in records[0]["tags"]`, both verified against `ITEM_A` (status=backlog, tags=["deferred"]).
- **Verdict**: PASS

### Requirement 4: Suppress deferred items from `## Refined` and `## Backlog`
- **Expected**: Deferred-tagged items skipped in both grouping loops; `is_item_ready` not modified.
- **Actual**: `generate_index.py:253–254` adds `if _is_deferred(item): continue` in the `## Refined` loop; `generate_index.py:269–270` adds the same guard in the `## Backlog` loop. `is_item_ready` is not modified (Req 6 confirms the file is unchanged). `TestGroupingSuppression.test_deferred_backlog_absent_from_backlog_section` verifies item 1 (deferred backlog) is absent from the `## Backlog` section; `test_control_backlog_present_in_backlog_section` verifies item 2 (control) is present; `test_deferred_refined_absent_from_refined_section` verifies item 3 (deferred refined) is absent from `## Refined`.
- **Verdict**: PASS

### Requirement 5: Table row is preserved
- **Expected**: Deferred item still has a row in the master table (not suppressed from the table, only from groupings).
- **Actual**: The master table loop (`generate_index.py:231–240`) has no `_is_deferred` guard — every active item gets a row. `TestGroupingSuppression.test_deferred_item_row_present_in_table` isolates the table region (`md.split("## ")[0]`) and asserts `"| 1 |" in table_region`.
- **Verdict**: PASS

### Requirement 6: No shared-logic or consumer change
- **Expected**: `git diff --name-only "$(git merge-base HEAD main)" -- cortex_command/` lists only `cortex_command/backlog/generate_index.py`.
- **Actual**: Running `git diff --name-only "$(git merge-base HEAD main)" -- cortex_command/` returns exactly `cortex_command/backlog/generate_index.py`. No changes to `readiness.py`, `ready.py`, `overnight/backlog.py`, or `common.py`.
- **Verdict**: PASS

### Requirement 7: Tests — new test file covering Reqs 1–5
- **Expected**: `tests/test_generate_backlog_index.py` exists, is collected, and the Req 1–5 assertions pass. `just test` exit 0 (with the environmental worktree caveat for `test-init`).
- **Actual**: File exists at `tests/test_generate_backlog_index.py`. Running `.venv/bin/pytest tests/test_generate_backlog_index.py -q` yields `14 passed in 0.02s`. All four fixture items (a)–(e) are present. `just test-pipeline` and `just test-overnight` pass (250 and 439 tests respectively). The `test-init` suite failure is the pre-existing environmental worktree guard (F9) unrelated to this feature, as documented.
- **Verdict**: PASS

### Requirement 8: Document the `deferred` tag convention
- **Expected**: Note added under `tags` field region in `skills/backlog/references/schema.md` stating: `deferred` tag is a parked-state signal, annotated in table, excluded from actionable groupings, index-view flag only (does not remove from overnight selection).
- **Actual**: `schema.md` line 17 (the `tags` row) appends the exact required note: "The `deferred` tag is recognized by the index generator as a parked-state signal: in the master table the item's Status cell renders `<status> (deferred)`, and the item is excluded from the `## Refined` and `## Backlog` actionable groupings. This is an index-view flag only — it does NOT affect overnight selection (`is_item_ready`). To fully park an item from overnight, set a non-eligible `status` (e.g. `abandoned`)." `grep -c 'deferred' skills/backlog/references/schema.md` = 1, and the note is within the `tags`-field row. The plugin mirror `plugins/cortex-core/skills/backlog/references/schema.md` is also updated (confirmed via `git diff --name-only`).
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `_is_deferred` follows the existing `_parse_inline_str_list` / `_opt` private-helper naming pattern (underscore-prefixed, snake_case, action-oriented). Consistent with the module's conventions.

- **Error handling**: `_is_deferred` uses `item.get("tags", [])` — safe default for missing key, no uncaught exceptions. Consistent with how `item.get("priority", "medium")` and similar accesses are handled elsewhere in `collect_items`.

- **Test coverage**: The test file is complete and non-trivial. Fixtures are distinct (items a–e cover distinct behavioral categories). Assertions use full-row equality for Req 2 (not bare substring), section-split isolation for grouping checks (Req 4/5), and JSON deserialization for Req 3. The `_md_for` helper correctly passes `all_items=items` so `is_item_ready`'s blocker resolution has a valid corpus. The negative whole-element control (item e) is a meaningful regression pin — a naive `"deferred" in tag` implementation would fail it. The fixture style mirrors `tests/test_select_overnight_batch.py` (module-level item dicts, helper function for call setup).

- **Pattern consistency**: `_is_deferred` is placed at module level between `_parse_inline_str_list` and `_opt` — the correct placement for a private predicate helper, consistent with the file's existing helper ordering. The local `status_display` variable (line 235) follows the `blocked_display` / `parent_display` / `spec_display` pattern in the same loop body (lines 232–235): each is a conditional expression assigned to a local, then interpolated into the f-string. No deviation from the established style. The deferred guard in the grouping loops (`if _is_deferred(item): continue`) mirrors the pattern for the status filter above it (`if item["status"] != "refined": continue`).

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
