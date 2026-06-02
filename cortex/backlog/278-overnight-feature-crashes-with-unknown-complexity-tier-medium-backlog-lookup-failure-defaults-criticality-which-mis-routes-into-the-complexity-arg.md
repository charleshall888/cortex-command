---
schema_version: "1"
uuid: bdefeb63-516d-4ddc-9508-fe8a0b263d3c
title: "Overnight feature crashes with 'Unknown complexity tier medium' — backlog-lookup failure defaults criticality, which mis-routes into the complexity arg"
status: complete
priority: high
type: bug
created: 2026-06-01
updated: 2026-06-01
complexity: complex
criticality: high
spec: cortex/lifecycle/overnight-feature-crashes-with-unknown-complexity/spec.md
areas: ['overnight-runner']
lifecycle_phase: implement
---
**Why:** In overnight session `overnight-2026-06-01-1518` (2026-06-01, run-now path), round-1 feature `build-the-grinder-agnostic-knowledge-layer` (backlog #025) **failed before its agent ran**: `Unexpected error: Unknown complexity tier 'medium'; must be one of ['complex','simple','trivial']`. This is a field mis-route, not bad data:

- The batch plan (`batch-plan-round-1.md`) recorded `Complexity: complex`; backlog #025 declares `complexity: complex` / `criticality: high` — all valid.
- Alongside the failure: `backlog_write_failed: "Backlog item not found for feature 'build-the-grinder-agnostic-knowledge-layer' (backlog_id=25)"`. The runtime backlog resolver could not map the lifecycle slug `build-the-grinder-agnostic-knowledge-layer` → file `025-grinder-agnostic-knowledge-layer.md`.
- `medium` is the hardcoded **criticality** fallback (`overnight/runner.py:2462` and `:2200`, `overnight/brain.py:232`) used when a feature's criticality can't be read. The orchestrator's own round-1 summary confirms it used "criticality `medium`" — not the backlog's `high`.
- That defaulted criticality `medium` then reached `pipeline/dispatch.py`'s **complexity** parameter (`TIER_CONFIG[complexity]`, keys `trivial/simple/complex`), throwing the error. `medium` is a criticality word that leaked into the complexity slot.

Cascade: 025 failed → 026 & 027 (`blocked-by: 025`) had no plan in round 2 → `orchestrator_no_plan` → two zero-progress rounds → `circuit_breaker (stall)` → session stopped 0/3 merged. The run also (a) left `phase: executing` so `cortex overnight status` looked like a live run when the runner was dead, (b) committed the generated `plan.md` to the home repo's **`main`** branch (`6b8cb06`) instead of the integration branch, and (c) logged `followup_commit_failed` (rc=128, "not a git repository") because the worktree was already torn down. **This crash is launch-method-independent — it would fail on run-now or scheduled — so it is more severe than the scheduling defect in #277.**

**Role:** A feature whose backlog item can't be resolved at dispatch time must not crash on an out-of-vocabulary complexity tier and take down the whole session via the dependency chain. Two compounding defects: (a) the backlog resolver fails to map lifecycle-slug ↔ backlog id/filename; (b) a criticality value reaches the complexity slot and dispatch hard-fails instead of sourcing complexity authoritatively / normalizing.

**Integration (fixes):**
- **Backlog resolution (root trigger).** Make the runtime resolver map a feature's lifecycle-slug → its backlog item reliably (by `backlog_id`/`uuid`/`lifecycle_slug` frontmatter, or scanning `cortex/backlog/NNN-*.md`), independent of CWD/worktree. The slug (`build-the-grinder-agnostic-knowledge-layer`) ≠ filename stem (`025-grinder-agnostic-knowledge-layer`), which appears to be why the lookup failed. Tie to #277's root-resolution footgun.
- **Don't conflate vocabularies.** `complexity ∈ {trivial,simple,complex}`, `criticality ∈ {low,medium,high,critical}`. Find where the defaulted criticality (`medium`) reaches `dispatch.run_feature(complexity=…)` and ensure complexity is sourced from the authoritative backlog/batch-plan (`complex`), never from criticality. Add an enum guard at the dispatch boundary.
- **Read the declared fields.** Refine wrote `complexity: complex` and `criticality: high` to backlog #025, yet the dispatch path used neither — confirm the path actually reads frontmatter rather than defaulting.
- **Fail soft, not whole-session-fatal.** A missing/invalid complexity should degrade within-vocabulary (e.g. default `complex`/`simple`) with a logged warning, or fail only that feature cleanly — not raise `Unexpected error` that also corrupts the backlog-write and followup-commit steps.
- **plan-gen commit target.** The round-1 plan commit landed on the home repo's checked-out `main`; plan generation/commit must target the integration branch/worktree.

**Edges:**
- Reproduce with any feature whose lifecycle slug differs from its backlog filename stem (the common case) → backlog lookup fails → criticality defaults to `medium` → complexity crash. Add a unit test asserting dispatch receives the backlog's `complex`, and that an unknown tier degrades gracefully rather than raising.
- Blast radius is amplified by `blocked-by` chains: the first feature failing zeroes every dependent sibling, so one mis-routed tier kills the whole session (here 3/3).
- **Do NOT "fix" by adding `medium` to `TIER_CONFIG`** — that masks the vocabulary confusion; complexity must stay `trivial/simple/complex`.
- Observability overlap with #277: a circuit-broken session with pending features shows `phase: executing` with no live runner, and the watchdog "fires at 30m" never fires (nothing evaluates it) — this is what made the dead session look like a hang.

**Touch-points:**
- `cortex_command/pipeline/dispatch.py` (`run_feature`, `TIER_CONFIG`, `complexity`/`criticality` params, `resolve_model`/`resolve_effort`, the `Unknown complexity tier` raise ~L519).
- `cortex_command/overnight/runner.py` (`read_criticality` call sites + `criticality = "medium"` default at ~2462 / 2200), `cortex_command/overnight/brain.py:232`.
- The feature→backlog resolver behind `backlog_write_failed` / `read_criticality`; its interaction with `cortex_command/common._resolve_user_project_root` and CWD/worktree.
- `cortex_command/overnight/orchestrator.py` / `run_batch` (where per-feature complexity/criticality are sourced for dispatch); `cortex_command/pipeline/parser.py` (batch-plan complexity parses correctly as `complex`, so the override is downstream of parsing).
- plan-gen commit target (integration branch, not home `main`).