---
schema_version: "1"
uuid: 2d0b25a4-90be-407a-9121-117b72b302d5
id: "045"
title: "Verify CLAUDE_CODE_SUBAGENT_MODEL priority order"
type: spike
status: complete
priority: high
parent: "044"
blocked-by: []
tags: [model-routing, subagents, cost-optimization]
areas: [multi-agent]
created: 2026-04-08
updated: 2026-04-08
session_id: null
lifecycle_phase: complete
lifecycle_slug: verify-subagent-model-env-var-priority
complexity: simple
criticality: high
discovery_source: cortex/research/subagent-model-routing/research.md
---

# Verify CLAUDE_CODE_SUBAGENT_MODEL priority order

Empirically determine whether `CLAUDE_CODE_SUBAGENT_MODEL` env var overrides or is overridden by per-invocation `Agent(model: ...)` params.

## Context from discovery

The documented priority order is disputed across multiple sources. Some say env var wins (highest priority); others say per-invocation overrides env var (conventional software pattern). GitHub issue anthropics/claude-code#10993 was filed specifically about this ambiguity and closed without resolution.

## Test procedure

1. Set `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` in the environment
2. Spawn an agent with `Agent(model: "opus", ...)`
3. Have the agent report which model it is running as
4. Record the result in the research artifact

## Success criteria

- The priority order is empirically determined
- The result is documented in `research/subagent-model-routing/research.md`
- The recommendation in DR-1 is updated to reflect the verified priority order
