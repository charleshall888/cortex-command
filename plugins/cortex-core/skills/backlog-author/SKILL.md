---
name: backlog-author
description: Compose a structured backlog ticket body from a context block, using the Why/Role/Integration/Edges/Touch-points template. Use when user says "compose a ticket", "write a ticket body", or "author a backlog item".
argument-hint: "compose <context-block>"
---

# backlog-author

Compose one ticket body per invocation from the provided context block (a caller with N pieces invokes N times). Emit only the markdown body to stdout — frontmatter belongs to `cortex-create-backlog-item --body`.

### compose

Emit the five-section markdown body to stdout, sections in order — `## Why`, `## Role`, `## Integration`, `## Edges`, `## Touch points` — all required except `## Touch points`. Prose only: no path:line or `§N` citations and no fenced code blocks outside `## Touch points`, where those forms are the norm.

- **`## Why`** — the problem in symptom-voice: what is broken, missing, or degraded, in observable terms. Not the solution. Omit this section when it collapses to a restatement of Role's lead.
- **`## Role`** — the job this piece does once the ticket lands that nothing did before (arc42 Responsibility), not its mechanism.
- **`## Integration`** — how it connects inbound and outbound, naming Interface surfaces by name (e.g. "the phase-transition contract").
- **`## Edges`** — structural constraints and boundary conditions: what breaks if an upstream contract changes shape, what this must not do, which non-goals keep scope tight. Each bullet names a contract surface or a non-goal.
- **`## Touch points`** — implementation locations: file paths with line numbers, section indices, code excerpts. Omit when none are known.

If an `## Edges` bullet needs a path:line to express its constraint, the path:line moves to `## Touch points` and a structural summary stays in `## Edges`.
