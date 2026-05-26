---
schema_version: "1"
uuid: 84bee538-707f-4e78-974a-13fb2c6961d8
title: "Re-establish perf budget for cortex-log-invocation post dual-channel-wrapper rewrite"
status: complete
priority: low
type: chore
created: 2026-05-25
updated: 2026-05-26
lifecycle_phase: research
lifecycle_slug: re-establish-perf-budget-for-cortex
complexity: complex
criticality: medium
spec: cortex/lifecycle/re-establish-perf-budget-for-cortex/spec.md
---
## Why

Commit 7c05529c replaced bin/cortex-log-invocation with a dual-channel Python wrapper (force-source / wheel-probe / working-tree-fallback / exit-2). The previous shim was a pure-bash fast-path that avoided git rev-parse via CORTEX_REPO_ROOT and completed in ~5-10ms.

The perf-budget tests at tests/test_log_invocation_perf.py:test_log_invocation_fast_path_budget and test_log_invocation_fast_path_faster_than_slow were authored against the bash shim's perf contract (p50 ≤ 15ms, fast-vs-slow delta ≥ 2ms). The new wrapper pays Python interpreter boot on every invocation (~50-70ms p50 on commodity hardware), so the 15ms budget is unachievable and the fast-vs-slow delta is structurally zero (both paths converge to the same Python boot cost).

Both tests are currently @pytest.mark.skip'd with reasons pointing here.

## Role

Operator / contributor running `just test` should see this gap re-closed so we don't lose perf regression detection on the shim.

## Integration

- Decide whether to re-establish a budget on the dual-channel wrapper (likely raise to ~100ms p50 / 150ms mean / 200ms p95)
- OR re-introduce a bash fast-path for the LIFECYCLE_SESSION_ID=set + valid CORTEX_REPO_ROOT case (skipping Python entirely for the happy path)
- Either way: un-skip the tests and update budgets / assertions

## Edges

- The wrapper's Branch (d) emits a remediation message; that path's perf is not the concern.
- Skipping the tests as a stop-gap is intentional — the alternative was a falsely-passing test if we'd just bumped the budget to 100ms without re-thinking what the budget represents.

## Touch-points

- bin/cortex-log-invocation
- cortex_command/log_invocation.py (or wherever the module lives)
- tests/test_log_invocation_perf.py

## Discovered during

Lifecycle complete for #259 reconcile-sessionstart-lifecycle-phase-summary-against; just test surfaced the failing perf test which proved unrelated to the reconcile work and pre-existing.