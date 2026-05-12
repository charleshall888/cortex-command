---
schema_version: "1"
uuid: b6c7d8e9-f0a1-2345-bcde-567890123456
id: "031"
title: "Add hover states, loading feedback, and badge micro-interactions"
type: feature
status: complete
priority: medium
parent: "033"
blocked-by: []
tags: [dashboard, ui, micro-interactions, ux, animation]
created: 2026-04-03
updated: 2026-04-08
discovery_source: cortex/research/generative-ui-harness/research.md
complexity: complex
criticality: low
spec: cortex/lifecycle/archive/add-hover-states-loading-feedback-and-badge-micro-interactions/spec.md
areas: [dashboard]
session_id: null
---

# Add hover states, loading feedback, and badge micro-interactions

## Context from discovery

The dashboard has no hover states on cards or interactive elements, no loading feedback during HTMX refreshes, and no transitions on status badge changes. These are quality gaps against the "operational usefulness" and "information clarity" evaluation criteria in DESIGN.md.

This ticket depends on 034 (clean violation-free baseline in the templates it will modify).

## What to produce

**1. Feature card hover states**

Cards should respond to hover with a subtle visual lift or highlight, indicating interactivity. The implementing agent should choose the approach that works best with the existing template structure and DESIGN.md token system.

**2. Loading feedback during HTMX refreshes**

Content updates from HTMX polling should provide visual feedback when content changes, rather than silently swapping. Only show feedback when content actually changes — not on every 5-second poll cycle.

**3. Badge status transitions**

Status badge changes (pending → running → merged) should animate smoothly rather than snapping instantly. Respect `prefers-reduced-motion` for accessibility.

## Constraints

- All new styles must use Tailwind utilities or CSS custom property tokens — no inline `style=` attributes
- Follow DESIGN.md guidelines and visual evaluation criteria
- Hover and transition timing must not conflict with HTMX polling cycles (5s interval)
