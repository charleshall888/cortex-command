---
schema_version: "1"
uuid: 43a366cf-e5f4-499e-90cb-0bbddec77bf7
title: "Make cortex-resolve-backlog-item ambiguous parity fixture robust to backlog drift"
status: complete
priority: low
type: chore
created: 2026-06-01
updated: 2026-06-01
complexity: complex
criticality: medium
spec: cortex/lifecycle/make-cortex-resolve-backlog-item-ambiguous/spec.md
areas: ['tests']
---
**Why:** `tests/test_cortex_resolve_backlog_item_parity.py::test_stderr_parity[title_phrase_ambiguous]` byte-compares `cortex-resolve-backlog-item lifecycle` stderr against a recorded golden fixture that snapshots the exact ambiguous-match count ("ambiguous: N matches" + first 5 filenames + "... (N more)"). Because the query term is "lifecycle", every backlog item whose title contains "lifecycle" that is added or removed drifts the count and breaks `just test` with a failure unrelated to whatever change is under test. Already re-captured twice for ambient drift (c582a84e, then 904bb80f during #274) — a recurring maintenance tax.

**Role:** Stop an unrelated `just test` failure from surfacing every time the backlog grows or loses a "lifecycle"-titled item.

**Integration:** Options to weigh — (a) assert structural shape (exit 2 + the "ambiguous: N matches" line format + that the query resolves to >1, with the count read live rather than pinned) instead of a byte-exact count/listing; (b) switch the ambiguous case to a query term that does not track a volatile title word; (c) accept the brittleness and document the re-capture cadence in the fixture README. (a) is the most robust and keeps real behavior under test.

**Edges:** The sibling cases (numeric_unambiguous, no_match) are stable — only the by-title ambiguous case drifts. Whatever the fix, keep the resolver behavior genuinely under test (do not weaken to a no-op). Mind the shared byte-compare helper in `test_parity_contract.py`.

**Touch-points:** `tests/test_cortex_resolve_backlog_item_parity.py`, `tests/fixtures/cortex-resolve-backlog-item/` (the three `title_phrase_ambiguous.*` files + README), `tests/test_parity_contract.py`.