# Research: Add Playwright MCP for dashboard visual evaluation

## Codebase Analysis

### Dashboard structure
- FastAPI + Jinja2 + HTMX + Tailwind v4 at `claude/dashboard/`
- HTMX partials at `/partials/{name}` with timer-driven polling (`every 5s`, `innerHTML` swap)
- Key panel IDs: `#alerts-banner`, `#session-panel`, `#feature-cards`, `#fleet-panel`, `#swim-lane`, `#round-history`
- Dev server: `just dashboard` at `localhost:8080`, fixtures via `just dashboard-seed`
- `.ui-config.json` documents dev server URL

### No existing MCP configuration
- No `.mcp.json` exists in the project root
- `claude/settings.json` has `"enableAllProjectMcpServers": false`
- No Node.js dependencies in the project (no `package.json`, no `node_modules`)

### Existing Playwright + vision patterns
- **`ui-judge` skill** already uses Playwright to capture screenshots and Claude vision to evaluate them via the UICrit two-call pattern (critique + localization)
- **`ui-a11y` skill** uses Playwright Python (`uv run --script` with PEP 723 inline dependency) for browser interaction
- Both skills demonstrate that Playwright screenshots + Claude vision evaluation works in this codebase
- `ui-judge` is advisory-only (exits 0) — not CI-gating; 77% accuracy is insufficient for automated gating

### DESIGN.md evaluation criteria
- Forbidden patterns documented: inline `style=` attributes, raw hex values, `bg-gray-*`/`text-gray-*` mixing
- Semantic token usage rules, composition rules, component patterns
- These are visually evaluable criteria Claude can check via screenshots

### Discovery source resolution (DR-4 contradiction)
- DR-4 concluded: "An evaluator agent with visual reasoning capabilities (not Playwright) would change this calculus, but no such tool is in the current MCP ecosystem"
- **Resolution**: Playwright MCP provides navigation + screenshot capture; MCP's image content type transports screenshots directly to Claude; Claude's multimodal vision provides the evaluation. The three-part combination (Playwright capture → MCP transport → Claude vision) is the "evaluator agent with visual reasoning capabilities" DR-4 said didn't exist. DR-4 was looking for a single tool that does evaluation; the answer is a pipeline.

## Web Research

### Playwright MCP tool capabilities
- `@playwright/mcp` (v0.0.70, April 2025) exposes 50+ tools
- **Core tools**: `browser_navigate`, `browser_take_screenshot`, `browser_snapshot` (accessibility tree), `browser_click`, `browser_type`, `browser_wait_for`, `browser_evaluate`, `browser_resize`
- **`browser_take_screenshot`** returns base64-encoded PNG as an MCP image content block — Claude sees it inline as a visual image, no file I/O intermediary
- **`browser_snapshot`** returns structured accessibility tree (semantic, text-based) — cheaper on tokens than screenshots
- **Optional capabilities**: `--caps=testing` adds assertion tools (`browser_verify_element_visible`, `browser_verify_text_visible`); `--caps=vision` adds coordinate-based mouse tools (unnecessary for this use case)

### Headless mode
- Fully supported via `--headless` flag in args
- Docker support exists for CI/CD
- Confirmed working in GitHub Actions (AI QA Engineer pattern by alexop.dev)

### Real-world examples of Claude + Playwright MCP for visual evaluation
- **AI QA Engineer** (alexop.dev): Claude Code + Playwright MCP in CI. Claude navigates, screenshots bugs, posts QA reports to PRs. Uses `--headless`.
- **Screenshot documentation** (Shipyard blog): Claude screenshots components across themes/viewports for visual diffs
- **Simon Willison TIL**: Practical walkthrough confirming screenshots work and Claude can see them

### `.mcp.json` configuration
- Project-scoped MCP servers go in `.mcp.json` at repo root
- Claude Code prompts for approval before using project-scoped servers
- Recommended to pin version rather than `@latest` to avoid regressions

### Known issues
- Screenshots exceeding 5MB or 8000px can break conversations
- Version instability: some users recommend pinning to known-good versions rather than `@latest`
- First invocation downloads Chromium (~150MB) — one-time setup cost

## Requirements & Constraints

### From requirements/project.md
- Quality bar: "Tests pass and the feature works as specced. ROI matters"
- Complexity: "Must earn its place by solving a real problem that exists now"
- Dashboard (~1800 LOC FastAPI) is in-scope

### From requirements/observability.md
- Dashboard is read-only — cannot modify session state
- Binds to `0.0.0.0`, unauthenticated
- Dependencies: Python 3, FastAPI, Jinja2, HTMX
- Feature status reflects actual state within 7s of change

### Existing patterns to follow
- MCP servers registered in `claude/settings.json` under `mcpServers` with `command`/`args` pattern
- Permission gating via `mcp__server-name__*` in `permissions.allow`
- `cortex-sync-permissions.py` hook merges MCP permissions for overnight agents
- Graceful degradation required: Playwright not installed → exit 0, not crash

### Node.js dependency assessment
- `.mcp.json` adds Node.js as an environment dependency (for `npx`)
- MCP server is managed by Claude Code as a subprocess — not a project code dependency
- `pyproject.toml` and Python codebase unchanged
- If Node.js unavailable, all existing Python-based skills (`ui-a11y`, `ui-judge`) continue to work
- Node.js 18+ commonly present on macOS with Homebrew

## Tradeoffs & Alternatives

### A: @playwright/mcp via .mcp.json (the ticket's proposal)
- **Pros**: Screenshots flow directly to Claude's vision via MCP image content type; interactive navigation (click between panels, resize viewport); rich tool set; project-scoped via `.mcp.json`; one JSON file, no code to write; matches Anthropic's documented harness pattern
- **Cons**: Node.js runtime dependency; MCP server process runs during session; token cost per screenshot; Chromium download on first use (~150MB); version instability with `@latest`
- **Verdict**: Right tool for interactive visual evaluation. Node.js dependency is bounded and does not spread into Python codebase.

### B: Python screenshot script (no MCP)
- **Pros**: No Node.js; pattern proven in codebase (`ui-a11y`, `ui-judge`); no MCP server overhead; screenshots persist on disk
- **Cons**: Two-step workflow (run script, then Read PNG); no interactive navigation; loses accessibility tree data; requires building/maintaining script
- **Verdict**: Already works for scripted evaluation but lacks interactive capability. MCP is a meaningful upgrade.

### C: No visual evaluation (status quo)
- **Pros**: Zero dependencies; existing tests adequate for current complexity; all dashboard work is daytime/interactive (human can see it)
- **Cons**: Claude generates dashboard UI blind; unit tests verify data binding not visual quality; no evaluation capability if dashboard work moves to overnight
- **Verdict**: Adequate for now but blocks future overnight dashboard development.

### D: Alternative browser MCP servers
- **Verdict**: No credible alternatives. `@playwright/mcp` is the clear leader (official Microsoft, 50+ tools, headless support, Claude Code integration docs).

### Recommended approach
**Alternative A (@playwright/mcp via .mcp.json)** — the MCP image transport mechanism is the key enabler that resolves DR-4. Interactive navigation adds genuine value over scripted screenshots. Node.js dependency is bounded. Pin version, use `--headless`.

## Open Questions

None — all questions from Clarify resolved during research:
- Core premise validated: `browser_take_screenshot` returns base64 PNG inline to Claude's vision
- DR-4 contradiction resolved: Playwright capture + MCP transport + Claude vision = the visual evaluation pipeline DR-4 said didn't exist
- `.mcp.json` format and headless mode confirmed
- Existing `ui-judge`/`ui-a11y` skills confirm the pattern works in this codebase
