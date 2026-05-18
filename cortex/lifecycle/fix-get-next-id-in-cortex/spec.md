# Specification: fix-get-next-id-in-cortex

## Problem Statement

`cortex_command/backlog/create_item.py:_get_next_id` allocates the next backlog ID via `max(ids) + 1` across every file matching `[0-9]*-*.md` in `cortex/backlog/`. The dashboard-seed fixture generator (`cortex_command/dashboard/seed.py:_BACKLOG_ITEMS`) writes test items at IDs 990–994 directly into the same directory. When the seeds are present in the working tree, allocation jumps from the natural ~231 range to 995, leaving large gaps in real-backlog IDs and forcing manual renumbering (rename + reference sweep + index regen). This was surfaced in the #228 daytime-dispatch lifecycle when ticket #230 was first created as 995. The fix reserves IDs 990–999 from allocator scope so newly-created tickets continue receiving `max-real-id + 1` regardless of seed presence.

## Phases

- **Phase 1: Reserve the seed range in the allocator** — add a predicate to `_get_next_id` that excludes IDs 990–999 from the max computation; add a test asserting allocation behavior with seeds present.

## Requirements

1. **Allocator excludes the reserved seed-fixture range**: `_get_next_id` filters out IDs in the inclusive range 990–999 before computing `max(...) + 1`. **Acceptance**: `pytest tests/test_create_backlog_item.py -v` exits 0, including a new test that constructs a `tmp_path` backlog directory containing both `990-seed-feature-*.md` through `994-seed-feature-*.md` and a sentinel real item (e.g., `229-foo.md`), invokes `_get_next_id`, and asserts the returned ID is `"230"` (not `"995"`). **Phase**: Reserve the seed range in the allocator.

2. **Allocator preserves existing behavior when seeds are absent**: with no files in the 990–999 range, `_get_next_id` returns `max(ids) + 1` over the real ID set, identical to current behavior. **Acceptance**: `pytest tests/test_create_backlog_item.py -v` exits 0, including a test where the `tmp_path` backlog contains only real items (e.g., `001-...`, `229-...`) and asserts the returned ID is `"230"`. **Phase**: Reserve the seed range in the allocator.

3. **Allocator preserves zero-prefix and overflow formatting**: the return value continues to be a 3-digit zero-padded string when `next_id < 1000` and a bare string otherwise (e.g., `"230"`, `"1000"`). **Acceptance**: `pytest tests/test_create_backlog_item.py -v` exits 0, including a test asserting the zero-padded return for a small ID (e.g., `001-foo.md` → `"002"`). **Phase**: Reserve the seed range in the allocator.

4. **New test file at `tests/test_create_backlog_item.py`**: file exists, imports `_get_next_id` from `cortex_command.backlog.create_item`, uses `tmp_path` fixtures, and contains the three tests above. **Acceptance**: `ls tests/test_create_backlog_item.py` exits 0; `grep -c "_get_next_id" tests/test_create_backlog_item.py` ≥ 3. **Phase**: Reserve the seed range in the allocator.

5. **Inline reservation comment**: the predicate carries an inline comment that names the seed-generator source so future readers can trace the reservation. **Acceptance**: `grep -F "reserved for dashboard-seed fixtures" cortex_command/backlog/create_item.py` ≥ 1 occurrence; the comment is on or adjacent to the predicate line. **Phase**: Reserve the seed range in the allocator.

6. **Parity check passes**: the change does not break `bin/cortex-check-parity` — the canonical source and any required SKILL.md/requirements/docs/hooks/justfile/tests cross-references stay in sync. **Acceptance**: `just validate-commit` exits 0 over the staged change. **Phase**: Reserve the seed range in the allocator.

## Non-Requirements

- **No structural relocation of seed fixtures.** Fix B (moving dashboard-seed output out of `cortex/backlog/` and merging at read time in ~10 reader modules) is explicitly out of scope. The ticket recommends Fix A; research validates Fix A; readers like `parse_backlog_counts` (`cortex_command/dashboard/data.py:987`) intentionally surface seeds in the dashboard's "Backlog by status" panel, which Fix B would break absent compensating changes.
- **No overflow handling for the reserved band.** If real backlog IDs ever reach 989, `max(filtered) + 1` returns 990 (inside the reserved band). User chose Defer: this collision is ~700+ tickets away and will be addressed if/when real IDs approach 989.
- **No module-level reservation constants.** Bounds are expressed as inline literals (`990 <= id <= 999`) with a comment pointing at `cortex_command/dashboard/seed.py`. If the predicate ever gets a second consumer (validator, reader), promote to a named constant then — not now.
- **No update to the seed generator.** `cortex_command/dashboard/seed.py` continues writing 990–994 into `cortex/backlog/`. The reservation in the allocator covers 990–999 to leave headroom for future seed entries without re-touching `_get_next_id`.
- **No ADR.** The reservation does not meet the three-criteria gate (hard to reverse + surprising without context + real trade-off). The inline comment is sufficient documentation; the change is trivially reversible.

## Edge Cases

- **Seeds present + real IDs 001–229**: predicate skips 990–994; `max([1..229]) + 1 = 230`. Returns `"230"`.
- **Seeds absent**: predicate is a no-op on the input set; behavior identical to today.
- **Empty backlog directory**: `ids` is empty; `next_id` falls back to `1`. Returns `"001"`. (Existing behavior preserved.)
- **Seeds present + no other files**: predicate filters out all five seed IDs; `ids` is empty after filter; `next_id` falls back to `1`. Returns `"001"`. This is a corner case unlikely to occur in practice (real backlog always has items), but the behavior is sensible.
- **Real ID happens to equal 990–999**: cannot occur in normal flow because the allocator itself never returns one. If someone manually places a real-content file at e.g., `995-foo.md`, the predicate skips it and the next allocation may collide with it on subsequent allocation — this is acceptable because the reservation is documented and manual placement in the reserved range is a user error, not a system case.
- **`max-real + 1 == 990`**: covered above under Non-Requirements (overflow handling deferred per user choice).

## Changes to Existing Behavior

- **MODIFIED**: `cortex_command/backlog/create_item.py:_get_next_id` no longer considers IDs in 990–999 when computing the next allocation. Callers (`cortex-create-backlog-item`) see no API change; the function signature, return type, and zero-padding behavior are preserved.
- **ADDED**: new test file `tests/test_create_backlog_item.py` covering `_get_next_id`. No prior file existed; the existing `cortex_command/backlog/tests/test_dispatch.py` (entry-point smoke test) is unchanged.

## Technical Constraints

- **Dual-source / parity**: `cortex_command/backlog/create_item.py` is the canonical source; the `bin/cortex-create-backlog-item` wrapper and any plugin mirror under `plugins/cortex-core/bin/` regenerate via pre-commit hook. Edit canonical source only.
- **Style preservation**: the existing list-comprehension + walrus-match in `_get_next_id` is retained; the new predicate is added as an additional `if` clause inside the comprehension, matching the ticket's Fix A snippet.
- **Comment placement**: the reservation comment is inline on the predicate (or the line above) and names `cortex_command/dashboard/seed.py` as the seed source so future readers can trace the convention.
- **File-based state (ADR-0001)**: preserved — no migration off file-based backlog items.

## Open Decisions

None — all three research-deferred items are resolved at spec time (overflow → Defer per user; literal style → inline + comment; test location → `tests/test_create_backlog_item.py`).

## Proposed ADR

None considered.
