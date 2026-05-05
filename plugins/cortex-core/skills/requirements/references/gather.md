# Requirements Gathering Protocol

Interactive interview to surface, clarify, and document requirements. Adapts depth to scope (project vs area) and codebase maturity (greenfield vs existing).

## Depth Principle

Capture the "what" and architectural constraints that narrow the solution space — but not implementation decisions. Good requirement: "Must support 16 concurrent players with sub-100ms input latency." Bad requirement: "Use WebSockets with a relay server architecture." The former constrains what's needed; the latter prescribes how to build it.

## Separation Principle

Requirements complement CLAUDE.md — they do not duplicate it. Before gathering, read the project's CLAUDE.md (or equivalent agent instructions). Understand what operational context is already documented there.

**Belongs in CLAUDE.md** (operational, every session):
- Repository structure and directory layout
- Commands and workflows (build, test, deploy)
- Dependencies and tooling
- Coding conventions and patterns
- Symlink mappings, file organization rules

**Belongs in requirements** (strategic, on-demand):
- Project vision, north star, and audience
- Core feature areas ranked by priority
- Quality attributes (reliability, maintainability, failure tolerance)
- Architectural constraints that may evolve (not operational rules)
- Project boundaries (in scope, out of scope, deferred)
- Open questions and unknowns

During the interview, skip or abbreviate areas already covered by CLAUDE.md. Focus questions on the strategic layer: intent, priorities, quality expectations, and boundaries that the operational docs don't capture.

## Project-Level Gathering

For `requirements/project.md`, cover these areas in sequence. Adapt based on answers — skip areas that aren't applicable, dive deeper into areas that surface complexity.

### 1. Project Vision

Start broad:

- What is this project? (one paragraph)
- Who is the target audience?
- What problem does it solve?
- What distinguishes it from existing solutions?

### 2. Feature Areas

Enumerate the major feature areas. For each area, capture a brief description (1–2 sentences) and when an agent would need to load its dedicated requirements doc. This information populates the `## Conditional Loading` trigger table in the artifact — not an inline feature area list.

- What does this area cover in one sentence?
- What work would cause an agent to need this area's requirements doc?

Do NOT go deep into any single feature here — that's what area-level requirements are for.

### 3. Architectural Constraints

Focus on strategic constraints that narrow the solution space — not operational details already in CLAUDE.md (platforms, tech stack, dependencies belong there).

- Architectural constraints that narrow the solution space (e.g., "must work offline", "must support real-time collaboration")
- Constraints that may evolve over time (e.g., "file-based state for now, may need a database later")
- Performance or scale requirements that affect what's feasible

### 4. Quality Attributes

- Security requirements (auth, data protection, compliance)
- Reliability requirements (uptime, data durability)
- Scalability requirements (user count, data volume)
- Accessibility requirements

### 5. Project Boundaries

- What is explicitly out of scope?
- What is deferred to later phases?
- Known risks or unknowns

## Area-Level Gathering

For `requirements/{area}.md`, the interview goes deeper since it's scoped to a specific feature area.

Before starting, read `requirements/project.md` if it exists. Reference the project requirements when asking questions — area requirements should be consistent with project-level decisions.

**For existing codebases**: Present what the code already reveals about this area's capabilities, patterns, and constraints. Frame the interview around confirming, correcting, and filling gaps — not re-stating what's visible in the code. Focus questions on: intent behind decisions, unwritten rules, known limitations, and planned changes.

### 1. Area Overview

- What is this area responsible for?
- How does it relate to other feature areas?
- Who are the primary users of this area?

### 2. Functional Requirements

For each distinct capability within this area:

- What does it do?
- What are the inputs and outputs?
- What are the success criteria?
- What are the failure modes?

Probe for:

- Happy path behavior
- Edge cases and error states
- User-facing vs internal behaviors
- Interactions with other feature areas

### 3. Non-Functional Requirements

- Performance expectations specific to this area
- Data requirements (storage, retention, formats)
- Security considerations specific to this area
- Concurrency and consistency requirements

### 4. Constraints and Dependencies

- Dependencies on other feature areas
- External system dependencies
- Technical constraints specific to this area
- Known unknowns

### 5. Acceptance Criteria

For each major requirement, establish:

- How will you know it works?
- What would a test for this look like?
- What is the minimum viable version?

## Interview Style

- Ask 2-4 questions at a time, not a wall of questions
- Use findings from codebase reconnaissance to ask informed questions
- Challenge assumptions — "You mentioned X, but what about Y?"
- Identify implicit requirements — things the user assumes but hasn't stated
- When the user says something vague, probe for specifics
- Continue until all major areas are covered and ambiguities resolved
- Circle back to earlier topics if later answers reveal gaps

## Re-Gather Triggers

Requirements are living documents. Re-run `/cortex-core:requirements <scope>` when any of these occur:

- **Lifecycle review identifies drift**: a lifecycle review surfaces a gap between what was built and what the requirements say. Run `/cortex-core:requirements <area>` to update the affected area doc, or `/cortex-core:requirements project` if the drift is project-level.
- **Retro surfaces unmet assumption**: a session retrospective identifies a requirement that was assumed but never documented, or a documented requirement that misled implementation.
- **Core architectural decision changes**: e.g., the state model changes, a core subsystem is replaced, or a constraint that was "may evolve" actually evolves.
- **Scope changes after discovery research**: a discovery epic reshapes what the project is doing in a feature area — update before refining tickets from that epic.
- **Open questions now have answers**: requirements gathered while unknowns existed should be revisited once those unknowns are resolved.

When updating (not replacing):

1. Use `/cortex-core:requirements {area}` to update a specific area doc without regenerating project.md — preferred for targeted drift fixes.
2. Run a focused interview targeting only what has changed: new requirements, invalidated constraints, resolved open questions.
3. Rewrite the full artifact (do not patch sections — maintain internal coherence).
4. After updating an area doc, check the parent's `## Conditional Loading` trigger table. If area scope changed, update the trigger phrase for that entry.

## Artifact Formats

### Project Requirements

Target length: 70–80 lines. The parent doc is always-loaded context — keep it concise. Area-specific detail belongs in area sub-docs, referenced via the Conditional Loading trigger table.

```markdown
# Requirements: {project-name}

> Last gathered: {date}

## Overview
[1-2 paragraph project description: what this is, who it's for, the north star]

## {Optional: project-specific cross-cutting sections}
[Principles, philosophy, or behavioral guidance that applies across all areas and agents need on every task — e.g., "Philosophy of Work", "Design Principles". Omit if nothing is universally cross-cutting.]

## Architectural Constraints
- [Strategic constraints that narrow the solution space — NOT operational details already in CLAUDE.md]

## Quality Attributes
- [Reliability, maintainability, performance, accessibility requirements]

## Project Boundaries

### In Scope
- [Explicit scope inclusions]

### Out of Scope
- [Explicit scope exclusions]

### Deferred
- [Items intentionally deferred to later phases]

## Conditional Loading
{trigger phrase} → requirements/{area}.md
{trigger phrase} → requirements/{area}.md
[One line per area doc. Trigger phrases describe the work that makes the area doc relevant.]
```

### Area Requirements

Area sub-docs do not contain "When to Load" guidance — that belongs in the parent's `## Conditional Loading` trigger table. The parent backlink is the only required navigation element.

```markdown
# Requirements: {area-name}

> Last gathered: {date}

**Parent doc**: [requirements/project.md](project.md)

## Overview
[What this area covers and how it fits into the project]

## Functional Requirements

### {Capability 1}
- **Description**: {What it does}
- **Inputs**: {What it takes}
- **Outputs**: {What it produces}
- **Acceptance criteria**: {How to verify it works}
- **Priority**: must-have | should-have | nice-to-have

### {Capability 2}
...

## Non-Functional Requirements
- [Performance, data, security, concurrency requirements]

## Architectural Constraints
- [Constraints that narrow the solution space without prescribing implementation]
- [e.g., "must work offline", "must support 16 concurrent players", "must be backward-compatible with v1 API"]

## Dependencies
- [Dependencies on other areas, external systems]

## Edge Cases
- [Known edge cases and expected behavior]

## Open Questions
- [Unresolved questions specific to this area]
```
