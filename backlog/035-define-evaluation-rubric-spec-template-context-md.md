---
schema_version: "1"
uuid: e3f4a5b6-c7d8-9012-efab-234567890123
id: "035"
title: "Add dashboard visual evaluation criteria to DESIGN.md"
type: chore
status: complete
priority: medium
parent: "033"
blocked-by: []
tags: [dashboard, ui, quality, evaluation]
created: 2026-04-03
updated: 2026-04-08
discovery_source: research/generative-ui-harness/research.md
complexity: simple
criticality: low
spec: lifecycle/archive/add-dashboard-visual-evaluation-criteria-to-designmd/spec.md
areas: [dashboard]
session_id: null
---

# Add dashboard visual evaluation criteria to DESIGN.md

## Context

Research into Anthropic's harness design article identified that the dashboard lacks defined quality criteria for UI work. The existing DESIGN.md covers design tokens, composition rules, and forbidden patterns, but does not define what "good" looks like at a higher level.

The article's evaluator uses Playwright to screenshot running UI and Claude's vision to evaluate it. All four quality criteria are Claude-vision-evaluable — the original research's conclusion that 3 of 4 require "human review" was based on treating Playwright as a DOM assertion tool rather than as eyes for Claude.

## What to produce

Add a `## Visual Evaluation Criteria` section to `cortex_command/dashboard/DESIGN.md` with four quality dimensions adapted from the Anthropic harness rubric:

| Criterion | Weight | What to evaluate via screenshots |
|-----------|--------|--------------------------------|
| Information clarity | High | Status hierarchy visually distinct, feature status scannable at a glance, operational state readable without studying labels |
| Consistency | High | Design tokens used throughout, no visual evidence of inline styles, no mixed styling patterns, forbidden patterns absent |
| Operational usefulness | Medium | Alerts prominent, swim-lane conveys temporal ordering, HTMX refresh produces no visible flicker, session history supports morning review |
| Purposefulness | Low | Looks like a purpose-built monitoring tool, not a generic admin panel |

Include brief guidance on how these criteria should be applied — during visual evaluation with Playwright MCP (ticket 029), as review criteria for dashboard PRs, or as acceptance criteria in dashboard feature specs.

## What NOT to produce

- No lifecycle spec template modifications — evaluation criteria live in DESIGN.md alongside existing design rules
- No separate CONTEXT.md — DESIGN.md is the single source of truth for dashboard design guidance
- No process gates or rubric infrastructure — these are reference criteria, not automation
