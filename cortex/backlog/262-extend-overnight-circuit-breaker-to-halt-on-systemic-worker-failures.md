---
schema_version: "1"
uuid: b2e12ee3-3499-4e17-8cca-d798b6aadf09
title: "Extend overnight circuit breaker to halt on systemic worker failures"
status: refined
priority: medium
type: chore
created: 2026-05-25
updated: 2026-05-25
complexity: complex
criticality: high
spec: cortex/lifecycle/extend-overnight-circuit-breaker-to-halt/spec.md
areas: [overnight-runner]
---
## Why

The overnight orchestrator's circuit breaker currently halts the batch only for two error types: \`budget_exhausted\` and \`api_rate_limit\` (\`cortex_command/overnight/feature_executor.py:70\` — \`_SESSION_HALT_ERROR_TYPES\`). Other systemic failures that affect every task in a session — Bash-sandbox EPERM, seatbelt-probe failures, silent worker exits — let the batch dispatch wave after wave against a known-broken environment.

\`WORKER_NO_EXIT_REPORT\` is emitted by \`feature_executor.py:774\` but the orchestrator never consumes it as a halt signal.

This was carved out of #258 (archived) after triage showed daytime pipeline removal (#246) plus the existing budget-exhaustion breaker covered most of #258's framing. Two residual gaps remain.

## Role

Make overnight bail loudly when the *environment* is broken, instead of grinding through a queue producing N identical failures.

## Integration

Two slices, ordered by effort:

**Slice A (trivial):** Add \`\"worker_no_exit_report\"\` to \`_SESSION_HALT_ERROR_TYPES\`. Requires verifying that \`feature_executor.py\` sets \`result.error = \"worker_no_exit_report\"\` (or equivalent) on the no-exit-report branch so the orchestrator check at \`orchestrator.py:404-411\` actually fires. ~10 lines + 1 test.

**Slice B (design-bearing):** Cascade-class detection. Classify task errors into systemic vs idiosyncratic (EPERM family, seatbelt-probe-fail, sandbox-denied, etc.). Track N consecutive systemic-class errors → set \`global_abort_signal\` with a new \`cause_class\` field on the pause event. Open design questions: which error strings belong in each class, what N should be, how to surface class in morning-report aggregation.

Slice A alone is a partial fix that papers over half the problem. Filing as a single ticket so the next implementer sees the full shape before deciding scope.

## Edges

- Slice A as standalone reduces signal: a single silent worker halts the batch even if the next task would have succeeded. Acceptable tradeoff because silent workers are rare and usually mean something deeper is wrong.
- Slice B's classification taxonomy needs to align with the EPERM subtypes already present in \`report.py:1916\` (\`plumbing_eperm\`, unclassified-EPERM) — don't invent a parallel taxonomy.
- \`worker_no_exit_report\` may fire on legitimate worker crashes that are *task-specific* (not systemic). Promoting it to halt-type means we'd rather over-halt than under-halt; document this tradeoff in the change.

## Touch points

- \`cortex_command/overnight/feature_executor.py:70\` (\`_SESSION_HALT_ERROR_TYPES\` tuple)
- \`cortex_command/overnight/feature_executor.py:774\` (\`WORKER_NO_EXIT_REPORT\` emit site — verify \`result.error\` is set)
- \`cortex_command/overnight/orchestrator.py:404-411,505-511\` (circuit-breaker check sites)
- \`cortex_command/overnight/report.py:1916\` (existing EPERM taxonomy to align with)
- \`cortex_command/overnight/events.py:53\` (\`WORKER_NO_EXIT_REPORT\` constant)
- New event for Slice B: \`pipeline_systemic_failure\` with \`cause_class\` field — needs registration in \`bin/.events-registry.md\`

## Related

- Carved out of archived #258 (\"Surface aggregated signal on daytime-pipeline sandbox/EPERM cascade failures\")
- #246 (\"remove-daytime-autonomous-pipeline-and-cancel\", complete) — removed the original incident's pipeline
- Commit \`a338437c\` — \`excludedCommands=['git:*']\` partial mitigation for the git-EPERM failure mode