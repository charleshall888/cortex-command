---
schema_version: "1"
uuid: 1bc38be0-1b0e-4c5f-9757-5df413d37b44
title: "Extract /backlog pick ready-set into bin/backlog-ready"
status: backlog
priority: medium
type: feature
parent: "101"
blocked-by: []
tags: [harness, scripts, backlog]
created: 2026-04-21
updated: 2026-04-28
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
---

# Extract /backlog pick ready-set into bin/backlog-ready (C7)

## Context from discovery

`/backlog pick` (`skills/backlog/SKILL.md:82-94`) filters `index.json` for ready items (status unblocked), sorts by priority, and renders a selection table. Filter + sort + render is mechanical; the selection itself is agent judgment (judgment-at-endpoints).

## Research context

- C7 in `research/extract-scripts-from-agent-tool-sequences/research.md`.
- Heat: warm.

## Scope

- New `bin/cortex-backlog-ready` emitting priority-grouped ready items as JSON.
- Top-level `bin/cortex-backlog-ready` is source-of-truth; `just build-plugin` ships it via `plugins/cortex-interactive/bin/`.
- Update `skills/backlog/SKILL.md` pick flow to invoke the script.

## Out of scope

- Changes to the selection UX (agent still renders options and asks the user).
