# Specification: Conflict-Aware Round Scheduling via `areas:` Field

> Epic reference: `research/overnight-merge-conflict-prevention/research.md` — this ticket implements Approach A (areas-field declaration + scheduling constraint) from that epic. Approaches C and D (morning report) are complete in tickets 015 and 016.

## Problem Statement

The overnight runner groups features into parallel execution rounds using a greedy tag-similarity algorithm. For features from a single discovery session, shared tags cluster the conflict-prone features together — producing the worst-case scheduling for conflict avoidance. No file-level or subsystem overlap detection exists at scheduling time. This spec adds an `areas:` field to backlog YAML frontmatter that declares which subsystems a feature touches, and uses it as a hard separation constraint in the grouping algorithm, so features with overlapping areas are assigned to different (sequential) rounds rather than the same parallel round.

**Important**: This is a purely additive, opt-in feature. It has zero effect on scheduling until `areas` fields are populated on backlog items. The constraint's effectiveness scales with adoption — a session where no items have `areas` populated behaves identically to the current system.

## Requirements

1. **`areas` field in BacklogItem**: `areas: list[str]` added to the `BacklogItem` dataclass at `claude/overnight/backlog.py:41–91`, with `default_factory=list`. Field is optional; absent or empty means no area constraint applies.

2. **Three parsing sites updated**: All three locations that construct `BacklogItem` instances must parse the `areas` field:
   - `parse_backlog_dir()` (~line 288): `areas=_parse_inline_str_list(fm.get("areas", "[]"))`
   - `load_from_index()` (~line 331): `areas=entry.get("areas") or []`
   - `backlog/generate_index.py` (~line 125): add `"areas": _parse_inline_str_list(fm.get("areas", "[]"))` to the index entry

3. **Area-separation as hard pre-filter in `group_into_batches()`**: In Phase 2's batch-selection loop (`backlog.py:915–940`), before computing tag overlap for a candidate batch, check whether any item in that batch has overlapping areas with the incoming item. If area overlap exists AND the incoming item has a non-empty `areas` list, skip that candidate batch. This makes area-separation a hard constraint: area overlap always forces a new batch, even when tag overlap would otherwise group them together.
   - Acceptance criteria: a unit test must verify that two items with overlapping areas are placed in different batches even when they share tags.

4. **Silent absence behavior**: When an item has an empty `areas` list (field absent or `[]`), the area-separation check is skipped for that item. No warning is emitted. Behavior is identical to the current algorithm. This is the defined fallback for items where areas are unknown or unset.

5. **Worst-case documentation**: When all items share areas, every item goes into its own single-item batch, and overnight execution is fully serialized. This is the intended outcome when areas genuinely overlap — serialized execution is preferable to parallel execution that will conflict. This behavior must be noted in the `skills/backlog/references/schema.md` documentation for the `areas` field.

6. **Quick wins exemption**: Phase 1 quick-win items (up to `_MAX_QUICK_WINS=2` bug/chore items) form a standalone first batch and are **exempt** from area-separation. They run before Phase 2's separation logic. If two quick-win items share areas and modify the same files, they will conflict — this is an accepted limitation. The maximum is 2 quick wins, making the conflict surface small.

7. **`_split_oversized_batch()` — no changes needed**: Phase 2 ensures all items in a batch have non-overlapping areas. Since `_split_oversized_batch()` only splits an existing batch (never merges items from outside), all resulting sub-batches will also have non-overlapping areas. No area-locality logic needs to be added to the split function.

8. **`_detect_risks()` replacement in `plan.py:47`**: Replace the tag-overlap-across-batches check (lines 77–93) with an area-overlap-within-batch check that validates the area-separation constraint was honored. Keep the parent-epic check (lines 61–75) unchanged. The replacement check should iterate each batch and flag any batch containing two or more items with overlapping areas.
   - Note: the existing tag-overlap-across-batches warnings will no longer be emitted after this change. This is intentional — that check flagged tag overlap across clusters, which `group_into_batches()` deliberately produces (tag similarity is a grouping attractor). Those warnings were checking the wrong condition and providing no useful signal.

9. **`/refine` writes `areas:` field**: When `/refine` produces a spec, it must determine which areas the feature touches and write them to the backlog item. Specifically:
   - **Timing**: areas are inferred from the **final approved spec** and written at approval time, as part of the existing approval write-back in Step 5 (alongside `status=refined` and `spec=...`). Areas must NOT be written at draft time, before user approval.
   - **Inference rule**: An area is in scope if the feature primarily modifies files in that subsystem. Use the primary subsystem focus — not every tangentially-touched file. The canonical area names are: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`. A feature that modifies `claude/overnight/backlog.py` declares `overnight-runner`. A feature that modifies `skills/refine/SKILL.md` declares `skills`.
   - **Cross-cutting fallback**: if the feature spans 4+ subsystems with no clear primary, write `areas: []`.
   - **SKILL.md update required**: `skills/refine/SKILL.md` Step 5 (Write-Back on Approval) must be updated to include the `areas` write-back, and Step 6 (Completion summary) must add `areas` to the list of written fields.

10. **Schema documentation updated**: `skills/backlog/references/schema.md` must document the `areas` field: type (`list[str]`), purpose (area-separation constraint in overnight scheduling), format (inline YAML array), population responsibility (`/refine` at spec approval time), the silent-absence behavior, and the worst-case serialization behavior. Must also document the degradation profile: the constraint has zero effect for items without areas, and protection scales with how many items in a session have the field populated.

11. **Unit tests for area-separation**: `tests/test_select_overnight_batch.py` must include:
    - Test: two items with overlapping areas AND overlapping tags → placed in different batches
    - Test: two items with overlapping areas but one has empty `areas` → placed together (silent absence)
    - Test: two items with no area overlap AND overlapping tags → placed in same batch (areas don't break tag grouping when no overlap)
    - Test: all items share one area → each item in its own single-item batch (serialization)
    - Test (`_detect_risks()`): batches where no items have areas → returns empty risk list (no false positives from replacement)
    - Test (`_detect_risks()`): a batch containing two items with overlapping areas → returns a risk warning (constraint violation detected)

## Non-Requirements

- No automatic inference of areas from plan file content or lifecycle spec files (Approach B — deferred)
- No canonical allowlist of valid area names — convention-based, no validator
- No changes to morning report (completed in 015 and 016)
- No changes to merge mechanics or conflict resolution
- No enforcement of `areas` population — field remains optional throughout
- No warning emitted when `areas` is absent on a backlog item
- No test required for `/refine`'s area write-back (verified by human review of spec output)

## Edge Cases

- **All items share areas** → single-item batches → fully serialized execution. Expected behavior; documented in schema.
- **Some items have areas, some don't** → items without areas participate in tag-only grouping and can co-batch with any item, including area-bearing items that share their files. The area constraint provides no protection for these items. This is the expected behavior for a session early in adoption, before most items have `areas` populated. Items without areas are not protected from each other OR from area-bearing items that touch the same subsystem.
- **Empty `areas: []`** → treated as absent; no constraint applied for this item.
- **Single item with areas** → placed normally; no isolation needed since there's nothing to conflict with.
- **Quick wins with area overlap** → both placed in Phase 1's standalone batch; no area check runs. Accepted limitation (max 2 quick wins).
- **`_detect_risks()` with no areas populated** → area-within-batch check finds no overlap in any batch (all empty area sets); function returns no risks. The existing tag-overlap-across-batches warnings from the old implementation will also be gone — that is the intended behavior (those warnings were checking the wrong condition).
- **Implementation ordering**: Requirement 1 (add `areas` to `BacklogItem`) must be deployed before Requirements 3 and 8 — both access `item.areas`. The three requirements should be implemented and tested together as a single atomic change.

## Technical Constraints

- `areas` field must live on backlog YAML frontmatter (not lifecycle spec) — `group_into_batches()` receives only `BacklogItem` data and never opens lifecycle files at scheduling time.
- `generate_index.py` must include `areas` in its index output or `load_from_index()` will return empty areas lists even when the backlog YAML has the field populated. `update-item` already regenerates the index automatically; manual YAML edits without running `update-item` may leave the index stale.
- Inline YAML array format: `areas: [overnight-runner, backlog]` — same convention as `tags`. Parsed by `_parse_inline_str_list()` (already exists).
- The `areas` field on this backlog item (017) should be `[overnight-runner]` once written.

## Open Decisions

- None — all design decisions resolved in research and spec.
