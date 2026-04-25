# Plugin Development: Local Dogfooding Workflow

This doc covers the maintainer workflow for installing in-repo plugins
(starting with `cortex-overnight-integration`) directly from this checkout,
before ticket 122 publishes the production marketplace manifest.

## Why this exists

Per epic decisions:

- **DR-9**: This repo (`cortex-command`) publishes the core plugins
  (`cortex-interactive`, `cortex-overnight-integration`); the
  `cortex-command-plugins` repo continues as the optional/per-project
  extras marketplace.
- **DR-2**: The runner boundary splits the agentic layer into two plugins:
  `cortex-interactive` (already shipped in ticket 120) and
  `cortex-overnight-integration` (this ticket's plugin —
  overnight + morning-review skills + runner-only hooks).

Until ticket 122 lands the production marketplace manifest, maintainers
need a way to install the in-repo plugin reproducibly from any commit.
The committed stub at `.claude-plugin/marketplace.json` (ticket 121,
Task 10) is the marketplace anchor — no off-tree maintainer-authored
file is required, and there is no cleanup ritual.

## Prerequisites

- The repo is checked out at `/Users/charlie.hall/Workspaces/cortex-command`
  (substitute your own path; `$PWD` works if you run the commands from the
  repo root).
- The plugin tree under `plugins/cortex-overnight-integration/` has been
  built (`just build-plugin` runs as part of pre-commit; the assembled
  tree is committed).
- You are in an interactive Claude Code session (these are slash commands,
  not shell commands).

## Dogfood workflow

### 1. Register the local marketplace

From inside Claude Code, point the marketplace at this repo:

    /plugin marketplace add /Users/charlie.hall/Workspaces/cortex-command

Or, if you launched Claude Code from the repo root:

    /plugin marketplace add $PWD

Claude Code reads `.claude-plugin/marketplace.json` at the repo root and
registers a marketplace named `cortex-command` (the `name` field in the
stub manifest).

### 2. Install the plugin

    /plugin install cortex-overnight-integration@cortex-command

The `@cortex-command` suffix selects the marketplace registered in step 1.
After install, `/plugin list` shows `cortex-overnight-integration` as
enabled, and `/cortex:overnight` becomes invocable.

### 3. Verify the install

In the same session:

- `/plugin list` should show `cortex-overnight-integration` enabled.
- `/cortex:overnight` should be available as a slash command.
- `/mcp` should show the `cortex-overnight` MCP server connected
  (registered via the plugin's `.mcp.json`).

## Iterating on plugin source

The plugin's authored sources live under `skills/`, `hooks/`, and friends
at the repo root; the assembled tree under `plugins/cortex-overnight-integration/`
is built by `just build-plugin` and committed. To pick up edits during
development, rebuild and either reinstall or restart the Claude Code
session — the pre-commit hook enforces that the assembled tree matches
the canonical sources before any commit lands.

## Future plugins

When ticket 122 lands, `.claude-plugin/marketplace.json` will be edited
in place to add `cortex-interactive` and any sibling plugins. That is a
normal file edit, not a blocking conflict against this ticket's stub.
The same `/plugin marketplace add` + `/plugin install <name>@cortex-command`
pattern will work for any plugin the manifest lists.
