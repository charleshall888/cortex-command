# Artifact-format templates (Task 21 working draft)

Working draft to seed Tasks 22–23. Templates will be inlined into `skills/requirements-write/SKILL.md` per R16 — no separate `references/` doc. The structural contract `/requirements-write` produces.

Derived from:
- Live parent: `cortex/requirements/project.md` (post-Task 15 trim, ≤1,200 tokens cl100k_base).
- Live areas: `cortex/requirements/{multi-agent,observability,pipeline,remote-access}.md`.
- Retiring v1 templates: `skills/requirements/references/gather.md` (removed in Task 25).

## Parent (project.md) template

Header: `# Requirements: {project-name}` followed by `> Last gathered: {YYYY-MM-DD}` blockquote.

Required H2 sections, in order:

1. `## Overview` — 1–2 paragraph project description: what this is, who it's for, the north star. Includes distribution/install posture if load-bearing for downstream consumers.
2. `## Philosophy of Work` — Cross-cutting principles every consumer needs each session (e.g., day/night split, complexity discipline, solution horizon, quality bar). Bold-led bullets. Omit only if nothing is genuinely universal — but the live project.md treats this as required.
3. `## Architectural Constraints` — Strategic constraints that narrow the solution space. NOT operational details (those belong in CLAUDE.md). Bold-led bullets, one per constraint.
4. `## Quality Attributes` — Reliability, maintainability, performance, security, accessibility — the non-functional bar the project holds itself to. Bold-led bullets.
5. `## Project Boundaries` — H3 sub-sections `### In Scope`, `### Out of Scope`, `### Deferred`. Per R14, discovery/backlog scope clarification lives inline here ("Discovery and backlog are documented inline (no area docs)") rather than via new area docs.
6. `## Conditional Loading` — One line per area doc: `{trigger phrase} → cortex/requirements/{area}.md`. Trigger phrases describe the work that makes the area doc relevant. Must intersect with real lifecycle index.md `tags:` words per R12.
7. `## Optional` — llms.txt-style prunable section. Per R11, the first non-heading line states the prunability convention ("Content here is prunable under token pressure — skip without losing spec-required guidance"). Bold-led bullets for deferred/lesser-priority architectural notes.

Structural rules:
- Token budget ≤1,200 tokens (`cl100k_base`), verified at acceptance time per R10. Not enforced at commit.
- All seven H2s required in this order. No additional H2s — overflow content goes into `## Optional` (prunable) or an area doc (Conditional Loading), not into new top-level sections.
- Anchor preservation: section headings are referenced by name from skill prose and hooks. Renaming an H2 requires a corresponding sweep of consumers. Preserve verbatim section names across rewrites.
- `## Optional` is the only prunable section. Consumers under token pressure may skip it; all other sections are always-loaded context.

## Area template

Header: `# Requirements: {area-name}` followed by `> Last gathered: {YYYY-MM-DD}` blockquote, then a `**Parent doc**: [requirements/project.md](project.md)` backlink line.

Required H2 sections, in order:

1. `## Overview` — What this area covers and how it fits into the project. 1–2 paragraphs.
2. `## Functional Requirements` — One H3 per capability. Each capability uses the canonical bullet shape: `**Description**`, `**Inputs**`, `**Outputs**`, `**Acceptance criteria**` (nested bullets), `**Priority**` (must-have / should-have / nice-to-have). Additional bold-led bullets allowed where load-bearing (see multi-agent.md's `Orchestrator dispatch-template substitution contract` under Parallel Dispatch).
3. `## Non-Functional Requirements` — Performance, latency, availability, resource constraints, idempotency, context hygiene. Bold-led bullets.
4. `## Architectural Constraints` — Constraints that narrow the solution space without prescribing implementation. Plain bullets.
5. `## Dependencies` — Internal area dependencies + external systems/binaries/env vars. Bold-led bullets when categorized; plain bullets when uniform.
6. `## Edge Cases` — Known edge cases and expected behavior. Bold-led `**Condition**: behavior` format.
7. `## Open Questions` — Unresolved questions specific to this area; `- None` when nothing is open.

Structural rules:
- Required H2s are the seven above, in order. Ad-hoc additional H2s are discouraged — they break the area-doc shape contract that consumers rely on. (Note: live `observability.md` carries one extra H2 `## Install-mutation invocations` as a documented exception; Task 24 audit may resolve it.)
- The Parent backlink is the only required navigation element. Area docs do NOT contain "When to Load" guidance — that belongs in the parent's `## Conditional Loading` trigger table.
- Area docs are loaded conditionally; no token budget is enforced. Keep capability count proportional to real surface area.
- Anchor preservation rule applies: section names are referenced by skill prose; preserve verbatim across rewrites.
