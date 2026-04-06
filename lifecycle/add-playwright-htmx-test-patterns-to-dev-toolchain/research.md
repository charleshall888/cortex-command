# Research: Add browser-level testing infrastructure to the dev toolchain using Playwright MCP

## Codebase Analysis

### Dashboard architecture
- FastAPI app at `claude/dashboard/app.py`, templates in `claude/dashboard/templates/`
- HTMX partials served at `/partials/{name}` routes with `hx-get`, `hx-trigger="load, every 5s"`, `hx-swap="innerHTML"`
- Key panel IDs receiving HTMX swaps: `#alerts-banner`, `#session-panel`, `#feature-cards`, `#fleet-panel`, `#swim-lane`, `#round-history`
- One out-of-band swap: `#live-indicator` with `hx-swap-oob="true"` in `session_panel.html`
- All HTMX is timer-driven polling — no user-triggered interactions, no forms, no click handlers

### Existing test patterns
- Tests in `claude/dashboard/tests/` using `unittest.TestCase` via `pytest`
- Pattern: render templates via Jinja2 directly (no HTTP server), assert string presence in HTML
- `TestStructuralElements` already verifies section IDs exist
- ~40+ test cases across 4-5 files covering data parsing, poller state, templates, alerts, sessions
- No browser-level or HTTP-layer tests exist

### No JavaScript/Node.js in project
- Zero Node.js dependencies — no `package.json`, no `node_modules`, no `.mcp.json`
- All dependencies managed via `pyproject.toml` with `uv`
- Dev dependencies: `pytest>=8.0`

### Dashboard dev tooling
- `just dashboard` starts uvicorn on port 8080
- `just dashboard-seed` writes synthetic fixture data
- `.ui-config.json` specifies `"devServerUrl": "http://localhost:8080"`

### DESIGN.md forbidden patterns (enforceable via assertions)
- Inline `style=` with raw hex colors
- Raw hex colors in new CSS
- Mixing `bg-gray-*`/`text-gray-*` utilities with semantic tokens
- Arbitrary Tailwind values like `p-[13px]`

### Blocker ticket 035
- Defines evaluation rubric and `dashboard/CONTEXT.md`
- "Consistency" (criterion 2) is the only criterion partially automatable via DOM assertions
- Criteria 1, 3, 4 require human judgment
- Status: `backlog` (not yet completed)

## Web Research

### @playwright/mcp is NOT an automated test runner
- `@playwright/mcp` (npm: `@playwright/mcp`, GitHub: microsoft/playwright-mcp) is an MCP server that gives LLMs interactive browser control — navigate, click, type, screenshot, snapshot
- It operates on structured accessibility snapshots, opens a visible Chrome window for interactive use
- Official Playwright docs explicitly position it as "interactive LLM browser interaction," contrasting it with the Playwright test runner which is designed for assertions
- **It does not run test files, produce test results, or support assertion APIs**
- The backlog item conflates two things: MCP for interactive Claude browser use, and a test framework for regression testing

### Playwright Python bindings exist
- `pip install pytest-playwright` — full Python bindings, same Playwright engine as Node.js
- Provides `page` fixture, `expect(locator)` assertions, `page.wait_for_function()`, `page.evaluate()`
- First-party Microsoft package — not a community wrapper
- Eliminates the Node.js dependency entirely for automated testing

### HTMX testing patterns (community-sourced, no official guide)
- **CSS class polling**: Check `.htmx-request, .htmx-settling, .htmx-swapping, .htmx-added` have count 0 — indicates no in-flight HTMX operations
- **Console message listener**: Inject listener for `htmx:afterSettle`, use `expect_console_message` to wait
- **HTMX init check**: `page.wait_for_function("() => window.htmx")` before any HTMX assertions
- **Anti-patterns**: Fixed `time.sleep()` waits (flaky), relying on Playwright auto-wait alone (doesn't understand HTMX lifecycle)

### Project-scoped MCP configuration
- `.mcp.json` at repo root is supported by Claude Code
- Three scopes: local > project > user
- Claude prompts for approval before using project-scoped servers
- Relevant only if MCP is added for interactive evaluation — not for automated tests

## Requirements & Constraints

### From requirements/project.md
- Quality bar: "Tests pass and the feature works as specced. ROI matters — the system exists to make shipping faster, not to be a project in itself."
- Complexity: "Must earn its place by solving a real problem that exists now."
- File-based state architecture; no database
- Graceful partial failure required

### From requirements/observability.md
- Dashboard is read-only, binds to `0.0.0.0`, no authentication
- Dependencies: Python 3, FastAPI, Jinja2, HTMX (embedded in templates)
- Resource usage: one FastAPI process, no database, in-memory cache only
- Dashboard process crash does not affect Claude session

### From requirements/pipeline.md
- Smoke test pattern exists (`claude/overnight/smoke_test.py`) — creates minimal lifecycle, runs batch, verifies branch state
- Test gate runs after any resolution; on gate failure, repair branch is cleaned up

### Existing test conventions
- pytest configured in `pyproject.toml` with testpaths
- Test recipes: `just test`, `just test-pipeline`, `just test-overnight`, `just test-skill-contracts`
- No dedicated dashboard browser test recipe exists

## Tradeoffs & Alternatives

### A: @playwright/mcp via npx (backlog item's proposal)
- **Pros**: Claude can interactively inspect dashboard; official Microsoft package; useful for development-time evaluation
- **Cons**: Not automated tests — MCP provides browser tools, not a test suite; JavaScript test snippets have no runner (no jest/vitest config); introduces Node.js dependency into Python-only project; JS test files invisible to `just test`
- **Verdict**: MCP server is a development convenience tool, not test infrastructure. The backlog item's framing is misleading.

### B: Playwright Python bindings (pytest-playwright)
- **Pros**: Stays in Python; solves DOM structure + HTMX swap verification directly; pytest-native; first-party Microsoft package
- **Cons**: Requires browser binary (~150MB one-time); needs live FastAPI server in fixtures; slower tests (seconds vs milliseconds); HTMX settlement helpers need custom implementation
- **Verdict**: Right tool if real browser execution is needed. Overkill if the HTMX patterns are simple polling.

### C: FastAPI TestClient + BeautifulSoup (no browser)
- **Pros**: No browser binary; pure Python; tests actual HTTP layer; CSS selector assertions more robust than string matching; runs in milliseconds; minimal new dependencies
- **Cons**: Cannot verify HTMX swap behavior (no JavaScript execution); cannot catch CSS/JS interactions; cannot verify dynamic DOM changes
- **Verdict**: Proportional to the actual problem. Dashboard HTMX is all timer-driven polling — the real risk is structural (template breaks DOM hierarchy), not behavioral (HTMX swap fails). CSS-selector assertions catch structural regressions without browser overhead.

### D: Status quo (template string assertions)
- **Pros**: Zero new dependencies; already covers major panels; fast
- **Cons**: Cannot verify DOM hierarchy (string match passes even if content is in wrong place); no HTTP-layer coverage; fragile
- **Verdict**: Insufficient for the stated goal but adequate for the current level of dashboard complexity.

### Recommended approach
**Alternative C (TestClient + BeautifulSoup) as the primary test infrastructure**, with MCP (.mcp.json) as an optional development convenience.

Rationale:
1. The actual gap is DOM structure verification, not HTMX swap behavior — all HTMX usage is simple polling
2. Proportional to the problem (project philosophy: "complexity must earn its place")
3. CSS-selector patterns translate directly to Playwright `page.locator()` if browser tests become needed later
4. Node.js remains unnecessary
5. MCP question is orthogonal — it's a development tool, not test infrastructure

## Open Questions

- **Scope pivot**: The backlog item assumes @playwright/mcp is the test infrastructure, but research shows it's an interactive tool. Should the scope pivot to TestClient + BeautifulSoup (proportional), pytest-playwright (full browser), or both MCP (interactive) + one of these (automated)?
- **Ticket 035 dependency**: The backlog item says `blocked-by: ["035"]`. Ticket 035 defines the evaluation rubric. Can test patterns be established independently, or do they need the rubric first to know what to assert?
- **MCP configuration scope**: If .mcp.json is added for interactive evaluation, should it go in the project root (version-controlled) or stay in local Claude config?
