---
name: backlog-author
description: Compose a ticket body from a context block, using the Why/Role/Integration/Edges/Touch-points template.
argument-hint: "compose <context-block>"
---

# backlog-author

Compose one ticket body per invocation from the given context block. A caller with N pieces invokes N times. Write only the markdown body to stdout — frontmatter belongs to `cortex-create-backlog-item --body`.

### compose

Write the five-section markdown body to stdout, in this order: `## Why`, `## Role`, `## Integration`, `## Edges`, `## Touch points`. All are required except `## Touch points`.

- **`## Why`** — the problem as a symptom: what is broken, missing, or worse, in terms someone can observe. Not the solution. Omit this section when it would only repeat the lead of Role.
- **`## Role`** — the job this piece does once the ticket lands that nothing did before (arc42 Responsibility). Not how it does it.
- **`## Integration`** — what it connects to, inbound and outbound. Name each interface (e.g. "the phase-transition contract").
- **`## Edges`** — constraints and boundary conditions: what breaks if an upstream contract changes shape, what this must not do, which non-goals keep scope tight. Each bullet names a contract or a non-goal.
- **`## Touch points`** — where the work lands: file paths with line numbers, section indices, code excerpts. Omit when none are known.
