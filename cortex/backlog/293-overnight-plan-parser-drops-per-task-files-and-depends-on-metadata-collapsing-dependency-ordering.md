---
schema_version: "1"
uuid: d1b862d0-1b46-44ca-98cc-f59983e900b3
title: "Overnight plan parser drops per-task Files and Depends-on metadata, collapsing dependency ordering"
status: complete
priority: high
type: bug
created: 2026-06-09
updated: 2026-06-09
complexity: complex
criticality: high
spec: cortex/lifecycle/overnight-plan-parser-drops-per-task/spec.md
areas: ['overnight-runner']
---
Observed in wild-light overnight run `overnight-2026-06-09-0222` (broke #202 climb task ordering).

## Bug
Auto-generated `plan.md` emits task metadata as bold-paragraph lines:
```
**Files:** `a.gd`, `b.gd`
**Depends on:** Task 1, Task 3.
```
But `pipeline/parser.py` requires list-item form: `_parse_field_files` (line 365) regex `[-*]\s+\*\*Files\*\*:` and `_parse_field_depends_on` (line 388) `[-*]\s+\*\*Depends\s+on\*\*:` — leading bullet required, colon OUTSIDE the bold. The plan dialect (no bullet, colon inside the bold) matches neither, so BOTH return empty for every task → `files=[]`, `depends_on=[]`.

Downstream: `feature_executor.py:610-611` formats the dispatch header from the empty lists → literally `- **Files**: N/A` / `- **Depends on**: None`. `compute_dependency_batches` (`common.py:670-706`, line 695 `all(d in assigned for d in [])` is vacuously true) collapses ALL tasks into one concurrent batch → phase ordering destroyed. In this run #202 Task 5 (enemy) dispatched concurrently with its prerequisite Task 1 (WorldRoot API); Task 1 never landed and the merged code was runtime-broken.

Not feature-specific — any plan in the bold-paragraph dialect loses all dependency ordering.

## Suggested fixes
1. Relax the `parser.py` field regexes to accept the bold-paragraph dialect (`**Files:**` / `**Depends on:**`, optional leading bullet, colon inside or outside the bold) — mirror the already-relaxed `_normalize_task_separators` (line 284).
2. Fail loud: if a `### Task N:` body has a Files/Depends-on label the regex cannot capture, raise instead of silently returning [].
3. Warn when a multi-task plan yields a single batch with zero declared dependencies (a strong drop signal).