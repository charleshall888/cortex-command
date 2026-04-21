# Claude Code Plugin + MCP Distribution — Research Report (April 2026)

*Web research agent output. Sources cited inline.*

## 1. Plugin installation UX

Plugins entered public beta Oct 9, 2025; GA by April 2026. "Lightweight way to package and share any combination of slash commands, subagents, MCP servers, and hooks."

**Install flow** is two-stage (marketplace → install). **Official `claude-plugins-official` marketplace is auto-registered** on startup:

```
/plugin install github@claude-plugins-official
/plugin marketplace add anthropics/claude-code
/plugin marketplace add https://gitlab.com/co/plugins.git#v1.0.0
/plugin marketplace add ./local-marketplace
claude plugin install foo@bar --scope project
```

Four **scopes**: `user` (default), `project` (committed), `local` (gitignored), `managed` (admin, read-only).

## 2. What a plugin contains

Plugin = directory keyed by `.claude-plugin/plugin.json`.

| Component | Location | Notes |
|---|---|---|
| Skills | `skills/<name>/SKILL.md` | Namespaced `/plugin-name:skill-name` |
| Slash commands | `commands/*.md` | |
| Subagents | `agents/*.md` | `hooks`, `mcpServers`, `permissionMode` **disallowed** for security |
| Hooks | `hooks/hooks.json` or inline | Full lifecycle event set |
| MCP servers | `.mcp.json` or inline | Auto-registered on enable |
| LSP servers | `.lsp.json` | |
| Monitors | `monitors/monitors.json` | Background processes (v2.1.105+) |
| Output styles | `output-styles/` | |
| **Executables** | `bin/` | **Added to Bash-tool PATH** |

Two env vars: `${CLAUDE_PLUGIN_ROOT}` (install dir, changes on update), `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/{id}/`, **survives updates** — use for venvs, node_modules, caches).

`userConfig` prompts users at enable-time, supplies `${user_config.KEY}` substitution + `CLAUDE_PLUGIN_OPTION_*` env vars; sensitive values → keychain (~2 KB limit).

## 3. Skill distribution

Ship exactly as today's `skills/<name>/SKILL.md`. Auto-discovered. `/commit` → `/cortex:commit` etc.

## 4. Hook distribution

**Hooks ship in the plugin** — no writing to user's `settings.json`. Full event set supported.

**Gotcha**: hooks registered from manifest, not filesystem-discovered — deleting script leaves dangling manifest entry ([#333](https://github.com/anthropics/claude-plugins-official/issues/333)).

## 5. MCP server registration

**Local stdio, remote HTTP, SSE (deprecated)** all supported. OAuth 2.0 first-class.

```
claude mcp add --transport http notion https://mcp.notion.com/mcp
claude mcp add --transport stdio --env KEY=V myserver -- npx -y pkg
```

**Plugins register MCP servers declaratively** via `.mcp.json` or inline; auto-start on enable.

**Hard limits**: default **25K token cap on MCP tool output**, warning at 10K; override with `MAX_MCP_OUTPUT_TOKENS` ([#9152](https://github.com/anthropics/claude-code/issues/9152)). Tool schemas load into every turn (~100-500 tok each).

## 6. Long-running processes via MCP

**Not viable today as a protocol primitive, but workable via workarounds.**

- **SEP-1686 "Tasks"** proposes `tasks/get`, `tasks/result`, `tasks/list`, `tasks/delete` — accepted but **not yet in a released MCP version** ([#1686](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1686)).
- **Working pattern**: [dylan-gluck/mcp-background-job](https://github.com/dylan-gluck/mcp-background-job) exposes 7 tools (`execute`, `status`, `tail`, `interact`, `kill`, `list`, …). MCP server manages job registry; client polls. **Exactly what the overnight runner needs conceptually.**
- **Plugin monitors** (v2.1.105+): persistent background process whose stdout lines = notifications. Runs unsandboxed at session lifetime. **Dies when session ends — not ideal for multi-hour overnight runs.**
- **Channels** (`claude/channel` capability) let a server push status updates.

**For cortex-command's overnight runner**: daemon would have to live **outside** Claude Code, with an MCP server as a thin control plane (`start_run`, `status`, `logs`, `cancel`). Stdio MCP servers aren't auto-restarted, so the control-plane server itself can't reliably run for hours.

## 7. Binaries in plugins

**Fully supported.** `bin/` in plugin root is **added to Bash tool PATH** when enabled. Python scripts work — use `${CLAUDE_PLUGIN_DATA}` for a venv that survives updates. `SessionStart` hook can diff-install deps.

**Replaces the current `just deploy-bin` + `~/.local/bin/` symlink mechanic.**

## 8. Pitfalls

- **No sandboxing**: plugins run with full user privileges. No binary signing ([#40036](https://github.com/anthropics/claude-code/issues/40036)).
- **Auto-update risk**: official marketplace auto-updates by default. Safe v1 can gain hooks in v1.1 with no re-consent. Third-party marketplaces default to no-auto-update.
- **No plugin dependency sharing**: each plugin self-contained ([#9444](https://github.com/anthropics/claude-code/issues/9444)).
- **Path traversal blocked**: plugins copied to `~/.claude/plugins/cache`; `../` breaks. Symlinks *inside* plugin dir preserved.
- **Rules/CLAUDE.md NOT plugin-distributable today** — upstream gap. `claude/Agents.md` needs different mechanism.
- **Hook manifest drift**: removing script leaves dangling entry + load error.
- **Managed scope** + `strictKnownMarketplaces` = enterprise lockdown.

## 9. Bottom line for cortex-command

**Ships cleanly as plugin(s):**
- All `skills/*` → `skills/` in plugin, renamed `/cortex:commit`, `/cortex:lifecycle`
- Hooks → `hooks/hooks.json` with `${CLAUDE_PLUGIN_ROOT}` paths
- `bin/` utilities → plugin `bin/`, auto-on-PATH
- Python deps → `${CLAUDE_PLUGIN_DATA}` via `SessionStart` hook
- Statusline, reference docs, output styles

**Harder / requires redesign:**
- **Overnight runner**: doesn't fit plugin or MCP model cleanly. Options:
  - (a) Ship runner as plugin binary invoked by user (`cortex-overnight start`) with MCP control-plane server for Claude-initiated start/status/stop, modeled on `mcp-background-job`
  - (b) Keep runner as separate install path; ship only Claude-side integration via plugin
- **Web dashboard**: external service, not plugin-shaped
- **Global `CLAUDE.md` / Agents.md rules**: not plugin-distributable today
- **`settings.json` permissions allow/deny**: can't be pushed by a plugin; only `agent` and `subagentStatusLine` keys supported in plugin settings.json. Users still need `/setup-merge` for curated permissions.

**Recommended packaging shape:**
- `cortex-core` plugin — skills + hooks + bin utilities
- `cortex-lifecycle` plugin — heavier lifecycle-specific skills
- Optional `cortex-overnight` plugin — MCP control-plane server + runner binary

## Sources
- [Discover and install plugins](https://code.claude.com/docs/en/discover-plugins)
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code plugins blog](https://claude.com/blog/claude-code-plugins)
- [MCP docs](https://code.claude.com/docs/en/mcp)
- [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official)
- [SEP-1686 Tasks proposal](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1686)
- [mcp-background-job](https://github.com/dylan-gluck/mcp-background-job)
- [Your Claude Plugin Marketplace Needs More Than a Git Repo](https://www.mpt.solutions/your-claude-plugin-marketplace-needs-more-than-a-git-repo/)
- Issues: [#333 hook disabling](https://github.com/anthropics/claude-plugins-official/issues/333), [#9444 dependencies](https://github.com/anthropics/claude-code/issues/9444), [#40036 install surface](https://github.com/anthropics/claude-code/issues/40036), [#2638 MCP truncation](https://github.com/anthropics/claude-code/issues/2638), [#9152 MCP token limit](https://github.com/anthropics/claude-code/issues/9152)
