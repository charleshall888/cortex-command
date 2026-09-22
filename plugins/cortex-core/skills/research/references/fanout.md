# Research Fan-Out

Shared by `/cortex-core:research` and `/cortex-core:discovery`.

## Count matrix

| tier \ criticality | low | medium | high | critical |
|--------------------|-----|--------|------|----------|
| **simple**         | 1   | 1      | 2    | 3        |
| **moderate**       | 1   | 2      | 3    | 4        |
| **complex**        | 3   | 4      | 5    | 6        |

A maximum, not a target — start fewer agents when the task has fewer distinct angles.

## Angle selection

- **Codebase** — always required.
- **Web** — required at complex; below it only when the task names an external dependency, protocol, or library question.
- **Requirements & Constraints** — required at complex; below it only when Clarify's alignment note was `partial` or `conflict`.
- **Adversarial** — always at high/critical (optional below), and always **last**, over a summary of the other agents' findings.

Lower rows are small on purpose: simple work follows an existing pattern, and the tier is checked again after research. You choose the remaining angles; each must be distinct. Split one angle by scope only when no distinct angles are left, and note in `## Open Questions` that the count caused the split.

## Dispatch order

1. **Core wave (parallel)** — every angle but the adversarial one. It reads widely and reports, so a cheaper model usually fits.
2. **Adversarial wave (last)** — over a summary of the core wave. It needs judgment, so don't use a cheap model.

With no adversarial agent, the core wave is the whole run.
