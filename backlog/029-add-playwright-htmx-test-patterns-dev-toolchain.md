---
schema_version: "1"
uuid: f4a5b6c7-d8e9-0123-fabc-345678901234
id: "029"
title: "Add Playwright + HTMX test patterns to dev toolchain"
type: feature
status: backlog
priority: medium
parent: "033"
blocked-by: ["035"]
tags: [dashboard, ui, testing, playwright, htmx]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/generative-ui-harness/research.md
---

# Add Playwright + HTMX test patterns to dev toolchain

## Context from discovery

The dashboard has no browser-level tests. Unit tests check string presence in rendered HTML but cannot verify layout integrity, visual coherence, or HTMX partial swap behavior. Playwright MCP is the evaluation tool used in Anthropic's harness design article for live UI evaluation.

Research confirmed: project-scoped configuration is supported via `.mcp.json` in the project root (not global `~/.claude/settings.json`). Package: `@playwright/mcp` (official Microsoft implementation).

## What to produce

**1. Project-scoped Playwright MCP configuration**

Add `.mcp.json` to the project root:
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}
```

Verify with: `claude mcp add --scope project playwright npx @playwright/mcp@latest`

**2. Browser binary installation**

Document: `npx playwright install` must be run manually before first use. Auto-install via MCP often fails due to permissions.

**3. HTMX settlement utility**

Write a reusable Playwright test helper:
```javascript
async function htmxReady(page) {
  await expect(
    page.locator('.htmx-request, .htmx-settling, .htmx-swapping, .htmx-added')
  ).toHaveCount(0);
}
```

This waits for all in-flight HTMX requests to settle before assertions.

**4. Fixture-setup script**

Write a script (or `just` recipe) that:
1. Runs `just dashboard-seed` to generate fixture data
2. Starts the dashboard server (`just dashboard`)
3. Outputs the server URL for Playwright to connect to

**5. Sample DOM-structure assertion**

Write one sample Playwright test demonstrating:
- Navigation to `localhost:8080`
- `htmxReady()` settlement check
- Assert no inline `style=` attributes on key elements (the consistency rubric criterion)
- Assert feature card elements present after seed data loads

## Scope note

Playwright verifies DOM structure only. It cannot verify: visual clarity ("readable at a glance"), animation smoothness, or temporal ordering correctness of computed layout. The rubric from ticket 028 specifies which criteria require human review vs. automated checking.

Ticket 030 (swim-lane fix) depends on this ticket because DOM-structure assertions provide a regression baseline for the swim-lane refactor — even though they cannot catch all correctness failures.
