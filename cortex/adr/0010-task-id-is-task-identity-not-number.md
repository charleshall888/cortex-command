---
status: accepted
---

# `task_id` is task identity, not `.number`

## Context

Making `### Task Na` sub-task headings (`3a`, `3b`) first-class requires a task identity that (a) orders `3 < 3a < 3b < 4` and (b) is distinct per sub-task. `FeatureTask.number` was the de facto identity, consumed as an `int` across the dispatch path: dependency batching (`compute_dependency_batches`), plan checkoff (`mark_task_done_in_plan`), exit-report read/write filenames, the idempotency-resume token, and the `has_dependents` membership test. Two sub-tasks of the same parent share a `.number` (both `3`), so any site that keyed identity on `.number` would silently merge `3a` and `3b` — collide their exit-report files, reuse one idempotency token, and drop one from dependency membership.

The overarching constraint is backward compatibility: integer-only plans (the overwhelming majority) must parse, batch, check off, and dispatch **byte-identically** after the change.

## Decision

Introduce a canonical `task_id` string property on `FeatureTask`, `task_id = f"{number}{suffix}"` (e.g. `"3a"`; `"3"` when unsuffixed), and make it the **sole** identity key for every identity-bearing site: dependency batching, plan checkoff, exit-report filename (both the worker's write target via the `IMPLEMENT_TEMPLATE` substitution and the orchestrator's `_read_exit_report`), the idempotency token, and `has_dependents`. `depends_on` becomes a `list[str]` of task_ids resolved verbatim.

`.number` stays an `int` and is **demoted to a non-unique "group ordinal"** used only by telemetry JSON payloads (event-log `task_number` fields), where two sub-tasks legitimately share the parent ordinal. Because `task_id == str(number)` for an unsuffixed task, every integer-only identity value is byte-identical to its pre-change form by construction.

## Three-criteria gate clearance

- **Hard to reverse** — the change retypes the identity contract across ~19 call sites in `parser.py`, `common.py`, and `feature_executor.py`; reversing it would require coordinated edits across the whole dispatch path plus the exit-report and idempotency-token wire formats.
- **Surprising without context** — a maintainer reading the code would reasonably assume `.number` is the task identity (it was, for the project's entire history) and would propose keying new logic on it; the demotion to "telemetry-only group ordinal" is non-obvious and, if violated, silently merges sub-tasks rather than failing loud.
- **Real trade-off** — see Rejected alternatives; the chosen design buys structural backward-compatibility at the cost of a documented residual hazard.

## Rejected alternatives

**Retype `.number` itself to a richer comparable type (str or custom).** This minimizes the number of identity concepts (one key, not two) but forces every integer wire-format — JSON `task_number` payloads, `int`-equality tests, `set[int]` narrowing — to change in lockstep, turning the "integer-only plans dispatch identically" guarantee into a careful audit rather than a structural property. Higher blast radius, harder to hold the backward-compat line.

**Encode the suffix into integer space (`3 → 300`, `3a → 301`).** Zero change to int consumers, but a leaky encoding that hides identity behind a scaling trick, needs a separate display label for checkoff, and fights the "first-class sub-task" intent.

## Consequences and residual hazard

The chosen design (`.number: int` + derived `task_id: str`) makes integer-only plans byte-identical by construction, but leaves a **documented residual hazard**: a future consumer that keys identity on the still-present, non-unique `.number` would silently merge `3a`/`3b`. This hazard is **contained, not eliminated** — it is held in check by (a) migrating every enumerated identity-bearing site together in one atomic change, and (b) merge-guard tests that assert distinct batches, distinct exit-report filenames, distinct idempotency tokens, and a `True` `has_dependents` for a sub-task reference. Those tests fail by returning a wrong value (silent-False / silent-merge) rather than raising, so they are the safety net that catches a regression the type system cannot. New code that needs per-task identity MUST use `task_id`, never `.number`.
