# Decomposition: overnight-layer-distribution

## Epic
- **Backlog ID**: 113
- **Title**: Distribute cortex-command as cortex CLI + plugin marketplace

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 114 | `cortex` CLI skeleton | high | M | — |
| 115 | **Rebuild** overnight runner under `cortex` CLI | high | **XL** | 114, 117 |
| 116 | MCP control-plane server + runner IPC contract | high | L | 115 |
| 117 | `cortex setup` subcommand + retire #006/#007 code | high | M | 114 |
| 118 | Bootstrap installer (`curl \| sh`) | high | S | 114, 117 |
| 119 | `cortex init` per-repo scaffolder | medium | M | 114 |
| 120 | `cortex-interactive` plugin | high | L | 114, 117 |
| 121 | `cortex-overnight-integration` plugin | high | M | 115, 116, 120 |
| 122 | Plugin marketplace manifest + install docs | high | S | 115, 116, 117, 120, 121 |
| 123 | Lifecycle autonomous-worktree graceful degrade | high | S | 120 |
| 124 | Migration guide + script for existing users | medium | S | 115, 116, 117, 118, 121, 122 |
| 125 | Homebrew tap (optional) | low | S | 118 |

**Sizing update from critical review**: ticket 115 was originally rated L; quantified surface-area evidence showed that undercount — runner.sh is 1,362 lines (not 600+), `claude/overnight/*.py` is ~10,400 LOC across 22 modules, `claude/pipeline/*.py` is ~5,500 LOC, plus ~13,300 LOC of tests. 50 inline Python snippets in runner.sh; 23 `REPO_ROOT` sites; 25 atomic-write call sites across 7 files; 4 `set -m` process-group sites with `kill -- -$PID` watchdog. This is a rebuild of the orchestration layer, not a wrapper. Upgraded to XL and explicitly gated on 117 (they share the `~/.claude/notify.sh` path literal contract at 13 call sites and the `apiKeyHelper` reader at runner.sh lines 50-66).

**Cross-epic gates added** (post-decomp critical review): #102, #103, #104 (children of #101 scripts epic) and potentially #112 (LaunchAgent scheduler) target surfaces that #115 and #117 restructure or retire. #102/#103/#104 now carry `blocked-by: [115]` to prevent them landing against the old `bin/` + `just deploy-*` shape that #115 retires. #112 remains ungated pending user decision (it is `in_progress` with an active lifecycle session; see Ask in the research artifact's critical-review log).

## Suggested Implementation Order

**Wave 1 — foundation**: 114 (CLI skeleton) blocks everything.

**Wave 2 — after 114**: 117 (cortex setup) || 119 (init scaffolder). Only 119 is genuinely orthogonal to the rest of the epic; 117 is on the critical path because 115, 118, and 120 all gate on it.

**Wave 3 — after 117**: 115 (runner rebuild) || 118 (bootstrap) || 120 (cortex-interactive plugin). 115 and 117 share the `~/.claude/notify.sh` and `apiKeyHelper` contracts (critical review finding), so 115 is explicitly gated on 117 — not parallel with it as the original plan claimed.

**Wave 4 — after 115 and 120**:
- 116 (MCP server) after 115
- 123 (lifecycle graceful degrade) after 120

**Wave 5 — integration**: 121 (cortex-overnight-integration plugin) after 115 + 116 + 120. Then 122 (marketplace manifest) after 115 + 116 + 117 + 120 + 121.

**Wave 6 — migration**: 124 after 115 + 116 + 117 + 118 + 121 + 122. This gate ensures users who run the migration land on a functional CLI (not a CLI whose `overnight` / `mcp-server` subcommands don't exist yet).

**Optional later**: 125 (Homebrew tap) after 118 — cortex-command is usable without it.

**Critical path**: 114 → 117 → 115 → 116 → 121 → 122 → 124. Most parallelism opportunities live in Wave 3 (115 || 118 || 120).

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
