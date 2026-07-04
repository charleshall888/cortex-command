# Research Fan-Out

Shared, canonical protocol for sizing and dispatching parallel research agents — the single source for the agent-count matrix, the hybrid angle-selection rule, and the dispatch order. Both consuming entry points (`/cortex-core:research`, `/cortex-core:discovery`) cite this file so their fan-out cannot drift apart.

## Count matrix

Agent count is the cell where the task's tier (row) meets its criticality (column):

| tier \ criticality | low | medium | high | critical |
|--------------------|-----|--------|------|----------|
| **simple**         | 3   | 4      | 5    | 6        |
| **complex**        | 5   | 6      | 8    | 10       |

The count is an **upper bound on breadth, not a quota** — the most distinct angles the task warrants. If a task offers fewer genuinely distinct angles than its cell allows, dispatch fewer.

## Hybrid angle selection

Three angles are the **mandatory core** and always run, at every cell of the matrix:

- **Codebase** — how the existing system works, where the change lands, what it touches.
- **Web** — external prior art, libraries, patterns, and known pitfalls.
- **Requirements & Constraints** — project/area requirements, scope boundaries, and non-negotiables in scope for this work.

An **Adversarial / critique** angle is **always present for high and critical** work (and optional below that, at orchestrator discretion when the cell's budget allows). It is dispatched **last**, over a brief summary of the other agents' findings rather than over the raw task.

The **remaining slots** the matrix buys (beyond the mandatory core and, where applicable, the adversarial agent) are **chosen by the orchestrator per task**. Pick angles that are distinct and non-redundant — each should investigate something the others do not. *Tradeoffs* (alternatives, costs, second-order effects) is a common orchestrator choice. Subdivide an existing angle by scope only once genuinely distinct angles are exhausted — for example, splitting Codebase into per-subsystem agents when one codebase pass cannot cover the surface area. When subdivision is reached because the cell's count exceeded the distinct angles available, the orchestrator may note that in `## Open Questions`.

There is **no** hardcoded topic→angle keyword router; angle choice beyond the mandatory core is orchestrator judgment in context — describing *what* each angle must cover and *why*.

## Dispatch protocol

1. **Core wave (parallel) — binds the `searcher` model.** Dispatch the mandatory core plus the orchestrator-chosen angles for the cell — every angle except the always-last adversarial one — in parallel. Because this is breadth-first gather work, each consuming orchestrator body resolves `model=$(cortex-resolve-model --role searcher)` and binds it as every core-wave `Agent`'s `model:`; on nonzero resolve it degrades loud — dispatch with **no** `model:` (inherit the parent) plus a one-line warning, never halting.
2. **Adversarial wave (last) — inherits the parent.** For high/critical work, once the core wave returns, summarize its findings and dispatch the adversarial agent over that summary; fold its critique into synthesis. It **omits** `model:` and inherits the parent — the error-correction layer is not routed to the cheaper `searcher`.

At low/medium criticality where no adversarial agent was chosen, the core wave is the whole dispatch and there is no second wave.

This file authors the *rule*; each consumer (`/cortex-core:research` Step 3, `/cortex-core:discovery`'s research dispatch) carries its own runnable resolve + `model:` bind, since each dispatches from its own body.

## Why this protocol

The two factors **compound** rather than being max'd together, so complex+critical peaks the count (10), and the cap holds there because parallel research hits a concurrency-and-diminishing-returns ceiling. Discovery biases its sizing upward toward the high end of this same grid (see discovery's clarify.md for why).
