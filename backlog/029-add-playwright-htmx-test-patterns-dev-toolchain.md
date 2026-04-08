---
schema_version: "1"
uuid: f4a5b6c7-d8e9-0123-fabc-345678901234
id: "029"
title: "Add Playwright MCP for dashboard visual evaluation"
type: feature
status: complete
priority: medium
parent: "033"
blocked-by: []
tags: [dashboard, ui, evaluation, playwright, mcp]
created: 2026-04-03
updated: 2026-04-08
discovery_source: research/generative-ui-harness/research.md
complexity: simple
criticality: medium
spec: lifecycle/add-playwright-mcp-for-dashboard-visual-evaluation/spec.md
areas: [dashboard]
session_id: null
---

# Add Playwright MCP for dashboard visual evaluation

## Context

Anthropic's harness design article describes an evaluator that "uses the Playwright MCP to click through the running application the way a user would, screenshotting and carefully studying the implementation before producing its assessment." Playwright MCP is a navigation and perception tool for Claude's vision — not an assertion framework. Claude's multimodal capabilities evaluate visual quality, layout coherence, and operational clarity from screenshots.

The dashboard currently has no mechanism for Claude to see its own UI output. Adding Playwright MCP gives Claude eyes on the dashboard, enabling visual evaluation of all quality criteria (information clarity, consistency, operational usefulness, purposefulness).

## What to produce

**1. Project-scoped Playwright MCP configuration**

Add `.mcp.json` to the project root so Claude can navigate and screenshot the dashboard.

**2. Fixture and server setup**

Document or script the setup for visual evaluation:
- `just dashboard-seed` generates fixture data
- `just dashboard` starts the server at `localhost:8080`
- Claude navigates, screenshots, and evaluates

**3. Evaluation workflow documentation**

Brief doc on how Claude uses Playwright MCP to evaluate dashboard changes:
- Navigate to the dashboard with seeded data
- Screenshot key panels
- Evaluate against quality criteria in DESIGN.md
- Report findings with specific visual evidence

## Scope notes

- Playwright MCP is for Claude's interactive visual evaluation — not automated CI tests
- Existing research (in lifecycle directory) identified TestClient + BeautifulSoup as the proportional approach for automated DOM regression testing — that's a separate concern and can be added independently if needed
- This ticket does not depend on ticket 035 — Claude can evaluate visually with criteria stated in DESIGN.md or prompts

## Prior research note

Research exists at `lifecycle/add-playwright-htmx-test-patterns-to-dev-toolchain/research.md` from the original ticket scope. That research correctly identified that @playwright/mcp is an interactive tool (not a test runner) and recommended TestClient + BeautifulSoup for automated testing. The research's core findings remain valid but were scoped around DOM assertion patterns — visual evaluation via Claude's vision was not explored. A research supplement or re-evaluation may be needed during refinement.
