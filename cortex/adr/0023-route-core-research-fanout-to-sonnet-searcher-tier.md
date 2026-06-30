---
status: accepted
---

# 0023 — Route the core research fan-out to a Sonnet `searcher` tier

## Context

The interactive parallel-research fan-out (`/cortex-core:research`, and `/cortex-core:discovery`'s research phase) dispatches its read-only core-wave agents with **no `model` parameter**, so they inherit the parent session model — Opus, in an interactive session. That runs breadth-first read-and-report "grunt" gather work on the most expensive model for no quality benefit: the orchestrator synthesizes the per-agent outputs, so individual-agent depth is not the bottleneck. This is the one interactive model-routing surface not already covered by the pipeline matrix (`cortex_command/pipeline/dispatch.py`, Path B — already Sonnet-heavy) or the lifecycle role matrix (`cortex-resolve-model`'s builder/reviewer/orchestrator-fix rows — already routed).

The single-matrix-owner constraint (`docs/internals/sdk.md`, `cortex_command/lifecycle/resolve_model_cli.py`, `skills/lifecycle/references/criticality-matrix.md`) requires the model name to be owned by the `cortex-resolve-model` verb, not hardcoded as a `"sonnet"` literal in a skill. A prior archived approach (`cortex/research/archive/subagent-model-routing/`, "Option D") scattered literals into each skill and flagged its own drift risk; this decision is the durable form of that rejected approach.

## Decision

Add a criticality-independent `searcher → sonnet` role to `cortex-resolve-model` (modeled on the existing `synthesizer` constant) and route the **entire core wave** (mandatory core — Codebase, Web, Requirements & Constraints — plus *all* orchestrator-chosen angles, including Tradeoffs) to it. The routing rule is authored once in the shared `skills/research/references/fanout.md`, and each consuming orchestrator body (`skills/research/SKILL.md` Step 3, `skills/discovery/references/research.md`) carries its own runnable `model=$(cortex-resolve-model --role searcher)` resolve + `model:` bind that cites it — because both entry points dispatch from their own bodies, not by executing fanout.md.

The **always-last adversarial wave** continues to inherit the parent model: it is the error-correction layer, runs only at high/critical over a brief summary of the other agents' findings, and downgrading the one agent whose job is to catch what the cheap gatherers missed is a false economy.

On nonzero exit from `cortex-resolve-model --role searcher`, the orchestrator **degrades loud to inherit** — it falls back to dispatching the core wave with no `model:` (the inherited parent, exactly as today) and surfaces a one-line warning — rather than halting. No opt-out flag or per-run override is added.

### The judgment-inherit contract

The currently-inheriting **judgment** dispatches are deliberately left inheriting the parent model rather than routed to `searcher`: the research **adversarial** wave, **critical-review's parallel reviewers** (`skills/critical-review/SKILL.md`), and the **clarify-critic** (`skills/refine/references/clarify-critic.md`). This boundary is file-locality, not feature-size: this change edits `skills/research`/`fanout.md`/`discovery`, so it reaches research-adversarial in-scope but does not reach into the critical-review/clarify skill files. Routing those reviewers to Sonnet specifically would be a *downgrade* this ADR opposes. The contract is documented here and in `docs/internals/sdk.md` so a future editor of any of those surfaces finds the omission deliberate, not an oversight.

## Trade-offs

1. **Routing unit is the wave, not the angle.** Chosen because the fan-out's only structural seam is core-vs-adversarial; an angle-level gather/judgment split has no structural anchor and produced contradictory routing for chosen angles like Tradeoffs. The cost: the mildly-evaluative Tradeoffs angle runs on Sonnet — accepted because its output is folded into the Opus synthesis and re-challenged by the adversarial pass.

2. **Constant role, not a tier-keyed row.** Chosen for minimal golden-test churn and to avoid the empty low/medium/high-cell drift the module warns against; criticality scales the angle count and triggers the adversarial wave, not the per-gatherer model. The cost is a small asymmetry versus the tier-keyed roles.

3. **Degrade-loud-to-inherit, not halt.** Chosen because a `searcher` failure's only fallback is the inherited parent (a non-regressing inherit, unlike the quality-*downgrade* risk that justifies halting at the criticality-keyed sibling sites), the realistic trigger is wheel-vs-mirror version skew (the skill ships in the plugin, the verb in the wheel — a single-site failure, not a global fault), and halting would break interactive `/research` against `project.md`'s "keep working unless blocked."

This decision is **hard to reverse** (it becomes the established convention for interactive fan-out model routing across research, discovery, and fanout.md), **surprising without context** (why interactive research runs on a different model than the session), and the **result of a real trade-off** on each axis above — clearing the three-criteria ADR gate.

## Implementation sites

- `cortex_command/lifecycle/resolve_model_cli.py` — the `searcher → sonnet` constant in `_CRITICALITY_INDEPENDENT`.
- `skills/research/references/fanout.md` — the canonical core-wave-binds / adversarial-inherits routing rule.
- `skills/research/SKILL.md` Step 3 and `skills/discovery/references/research.md` — the per-consumer runnable resolve + bind.
- `docs/internals/sdk.md` — the `searcher → sonnet` rationale bullet and the judgment-inherit contract.
