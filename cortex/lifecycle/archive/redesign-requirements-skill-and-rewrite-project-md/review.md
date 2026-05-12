# Review: redesign-requirements-skill-and-rewrite-project-md

## Stage 1: Spec Compliance

### Requirement 1: gather.md parent-doc template updated to hybrid index format
- **Expected**: Template has sections in order: Overview, {optional cross-cutting}, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading. Conditional Loading defined as trigger table (trigger phrase -> path).
- **Actual**: Template (lines 158-190) has exactly this structure: `## Overview`, `## {Optional: project-specific cross-cutting sections}`, `## Architectural Constraints`, `## Quality Attributes`, `## Project Boundaries`, `## Conditional Loading`. The Conditional Loading section uses `{trigger phrase} -> requirements/{area}.md` format. The cross-cutting section is generalized from "Philosophy of Work" to an optional placeholder -- correct for a reusable template.
- **Verdict**: PASS

### Requirement 2: gather.md area sub-doc template has parent backlink, no "When to Load"
- **Expected**: Area template starts with `**Parent doc**: requirements/project.md` (or equivalent) as first element. No "When to Load" or "when_to_load" anywhere in the template.
- **Actual**: Area template (lines 196-233) starts with `**Parent doc**: [requirements/project.md](project.md)` immediately after the date line. The only mention of "When to Load" in the entire file is on line 194, which is instructional text explaining that area sub-docs do NOT contain it. No `when_to_load` field exists anywhere.
- **Verdict**: PASS

### Requirement 3: gather.md has Re-Gather Triggers section with at least 4 triggers
- **Expected**: `## Re-Gather Triggers` section exists with at minimum: lifecycle review identifies drift, retro surfaces unmet assumption, core architectural decisions change, scope changes after discovery research.
- **Actual**: Section exists at line 135 with 5 triggers: (1) lifecycle review identifies drift, (2) retro surfaces unmet assumption, (3) core architectural decision changes, (4) scope changes after discovery research, (5) open questions now have answers. Also includes incremental update guidance (4 steps).
- **Verdict**: PASS

### Requirement 4: project.md four inaccuracies fixed
- **Expected**: (a) No "Cursor, Gemini, Copilot" claim, (b) no `remote/SETUP.md` reference, (c) multi-agent reflects worktree isolation + parallel dispatch + model selection matrix, (d) dashboard and conflict pipeline in scope.
- **Actual**: (a) grep for "Cursor" and "Gemini" returns no matches. (b) grep for "remote/SETUP" returns no matches. (c) Line 43 reads: "Multi-agent orchestration: parallel dispatch, worktree isolation, Haiku/Sonnet/Opus model selection matrix". (d) Lines 39-40: "Dashboard (~1800 LOC FastAPI): real-time web monitoring of overnight sessions" and "Conflict resolution pipeline (~2500 LOC): classifies conflicts, dispatches repair agents, retries merges".
- **Verdict**: PASS

### Requirement 5: project.md restructured to 6-section hybrid format, no Core Feature Areas or Open Questions, <=80 lines
- **Expected**: Six sections: Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading. No Core Feature Areas or Open Questions. Line count <=80.
- **Actual**: Exactly six `##` headings in order: Overview (line 5), Philosophy of Work (line 9), Architectural Constraints (line 23), Quality Attributes (line 27), Project Boundaries (line 33), Conditional Loading (line 58). No "Core Feature Areas" or "Open Questions" headings. Line count: 63 (well under 80).
- **Verdict**: PASS

### Requirement 6: project.md Conditional Loading table has 4 entries for area docs
- **Expected**: Four trigger entries with format `trigger phrase -> requirements/{area}.md` for observability, pipeline, remote-access, multi-agent.
- **Actual**: Lines 60-63 contain exactly four entries: observability.md, pipeline.md, remote-access.md, multi-agent.md. Each has a descriptive trigger phrase and arrow-separated path.
- **Verdict**: PASS

### Requirement 7: `## Overview` is the first H2 in project.md
- **Expected**: `grep "^## Overview" requirements/project.md` returns a match as the first `##` heading.
- **Actual**: First `##` heading is `## Overview` on line 5. No other `##` heading precedes it.
- **Verdict**: PASS

## Requirements Compliance

- **File-based state constraint**: No violations -- all changes are to markdown files, no database or server introduced.
- **Symlink architecture**: Both changed files are repo copies (not symlink destinations). Correct.
- **Context-file-authoring.md conventions**: The Conditional Loading trigger table format (`trigger phrase -> path`) matches the CLAUDE.md Template pattern from context-file-authoring.md. The progressive disclosure structure is preserved -- project.md is a concise always-loaded index pointing to area sub-docs.
- **Non-requirements respected**: No area sub-doc files created (deferred to ticket 012). No changes to consuming skills. No SKILL.md changes.

## Stage 2: Code Quality

- **Naming conventions**: Section headings (`## Overview`, `## Conditional Loading`, etc.) are consistent with existing project patterns in CLAUDE.md and context-file-authoring.md. Area doc paths use kebab-case (`remote-access.md`, `multi-agent.md`) -- consistent with existing file naming.
- **Pattern consistency**: The trigger table format matches context-file-authoring.md's CLAUDE.md Template. The parent backlink in the area template uses a relative markdown link `[requirements/project.md](project.md)` -- reasonable for co-located files. The gather.md interview protocol sections maintain the existing numbered-section approach. The Re-Gather Triggers section follows the same bold-label-then-explanation pattern used elsewhere in gather.md.
- **Completeness**: All spec requirements are addressed. The gather.md interview protocol was updated to align with the new format (Section 2 "Feature Areas" now references the Conditional Loading table instead of an inline feature list). The instructional note on line 194 clarifying that area sub-docs do not contain "When to Load" is a helpful guardrail.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": []}
```
