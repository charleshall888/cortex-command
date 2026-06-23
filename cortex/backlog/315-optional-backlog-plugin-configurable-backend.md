---
schema_version: "1"
uuid: 532c410b-96d9-467c-8569-65ed7f3e4033
title: Optional backlog plugin + configurable backend
status: backlog
priority: high
type: epic
created: 2026-06-23
updated: 2026-06-23
tags: ['backlog-optional-plugin']
discovery_source: cortex/research/backlog-optional-plugin/research.md
---
## Why

The backlog is hard-wired into the harness: every consumer reads local `cortex/backlog/` files and the management skills ship inside cortex-core, so a team that lives in GitHub Issues or Jira cannot adopt the harness without also adopting its backlog. Prospective users have asked to keep their own tracker.

## Role

Make the backlog an optional, backend-configurable capability. The local backlog becomes an installable plugin, and a single config field tells every consumer which tracker is active — the local engine, an external tracker driven best-effort by the LLM, or none. This epic is the parent of three children that each ship an independently-valuable slice: the optional plugin, the configurable backend with local/none routing and overnight safety, and the external best-effort arm.

## Integration

The work spans the plugin/build distribution surface, the cortex init config, and the backlog consumers (lifecycle, discovery, refine, dev, morning-review, overnight). Consumers route through a new config-resolution seam rather than reading the local backlog directly. The authoritative design and the full ten-piece analysis live in the discovery research artifact, which the lifecycle plan phase consumes to break each child into phases.

## Edges

- Deliberate scope wall: no per-tracker code adapters are built — external trackers are driven by user-authored prose plus the LLM's judgment.
- The backlog engine stays in the wheel; "optional" means the interactive management surface and the active-backend selection, not removal of the engine or its consumers' default behavior.
- Overnight remains local-backlog-only and must never write to an external tracker.
- Config is the source of truth for the active backend; an absent config block resolves to the local backend so existing repos are unchanged.

## Touch points

- cortex/requirements/backlog.md (authoritative spec)
- cortex/research/backlog-optional-plugin/research.md (ten-piece analysis and sequencing)