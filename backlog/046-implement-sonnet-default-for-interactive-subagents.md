---
schema_version: "1"
uuid: 5da17a6f-62f1-4676-ad09-b7df01da1efa
id: "046"
title: "Implement Sonnet default for interactive subagents"
type: feature
status: backlog
priority: high
parent: "044"
blocked-by: ["045"]
tags: [model-routing, subagents, cost-optimization]
areas: [multi-agent]
created: 2026-04-08
updated: 2026-04-08
session_id: null
lifecycle_phase: null
lifecycle_slug: null
complexity: simple
criticality: high
discovery_source: research/subagent-model-routing/research.md
---

# Implement Sonnet default for interactive subagents

Route non-critical interactive subagents to Sonnet 4.6 by default, preserving Opus for the main chat session and critical implementation tasks.

## Context from discovery

The implementation approach depends on the spike result (backlog #045):

**If per-invocation overrides env var:**
- Set `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` in shell profile (catches all subagents by default)
- Add `model: "opus"` to lifecycle implement Agent() calls for high/critical tasks
- Add model selection guidance to Agents.md (CLAUDE.md)

**If env var overrides per-invocation:**
- Add `model: "sonnet"` to all non-critical skill Agent() calls
- Add `model: "opus"` to lifecycle implement Agent() calls for high/critical tasks
- Add model selection guidance to Agents.md (CLAUDE.md)
- Update `claude/reference/parallel-agents.md` with model selection guidance

## Interactive spawn sites to update

| Location | Current model | Target model |
|----------|--------------|--------------|
| `skills/lifecycle/SKILL.md:345` | inherit (Opus) | sonnet |
| `skills/research/SKILL.md:169` | inherit (Opus) | sonnet |
| `skills/discovery/` (via research skill) | inherit (Opus) | sonnet |
| `skills/critical-review/` | inherit (Opus) | sonnet |
| `skills/lifecycle/references/implement.md:37` | inherit (Opus) | sonnet (low/med) / opus (high/critical) |

## Success criteria

- Non-critical interactive subagents use Sonnet 4.6
- Critical implementation tasks preserve Opus 4.6
- Model selection guidance is documented in Agents.md
