# Plan: Conflict-Aware Round Scheduling via `areas:` Field

## Overview

Implement the `areas:` field as a hard area-separation constraint in the overnight runner's batch-grouping algorithm. The change is purely additive: a new optional field on `BacklogItem` flows through three parsing sites into `group_into_batches()` Phase 2, where it acts as a pre-filter that forces area-overlapping items into separate rounds. A corresponding update to `_detect_risks()` replaces the backwards tag-overlap check with an areas-within-batch validation. Six unit tests and documentation round out the implementation.

## Tasks

### Task 1: Add `areas` field to BacklogItem dataclass and all three parsing sites

- **Files**: `claude/overnight/backlog.py`, `backlog/generate_index.py`
- **What**: Add `areas: list[str] = field(default_factory=list)` to the `BacklogItem` dataclass and ensure all three construction sites populate it from source data. This is the foundational data-model change that Tasks 2 and 3 depend on.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - `BacklogItem` dataclass definition starts at `claude/overnight/backlog.py:41`. Add `areas` after the existing `tags` field (line ~50) to keep related fields together.
  - `parse_backlog_dir()` constructs `BacklogItem` at `backlog.py:~267–289` using `fm.get(...)` calls. Add: `areas=_parse_inline_str_list(fm.get("areas", "[]"))`. The `_parse_inline_str_list()` utility is already defined at `backlog.py:~154` — use the same utility as for `tags`.
  - `load_from_index()` constructs `BacklogItem` at `backlog.py:~308–332` from a JSON dict. Add: `areas=entry.get("areas") or []`.
  - `backlog/generate_index.py` outputs a dict per backlog item at `~line 125` where `"tags": _parse_inline_str_list(fm.get("tags", "[]"))` already exists. Add an adjacent line: `"areas": _parse_inline_str_list(fm.get("areas", "[]"))`. The `_parse_inline_str_list` function is imported/defined in that file already (it handles inline YAML arrays like `[foo, bar]`).
- **Verification**: Run `python3 -c "from cortex_command.overnight.backlog import BacklogItem; b = BacklogItem(); assert b.areas == []"` to confirm the default. Run `python3 backlog/generate_index.py` and check that `backlog/index.json` entries include an `"areas"` key (value `[]` for items without the field). Run existing tests to confirm no regressions: `python3 -m pytest tests/test_select_overnight_batch.py -x`.
- **Status**: [x] complete

---

### Task 2: Implement area-separation pre-filter in `group_into_batches()` Phase 2

- **Files**: `claude/overnight/backlog.py`
- **What**: Insert an area-overlap check before the tag-overlap assignment in Phase 2's batch-selection loop so that items with overlapping areas are forced into separate batches.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Phase 2 runs at `backlog.py:915–940`. The loop iterates `enumerate(batches)` where each element is a `tuple[list[BacklogItem], set[str]]` — `(batch_items, batch_tags)`.
  - At the top of the inner loop (after extracting `batch_items` from the tuple but before computing tag overlap), add the pre-filter: collect the areas of the incoming item and the union of areas across all items already in the candidate batch. If both the incoming item and the candidate batch have non-empty area sets that share at least one area, skip that candidate batch and move on to the next one.
  - The existing tie-break logic (`best_overlap`, `best_batch_size`) is unchanged — the pre-filter only gates which batches are candidates. If all existing batches are skipped, the algorithm falls through to opening a new batch (the `best_idx == -1` path at `~line 936`).
  - Do not modify Phase 1 (quick wins extraction at `~lines 900–912`) or Phase 3 (`_split_oversized_batch()` at `~lines 942–949`).
- **Verification**: Manually verify inline (Task 4 adds the full test suite — this step must be self-contained): construct two `BacklogItem` instances with `tags=["auth"]` and `areas=["overnight-runner"]`; call `group_into_batches([(item1, 1.0), (item2, 1.0)], batch_size_cap=5)` and confirm they land in different batches (different list indices in the result). Also verify negative case: same two items with `areas=[]` land in the same batch. Run `python3 -m pytest tests/test_select_overnight_batch.py -x` to confirm existing tests still pass.
- **Status**: [x] complete

---

### Task 3: Replace `_detect_risks()` tag-overlap check with area-within-batch validation

- **Files**: `claude/overnight/plan.py`
- **What**: Replace the tag-overlap-across-batches check (lines 77–93) with an area-overlap-within-batch check. Keep the parent-epic check (lines 61–75) unchanged.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - `_detect_risks()` signature at `plan.py:47`: `def _detect_risks(batches: list[Batch]) -> list[str]`. Return type and signature unchanged.
  - Current lines 61–75: iterates pairs of batches, finds shared `parent` IDs across batches. **Keep this section as-is.**
  - Current lines 77–93: iterates pairs of batches, finds overlapping tag sets. **Replace this section.**
  - Replacement logic: iterate each batch; for each batch, check all pairs of items within the same batch for area overlap. When two items in the same batch share at least one area name, append a risk string that identifies the batch by its `batch_id`, names both items by their `title` fields, and lists the sorted shared area names. Frame the message as a possible area-separation constraint violation.
  - When `item.areas` is empty on both items, the intersection is empty — no risk appended. This is the correct behavior for items without areas.
  - `render_session_plan()` at `plan.py:231` calls `_detect_risks(selection.batches)` and renders its return value under `## Risks`. No change to the call site is needed — the function signature and return type are unchanged.
- **Verification**: Manually verify inline (pass `list[Batch]` directly — not `SelectionResult`): construct two `Batch` objects each containing one `BacklogItem` with `areas=[]`; call `_detect_risks([batch1, batch2])` and confirm an empty list is returned (no false positives). Then construct one `Batch` containing two `BacklogItem` instances both with `areas=["overnight-runner"]`; call `_detect_risks([batch])` and confirm a non-empty list is returned (area collision detected). Run `python3 -m pytest tests/test_select_overnight_batch.py -x` to confirm existing tests pass.
- **Status**: [x] complete

---

### Task 4: Add unit tests for area-separation

- **Files**: `tests/test_select_overnight_batch.py`
- **What**: Add 6 unit tests — 4 for `group_into_batches()` area-separation behavior and 2 for the `_detect_risks()` replacement.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**:
  - Test file already imports from `claude.overnight.backlog` (check existing imports at top of file for the exact import pattern). Import `_detect_risks` from `claude.overnight.plan` for the two detect-risks tests.
  - Helper: construct `BacklogItem` instances with `areas=`, `tags=`, `title=` fields for test clarity. The existing tests construct `BacklogItem` directly — follow the same pattern.
  - Test 1 (overlap forced separation): two items with `areas=["overnight-runner"]` AND `tags=["auth"]` → must land in different batches.
  - Test 2 (silent absence): item A with `areas=["overnight-runner"]`, item B with `areas=[]` and same tags → may land in same batch (silent absence applies).
  - Test 3 (no-overlap tags preserved): item A with `areas=["overnight-runner"]`, item B with `areas=["skills"]`, both with `tags=["auth"]` → may land in same batch (no area overlap, tag grouping applies).
  - Test 4 (full serialization): 4 items all with `areas=["overnight-runner"]` → 4 batches of 1 item each.
  - Test 5 (detect_risks: no areas): construct 2 batches with items having no areas → `_detect_risks()` returns `[]`.
  - Test 6 (detect_risks: area overlap within batch): construct a `Batch` containing 2 items with `areas=["overnight-runner"]` → `_detect_risks()` returns a non-empty list.
  - For Tests 5–6: construct `Batch` objects directly (import `Batch` from `claude.overnight.backlog`). `_detect_risks()` takes a `list[Batch]`.
- **Verification**: `python3 -m pytest tests/test_select_overnight_batch.py -x -v` — all 6 new tests pass. Run full test suite `python3 -m pytest tests/ -x` to confirm no regressions.
- **Status**: [x] complete

---

### Task 5: Update `/refine` SKILL.md with areas write-back

- **Files**: `skills/refine/SKILL.md`
- **What**: Update Step 5 (Write-Back on Approval) to include the areas write-back, and Step 6 (Completion summary) to list `areas` as a written field. Also add area-inference guidance to Step 5.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `skills/refine/SKILL.md` Step 5, "Write-Back on Approval" currently shows: `update-item {backlog-filename-slug} status=refined spec=lifecycle/{lifecycle-slug}/spec.md`. Add a **separate second call** immediately after: `update-item {backlog-filename-slug} "areas=[area1,area2]"`. Do NOT combine with the existing call — keep them as two sequential invocations to avoid argument-parsing ambiguity with list values. For empty areas: `update-item {backlog-filename-slug} "areas=[]"`. The quoted string preserves the list format through shell argument parsing.
  - Inference rule to add in Step 5 (before the write-back calls): identify which subsystem the feature primarily modifies. Canonical names: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`. Use the primary subsystem only — the one where most files change. If the feature spans 4+ subsystems with no clear primary, use `areas=[]`.
  - Timing: both write-back calls fire at spec approval time (not draft time).
  - Step 6 completion summary currently lists: `complexity`, `criticality`, `status: refined`, `spec`. Add `areas` to this list.
  - Do not change any other steps or the skill's overall structure.
- **Verification**: Read the updated SKILL.md and confirm Step 5 shows `areas` in the write-back and Step 6 lists `areas` in the completion summary. No automated test needed.
- **Status**: [x] complete

---

### Task 6: Update backlog schema documentation with `areas` field

- **Files**: `skills/backlog/references/schema.md`
- **What**: Document the new `areas` field in the backlog item schema reference.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `skills/backlog/references/schema.md` contains a schema table/template listing all supported frontmatter fields. Add `areas` near `tags` (alphabetical or grouped with related fields).
  - Required documentation content:
    - **Type**: `list[str]` — inline YAML array, e.g. `areas: [overnight-runner, backlog]`
    - **Purpose**: Area-separation constraint for overnight scheduling. Features with overlapping areas are assigned to different rounds.
    - **Population**: Written by `/refine` at spec approval time. Optional — absent/empty means no constraint applied.
    - **Silent absence**: If field is absent or empty, the separation constraint is silently skipped. Behavior is identical to the current algorithm.
    - **Worst case**: If all items in a session share an area, every item runs in its own single-item batch (fully serialized execution). This is the intended behavior.
    - **Degradation profile**: The constraint has zero effect until `areas` is populated. Protection scales with how many items in a session have the field. Pre-existing items without `areas` receive no protection.
    - **Canonical area names**: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`
- **Verification**: Read the updated schema file and confirm the `areas` field appears with all required documentation points.
- **Status**: [x] complete

---

## Verification Strategy

After all tasks complete:

1. Run the full test suite: `python3 -m pytest tests/ -v` — all tests pass including the 6 new area-separation tests.
2. Run `python3 backlog/generate_index.py` and confirm `backlog/index.json` entries contain `"areas": []` (not missing the key).
3. Construct a synthetic overnight session plan with 3 features that share `areas: [overnight-runner]` and 2 features with `areas: []`. Call `select_overnight_batch()` and confirm:
   - The 3 area-bearing features land in 3 separate batches
   - The 2 area-less features are grouped by tags as before
4. Verify `_detect_risks()` returns an empty list for the resulting batches (no area overlap within any batch).
5. Read `skills/refine/SKILL.md` Step 5 and confirm areas write-back is documented at approval time.
6. Read `skills/backlog/references/schema.md` and confirm `areas` field is documented with canonical names and degradation profile.
