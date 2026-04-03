---
schema_version: "1"
uuid: b6c7d8e9-f0a1-2345-bcde-567890123456
id: "031"
title: "Add hover states, loading feedback, and badge micro-interactions"
type: feature
status: backlog
priority: medium
parent: "033"
blocked-by: ["034", "035"]
tags: [dashboard, ui, micro-interactions, ux, animation]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/generative-ui-harness/research.md
---

# Add hover states, loading feedback, and badge micro-interactions

## Context from discovery

The dashboard has no hover states on cards or interactive elements, no loading feedback during HTMX refreshes, and no transitions on status badge changes. These are identified quality gaps against the "operational usefulness" and "information clarity" rubric criteria (ticket 028).

This ticket depends on 027 (clean violation-free baseline in the templates it will modify) and 028 (rubric and CONTEXT.md defining what correct micro-interaction implementation looks like).

## What to produce

**1. Feature card hover states**

Using Tailwind `group` and `group-hover:` modifiers:
- Lift effect: `group-hover:shadow-lg group-hover:-translate-y-1 transition-all duration-200`
- Subtle reveal of secondary actions on hover where applicable
- Use `transform` + `opacity` for GPU-accelerated transitions (not `width`/`height`)

**2. Loading feedback during HTMX refreshes**

Replace silent 5-second polling swaps with visible feedback:
- Shimmer skeleton loader (left-to-right wave, not pulse — perceived ~15% faster per UX research)
- Apply during HTMX swap via `.htmx-swapping` CSS class hook
- Do not animate on every poll cycle — only when content actually changes

**3. Badge status transitions**

For status transitions (pending → running → merged):
- CSS transitions on `background-color`, `border-color`, `color` — 300ms ease-out
- Animate `transform`/`opacity` for smooth entry/exit
- Respect `prefers-reduced-motion` via `motion-safe:` Tailwind prefix

## Constraints

- All new styles must use Tailwind utilities or CSS custom property tokens — no inline `style=` attributes
- Implementation must reference the evaluation rubric from ticket 028 as acceptance criteria
- Hover and transition timing must not conflict with HTMX polling cycles (5s interval)
