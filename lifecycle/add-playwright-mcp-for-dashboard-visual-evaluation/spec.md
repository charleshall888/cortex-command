# Specification: Add Playwright MCP for dashboard visual evaluation

## Problem Statement

Claude generates dashboard UI code without being able to see the result. The dashboard has no mechanism for Claude to visually evaluate its own output during interactive development sessions. Adding Playwright MCP gives Claude interactive browser access — navigate, screenshot, and evaluate the dashboard using its multimodal vision — closing the feedback loop between code changes and visual outcomes.

## Requirements

1. **Project-scoped `.mcp.json`**: Add `.mcp.json` to the project root configuring `@playwright/mcp` as a project-scoped MCP server. Pin to a specific known-good version (e.g., `@playwright/mcp@0.0.70`). Use `--headless` mode. Acceptance: Claude Code discovers the server, prompts for approval on first use, and `browser_navigate` + `browser_take_screenshot` tools become available.

2. **Setup and context documentation**: Document the setup steps and evaluation context in a brief section added to an appropriate existing doc (e.g., `docs/setup.md` or `claude/dashboard/DESIGN.md`). Content: (a) prerequisite: Node.js 18+ must be installed; (b) first invocation may download Chromium browser binaries (~150MB, handled automatically by the MCP server); (c) per-session: `just dashboard-seed` then `just dashboard` to start server with fixture data before using Playwright MCP; (d) how Playwright MCP complements existing skills — `ui-judge` provides structured rubric-based evaluation (UICrit pattern), `ui-a11y` provides accessibility checking, Playwright MCP provides ad-hoc interactive visual access for development-time inspection. Acceptance: a developer can follow the documented steps to set up and use visual evaluation from scratch, and the relationship between MCP tools and existing evaluation skills is unambiguous.

## Non-Requirements

- Not an automated test framework — Playwright MCP is for interactive visual evaluation during development, not CI test assertions
- Not for overnight/autonomous agent use — overnight evaluation uses existing `ui-judge` and `ui-a11y` skills, which provide structured rubric-based output. MCP's interactive approval prompt is incompatible with unattended execution.
- Not replacing `ui-judge` or `ui-a11y` — those skills provide structured evaluation; MCP provides interactive access
- Not adding `pytest-playwright` or `beautifulsoup4` — automated DOM regression testing is a separate concern
- Not adding Node.js as a project code dependency — `npx` runs the MCP server as a subprocess managed by Claude Code; `pyproject.toml` is unchanged
- Not adding permission hooks or `cortex-sync-permissions.py` changes — Playwright MCP permissions are handled by Claude Code's built-in project-scoped server approval flow
- Not addressing multi-agent MCP contention — this is a single-session developer tool; concurrent overnight agents do not use it

## Edge Cases

- **Node.js not installed**: MCP server won't start. All existing Python-based skills (`ui-judge`, `ui-a11y`) continue to work. Document Node.js 18+ as an environment prerequisite.
- **Dashboard not running**: `browser_navigate` to `localhost:8080` fails with connection error. Document that `just dashboard` must be running before evaluation.
- **First use**: MCP server automatically downloads Chromium on first invocation (~150MB). No manual setup step required, but the download adds latency to the first tool call.
- **Large screenshots**: Screenshots exceeding 5MB or 8000px in either dimension can cause API errors. Dashboard at default viewport (1440px wide) is well under these limits.
- **Version drift**: Pinning `@playwright/mcp` to a specific version avoids regressions. Document how to bump the version when needed.

## Technical Constraints

- `.mcp.json` format must follow Claude Code's project-scoped MCP specification
- `enableAllProjectMcpServers` is `false` in settings — Claude Code will prompt for user approval on first use (acceptable for interactive developer sessions)
- MCP server runs as a subprocess of Claude Code — not managed by the project's Python environment
- `@playwright/mcp` and Python Playwright use separate Chromium revision-stamped binaries — they share a cache directory but not necessarily the same binary. Do not assume one installation satisfies the other.

## Open Decisions

None.
