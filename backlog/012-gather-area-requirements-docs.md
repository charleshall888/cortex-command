---
schema_version: "1"
uuid: 1e372778-b612-4033-b008-c95ec08a12ab
id: 012
title: "Gather area requirements docs for four missing areas"
type: chore
status: backlog
priority: medium
parent: 009
blocked-by: [011]
tags: [requirements, process]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/requirements-audit/research.md
---

# Gather area requirements docs for four missing areas

## Context from discovery

Four feature areas are substantial enough to warrant their own requirements docs but have none. The audit identified these by cross-referencing `requirements/project.md` against the codebase:

- **observability**: statusline, 3 notification channels (macOS/Android/Windows via terminal-notifier and ntfy.sh), FastAPI dashboard (~1800 LOC, 9 HTML templates)
- **remote-access**: tmux skill for session persistence, ntfy.sh push notifications to Android, Tailscale/mosh setup. A `remote/SETUP.md` reference in `docs/setup.md` points to a file that doesn't exist — this area needs formal documentation.
- **multi-agent**: agent spawning patterns, worktree isolation, parallel dispatch with the 3-dimensional model selection matrix (complexity × criticality × phase), PR review with 4-agent parallelism
- **pipeline**: overnight runner, conflict resolution and merge recovery, deferral system, metrics and cost tracking, smoke test gates

These should be gathered using the redesigned `/requirements` skill from ticket 011, so they follow the new area sub-doc format with "when to load" triggers and parent links.

## Scope

- Run `/requirements {area}` for each of the four areas using the updated skill
- Each area doc should follow the new format from ticket 011
- Update `requirements/project.md` area index to link to each new sub-doc (if not already done in ticket 011)
