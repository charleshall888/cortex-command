# Review: investigate-and-solve-conflict-aware-round-scheduling-in-overnight-runner

## Stage 1: Spec Compliance

### Requirement 1: `areas` field in BacklogItem
- **Expected**: `areas: list[str]` added to `BacklogItem` dataclass with `default_factory=list`. Optional; absent or empty means no constraint.
- **Actual**: Field added at `backlog.py:77` as `areas: list[str] = field(default_factory=list)`. Documented in docstring at line 53.
- **Verdict**: PASS

### Requirement 2: Three parsing sites updated
- **Expected**: `parse_backlog_dir()`, `load_from_index()`, and `generate_index.py` all parse the `areas` field.
- **Actual**: `parse_backlog_dir()` at line 276: `areas=_parse_inline_str_list(fm.get("areas", "[]"))`. `load_from_index()` at line 318: `areas=entry.get("areas") or []`. `generate_index.py` at line 126: `"areas": _parse_inline_str_list(fm.get("areas", "[]"))`.
- **Verdict**: PASS

### Requirement 3: Area-separation as hard pre-filter in `group_into_batches()`
- **Expected**: In Phase 2's batch-selection loop, check area overlap before tag overlap. If overlap exists AND incoming item has non-empty areas, skip that batch. Unit test required: two items with overlapping areas in different batches despite shared tags.
- **Actual**: Lines 926-937 of `backlog.py`: `item_areas = set(item.areas)`, then for each candidate batch, if `item_areas` is non-empty, compute `batch_areas` and skip if intersection exists. Test `test_overlap_forced_separation` verifies the behavior.
- **Verdict**: PASS

### Requirement 4: Silent absence behavior
- **Expected**: Empty `areas` list skips the area-separation check. No warning emitted. Identical to current algorithm.
- **Actual**: The check `if item_areas:` at line 932 ensures the pre-filter is skipped entirely when the incoming item has no areas. Test `test_silent_absence_allows_same_batch` verifies items with empty areas can co-batch with area-bearing items.
- **Verdict**: PASS

### Requirement 5: Worst-case documentation
- **Expected**: When all items share areas, every item gets its own single-item batch (fully serialized). This behavior must be documented in `schema.md`.
- **Actual**: Test `test_full_serialization` verifies 4 items with the same area produce 4 single-item batches. `schema.md` line 18 documents: "When all items in a session share an area, every item runs in its own single-item batch (fully serialized execution) -- this is intended."
- **Verdict**: PASS

### Requirement 6: Quick wins exemption
- **Expected**: Phase 1 quick-win items (up to 2 bug/chore) form a standalone first batch, exempt from area-separation. Accepted limitation.
- **Actual**: Quick wins are extracted at lines 905-912 before Phase 2 begins. Phase 2 iterates `remaining` (which excludes quick wins). Quick wins are prepended as batch 1 at lines 967-970. No area check applies to them.
- **Verdict**: PASS

### Requirement 7: `_split_oversized_batch()` -- no changes needed
- **Expected**: No area-locality logic added to the split function.
- **Actual**: `_split_oversized_batch()` (lines 808-870) contains no references to `areas`. Unchanged from pre-feature state.
- **Verdict**: PASS

### Requirement 8: `_detect_risks()` replacement in `plan.py`
- **Expected**: Replace tag-overlap-across-batches check with area-overlap-within-batch check. Keep parent-epic check. No more tag-overlap-across-batches warnings.
- **Actual**: `_detect_risks()` at plan.py lines 47-91 retains the parent-epic cross-batch check (lines 59-73) and adds area-overlap-within-batch detection (lines 76-89). Grep confirms no tag-overlap logic remains in the function.
- **Verdict**: PASS

### Requirement 9: `/refine` writes `areas:` field
- **Expected**: At spec approval time (Step 5 write-back), infer areas from the final spec and write to backlog item. Two separate `update-item` calls. Step 6 lists `areas` in written fields. Inference rule uses canonical names. Cross-cutting fallback: `areas=[]` for 4+ subsystems.
- **Actual**: SKILL.md Step 5 "Write-Back on Approval" (lines 163-181): includes inference instructions with canonical area names, cross-cutting fallback, and two separate `update-item` calls (one for status+spec, one for areas). Step 6 (line 189): lists `areas` in "Backlog fields written". Outputs frontmatter (line 9) includes `areas:`.
- **Verdict**: PASS

### Requirement 10: Schema documentation updated
- **Expected**: `schema.md` documents `areas` field: type, purpose, format, population responsibility, silent-absence behavior, worst-case serialization, degradation profile.
- **Actual**: `schema.md` line 18 documents all required aspects: type (`list[str]`), purpose ("Area-separation constraint for overnight scheduling"), format ("Inline YAML only"), population ("Written by `/refine` at spec approval time"), silent-absence ("If absent or empty, separation constraint is silently skipped"), worst-case serialization ("fully serialized execution -- this is intended"), and degradation ("Zero effect until populated; protection scales with how many items have the field"). Canonical names listed.
- **Verdict**: PASS

### Requirement 11: Unit tests for area-separation
- **Expected**: 6 specific tests covering overlap forced separation, silent absence, no-overlap with tags, full serialization, no-areas-no-risks, and area-overlap-within-batch detected.
- **Actual**: All 6 tests present in `tests/test_select_overnight_batch.py`:
  - `test_overlap_forced_separation` (lines 403-419)
  - `test_silent_absence_allows_same_batch` (lines 421-437)
  - `test_no_overlap_tags_preserved` (lines 439-455)
  - `test_full_serialization` (lines 457-471)
  - `test_no_areas_no_risks` (lines 481-499)
  - `test_area_overlap_within_batch_detected` (lines 501-513)
  All 23 tests pass.
- **Verdict**: PASS

## Requirements Compliance

- **Complexity must earn its place**: The implementation is minimal and additive. The area-separation check is 6 lines in the batch-selection loop. The `_detect_risks` replacement is a clean swap of one check for another. No new abstractions, no new files, no new dependencies. The complexity is proportional to the problem solved.
- **Graceful partial failure**: Items without `areas` are unaffected (silent absence). The feature degrades gracefully to the existing algorithm when areas are not populated. No new failure modes introduced.
- **File-based state**: Areas are stored in backlog YAML frontmatter and propagated through `index.json`. No database or server. Consistent with project constraints.
- **Maintainability through simplicity**: The implementation follows existing patterns (inline YAML array parsing, pre-filter in the batch loop, risk detection in plan.py). No novel patterns introduced.
- **Self-contained artifacts**: The spec, schema docs, SKILL.md, and tests are each self-contained. The spec documents edge cases, the schema documents the field, the SKILL.md documents the write-back, and the tests verify all key behaviors.

## Stage 2: Code Quality

- **Naming conventions**: `areas` field name is consistent with `tags` and `blocks` (plural noun, list type). `item_areas`, `batch_areas` local variables follow the `item_tags`, `batch_tags` pattern already in the function. `areas_i`, `areas_j` in `_detect_risks` follow the `parents_by_batch[i]`/`[j]` pattern. Canonical area names use kebab-case consistent with existing tag conventions.
- **Error handling**: No new error paths needed. Absent/empty areas produce empty sets, which have no intersection, so the check naturally no-ops. The `or []` fallback in `load_from_index()` handles missing keys. Consistent with existing `tags` handling.
- **Test coverage**: All 6 spec-required tests are present and pass. Tests cover the four key behaviors (forced separation, silent absence, tag-grouping preserved, full serialization) and both `_detect_risks` scenarios (no false positives, violation detected). Tests use the existing `_make_item` helper and follow the file's test class organization pattern.
- **Pattern consistency**: The area pre-filter in `group_into_batches()` follows the same structure as the existing tag-overlap computation (compute sets, check intersection). The `_detect_risks()` within-batch check mirrors the existing across-batch parent-epic check structure. The `generate_index.py` `areas` entry sits alongside the existing `tags` entry. SKILL.md write-back uses the same `update-item` pattern as `status` and `spec`.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": []}
```
