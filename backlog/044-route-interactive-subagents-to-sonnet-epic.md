---
schema_version: "1"
uuid: c63938cd-ba2c-420b-bb8f-b4e2de017301
id: "044"
title: "Route interactive subagents to Sonnet by default"
type: epic
status: complete
priority: high
parent: null
blocked-by: []
tags: [model-routing, subagents, cost-optimization]
areas: [multi-agent]
created: 2026-04-08
updated: 2026-04-08
session_id: null
lifecycle_phase: null
lifecycle_slug: null
complexity: null
criticality: null
discovery_source: research/subagent-model-routing/research.md
---

# Route interactive subagents to Sonnet by default

When the main chat runs on Opus 4.6 1M, all subagents inherit Opus by default. Most interactive subagent tasks (research, exploration, critic review, planning, discovery) don't need the 1M context window or Opus-level reasoning. Routing them to Sonnet 4.6 reduces rate limit pressure, daily usage cap consumption, and reserves Opus capacity for the main chat and critical implementation tasks.

## Context from discovery

Research identified 6 interactive spawn sites across skills that specify no model override. The overnight runner already routes correctly via a complexity x criticality matrix in dispatch.py. The gap is entirely in interactive sessions.

The implementation approach depends on empirically verifying the priority order between `CLAUDE_CODE_SUBAGENT_MODEL` env var and per-invocation `model` params (disputed — see anthropics/claude-code#10993).

## Children

- 045: Verify CLAUDE_CODE_SUBAGENT_MODEL priority order
- 046: Implement Sonnet default for interactive subagents
