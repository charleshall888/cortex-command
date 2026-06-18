---
schema_version: "1"
uuid: 4e0bd4d0-a8e5-4627-b348-85035f3c97a5
title: Overnight task failures produce empty captured output (exit code 1, no stdout/stderr) — failures undiagnosable
status: complete
priority: high
type: bug
created: 2026-06-17
updated: 2026-06-17
complexity: complex
criticality: high
spec: cortex/lifecycle/overnight-task-failures-produce-empty-captured/spec.md
areas: ['overnight-runner']
---
**Why:** In wild-light overnight session `overnight-2026-06-17-1821` (2026-06-17), feature `codify-sim-render-boundary` (#239) Task 5 failed **4× across rounds 1 and 2** with an identical generic `ProcessError: Command failed with exit code 1` and a **completely empty** Final Attempt Output — no stdout, no stderr, no GDScript/tool output. The brain's own pause reasoning flagged it as the worker-crashes-without-capturing-output class: "zero output + identical error across both retries… characteristic of an infrastructure-level failure rather than a logic defect." With no captured output, neither the brain, the morning report, nor a human can tell whether the cause was a Godot subprocess failure, a pre-commit gate rejection, worktree contention, or a real code defect — so the retry/defer decision is a guess and the same failure recurs. (In this incident the likely trigger was a wild-light pre-commit gate silently rejecting commits — but the harness should have captured *whatever* the failing command emitted.)

**Role:** Capture and surface the failing subprocess's output (stdout/stderr tail) plus the exact command, exit code, and cwd on a task/dispatch failure, so failures are diagnosable from the event log and morning report instead of an opaque `exit code 1`.

**Integration:**
- In the dispatch / feature-executor layer, on a non-zero subprocess exit, persist the captured stdout/stderr (truncated tail) into the task result and the event log — not just a generic `ProcessError` string — alongside the command, exit code, and cwd.
- Surface that output tail in the morning report's failed-feature section and in the brain's retry context, so the pause/retry decision is evidence-based rather than pattern-guessing.
- Relate to #258 (abandoned) / #262 (systemic-failure aggregation): those aggregate the *signal*; this is about capturing the per-failure *content*.

**Edges:**
- The empty output here may itself be downstream of the wild-light pre-commit gate (filed separately) silently rejecting commits — but an empty capture is the defect regardless of root cause; the harness should record what the failing command produced.
- Non-goal: fixing any specific task's failure; the orchestrator supervision / circuit-breaker gap (companion cortex-command ticket).