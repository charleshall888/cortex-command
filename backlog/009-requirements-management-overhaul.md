---
schema_version: "1"
uuid: dadaf6b6-431d-4c5a-92b5-6226be90d26b
id: 009
title: "Requirements management overhaul"
type: epic
status: complete
priority: high
tags: [requirements, skills, process]
created: 2026-04-03
updated: 2026-04-03
discovery_source: cortex/research/requirements-audit/research.md
---

# Requirements management overhaul

Overhaul the requirements skill, document format, and maintenance process based on an audit revealing inaccuracies in project.md, four missing area docs, a skill sub-file path bug, and no mechanism to keep requirements accurate after features are built.

## Context from discovery

Full research: `research/requirements-audit/research.md`

Key findings:
- `requirements/project.md` has four specific inaccuracies (stale Cursor/Gemini claim, broken remote/SETUP.md reference, understated multi-agent implementation, missing dashboard and pipeline subsystems)
- Four area docs are missing: observability, remote-access, multi-agent, pipeline
- All skills with sub-files have a path bug: relative links break when invoked outside cortex-command's CWD
- The `/requirements` skill has no re-gather guidance and no format enforcement for the parent doc
- The lifecycle review phase has no required output for requirements drift — drift accumulates silently

## Children

- 010: Fix skill sub-file path bug
- 011: Redesign /requirements skill and rewrite project.md
- 012: Gather area requirements docs
- 013: Wire requirements drift check into lifecycle review
