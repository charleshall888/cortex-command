# Research Fan-Out

Shared by `/cortex-core:research` and `/cortex-core:discovery` so their fan-out cannot drift apart.

## Count matrix

| tier \ criticality | low | medium | high | critical |
|--------------------|-----|--------|------|----------|
| **simple**         | 1   | 1      | 2    | 3        |
| **moderate**       | 1   | 2      | 3    | 4        |
| **complex**        | 3   | 4      | 5    | 6        |

An **upper bound on breadth, not a quota** — dispatch fewer when the task offers fewer genuinely distinct angles.

## Angle selection

The mandatory core is tier-scoped:

- **Codebase** — mandatory at every cell.
- **Web** — mandatory at complex tier; below it only when the task names an external dependency, protocol, or library question.
- **Requirements & Constraints** — mandatory at complex tier; below it only when Clarify's requirements-alignment note was `partial` or `conflict`.

The lower rows are thin by design: simple work follows an existing pattern, and `cortex-complexity-escalator` raises the tier when research surfaces unresolved uncertainty.

**Adversarial** is always present for high/critical (optional below), and runs **last**, over a summary of the other agents' findings.

Remaining slots are orchestrator-chosen: distinct, non-redundant angles. Subdivide an existing angle by scope only once distinct angles are exhausted, noting in `## Open Questions` when subdivision was driven by the cell's count rather than genuine distinctness.

## Dispatch order

1. **Core wave (parallel)** — every angle except the adversarial one. Breadth-first read-and-report, so a cheaper model usually fits; the choice is yours per dispatch.
2. **Adversarial wave (last)** — summarize the core wave and dispatch over that summary. Judgment rather than gather, so don't cheap it out.

At low/medium criticality with no adversarial agent, the core wave is the whole dispatch.
