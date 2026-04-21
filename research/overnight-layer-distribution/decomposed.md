# Decomposition: overnight-layer-distribution

## Epic
- **Backlog ID**: 113
- **Title**: Distribute cortex-command as cortex CLI + plugin marketplace

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 114 | `cortex` CLI skeleton | high | M | — |
| 115 | Port overnight runner into `cortex` CLI | high | L | 114 |
| 116 | MCP control-plane server + runner IPC contract | high | L | 115 |
| 117 | `cortex setup` subcommand + retire #006/#007 code | high | M | 114 |
| 118 | Bootstrap installer (`curl \| sh`) | high | S | 114, 117 |
| 119 | `cortex init` per-repo scaffolder | medium | M | 114 |
| 120 | `cortex-interactive` plugin | high | L | 114, 117 |
| 121 | `cortex-overnight-integration` plugin | high | M | 120 |
| 122 | Plugin marketplace manifest + install docs | high | S | 120, 121 |
| 123 | Lifecycle autonomous-worktree graceful degrade | high | S | 120 |
| 124 | Migration guide + script for existing users | medium | S | 118, 121, 122 |
| 125 | Homebrew tap (optional) | low | S | 118 |

## Suggested Implementation Order

**Wave 1 — foundations**: 114 (CLI skeleton) blocks everything else.

**Wave 2 — parallel after 114**: 115 (runner port) || 117 (cortex setup) || 119 (init scaffolder). These touch different files and can land independently.

**Wave 3 — parallel after wave 2**:
- 116 (MCP server) after 115
- 118 (bootstrap) after 114 + 117
- 120 (cortex-interactive plugin) after 114 + 117

**Wave 4 — parallel after 120**:
- 121 (cortex-overnight-integration) after 120
- 123 (lifecycle degrade) after 120

**Wave 5 — integration**: 122 (marketplace manifest) after 120 + 121, then 124 (migration guide) after 118 + 121 + 122.

**Optional later**: 125 (Homebrew tap) after 118 — cortex-command is usable without it.

## Key Design Decisions (consolidations made during §3 review)

- **IPC contract design merged into 116**. Was originally a separate design spike; merged because the MCP server consumes the contract and designing it separately creates a ticket with no standalone deliverable.
- **Import-graph verification for `critical-review` / `morning-review` merged into 120**. Was originally a separate spike to decide plugin placement; merged as a prerequisite check the authoring ticket must run during implementation. The check output determines whether those two skills land in 120 or 121.
- **Retiring #006/#007 shareable-install code merged into 117**. Was originally a standalone cleanup ticket; merged because it touches the same file surface (`~/.claude/*` deployment) that 117 replaces with `cortex setup`.

## Created Files
- `backlog/113-distribute-cortex-command-as-cli-plus-plugin-marketplace.md` — Epic
- `backlog/114-cortex-cli-skeleton.md`
- `backlog/115-port-overnight-runner-into-cortex-cli.md`
- `backlog/116-mcp-control-plane-server-and-runner-ipc-contract.md`
- `backlog/117-cortex-setup-subcommand-and-retire-shareable-install-scaffolding.md`
- `backlog/118-bootstrap-installer-curl-sh-pipeline.md`
- `backlog/119-cortex-init-per-repo-scaffolder.md`
- `backlog/120-cortex-interactive-plugin.md`
- `backlog/121-cortex-overnight-integration-plugin.md`
- `backlog/122-cortex-command-plugin-marketplace-manifest.md`
- `backlog/123-lifecycle-autonomous-worktree-graceful-degrade.md`
- `backlog/124-migration-guide-and-script-for-existing-installs.md`
- `backlog/125-homebrew-tap-for-cortex-command.md`
