---
name: requirements-write
description: Synthesize-only sub-skill that turns a /requirements-gather Q&A block into a v2-compliant cortex/requirements/{project|area}.md; never conducts an interview itself. Invoked by the /cortex-core:requirements orchestrator.
when_to_use: "Use only as a sub-skill of /cortex-core:requirements after /requirements-gather. It synthesizes and writes the doc; gather interviews."
argument-hint: "<scope>"
---

# /requirements-write

Synthesize the Q&A block plus any existing target doc into `cortex/requirements/project.md` or `cortex/requirements/{area}.md`. Return the written path; invoke no further sub-skills.

Preserve existing prose wherever the user's answer confirms it — refine in place, never rewrite from scratch. H2/H3 anchors stay verbatim across rewrites: downstream consumers grep section names. For a section the gather phase collapsed to a confirmed code-derived position, apply the template default. For a missing answer, keep the H2 with a one-line note pointing at Open Questions (area) or a `## Optional` bullet (project). Update `> Last gathered:` to today when any section changes.

## Project template

`# Requirements: {project-name}` + `> Last gathered: {YYYY-MM-DD}`, then these eight H2s in order:

1. `## Overview` — 1–2 paragraph north star; distribution posture if load-bearing.
2. `## Philosophy of Work` — cross-cutting principles, bold-led bullets.
3. `## Architectural Constraints` — strategic constraints only; operational detail lives in CLAUDE.md.
4. `## Quality Attributes` — the non-functional bar.
5. `## Project Boundaries` — H3s `### In Scope`, `### Out of Scope`, `### Deferred`.
6. `## Conditional Loading` — `{trigger phrase} → cortex/requirements/{area}.md` lines; trigger phrases must intersect real lifecycle `index.md` `tags:` words.
7. `## Global Context` — bare paths under `cortex/requirements/` that every consumer loads on every invocation regardless of tag matches. No trigger phrases, no conditional prose. Absent paths are silently skipped, so listing one before its file exists is valid.
8. `## Optional` — prunable; first line states the prunability convention. Token budget ≤1,200 (`cl100k_base`); overflow goes here or into an area doc, never into new top-level H2s.

## Area template

`# Requirements: {area-name}` + `> Last gathered:` + a backlink written verbatim as `**Parent doc**: [requirements/project.md](project.md)`, then seven H2s in order: `## Overview`, `## Functional Requirements` (one H3 per capability, with `**Description**`, `**Inputs**`, `**Outputs**`, nested `**Acceptance criteria**`, `**Priority**`), `## Non-Functional Requirements`, `## Architectural Constraints`, `## Dependencies`, `## Edge Cases` (`**Condition**: behavior`), `## Open Questions` (`- None` when nothing is open).

No token budget. The parent backlink is the only navigation element — area docs carry no "When to Load" prose.

## Acceptance

```bash
cortex-validate-requirements-doc --path {written-path} --scope {project|area}
```

`pass` → return the path. `fail` → `checks` names the failing check (missing canonical H2, over-budget `## Optional`); fix in place and re-run. `file-not-found`/`error` → the doc isn't where expected; resolve before returning.
