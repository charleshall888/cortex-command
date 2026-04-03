# Plan: redesign-requirements-skill-and-rewrite-project-md

## Overview

Three sequential content edits across two files. gather.md gets updated format templates and re-gather guidance; requirements/project.md gets a full rewrite applying the new format with all four inaccuracies corrected.

## Tasks

### Task 1: Update gather.md format templates
- **Files**: `skills/requirements/references/gather.md`
- **What**: Replace the project.md artifact format template with the hybrid index structure and update the area sub-doc template to add a parent backlink and remove any "When to Load" placeholder.
- **Depends on**: none
- **Complexity**: simple
- **Context**: gather.md has two format template sections — one for `requirements/project.md` (project-level) and one for `requirements/{area}.md` (area-level). The project.md template currently lists these sections: Overview, Philosophy of Work, Core Feature Areas, Architectural Constraints, Quality Attributes, Project Boundaries, Open Questions. Replace with: `## Overview`, `## Philosophy of Work`, `## Architectural Constraints`, `## Quality Attributes`, `## Project Boundaries`, `## Conditional Loading`. The `## Conditional Loading` section uses a trigger table format: `trigger phrase → path/to/file.md`, one line per area. The area sub-doc template currently has: Area Overview, Functional Requirements, Non-Functional Requirements, Constraints and Dependencies, Acceptance Criteria — with no parent backlink. Add a prose parent backlink as the first element: `**Parent doc**: requirements/project.md`. Do not add any "When to Load" section or `when_to_load` frontmatter — loading guidance belongs in the parent's Conditional Loading table. The `## Conditional Loading` format is documented in `claude/reference/context-file-authoring.md` under "CLAUDE.md Template".
- **Verification**: Open gather.md and confirm: (1) project.md template contains exactly the six sections listed above, does not contain "Core Feature Areas" or "Open Questions"; (2) area template contains "Parent doc:" as its first content element; (3) no "When to Load" or "when_to_load" appears anywhere in either template.
- **Status**: [ ] pending

### Task 2: Add Re-Gather Triggers section to gather.md
- **Files**: `skills/requirements/references/gather.md`
- **What**: Add a `## Re-Gather Triggers` section documenting when to re-run `/requirements` and how to update incrementally without losing coherence.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: This is a new section added to gather.md after the existing interview protocol sections. The section should list these specific trigger conditions (at minimum): (a) lifecycle review identifies drift between implementation and documented requirements, (b) a retro surfaces an assumption that requirements didn't cover, (c) a core architectural decision changes (e.g., file-based state migrates to a database), (d) scope changes significantly after a discovery research epic. For each trigger, note what signals the condition. Also include guidance on incremental updates: run `/requirements` with the `area` argument to update a specific sub-doc without regenerating the full project.md; update only the sections whose claims have changed; cross-check the Conditional Loading table in project.md if area scope has changed.
- **Verification**: grep for "## Re-Gather Triggers" in gather.md returns a match. The section contains at least the four trigger conditions listed above.
- **Status**: [ ] pending

### Task 3: Rewrite requirements/project.md
- **Files**: `requirements/project.md`
- **What**: Full rewrite of project.md applying the hybrid index format, fixing all four inaccuracies, and adding the Conditional Loading trigger table. The resulting document must be ≤80 lines with `## Overview` as the first `##` heading.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  **Six-section structure** (in order): `## Overview`, `## Philosophy of Work`, `## Architectural Constraints`, `## Quality Attributes`, `## Project Boundaries`, `## Conditional Loading`. Sections NOT present in output: `## Core Feature Areas`, `## Open Questions`.
  **Four inaccuracies to fix**: (a) remove "Cursor, Gemini, Copilot get best-effort" from the multi-agent description — this was explicitly removed from the codebase; (b) remove the broken `remote/SETUP.md` reference (that file does not exist); (c) update the multi-agent description to reflect actual implementation: parallel dispatch via the Agent tool, worktree isolation per feature branch, and a three-tier model selection matrix (Haiku for low-cost exploration, Sonnet for standard build/review, Opus for high-criticality phases); (d) add the dashboard (~1800 LOC FastAPI, real-time overnight monitoring) and conflict resolution pipeline (~2500 LOC, classifies and repairs merge conflicts) to the scope description. These currently exist in production but are absent from the document.
  **Conditional Loading table** (last section, four entries — files are placeholders for ticket 012):
  - `Working on statusline, dashboard, or notifications → requirements/observability.md`
  - `Working on pipeline, overnight runner, conflict resolution, or deferral → requirements/pipeline.md`
  - `Working on remote access, tmux, mosh, or Tailscale → requirements/remote-access.md`
  - `Working on agent spawning, parallel dispatch, worktrees, or model selection → requirements/multi-agent.md`
  **Philosophy of Work**: retain all existing sections (Day/Night Split, Handoff Readiness, Failure Handling, Daytime Work Quality, Complexity, Quality Bar) — these are accurate cross-cutting behavioral constraints agents need.
  **## Overview heading**: must remain the first `##` heading. `critical-review/SKILL.md` extracts this section by name for reviewer prompts.
- **Verification**: (1) `grep "^## Overview" requirements/project.md` returns a match as the first `##` heading; (2) `wc -l requirements/project.md` returns ≤80; (3) `grep "Cursor\|Gemini\|remote/SETUP" requirements/project.md` returns no match; (4) `grep "## Conditional Loading" requirements/project.md` returns a match; (5) `grep "## Core Feature Areas\|## Open Questions" requirements/project.md` returns no match; (6) all four area trigger entries are present.
- **Status**: [ ] pending

## Verification Strategy

After all tasks complete: (1) run `just test` to confirm no test regressions; (2) invoke `/requirements` on a test feature and confirm the agent follows the new gather.md format (produces hybrid index with Conditional Loading table, no "When to Load" in any area sub-doc template); (3) read requirements/project.md and verify it reads coherently as a project-level index — no orphaned references, trigger table entries are well-formed, line count ≤80.
