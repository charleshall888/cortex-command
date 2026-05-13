---
schema_version: "1"
uuid: c5df69bc-ea51-4f85-94b4-bc0dbc72dfb6
id: 207
title: "Rebuild /requirements skill and docs as v2"
type: chore
status: complete
priority: high
parent: 9
blocked-by: []
tags: [requirements, skills, process]
created: 2026-05-12
updated: 2026-05-12
session_id: null
lifecycle_phase: implement
lifecycle_slug: requirements-skill-v2
complexity: complex
criticality: critical
---

# Rebuild /requirements skill and docs as v2

## Context

Epic #009 (Requirements management overhaul, complete 2026-04) established v1: sectioned `project.md`, conditional-loading triggers, four area sub-docs, and a drift check in lifecycle review (#013). After ~5 weeks of use, the user is flagging four ongoing gaps:

- **Token efficiency** — parent doc and always-loaded surfaces are heavier than necessary; progressive disclosure isn't aggressive enough.
- **Skill protocol weakness** — the `/requirements` skill itself doesn't reliably produce well-structured output; no format enforcement, weak re-gather workflow.
- **Agent navigability** — downstream skills (lifecycle, refine, discovery) aren't reliably loading the right area sub-docs at the right moments.
- **Drift / accuracy** — requirements drift continues to accumulate despite the lifecycle-review check from #013.

## Scope

Full v2 rebuild covering all three layers:

1. **`/requirements` skill** (`skills/requirements/SKILL.md`, `references/gather.md`) — protocol redesign, format enforcement, stronger re-gather workflow, drift-aware loop with lifecycle.
2. **Parent doc** (`cortex/requirements/project.md`) — restructure for stronger progressive disclosure, fewer always-loaded tokens, better area-index navigation.
3. **Area sub-docs** (`cortex/requirements/{multi-agent,observability,pipeline,remote-access}.md`) — audit against current code reality, rewrite each via the new skill.

Industry comparison must include `https://github.com/mattpocock/skills` (notably the "grill me" skill) as a primary study target alongside other established patterns (Cursor rules, OpenAI specs, Anthropic skill-authoring guidance).

## Acceptance

- Skill v2 produces parent + area docs that pass a freshly-defined token budget
- Skill includes a re-gather/drift-recovery workflow that closes the loop with lifecycle review
- Parent `project.md` re-written and passes the v2 format
- Each of the 4 area sub-docs audited and rewritten against current code state
- Industry comparison documented in research, including mattpocock/skills "grill me" study
- Backlog item #009 referenced in retrospective as v1 superseded
