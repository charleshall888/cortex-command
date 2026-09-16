# Research Fan-Out

Shared by `/cortex-core:research` and `/cortex-core:discovery`.

## Count matrix

| tier \ criticality | low | medium | high | critical |
|--------------------|-----|--------|------|----------|
| **simple**         | 1   | 1      | 2    | 3        |
| **moderate**       | 1   | 2      | 3    | 4        |
| **complex**        | 3   | 4      | 5    | 6        |

An upper bound on breadth, not a quota — dispatch fewer when the task offers fewer distinct angles.

## Angle selection

- **Codebase** — mandatory at every cell.
- **Web** — mandatory at complex; below it only when the task names an external dependency, protocol, or library question.
- **Requirements & Constraints** — mandatory at complex; below it only when Clarify's alignment note was `partial` or `conflict`.
- **Adversarial** — always at high/critical (optional below), and always **last**, over a summary of the other agents' findings.

Lower rows are thin by design: simple work follows an existing pattern, and the tier is re-assessed after research. Remaining slots are orchestrator-chosen, distinct, non-redundant; subdivide an angle by scope only once distinct angles are exhausted, noting in `## Open Questions` when the count drove it.

## Dispatch order

1. **Core wave (parallel)** — every angle but the adversarial one; breadth-first, so a cheaper model usually fits.
2. **Adversarial wave (last)** — over a summary of the core wave; judgment, not gather — don't cheap it out.

With no adversarial agent, the core wave is the whole dispatch.
