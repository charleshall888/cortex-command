# Specification: redesign-requirements-skill-and-rewrite-project-md

## Problem Statement

The `/requirements` skill currently produces a flat, unconstrained document with no format enforcement, no area index, and no re-gather guidance. `requirements/project.md` was first gathered 2026-04-01 and already has four concrete inaccuracies plus omits the dashboard, conflict resolution pipeline, deferral system, and model selection tier — all production subsystems. As the project grows, a single flat parent doc will accumulate area-specific detail that belongs in sub-docs, making it harder for agents to load relevant context efficiently. This ticket fixes the immediate accuracy problems and introduces the format conventions that keep project.md coherent long-term: a hybrid index (cross-cutting content + conditional loading trigger table) and a clean area sub-doc template with parent backlink and no loading guidance in the sub-doc itself.

## Requirements

1. **gather.md: update parent-doc artifact format template**: The template for `requirements/project.md` produced by `/requirements` must change from an unconstrained flat document to a hybrid index format with these sections in order: `## Overview`, `## Philosophy of Work`, `## Architectural Constraints`, `## Quality Attributes`, `## Project Boundaries`, `## Conditional Loading`. Target length ~70–80 lines. Acceptance: the template in gather.md matches this section structure, and `## Conditional Loading` is defined as a trigger table (`trigger phrase → path/to/file.md`).

2. **gather.md: update area sub-doc artifact format template**: The template for `requirements/{area}.md` must add a parent backlink as the first element and must NOT include a "When to Load" section. Acceptance: the area template starts with a prose "**Parent doc**: requirements/project.md" line (or equivalent) followed by the content sections; there is no "When to Load" or "when_to_load" field anywhere in the template.

3. **gather.md: add re-gather guidance**: A new `## Re-Gather Triggers` section must be added to gather.md listing the conditions under which `/requirements` should be re-run and how to update incrementally without losing coherence. Acceptance: the section exists and lists at minimum: lifecycle review identifies drift, retro surfaces unmet assumption, core architectural decisions change, scope changes after discovery research.

4. **project.md: fix four inaccuracies**: (a) Remove "Cursor, Gemini, Copilot get best-effort" from the multi-agent description. (b) Remove the broken `remote/SETUP.md` reference (the file does not exist). (c) Update the multi-agent description to reflect actual implementation: worktree isolation, parallel dispatch, model selection matrix (Haiku/Sonnet/Opus by phase and criticality). (d) Add the dashboard and conflict resolution pipeline to the project scope description. Acceptance: none of the four stale claims appear in the updated project.md; the four updated descriptions appear instead.

5. **project.md: restructure to hybrid index format**: project.md must be reorganized to the section structure defined in Requirement 1, with Philosophy of Work retained inline as cross-cutting content. The `## Core Feature Areas` section is removed; its content either becomes brief inline notes in the overview or is replaced by the `## Conditional Loading` trigger table entries. `## Open Questions` is removed — open questions belong in planning/backlog artifacts, not the requirements doc. Acceptance: project.md has the six sections from Requirement 1 and no others; `## Core Feature Areas` and `## Open Questions` do not appear; total line count is ≤80.

6. **project.md: add Conditional Loading trigger table**: A `## Conditional Loading` section must be added as the last section of project.md with trigger table entries for all four area docs. Entries must follow the format `trigger phrase → path/to/area.md`. The four area docs (observability, pipeline, remote-access, multi-agent) are placeholder entries — the files will be created by ticket 012. Acceptance: all four trigger entries are present; each entry has a trigger phrase and a path; the paths point to `requirements/{area}.md`; the files need not exist yet.

7. **`## Overview` section is preserved as the first H2**: `critical-review/SKILL.md` extracts the `## Overview` section by name from project.md for reviewer context prompts. This section heading must remain the first H2 after any frontmatter. Acceptance: `grep "^## Overview" requirements/project.md` returns a match as the first `##` heading.

## Non-Requirements

- This ticket does NOT create the four area sub-doc files (`requirements/observability.md`, etc.) — that is ticket 012.
- This ticket does NOT add a `requirements_drift` structured output field to the lifecycle review phase — that is a follow-on ticket.
- No skills other than `skills/requirements/` are modified. The SKILL.md entry point does not need changes (it delegates format to gather.md).
- No changes to how consuming skills (lifecycle, discovery, critical-review, prime) load requirements files — they continue to read files via explicit Read calls.

## Edge Cases

- **critical-review extraction breaks if `## Overview` is renamed**: `critical-review/SKILL.md` reads project.md and extracts `## Overview` by heading name. If this heading is renamed or removed, critical-review will silently produce reviewer prompts without project context. Mitigation: Requirement 7 enforces retention.
- **Area trigger entries point to non-existent files**: The conditional loading trigger table will reference `requirements/observability.md` etc. before ticket 012 creates them. Agents following the trigger guidance will get a "file not found" if they attempt to Read the linked file. Acceptable: the trigger table is advisory; the missing files are a known transitional state pending ticket 012.
- **gather.md format change doesn't affect existing project.md**: gather.md defines the format for *new* documents produced by `/requirements`. The rewrite of `requirements/project.md` in this ticket is a one-time manual update following the new format; gather.md format changes do not automatically update existing docs.

## Technical Constraints

- `requirements/project.md` must preserve `## Overview` as the first `##` heading — consumed by name in `critical-review/SKILL.md`.
- gather.md area sub-doc template must not include "When to Load" content in the sub-doc — loading guidance belongs in the parent's `## Conditional Loading` trigger table, per the progressive disclosure pattern in `claude/reference/context-file-authoring.md`.
- The `## Conditional Loading` trigger table format follows the CLAUDE.md Template from `claude/reference/context-file-authoring.md`: `trigger phrase → path/to/file.md`, one entry per line.
- project.md line count target is ≤80 lines (flexed from the 50–70 line design target to preserve the Philosophy of Work sections, which are cross-cutting behavioral context agents need).
