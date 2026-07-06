# Body Template

Five-section template for backlog ticket bodies, in order; all required except `## Touch points` (optional). Prose only — no path:line or section-index citations, no fenced code blocks — except inside `## Touch points`, where those forms are the norm.

## Why

The problem in symptom-voice: what's broken, missing, or degraded in observable terms, as a user or operator would describe it — not the solution or mechanism (one paragraph).

**Why-vs-Role rule**: Why is the problem in symptom-voice; Role is the slot this piece fills after the ticket lands (arc42 Responsibility — the task it fulfills). Omit Why when it collapses to one sentence restating Role's lead; otherwise required.

## Role

What this piece does by its Responsibility (arc42 framing), not its mechanism: the job that exists after the ticket lands that didn't before (one paragraph; not how it's built or which files it touches).

## Integration

How this piece connects to neighboring pieces and the system, referencing Interface surfaces from the Architecture section by name (e.g., "the phase-transition contract") — one paragraph, inbound and outbound.

## Edges

Structural constraints and Boundary conditions: what breaks if an upstream contract changes shape, what this piece must not do, and non-goal decisions keeping scope tight. Each bullet names a contract surface or non-goal.

## Touch points

Implementation locations — file paths with line numbers, section indices (§N, RN), or code excerpts, one bullet per location. Omit entirely when none are known at authoring time (optional by design).
