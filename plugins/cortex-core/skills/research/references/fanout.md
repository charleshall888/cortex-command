# Research Fan-Out

Shared, canonical protocol for sizing and dispatching parallel research agents — single source for the agent-count matrix, angle-selection rule, and dispatch order. Cited by both consuming entry points (`/cortex-core:research`, `/cortex-core:discovery`) so their fan-out cannot drift apart.

## Count matrix

Agent count is the cell where the task's tier (row) meets its criticality (column):

| tier \ criticality | low | medium | high | critical |
|--------------------|-----|--------|------|----------|
| **simple**         | 3   | 4      | 5    | 6        |
| **complex**        | 5   | 6      | 8    | 10       |

The count is an **upper bound on breadth, not a quota** — dispatch fewer if the task offers fewer genuinely distinct angles than its cell allows.

## Hybrid angle selection

Three angles are the **mandatory core**, run at every cell:

- **Codebase** — how the existing system works, where the change lands, what it touches.
- **Web** — external prior art, libraries, patterns, and known pitfalls.
- **Requirements & Constraints** — project/area requirements, scope boundaries, non-negotiables.

An **Adversarial** angle is **always present for high/critical** work (optional below that, at orchestrator discretion). It runs **last**, over a summary of the other agents' findings rather than the raw task.

The **remaining slots** are **chosen by the orchestrator per task** — distinct, non-redundant angles, each investigating something the others don't. *Tradeoffs* is a common choice. Subdivide an existing angle by scope (e.g., Codebase into per-subsystem agents) only once distinct angles are exhausted; note in `## Open Questions` when subdivision was driven by the cell's count rather than genuine distinctness.

## Dispatch protocol

1. **Core wave (parallel) — binds the `searcher` model.** Dispatch the mandatory core plus orchestrator-chosen angles — every angle except the always-last adversarial one — in parallel. Each consuming orchestrator body resolves `model=$(cortex-resolve-model --role searcher)` and binds it as every core-wave `Agent`'s `model:`; on nonzero resolve it degrades loud — dispatch with **no** `model:` (inherit the parent) plus a one-line warning, never halting.
2. **Adversarial wave (last) — inherits the parent.** For high/critical work, once the core wave returns, summarize its findings and dispatch the adversarial agent over that summary; fold its critique into synthesis. It omits `model:` (not routed to the cheaper `searcher`).

At low/medium criticality with no adversarial agent, the core wave is the whole dispatch.

This file authors the *rule*; each consumer carries its own runnable resolve + `model:` bind.

## Why this protocol

The two factors compound rather than max, so complex+critical peaks the count (10) at a concurrency-and-diminishing-returns ceiling. Discovery biases sizing toward this grid's high end (see clarify.md for why).
