---
name: requirements-write
description: Synthesize-only sub-skill that turns a Q&A markdown block from /requirements-gather into a v2-compliant cortex/requirements/{project|area}.md. Invoked by the /cortex-core:requirements orchestrator; never conducts an interview itself.
when_to_use: "Use only as a sub-skill of /cortex-core:requirements after /requirements-gather has produced a Q&A block. Different from /requirements-gather — gather interviews, write synthesizes and is the only sub-skill that touches the filesystem."
argument-hint: "<scope>"
inputs:
  - "scope: string (required) — 'project' for parent doc, or area kebab-case slug for an area doc"
  - "qa-block: markdown (required) — the structured Q&A block returned by /requirements-gather"
  - "existing-doc: string (optional) — path to an existing target doc to refine rather than write fresh"
outputs:
  - "cortex/requirements/project.md (scope=project) OR cortex/requirements/{area}.md (scope=area)"
---

# /requirements-write

Synthesize the Q&A block plus any existing target doc into a v2-compliant artifact at `cortex/requirements/project.md` or `cortex/requirements/{area}.md`. Return the written path to the orchestrator; do not invoke further sub-skills.

## Synthesis decisions

- **Preserve existing prose** where the user's answer confirms current text — refine in place, do not rewrite from scratch.
- **Apply template defaults** for sections the gather phase collapsed to "code-derived position confirmed." Keep H2/H3 anchors verbatim; downstream consumers grep section names.
- **Surface missing answers** by keeping the H2 in place with a one-line note pointing at Open Questions (area) or a `## Optional` bullet (project). Never drop a required H2 to hide a gap. Update the `> Last gathered:` date to today when any section changes.

## Project template — `cortex/requirements/project.md`

Header `# Requirements: {project-name}` + `> Last gathered: {YYYY-MM-DD}` blockquote, then these seven H2s in order:

1. `## Overview` — 1–2 paragraph north star; distribution posture if load-bearing.
2. `## Philosophy of Work` — Cross-cutting principles, bold-led bullets.
3. `## Architectural Constraints` — Strategic constraints, bold-led bullets (NOT operational details — those live in CLAUDE.md).
4. `## Quality Attributes` — Non-functional bar, bold-led bullets.
5. `## Project Boundaries` — H3s `### In Scope`, `### Out of Scope`, `### Deferred`. Discovery/backlog scope clarified inline per R14.
6. `## Conditional Loading` — `{trigger phrase} → cortex/requirements/{area}.md` lines; trigger phrases must intersect real lifecycle `index.md` `tags:` words.
7. `## Optional` — Prunable. First non-heading line states the prunability convention; bold-led bullets for deferred notes. Token budget ≤1,200 (`cl100k_base`), verified at acceptance — overflow goes into `## Optional` or an area doc, never new top-level H2s.

## Area template — `cortex/requirements/{area}.md`

Header `# Requirements: {area-name}` + `> Last gathered: {YYYY-MM-DD}` + `**Parent doc**: [requirements/project.md](project.md)`, then seven H2s in order:

1. `## Overview` — What this area covers and its place in the project.
2. `## Functional Requirements` — One H3 per capability; canonical bullets `**Description**`, `**Inputs**`, `**Outputs**`, `**Acceptance criteria**` (nested), `**Priority**` (must/should/nice-to-have).
3. `## Non-Functional Requirements` — Performance, latency, idempotency, context hygiene; bold-led bullets.
4. `## Architectural Constraints` — Solution-space narrowing; plain bullets.
5. `## Dependencies` — Internal areas + external systems/binaries/env vars.
6. `## Edge Cases` — `**Condition**: behavior` format.
7. `## Open Questions` — `- None` when nothing is open.

No token budget. Parent backlink is the only navigation element; area docs do NOT carry "When to Load" prose. Preserve H2 names verbatim across rewrites.
