---
schema_version: "1"
uuid: a96cd089-29a5-47d5-95c9-1f233e2e40e4
title: "cortex-backlog-ready treats blockers pointing to terminal items as external"
status: complete
priority: medium
type: bug
tags: [harness, scripts, backlog]
areas: [backlog]
created: 2026-04-29
updated: 2026-04-29
parent: "101"
---

# cortex-backlog-ready treats blockers pointing to terminal items as external

## Context

`bin/cortex-backlog-ready` (shipped in ticket 108) reads `backlog/index.json`, which `collect_items()` filters to active-status items only — terminal items like `complete`/`done` are dropped before serialization. Because the script's `partition_ready` invocation passes the active-only items as `all_items` to `is_item_ready`, blockers pointing to terminal IDs surface as `"external blocker: 85"` in `--include-blocked` output.

This is the same gap that ticket 108 Task 3 fixed for `backlog/generate_index.py` (Objection 4 from critical review): `generate_index.py` was extended to build a full-corpus `all_items_map` covering active + terminal + archived `.md` files. The fix landed at the index-generator level, not at the `index.json` schema level — so consumers of `index.json` still see only active items.

Concrete repro: items 86 and 91 (live, `status: backlog`) carry `blocked_by: ["85"]`. Item 85 is `status: complete` (terminal). After ticket 108:
- `backlog/index.md` shows 86 and 91 as ready (correct — `generate_index.py` builds full corpus)
- `bin/cortex-backlog-ready --include-blocked` reports them as `external blocker: 85` (wrong — script reads active-only `index.json`)

This causes `/backlog pick` and `/backlog ready` to under-report the true ready set whenever any active item has a terminal-status blocker.

## Scope

Fix `cortex-backlog-ready` (or its data source) so blockers pointing to terminal items resolve as ready.

Two implementation directions for research:

1. **Extend `index.json` schema** to include a separate `terminal_items` array (active items keep their slot, terminal items in a parallel list with minimal `{id, status, uuid}` records). `cortex-backlog-ready` merges them when building `all_items_ns`. Affects all `index.json` consumers — needs `schema_version` bump.

2. **Mirror generate_index.py's full-corpus scan in ready.py**: have `ready.py` directly scan `backlog/[0-9]*-*.md` and `backlog/archive/[0-9]*-*.md` to build its own `all_items` map. Keeps `index.json` schema stable but duplicates the scan cost on every `cortex-backlog-ready` invocation (the same duplication that ticket 108 was trying to retire).

## Out of scope

- Changing `is_item_ready` helper semantics (it's correct — the bug is upstream data).
- Changing `index.json` for non-`cortex-backlog-ready` reasons.

## Acceptance

- `bin/cortex-backlog-ready --include-blocked` reports items 86 and 91 as ready (in `groups`, not `ineligible`) when item 85 is terminal.
- `tests/test_backlog_ready_render.py` extended with a fixture item carrying a terminal-status blocker; assertion that it routes to `groups` not `ineligible`.
- No regression: all existing tests still pass.

## Background

Discovered during ticket 108 review (cycle 1, APPROVED). Reviewer flagged it as a user-visible divergence between `index.md` (ready) and `cortex-backlog-ready` (blocked) for the same item. Originally classified by-design per the spec's Non-Requirement that `cortex-backlog-ready` is read-only over `index.json`, but on reflection it's a real correctness bug that breaks parity between the two consumer surfaces.

Discovery source: `lifecycle/archive/extract-backlog-pick-ready-set-into-bin-backlog-ready/review.md` (Code Quality section).
