# Research: redesign-requirements-skill-and-rewrite-project-md

## Epic Reference

This ticket is scoped from the requirements-audit epic. Background context: `research/requirements-audit/research.md`. That document covers accuracy audit of project.md, area doc design, skill defects, and feasibility assessment for approaches A/B/C. This ticket implements Approach B (restructure + skill update) for the skill and project.md only; area doc creation is ticket 012.

---

## Codebase Analysis

### Files to modify

| File | Change |
|---|---|
| `skills/requirements/references/gather.md` | Update parent-doc artifact format template; update area sub-doc format template; add re-gather guidance section |
| `requirements/project.md` | Fix four inaccuracies; restructure to hybrid index (~50–70 lines); add `## Conditional Loading` trigger table |
| `skills/requirements/SKILL.md` | Minor: no format changes needed — the skill's step flow already references gather.md for format. Only update if the skill's own prose references the old format. |

### Files NOT in scope

- `skills/lifecycle/references/review.md` — has a requirements compliance check but no drift output field. The epic research DR-3 recommends adding `requirements_drift` as a required review output; this is **not in 011's scope** — it is a follow-on change.
- All other lifecycle/discovery references that read `requirements/` — they load the files; the content format change is transparent to them.

### Current gather.md format templates

The current templates in `gather.md` produce:

**project.md template** (current): Full prose sections — Overview, Philosophy, Core Feature Areas, Architectural Constraints, Quality Attributes, Project Boundaries, Open Questions. No format constraints on length. No area index section. No conditional loading guidance.

**area.md template** (current): Area Overview, Functional Requirements, Non-Functional Requirements, Constraints and Dependencies, Acceptance Criteria. No backlink to parent. No "When to Load" guidance.

### Target format: hybrid index for project.md

Per `claude/reference/context-file-authoring.md` CLAUDE.md Template pattern:
- Core file ~50–70 lines, always loaded
- Sections: overview, cross-cutting invariants (constraints, quality attributes, philosophy), conditional loading trigger table
- `## Conditional Loading` format: `trigger phrase → path/to/file.md`

The current project.md is 107 lines. The restructure removes area-specific content (which moves to area sub-docs) and adds a trigger table. Target: ~60 lines.

### Target format: area sub-docs

Per design decision from Clarify (grounded in context-file-authoring.md progressive disclosure pattern):
- NO "When to Load" section in the sub-doc itself — loading guidance lives in the parent trigger table
- Minimal frontmatter: `parent: requirements/project.md` (backlink only)
- Content sections follow the existing area-level interview format from gather.md
- gather.md area template needs to add the backlink frontmatter and remove any "When to Load" placeholder

### Re-gather guidance

The current gather.md has no section on when to re-run. Target: a `## Re-Gather Triggers` section in gather.md listing conditions (lifecycle review identifies drift, retro identifies unmet assumption, model selection / core arch changes, scope change post-discovery) and how to update incrementally without losing coherence.

### Integration: skills that consume requirements/

Many skills read `requirements/` — clarify, research, specify, review, discovery auto-scan, prime, critical-review, the requirements skill itself. All of them read the files and extract content. The format change (shorter parent doc, trigger table added) does not break any of these — they read prose and extract intent. The trigger table entries are short prose lines that add signal, not noise.

The one risk: `skills/critical-review/SKILL.md` reads project.md and extracts the `## Overview` section specifically. If we rename that section, the extraction fails. Keep `## Overview` as the first section heading.

### project.md: specific inaccuracies to fix

1. Remove "Cursor, Gemini, Copilot get best-effort" from Multi-agent description — git commit explicitly removed Cursor/Gemini support
2. Fix broken `remote/SETUP.md` reference — file doesn't exist; reference should be removed or updated to `docs/setup.md`
3. Update multi-agent description to reflect actual implementation: worktree isolation, parallel dispatch, 3D model selection matrix, PR review with 4 parallel agents
4. Add dashboard and conflict resolution pipeline to subsystem descriptions (in the area trigger table entries)

### project.md: conditional loading trigger table entries

The four areas from epic research:
```
Working on statusline, dashboard, or notifications → requirements/observability.md
Working on pipeline, overnight runner, conflict resolution, or deferral → requirements/pipeline.md
Working on remote access, tmux, mosh, or Tailscale → requirements/remote-access.md
Working on agent spawning, parallel dispatch, worktrees, or model selection → requirements/multi-agent.md
```

These entries go in project.md as placeholders; actual files created by ticket 012.

---

## Open Questions

- Should `skills/lifecycle/references/review.md` be updated to add a `requirements_drift` structured output field as a required review deliverable (per epic research DR-3)? Deferred — out of 011's stated scope. Recommend as a follow-on ticket after 012 ships area docs, when the full requirements structure exists to drift against.
