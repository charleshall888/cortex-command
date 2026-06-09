---
schema_version: "1"
uuid: 716e4a05-93c5-4e53-88bc-e2db3ca753b7
title: "Plan parser: support sub-task headings (### Task Na) as first-class ordered units"
status: backlog
priority: low
type: feature
created: 2026-06-09
updated: 2026-06-09
parent: "293"
---
As of commit 87239c4b the plan parser fails loud on letter-suffixed sub-task headings; this ticket adds real support for them.

## Why
Authors organically use `### Task Na` sub-task headings (`### Task 3a`, `### Task 3b`) to decompose a task into ordered sub-units — 6 lifecycle plans already do. The parser task-heading regex captures integer numbers only (`^###\s+Task\s+(\d+)`), so a letter-suffixed heading is not recognized: its body was silently absorbed into the preceding integer task, dropping the sub-task `Files`/`Depends on` from dispatch ordering. Commit 87239c4b (under #293) now raises `ValueError` -> `parse_error` on such headings rather than silently mis-parsing — but that only converts a silent drop into a hard failure; it does not let authors use the pattern.

## Role
Make `### Task Na` sub-task headings parse into ordered, independently-dispatchable units whose intra-parent ordering and dependencies are preserved, so a plan author can decompose a task without losing dispatch fidelity or hitting the fail-loud guard.

## Integration
- `cortex_command/pipeline/parser.py`: the integer-only task-heading regex in `_parse_tasks` and the fail-loud sub-task guard added in 87239c4b (this work lifts/replaces that guard). `FeatureTask.number` is currently `int` — sub-task identity needs a representation that orders 3 < 3a < 3b < 4.
- `cortex_command/common.py:compute_dependency_batches`: keys on `.number`/`.depends_on` for topological batching. Decide how a dependency `[3]` expands across sub-tasks (parent only, or all of 3/3a/3b) and how sub-tasks order within a batch.
- `_parse_field_depends_on` currently collapses `3a`->`3` (integer-only digit extraction); first-class support means preserving the suffix in dependency references.
- Implement-phase batch dispatch (`skills/lifecycle/references/implement.md` section 2) keys on task identity.

## Edges
- `[3]` dependency when 3a/3b exist: parent-only vs fan-out semantics must be decided, not assumed.
- Ordering: 3a before 3b; the whole 3* group relative to integer 3 and 4.
- Backward compat: integer-only plans (the overwhelming majority) must parse identically.
- The 6 existing sub-task plans are all COMPLETE (history) — not a migration target, but real-world fixtures for the desired parse.

## Touch-points / tests
- `cortex_command/pipeline/tests/test_parser.py`: replace `TestSubTaskHeadingFailLoud` with positive parse cases once support lands.
- `cortex_command/tests/test_common.py`: direct `compute_dependency_batches` tests for sub-task ordering and dependency expansion.
- `skills/lifecycle/references/plan.md`: document the sub-task syntax if it becomes supported.

Related: #293 (parent — field-metadata dialect fix and the fail-loud posture this extends).