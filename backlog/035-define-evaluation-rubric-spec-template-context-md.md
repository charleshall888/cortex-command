---
schema_version: "1"
uuid: e3f4a5b6-c7d8-9012-efab-234567890123
id: "035"
title: "Define evaluation rubric, update lifecycle spec template, create dashboard/CONTEXT.md"
type: chore
status: backlog
priority: high
parent: "033"
blocked-by: []
tags: [dashboard, ui, quality, rubric, context-engineering, lifecycle]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/generative-ui-harness/research.md
---

# Define evaluation rubric, update lifecycle spec template, create dashboard/CONTEXT.md

## Context from discovery

Research into Anthropic's harness design article identified that the dashboard lacks any defined quality criteria for UI work. The research artifact (`research/generative-ui-harness/research.md`, sections DR-4 and RQ3) already provides the rubric draft. This ticket formalizes it into two referenceable locations.

## Rubric (from research DR-4)

Four adapted criteria and their Playwright-verifiability:

| Criterion | Weight | Playwright-verifiable? |
|-----------|--------|----------------------|
| Information clarity | High | No — perceptual judgment |
| Consistency | High | Partially — inline `style=` attribute absence, element presence |
| Operational usefulness | Medium | No — perceptual + workflow judgment |
| Purposefulness | Low | No — entirely perceptual |

Only "consistency" can be partially automated. The other three require human review.

## What to produce

**1. Lifecycle spec template update**

Add a dashboard-feature section to the lifecycle spec template (or a dashboard-specific lifecycle config override) requiring:
- Explicit acceptance criteria for each of the four rubric dimensions
- Browser-level verifiable behaviors listed as a checklist (element selectors, HTMX swap behavior, no inline `style=` on new elements)
- Clear distinction between Playwright-checkable criteria and human-review criteria

**2. `claude/dashboard/CONTEXT.md`** (~300 words)

Right-altitude implementation guidance for agents working on dashboard features. Based on the context engineering research, this should cover:
- Multi-file coordination rules (app.py → data.py → templates → base.html)
- JIT retrieval sequence: read task spec → read one relevant parser function → read reference template → read patterns/ → read DESIGN.md excerpt only as needed
- Forbidden patterns: raw hex colors, inline `style=` attributes, arbitrary spacing values
- Tool scope: Glob bounded to `templates/` and `claude/dashboard/`, no root-level wildcards
- Reference to evaluation rubric above

This ticket is a prerequisite for tickets 029, 031, and 032.
