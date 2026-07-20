---
status: proposed
---

# Mode-agnostic interactive dispatch prose

_Decision date: 2026-07-20 (#401 — trim the interactive implement loop's orchestration overhead)._

## Context

The interactive implement loop dispatches per-task builders and needs their exit reports back to checkpoint each task. The source ticket framed the work as "decide the dispatch mode first" — pick synchronous or background dispatch and write the orchestration prose to match. Research found that decision is not the harness's to make.

The dispatch mode (synchronous vs background) is owned by the Claude Code runtime, not by this repo. It is version-dependent and has moved twice in recent patch releases: background-by-default arrived at ≥v2.1.198, and report-bearing completion notifications at ≥v2.1.211. Only the synchronous direction is pinnable at all — via a session-wide environment variable whose effect is not task-scoped and carries collateral damage across the whole session. So there is no mode the harness can assume for the whole installed base: prose that is mode-dependent, or that adapts to a detected mode, would be wrong for some runtime version at any given time. The #353 round-trip that motivated the ticket does not even reproduce on the current runtime.

## Decision

Interactive lifecycle dispatch prose is written **mode-agnostic**. The builder's exit report lives in its **final message** — in whatever shape the runtime delivers it (tool result or completion notification) — and per-task completion is derived **exclusively from the git checkpoint**, never from the return-delivery shape. The orchestrator sends no follow-up "send your report" message, and nothing in the prose branches on whether dispatch was synchronous or background.

Consequences deferred (not built):

- **Dependency-pipelined dispatch** — deferred until the upstream dispatch-mode substrate is stable and a measured case survives token accounting (extra orchestrator turns × growing context, weighed against a saving bounded by a single straggler). The **batch barrier stays**: batch N+1 waits for batch N.
- **A `task_complete` completion event** — deferred for the same reason. Under the batch barrier a checkpoint-time event would measure the barrier, not the task, and the commit timestamps recorded at the git checkpoint are strictly better data. Revisit only alongside pipelining.

Trade-off accepted: bounded wall-clock idling behind stragglers — mitigated at plan time by straggler isolation, not by runtime coordination — in exchange for prose that is correct on every runtime version and zero new coordination machinery. This reverses the source ticket's "decide the dispatch mode first" framing: the durable decision is to **not couple the harness to either mode**.
