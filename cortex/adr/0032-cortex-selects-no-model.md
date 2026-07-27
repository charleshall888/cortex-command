---
status: accepted
---

# 0032 — cortex selects no model; the dispatching agent chooses

## Context

cortex used to own three separate model-selection surfaces:

- **Path A, interactive.** The `cortex-resolve-model` verb held a deterministic *(role, criticality) → model* Lifecycle Matrix (`review`, `builder`, `orchestrator-fix`, `competing-plan`, plus criticality-independent `synthesizer → opus` and `searcher → sonnet`). Eight skill dispatch sites shelled out to it, read the model back, and bound it to the sub-agent.
- **Path B, autonomous.** `resolve_model(complexity, criticality)` in `cortex_command/pipeline/dispatch.py` held a *(complexity, criticality) → model* matrix for the overnight runner, plus a `haiku → sonnet → opus` escalation ladder the retry loop climbed on an `escalate`-classified failure, plus per-attempt model pins in the merge-conflict and test-failure repair paths.
- **Path C, prompt prose.** `cortex_command/overnight/prompts/orchestrator-round.md` told the orchestrator agent to dispatch "Sonnet plan-gen sub-agents" and an "Opus synthesizer".

Two matrices were documented as structurally unmergeable (the `orchestrator-fix` row is not representable in a complexity × criticality lattice), so the shapes were maintained separately, tested separately, and explained separately — in `docs/internals/sdk.md`, `docs/agentic-layer.md`, `docs/overnight-operations.md`, and on the public landing page.

The cost of all this was carried on every dispatch: a subprocess call and a paragraph of halt-and-escalate prose at each interactive site, a golden-anchor parity test plus a wiring test, an effort matrix whose skill overrides were *gated* on the resolved model being opus, a model-capability guard that had to prove no cell ever requested `xhigh` on Sonnet, and a landing-page schematic explaining the ladder to readers.

What it bought was a routing decision a capable dispatching agent already makes well from context it already has — the task, the tier, the criticality — and which the operator can no longer easily override when a matrix cell is wrong for a particular run.

## Decision

**cortex does not choose a model anywhere.** All three surfaces are removed:

- `cortex-resolve-model` is deleted — the verb, its console-script entry, its binstub, its plugin mirror, and its two test files. Skill dispatch sites state *what the dispatch is for* (gather vs judgment, builder vs reviewer) and leave the model to the dispatching agent.
- `ClaudeAgentOptions.model` is left unset for every overnight dispatch, so the agent runs on the CLI's own default. `_MODEL_MATRIX`, `resolve_model()`, `TIER_CONFIG["model"]`, `MODEL_ESCALATION_LADDER`, and the `model_override` parameter are gone.
- The orchestrator-round prompt names no model.

Three consequences are load-bearing and were chosen deliberately:

**The `escalate` recovery path collapses into `retry`.** With no ladder to climb, `agent_test_failure` and `agent_confused` re-dispatch with accumulated learnings and pause when attempts run out — the same terminal behavior as before, minus the tier climb. The `escalated` / `escalation_event` dispatch kwargs and the `retry_escalate` event are removed; `repair_agent_escalated` is renamed `repair_agent_retried`. (The *lifecycle* state named `escalated` — a REJECTED review needing human direction — is unrelated and unchanged.)

**Effort survives, decoupled from model.** `resolve_effort(complexity, criticality, skill)` keeps the 12-cell matrix and the `review-fix` / `integration-recovery` → `max` overrides, which are now unconditional because their opus gate is gone. The model-capability guard (fail loudly if a cell requests `xhigh` on Sonnet) is deleted: cortex cannot evaluate it without knowing the model. An unacceptable `--effort` is instead caught at the CLI boundary by the pre-existing loud-degradation path from ADR-0014 — hard-reject clamps once to `max`, warn-ignore emits `dispatch_effort_ignored`.

**Observability is preserved by reading the model back rather than dropping it.** `AssistantMessage` reports the model each dispatch actually ran on. cortex captures the first non-empty value, emits a one-shot `dispatch_model_observed` event so the dashboard can badge a *running* dispatch, and repeats it on `dispatch_complete` so `pair_dispatch_events` can bucket. The pairing reads the completion event first and falls back to the start event, so metrics written before this change still aggregate. `dispatch_start` no longer carries a `model` key — nothing has replied when it is written.

## Alternatives considered

**Keep Path B, remove only Path A.** The pipeline matrix is programmatic, not agentic — no agent is "choosing" there — so it was not obviously in scope. Rejected: it would have left two of the three surfaces standing (the pipeline matrix and the orchestrator prompt), kept the escalation ladder, the model-gated effort overrides, and the capability guard, and preserved exactly the split-brain the docs already had to explain at length. Removing selection in one path and not the other is the worst of both.

**Keep the criticality-independent constants (`synthesizer → opus`, `searcher → sonnet`) and delete only the criticality matrix.** Rejected: keeping the verb, binstub, plugin mirror, console entry, and test suite alive to serve a two-entry lookup costs more than either extreme. The intent behind them survives as prose at the dispatch sites — gather angles are read-and-report and a cheaper tier usually fits; synthesis is the judgment step and should be weighted accordingly — which is guidance the agent can act on and override, rather than a lookup it must obey.

**Drop model recording along with model selection.** Rejected. Not choosing the model does not mean not wanting to know it. Dropping the field would have blanked the dashboard's model badges, the per-model cost buckets in `metrics.json`, and the per-model price table in `session_tokens.py` — a cost-visibility regression with no relationship to the routing simplification. `AssistantMessage.model` makes the tradeoff unnecessary.

## Consequences

ADR-0023 (route the core research fan-out to a Sonnet `searcher` tier) is superseded: its `searcher` role no longer exists. Its underlying observation — that breadth-first gather work does not need the most expensive model — is retained as guidance in `skills/research/references/fanout.md` rather than as a pinned model.

Interactive fan-out that ADR-0023 routed to Sonnet now runs on whatever the dispatching agent picks. If overnight cost-per-round or interactive research cost regresses measurably, the lever is the dispatch-site guidance, not a reinstated matrix.
