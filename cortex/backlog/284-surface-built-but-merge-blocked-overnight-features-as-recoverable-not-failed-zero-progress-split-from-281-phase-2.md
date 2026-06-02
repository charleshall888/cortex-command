---
schema_version: "1"
uuid: f04521e4-474d-447e-9035-c9d46a2176eb
title: "Surface built-but-merge-blocked overnight features as recoverable, not failed/zero-progress (split from #281 Phase 2)"
status: complete
priority: medium
type: feature
created: 2026-06-02
updated: 2026-06-02
complexity: complex
criticality: high
spec: cortex/lifecycle/surface-built-but-merge-blocked-overnight/spec.md
areas: ['overnight-runner']
---
**Why:** When an overnight home-repo feature builds correctly but genuinely cannot be integrated (a real merge conflict where repair is exhausted), its completed work on `pipeline/<feature>` is currently mis-surfaced as a plain failure/pause and can contribute to a `0/N` + `[ZERO PROGRESS]` PR, rather than being surfaced as "built, merge-blocked, recoverable on `pipeline/<feature>`". This is the reporting/state-surfacing half of #281, split out after #281's Phase 1 (the wrong-tree merge-resolution fix) removed the common cause of stranding. The residual harm is real but lower-frequency: after the tree fix, it fires only on genuine conflicts, whose real-world frequency for home features is currently unmeasured.

**Role:** A genuinely-merge-blocked-but-built feature should stop auto-retrying into recovery, should not cascade-fail or strand its built siblings, and should surface to the operator as recoverable on its branch — distinct both from "never built" and from "awaiting a human answer".

**Integration:** #281's spec chose to reuse the existing `deferred` feature status plus a new optional `recoverable_branch` metadata field rather than mint a new status (see #281 Proposed ADR 0007). Critical review of that spec surfaced concrete design constraints, recorded here so they are not re-discovered:
- The morning-report recoverable rendering cannot route through `render_failed_features`, which filters `status in ('failed','paused')` and so excludes `deferred`; a `deferred` feature also renders nowhere in `render_deferred_questions` without a question file. The recoverable surface keys off `recoverable_branch` wherever `deferred` features actually display.
- Sibling handling cannot rely on `sweep_blocker_failed_dependents`, which cascades only on terminal `failed` and never on `deferred`; dependents of a merge-blocked blocker need an explicit path out of the pending set, or they churn into a `circuit_breaker (stall)`.
- The web dashboard (`alerts.py`, `feature_cards.html`) is a third `deferred` consumer that renders `⏸ deferred` + `deferred_questions` blind to `recoverable_branch`, so without a change it mislabels the feature as an answer-deferral.
- `recoverable_branch` carries the feature's actual branch (which may be suffixed `pipeline/<name>-2`/`-N`), sourced from the persisted branch or the `merge_start` event — not the bare `pipeline/<name>`.
- The mutation and write-back paths need threading: `update_feature_status` has no `recoverable_branch` parameter today, and `_write_back_to_backlog` receives only the status string, so the merge-blocked sub-case cannot currently select a non-`backlog` write-back (which would avoid a from-scratch rebuild) without new wiring.
- Whether to reuse `deferred`+metadata or mint a distinct status is worth re-evaluating given the consumer-touch count above (the reuse touches at least four consumers, which undercuts the "without vocabulary cost" rationale of ADR 0007).

**Edges:**
- Only exercised after #281 Phase 1 lands; the remaining trigger is a genuine conflict plus repair exhaustion on the integration worktree.
- Must not regress the existing `deferred` question-deferral semantics (question files, the "questions need answers" surfacing).
- The `[ZERO PROGRESS]` draft-PR gating still blocks accidental merge of an empty integration branch, while no longer labeling a session with built-but-merge-blocked work as zero progress.

**Touch-points:**
- `cortex_command/overnight/state.py` (`OvernightFeatureStatus`, `FEATURE_STATUSES`/`_TERMINAL_FEATURE_STATUSES`, `update_feature_status`, `sweep_blocker_failed_dependents`).
- `cortex_command/overnight/outcome_router.py` (recovery-result routing to `paused`/`deferred`, `_OVERNIGHT_TO_BACKLOG`, `_write_back_to_backlog`).
- `cortex_command/overnight/report.py` (`render_executive_summary`, `render_failed_features`, `render_deferred_questions`, `create_followup_backlog_items`).
- `cortex_command/overnight/runner.py` (`[ZERO PROGRESS]` PR-gating in `_run_post_loop_sequence`, `_count_merged_home_repo`, circuit-breaker stall accounting).
- `cortex_command/dashboard/alerts.py`, `cortex_command/dashboard/templates/feature_cards.html`.
- `bin/.events-registry.md` + `cortex_command/overnight/events.py` (`EVENT_TYPES`) if a new event is emitted.

Related to #281 (this is its split-out Phase 2).