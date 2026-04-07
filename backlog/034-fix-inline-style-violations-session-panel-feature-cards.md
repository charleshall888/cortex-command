---
schema_version: "1"
uuid: d2e3f4a5-b6c7-8901-defa-123456789012
id: "034"
title: "Fix inline style violations in session_panel and feature_cards templates"
type: chore
status: in_progress
priority: high
parent: "033"
blocked-by: []
tags: [dashboard, ui, quality, css]
created: 2026-04-03
updated: 2026-04-07
discovery_source: research/generative-ui-harness/research.md
complexity: simple
criticality: medium
spec: lifecycle/fix-inline-style-violations-in-session-panel-and-feature-cards-templates/spec.md
areas: [dashboard]
session_id: null
---

# Fix inline style violations in session_panel and feature_cards templates

## Context from discovery

The dashboard's `DESIGN.md` explicitly forbids inline `style=` attributes — all styling must use Tailwind utilities or CSS custom property token classes. Codebase analysis found confirmed violations in `session_panel.html` and `feature_cards.html`.

This ticket is scoped to these two templates only. The swim-lane is intentionally excluded: it likely uses data-driven positional values (widths as percentages of event durations, offsets from timestamps) that cannot simply be deleted — that work is ticket 030, which requires Playwright tooling first.

## Findings

- `session_panel.html`: inline `style=` attributes present; investigate before removing (may be static or data-driven)
- `feature_cards.html`: inline `style=` attributes present; investigate before removing

## Scope boundary

Before removing any inline style, verify:
1. Is the value static (can be replaced with a Tailwind utility or token class)?
2. Is the value data-driven (computed from template variables)? If so, it requires a different approach — do not remove and break the layout. Surface as a follow-on concern, not a blocker for this ticket.

This ticket is a prerequisite for ticket 031 (hover states), which must build on a violation-free baseline.
