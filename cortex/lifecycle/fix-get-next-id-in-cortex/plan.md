# Plan: fix-get-next-id-in-cortex

## Overview

Add an inline range-exclusion predicate to `_get_next_id` in `cortex_command/backlog/create_item.py` so the allocator skips IDs 990–999 (reserved for dashboard-seed fixtures). Write a new pytest module covering the seeded, unseeded, and zero-padding cases to lock in behavior. Tests-first ordering keeps each task's verification self-contained without self-sealing.

## Outline

### Phase 1: Reserve the seed range in the allocator (tasks: 1, 2)
**Goal**: ID allocation in `cortex-create-backlog-item` excludes 990–999 from the `max + 1` computation, with regression coverage in place.
**Checkpoint**: `pytest tests/test_create_backlog_item.py -v` exits 0 with 3 passing tests; `grep -F "reserved for dashboard-seed fixtures" cortex_command/backlog/create_item.py` returns ≥ 1.

## Tasks

### Task 1: Create test module covering _get_next_id
- **Files**: `tests/test_create_backlog_item.py` (new)
- **What**: Add a pytest module with three tests for `_get_next_id` using `tmp_path` backlog directories — covering seeded-present, seeded-absent, and zero-padding scenarios. Tests reference `_get_next_id` by direct import from `cortex_command.backlog.create_item`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Module under test: `cortex_command/backlog/create_item.py:_get_next_id` (lines 36–44), signature `_get_next_id(backlog_dir: Path) -> str`.
  - Import path: `from cortex_command.backlog.create_item import _get_next_id`.
  - Pattern reference for fixture style: `tests/test_backlog_readiness.py` and `tests/test_resolve_backlog_item.py` both use `tmp_path` to construct synthetic backlog directories; follow that shape.
  - Test cases to encode:
    1. `test_skips_seed_range_when_seeds_present` — populate `tmp_path` with `229-foo.md` plus `990-seed-alpha.md` through `994-seed-epsilon.md`; expect return value `"230"`.
    2. `test_falls_back_to_max_plus_one_without_seeds` — populate `tmp_path` with `001-foo.md` and `229-bar.md`; expect return value `"230"`.
    3. `test_zero_pads_small_ids` — populate `tmp_path` with `001-foo.md`; expect return value `"002"`.
  - Content of each `NNN-*.md` file may be a minimal stub (`# stub`); `_get_next_id` only reads filenames via the glob, not file contents.
- **Verification**: `ls tests/test_create_backlog_item.py` exits 0; `grep -c "_get_next_id" tests/test_create_backlog_item.py` ≥ 3; `grep -c "tmp_path" tests/test_create_backlog_item.py` ≥ 3. Pass if all three checks hold.
- **Status**: [x] completed

### Task 2: Add reservation predicate to _get_next_id
- **Files**: `cortex_command/backlog/create_item.py`
- **What**: Add an `if not (990 <= int(m.group(1)) <= 999)` predicate to the list comprehension inside `_get_next_id`, with an inline comment `# reserved for dashboard-seed fixtures (cortex_command/dashboard/seed.py)` on or adjacent to the predicate line. Preserve function signature, return-type, and zero-padding behavior.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Edit site: `cortex_command/backlog/create_item.py` lines 36–44 (function body of `_get_next_id`). Existing shape is a list comprehension over `backlog_dir.glob("[0-9]*-*.md")` with a walrus-match `(m := re.match(r"^(\d+)-", p.name))` predicate, followed by `next_id = max(ids) + 1` (or 1 on empty), then a zero-pad-if-< 1000 format string. Read the current source before editing.
  - Add the new predicate as an additional `if` clause inside the comprehension — same shape as the existing walrus-match clause. The predicate excludes IDs where the parsed integer falls in the inclusive range 990–999. The ticket body in `cortex/backlog/231-fix-get-next-id-in-cortex-create-backlog-item-to-ignore-ids-990-seed-fixture-range.md` shows the literal snippet to insert.
  - Style invariant: walrus-match pattern (`(m := re.match(...))`) stays intact; the new clause references `m.group(1)` and re-parses to int (negligible cost). Do not introduce module-level constants per spec Non-Requirements.
  - This file has a plugin mirror under `plugins/cortex-core/bin/cortex-create-backlog-item` — the canonical source is the one being edited; the pre-commit dual-source hook regenerates the mirror automatically. Do not edit the mirror by hand.
- **Verification**: `pytest tests/test_create_backlog_item.py -v` exits 0; `grep -F "reserved for dashboard-seed fixtures" cortex_command/backlog/create_item.py` ≥ 1. Pass if both hold.
- **Status**: [x] completed

## Risks

- **Burns IDs 990–999 from the natural sequence permanently.** Real backlog IDs are ~231 today; this loses 10 IDs of headroom. If real IDs ever approach 989, `max(filtered) + 1` returns 990 (inside the reserved band) — overflow handling is deferred per the spec's Non-Requirements. ~700+ tickets away. Acceptable per the operator's explicit choice during refine.
- **No structural separation of seed fixtures from real backlog items.** Fix B (relocate seeds + reader audit ~10 modules) is out of scope. If dashboard-seed grows beyond the 5-item scaffolding it is today, the reservation predicate will not protect the readers, only the allocator. Spec notes this as a future ticket trigger.
