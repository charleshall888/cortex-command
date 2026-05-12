---
schema_version: "1"
uuid: a5b6c7d8-e9f0-1234-abcd-456789012345
id: "030"
title: "Investigate and fix swim-lane inline styles and layout degradation"
type: chore
status: complete
priority: medium
parent: "033"
blocked-by: []
tags: [dashboard, ui, swim-lane, css, quality]
created: 2026-04-03
updated: 2026-04-08
discovery_source: cortex/research/generative-ui-harness/research.md
complexity: complex
criticality: medium
spec: cortex/lifecycle/archive/investigate-and-fix-swim-lane-inline-styles-and-layout-degradation/spec.md
areas: [dashboard]
session_id: null
---

# Investigate and fix swim-lane inline styles and layout degradation

## Context from discovery

`swim-lane.html` contains inline `style=` attributes forbidden by DESIGN.md. Unlike `session_panel.html` and `feature_cards.html` (ticket 027), the swim-lane's inline styles likely encode computed positional values derived from template variables (widths as percentages of event durations, position offsets from timestamps). These cannot simply be deleted — they require investigation before any change is made.

Additionally, the swim-lane layout already degrades when many events cluster: overlapping event labels at fixed width, and a "summary mode" that hides tool ticks above 200 events with no user-visible explanation.

This ticket depends on ticket 029 (Playwright toolchain) because DOM-structure assertions provide a regression baseline before touching the fragile layout.

## Investigation first

Before making any changes, answer:
1. Which inline styles are static values that can be replaced with Tailwind utilities?
2. Which inline styles encode data-driven positional values (e.g., `width: {{ pct }}%`)? For these, what is the appropriate alternative — a Jinja-rendered `style=` inside a component class, a scoped `<style>` block, or data attributes consumed by CSS?
3. Is the "summary mode" behavior (hiding tool ticks >200 events) intentional or a workaround? Is its trigger visible to the user?
4. What causes the overlapping event label problem at scale? Is it fixable within the current fixed-width HTML approach, or does it require a different layout strategy?

## Scope boundary

This ticket covers the swim-lane template only. It does not cover swim-lane feature enhancements (those belong in a separate ticket). The goal is DESIGN.md compliance and layout stability, not new functionality.

## Safety net note

Playwright (from ticket 029) can assert DOM structure: inline `style=` attribute absence on elements where static replacement was made, element presence, HTMX settlement after data update. Playwright **cannot** verify temporal ordering correctness of data-driven positional layout. If computed widths or offsets are changed, the correctness of the resulting layout requires manual visual verification against real session data — not just fixture data.
