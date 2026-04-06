---
schema_version: "1"
uuid: c1d2e3f4-a5b6-7890-cdef-012345678901
id: "033"
title: "Establish dashboard UI quality baseline"
type: epic
status: backlog
priority: high
blocked-by: []
tags: [dashboard, ui, quality, epic]
created: 2026-04-03
updated: 2026-04-06
discovery_source: research/generative-ui-harness/research.md
---

# Establish dashboard UI quality baseline

Research into Anthropic's generative UI harness identified that the dashboard lacks visual evaluation tooling and defined quality criteria. The article's evaluator uses Playwright MCP to navigate and screenshot running UI, with Claude's vision evaluating quality — not programmatic DOM assertions.

The full research is at `research/generative-ui-harness/research.md`.

## Child tickets

- 034 — Fix inline style violations in session_panel and feature_cards templates
- 035 — Add dashboard visual evaluation criteria to DESIGN.md
- 029 — Add Playwright MCP for dashboard visual evaluation
- 030 — Investigate and fix swim-lane inline styles and layout degradation
- 031 — Add hover states, loading feedback, and badge micro-interactions
- 032 — Add accessibility foundations (aria-live, multi-modal severity)

## Wave structure

- Wave 1: 034, 035, 029 (no dependencies between them)
- Wave 2: 030, 031, 032 (030 depends on 029; 031 depends on 034; 032 has no blockers but benefits from 029 for visual verification)
