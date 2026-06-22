# Implement notes — refine-default-interactive-not-overnight

Human-readable record for the Review phase. These notes are an audit trail, **not**
the pass condition (per plan Task 5 / backlog 025): the pass condition is `just test`
(mechanical) plus the reviewer's live observation (behavioral).

## R6 behavioral walkthrough (Task 5)

Step 6's advisory is model-interpreted prose; its firing decision was walked in-session
against four fixtures. Mechanical signals were measured with grep; the fire/no-fire
decision applies Step 6's logic (guard on `phase_transition`-absence, then mechanical
anchors).

| Case | events.log `phase_transition` | spec mechanical signal | Step 6 decision | Expected |
|------|-------------------------------|------------------------|-----------------|----------|
| (i) standalone, Interactive criterion, no open decisions | 0 → standalone | `Interactive/session-dependent` ×1 | **WARN**, cites the interactive criterion | warn ✓ |
| (ii) standalone, all (a)/(b) checked, no open decisions | 0 → standalone | none | **SILENT** | silence ✓ |
| (iii) standalone, unresolved `## Open Decisions` | 0 → standalone | open-decision bullet ×1 | **WARN**, cites the unresolved decision | cited ✓ |
| (iv) lifecycle arm (this feature's own dir) | 4 → suppress | (4 `Interactive/session-dependent` present — irrelevant) | **SILENT** (guard suppresses) | silence ✓ |

Case (iv) is the load-bearing arm: the spec carries signals that WOULD fire under (i),
but the guard suppresses because the events.log carries `phase_transition` rows. All four
match expectation.

## Suite status (`just test`)

Feature acceptance — all pass (53 passed in the targeted run):
- `tests/test_skill_routing_disambiguation.py` (R3) — pass
- `tests/test_l1_surface_ratchet.py` (R4, re-capped refine 644→624, total 7197→7177) — pass
- `tests/test_plugin_mirror_parity.py` (R5) — pass

Two `just test` failures remain, both **external to this feature** (verified):
- `tests/test_resolve_backlog_item.py::test_no_order_drift_against_baseline` — drift against
  `tests/fixtures/predicate_a_baseline.json`, which a **concurrent session** modified in the
  working tree (uncommitted; not touched by any commit in this lifecycle).
- `tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero` —
  **sandbox-network**: spawns `uv run --script` resolving PEP 723 deps from PyPI (not in the
  sandbox allowlist). Re-run with network enabled → **passes** (15.25s). Environmental.

Neither failing test references any file edited by this feature.
