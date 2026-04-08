# Plan: Add Playwright MCP for dashboard visual evaluation

## Overview

Two files to create or modify:

1. **`.mcp.json`** (new) — project-scoped MCP server config registering `@playwright/mcp@0.0.70` in headless mode. Claude Code discovers it automatically, prompts for approval on first use, and `browser_navigate` + `browser_take_screenshot` become available in-session.

2. **`docs/dashboard.md`** (existing) — add a "Visual Evaluation with Playwright MCP" section documenting prerequisites, first-use behavior, the per-session workflow, and how MCP complements the existing `ui-judge` and `ui-a11y` skills.

No Python code, no `pyproject.toml` changes, no hook changes.

---

## Tasks

### Task 1 — Create `.mcp.json`

**Files:** `.mcp.json` (new file at repo root)

**What:** Create a project-scoped MCP configuration file at the repo root. Register `@playwright/mcp@0.0.70` with `npx -y` and `--headless`. The file must be valid JSON following Claude Code's `.mcp.json` schema.

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@0.0.70", "--headless"]
    }
  }
}
```

**Depends on:** Nothing — standalone file creation.

**Context:** `claude/settings.json` has `"enableAllProjectMcpServers": false`, which means Claude Code will prompt for per-session approval before connecting — appropriate for an interactive-only tool. The `npx` command is already in the global `permissions.allow` list (`"Bash(npx *)"`), so no settings.json changes are needed. The MCP server runs as a Claude Code subprocess and does not interact with the Python environment or `pyproject.toml`.

**Verification:** `python3 -c "import json; d=json.load(open('.mcp.json')); assert d['mcpServers']['playwright']['command']=='npx'"` exits 0 (no parse errors, correct command).

**Status:** pending

---

### Task 2 — Document in `docs/dashboard.md`

**Files:** `docs/dashboard.md`

**What:** Append a new top-level section "## Visual Evaluation with Playwright MCP" after the existing "Known Limitations" section. The section must cover:

- **Prerequisite**: Node.js 18+ must be installed (`node --version` to verify); all existing Python skills (`ui-judge`, `ui-a11y`) continue to work without it.
- **First use**: MCP server automatically downloads Chromium binaries (~150MB) on first invocation — no manual step required, but expect latency on the first call.
- **Per-session workflow**: Start with `just dashboard-seed` (write fixture data) then `just dashboard` (start server at `localhost:8080`), then use `browser_navigate` and `browser_take_screenshot` within Claude Code. Claude sees screenshots inline via its multimodal vision.
- **Relationship to existing skills**: `ui-judge` provides structured rubric-based evaluation (UICrit two-call pattern, exit 0, advisory); `ui-a11y` provides accessibility checking; Playwright MCP provides ad-hoc interactive visual access for development-time inspection. They are complementary — Playwright MCP is not a replacement.
- **Version pinning**: The `.mcp.json` pins to `@playwright/mcp@0.0.70`. To upgrade, change the version string in `.mcp.json`.
- **Known edge cases**: If `browser_navigate` to `localhost:8080` fails with a connection error, `just dashboard` is not running. Screenshots at default 1440px viewport are well within the 5MB / 8000px API limits.

**Depends on:** Task 1 (the section references `.mcp.json` and its configuration).

**Context:** `docs/dashboard.md` is the natural home — it already documents the dashboard dev workflow (`just dashboard`, `just dashboard-seed`), prerequisites, and known limitations. Adding a visual evaluation section extends the existing dev-workflow narrative without requiring a new file.

**Verification:** `grep -c "Visual Evaluation" docs/dashboard.md` returns `1`. The section must contain references to `just dashboard-seed`, `just dashboard`, `browser_navigate`, `browser_take_screenshot`, `ui-judge`, `ui-a11y`, and Node.js 18+.

**Status:** pending

---

## Verification Strategy

Automated smoke checks (no live browser needed):

```sh
python3 -c "import json; d=json.load(open('.mcp.json')); assert d['mcpServers']['playwright']['command']=='npx'"  # exits 0
grep -c "Visual Evaluation" docs/dashboard.md    # returns 1
git log --oneline -1                             # shows a commit for this feature
```

End-to-end acceptance (manual, interactive session):

1. Open Claude Code in the project root. Claude Code detects `.mcp.json` and prompts to approve the `playwright` MCP server.
2. Approve the server. Confirm `browser_navigate` and `browser_take_screenshot` appear in the available tools list.
3. Run `just dashboard-seed` then `just dashboard` in a terminal.
4. In Claude Code: call `browser_navigate` to `http://localhost:8080` — no connection error.
5. Call `browser_take_screenshot` — Claude sees an inline PNG of the dashboard in the conversation.
6. Verify `docs/dashboard.md` renders the new section correctly (readable, no broken references).
