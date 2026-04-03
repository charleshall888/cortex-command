---
schema_version: "1"
uuid: 23658633-f99e-4bfc-8da4-bff5e4f533c1
id: 011
title: "Redesign /requirements skill and rewrite project.md"
type: chore
status: backlog
priority: high
parent: 009
blocked-by: []
tags: [requirements, skills, process]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/requirements-audit/research.md
---

# Redesign /requirements skill and rewrite project.md

## Context from discovery

The current `/requirements` skill produces a single flat document with no format enforcement, no re-gather guidance, and no "when to load" guidance for area sub-docs. Research shows that effective machine-consumed requirements docs use a hybrid parent format: project-wide invariants + an area index with explicit load triggers, targeting 50–70 lines. Area-specific detail belongs in sub-docs.

`requirements/project.md` has four concrete inaccuracies and omits the dashboard, conflict resolution pipeline, deferral system, and model selection tier system — all substantial production subsystems. It was first gathered 2026-04-01 and some claims are already stale.

The restructure's primary value is navigation and maintenance: a thin parent doc stays coherent as the project grows; area sub-docs give lifecycle/discovery better-scoped context when working in a specific area. Prose "when to load" triggers in the parent index are advisory (Claude Code has no native conditional loading), but they reliably orient agents toward the right sub-doc.

## Scope

**Skill redesign (`skills/requirements/`):**
- Update `gather.md` artifact format: parent doc as hybrid index (50–70 lines: overview + cross-cutting invariants + area index with "when to load" triggers per entry)
- Update area sub-doc format: add "when to load" trigger in frontmatter/header; link back to parent
- Add re-gather guidance: when to re-run, what signals trigger an update, how to update without losing coherence

**Rewrite `requirements/project.md`:**
- Fix inaccuracies: remove Cursor/Gemini claim, fix broken remote/SETUP.md reference, update multi-agent description, add dashboard and pipeline subsystems to scope
- Restructure to hybrid index format per the new skill design
- Add area index section linking to the four area docs created in ticket 012
