# Research Fan-Out

Shared protocol for sizing and dispatching parallel research agents. Consumed by `/cortex-core:research` (and therefore by `/refine` and `/lifecycle`, which delegate to it) and by `/cortex-core:discovery`'s research phase. It is the single canonical source for the agent-count matrix, the hybrid angle-selection rule, and the dispatch order — both entry points cite this file so their fan-out cannot drift apart.

## Count matrix

Agent count scales with **both** the complexity tier and the criticality of the work. Look up the cell where the task's tier (row) meets its criticality (column):

| tier \ criticality | low | medium | high | critical |
|--------------------|-----|--------|------|----------|
| **simple**         | 3   | 4      | 5    | 6        |
| **complex**        | 5   | 6      | 8    | 10       |

Both axes raise the count monotonically; the complex+critical corner is the strict peak (10). The count is an **upper bound on investigation breadth, not a quota** — it is the most distinct angles the task warrants, not a target to pad with redundant agents. If a task offers fewer genuinely distinct angles than its cell allows, dispatch fewer; do not invent overlapping work to hit the number.

## Hybrid angle selection

Three angles are the **mandatory core** and always run, at every cell of the matrix:

- **Codebase** — how the existing system works, where the change lands, what it touches.
- **Web** — external prior art, libraries, patterns, and known pitfalls.
- **Requirements & Constraints** — project/area requirements, scope boundaries, and non-negotiables in scope for this work.

An **Adversarial / critique** angle is **always present for high and critical** work (and optional below that, at orchestrator discretion when the cell's budget allows). It is dispatched **last**, over a brief summary of the other agents' findings rather than over the raw task — so it challenges a *synthesis* of what was found, which cuts error amplification by catching mistakes the parallel agents made independently before they propagate into the artifact. This preserves the centralized-synthesis error-correction layer.

The **remaining slots** the matrix buys (beyond the mandatory core and, where applicable, the adversarial agent) are **chosen by the orchestrator per task**. Pick angles that are distinct and non-redundant — each should investigate something the others do not. *Tradeoffs* (alternatives, costs, second-order effects) is a common orchestrator choice. Subdivide an existing angle by scope only once genuinely distinct angles are exhausted — for example, splitting Codebase into per-subsystem agents when one codebase pass cannot cover the surface area. When subdivision is reached because the cell's count exceeded the distinct angles available, the orchestrator may note that in `## Open Questions`.

There is **no** hardcoded topic→angle keyword router. Angle choice beyond the mandatory core is orchestrator judgment in context — describing *what* each angle must cover and *why*, not following a fixed lookup of topic words to specialists. (This follows the What/Why-not-How authoring principle: capable models pick the right distinct angles given the intent, and a hardcoded router would be brittle.)

## Dispatch protocol

1. **Core wave (parallel) — routes to the Sonnet `searcher` tier.** Dispatch the mandatory core plus the orchestrator-chosen angles for the cell, all in parallel. This is every angle except the always-last adversarial one. The core wave is breadth-first gather work the orchestrator synthesizes, so bind it to the `searcher` model rather than inheriting the (interactively, Opus) parent: in the consuming orchestrator **body**, resolve `model=$(cortex-resolve-model --role searcher)` and pass the captured value as the `model:` parameter of every core-wave `Agent` call. If the resolve exits nonzero, fall back to dispatching the core wave with **no** `model:` (inherit the parent, exactly as before) and surface a one-line warning that the gather wave is running on the inherited model because role resolution failed — do not halt. `searcher` is criticality-independent, so this resolves with no `--criticality` and no lifecycle-state read (it works in standalone `/research` with no lifecycle session).
2. **Adversarial wave (last) — inherits the parent.** For high/critical work, once the core wave returns, summarize its findings briefly and dispatch the adversarial agent over that summary. Fold its critique into synthesis. The adversarial wave **omits** `model:` and inherits the parent — it is the error-correction layer that catches what the cheaper gatherers missed, so it is not routed to `searcher` (the judgment-inherit contract; see `docs/internals/sdk.md` and ADR-0023).

At low/medium criticality where no adversarial agent was chosen, the core wave is the whole dispatch and there is no second wave.

This file authors the routing *rule*; each consuming entry point (`/cortex-core:research` Step 3, `/cortex-core:discovery`'s research dispatch) carries its own runnable resolve + `model:` bind that follows it, because each dispatches from its own orchestrator body rather than by executing this file.

## Why this protocol

The grid is **corner-anchored**: the two factors compound rather than being max'd together, so the hardest *and* riskiest work — complex+critical — gets the deepest investigation (10) instead of the same count as work elevated on a single axis. Single-axis cells rise modestly; the floor (simple+low) stays at 3. Discovery sets the initial direction of an epic, where a wrong direction propagates across every ticket it spawns, so discovery's sizing assessment is biased upward toward the high end of this same grid.

The cap holds at 10 because parallel research hits a concurrency-and-diminishing-returns ceiling — beyond roughly ten distinct angles, added agents overlap and synthesis cost outweighs marginal coverage.
