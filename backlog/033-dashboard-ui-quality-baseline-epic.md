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
updated: 2026-04-03
discovery_source: research/generative-ui-harness/research.md
---

# Establish dashboard UI quality baseline

Research into Anthropic's generative UI harness identified concrete gaps in the dashboard's current quality posture: inline style violations against DESIGN.md rules, no hover states or loading feedback, no accessibility foundations (aria-live regions, multi-modal severity), no Playwright-level evaluation tooling, and no implementation guidance for AI-driven feature work.

The full research is at `research/generative-ui-harness/research.md`.

## Child tickets

- 034 — Fix inline style violations in session_panel and feature_cards templates
- 035 — Define evaluation rubric, update lifecycle spec template, create dashboard/CONTEXT.md
- 029 — Add Playwright + HTMX test patterns to dev toolchain
- 030 — Investigate and fix swim-lane inline styles and layout degradation
- 031 — Add hover states, loading feedback, and badge micro-interactions
- 032 — Add accessibility foundations (aria-live, multi-modal severity)

## Wave structure

- Wave 1: 034, 035 (no dependencies — truly disjoint file sets)
- Wave 2: 029, 031, 032 (unlock when both 034 and 035 complete)
- Wave 3: 030 (depends on 029)
