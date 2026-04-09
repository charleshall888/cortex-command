---
id: 49
title: Improve agent output signal-to-noise ratio
status: ready
priority: medium
type: epic
tags: [output-efficiency, context-management, multi-agent]
created: 2026-04-09
updated: 2026-04-09
discovery_source: research/agent-output-efficiency/research.md
---

# Improve agent output signal-to-noise ratio

## Context from discovery

The harness's skill prompts override Claude Code's built-in output efficiency instructions ("be extra concise") with verbose output requirements — unconstrained subagent dispatch, multi-sentence phase transition summaries, synthesis skills that reproduce all intermediate findings. Anthropic's context engineering guidance says subagent dispatch prompts need "an objective, an output format, guidance on tools, and clear task boundaries" — most harness skills provide none of these for output.

The same output text serves multiple consumers with incompatible requirements: interactive users need enough to approve without reading full artifacts; overnight agents need output that survives 12% compaction retention for morning review. Any compression must respect both floors.

## Children

- #050 — Define output floors for interactive approval and overnight compaction
- #051 — Add hook-based preprocessing for test/build output
- #052 — Audit skill prompts and remove verbose instructions above the floor
- #053 — Add subagent output format specs and compress synthesis
