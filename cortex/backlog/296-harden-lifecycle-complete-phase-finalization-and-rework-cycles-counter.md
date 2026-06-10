---
schema_version: "1"
uuid: 4ca3e2f7-42a5-4ed5-9ec2-5e9c777d3815
title: "Harden lifecycle complete-phase finalization and rework_cycles counter"
status: complete
priority: low
type: bug
created: 2026-06-09
updated: 2026-06-10
complexity: complex
criticality: high
spec: cortex/lifecycle/harden-lifecycle-complete-phase-finalization-and/spec.md
areas: ['lifecycle']
---
## Why

Running the `/cortex-core:lifecycle` Complete phase end-to-end on a `main`/trunk checkout (during feature #291, harden-the-distributed-cli-against-transitive) surfaced four finalization-tooling rough edges. None blocked completion — each had a workaround applied inline — but each is latent and recurs on the next trunk-completed or concurrently-edited lifecycle.

## Role

Four distinct defects in the complete-phase finalization path and the lifecycle counters helper:

1. **Dead index-sync fallback.** Complete-phase Step 10's first fallback runs `cortex_command/backlog/generate_index.py` under a bare `python3`, which raises `ModuleNotFoundError: No module named 'cortex_command'` (the script does `from cortex_command.backlog import _telemetry`, but a bare `python3` lacks the package on `sys.path`). Index regeneration succeeded only via the second fallback, the `cortex-generate-backlog-index` console script. The first fallback is effectively dead in any non-editable-install invocation.

2. **Finalization staging drops auto-applied source drift.** On the on-`main` short-circuit, Complete skips the Step 2 source-commit and reaches Step 11a, whose staging enumerates only `cortex/lifecycle/{slug}/` artifacts plus a directory-scoped backlog add. The review phase's auto-applied requirements drift (a `cortex/requirements/project.md` edit) is therefore left unstaged; it landed only because it was staged manually.

3. **Finalization backlog add sweeps unrelated tickets.** Step 11a's directory-scoped `git add cortex/backlog/` stages every untracked backlog file in the tree, not only the feature's write-back. With concurrent in-flight tickets present (#292–#294 were untracked during #291's completion), a directory add bundles unrelated tickets into the finalization commit; this was avoided by deviating to a path-scoped add.

4. **`rework_cycles` over-counts clean approvals.** `cortex_command/lifecycle/counters.py:count_rework_cycles` returns `len(RE_VERDICT.findall(text))` — the count of `"verdict"` blocks in `review.md`. A feature approved on the first review cycle (one verdict, zero CHANGES_REQUESTED loops) reports `rework_cycles=1` rather than `0`. The over-count rides into the `feature_complete` event and the morning-report `avg_rework_cycles` metric. A separate `rework_cycles` computation in `cortex_command/pipeline/metrics.py` may diverge from this one.

## Integration

The complete-phase defects live in the lifecycle Complete reference (`skills/lifecycle/references/complete.md`, Steps 10 and 11a); the counter defect lives in `cortex_command/lifecycle/counters.py`. Both sit behind the `/cortex-core:lifecycle` skill, so changes flow through a lifecycle. Candidate directions, not prescribed: a working first-fallback invocation for index regeneration (or its removal); Step 11a staging that includes auto-applied requirements drift and a feature-scoped rather than directory-scoped backlog add; and a reconciliation of whether `rework_cycles` denotes review cycles or rework iterations, aligned across the field name, the counter, and the metrics aggregation.

## Edges

- Simple-tier features have no `review.md`, so `count_rework_cycles` returns 0 — the over-count touches only complex-tier (reviewed) features.
- The drift-drop (defect 2) appears only on the on-`main`/trunk completion path; the PR path commits source via Step 2.
- The backlog-sweep (defect 3) appears only when unrelated untracked backlog files coexist with a completing lifecycle.
- All four are latent rather than blocking: #291 completed correctly because each had an inline workaround.

## Touch-points

- `skills/lifecycle/references/complete.md` — Steps 10 and 11a
- `cortex_command/backlog/generate_index.py`
- `cortex_command/lifecycle/counters.py` — `count_rework_cycles`, `RE_VERDICT`
- `cortex_command/pipeline/metrics.py` — `rework_cycles` aggregation