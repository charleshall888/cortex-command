# Cortex Command

Cortex Command is an AI workflow framework for Claude Code built on a single insight: autonomous execution is only as good as the specification that precedes it. Most AI coding tools optimize for speed. The result is fast accumulation of plausible-looking code that misses the point, because the problem space was never mapped, the scope was never agreed on, and nobody was asking the hard questions before the first line was written.

The front half of the lifecycle is deliberately human-driven. You run discovery to understand the problem space, collaborate with agents to write tight specs, and mark features ready only when the scope is genuinely clear. Once that work is done, the handoff is earned. Run `/cortex-core:lifecycle` to stay in the loop for interactive development, or queue a batch for `/overnight` and wake up to a morning report with PRs ready to review. The overnight runner is the natural payoff of doing the front half well.

Skills are slash commands you invoke from Claude Code. Hooks wire them into the development environment at the right moments. State files let the system resume across sessions and tool invocations. Cortex-command ships as a CLI (installed via `uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0`) plus Claude Code plugins (each installed as `<name>@cortex-command` after adding the marketplace) — everything lives in version control and is distributed without host-level symlinks.

Work flows through four stages: **discovery** maps the problem space and decomposes it into backlog tickets; **backlog** items progress from draft to refined as scope is clarified; **refine/lifecycle** drives each feature through research, spec, plan, implement, and review phases; and **overnight** executes refined items autonomously in parallel so you wake up to a morning report with PRs ready to review. For a visual of the full pipeline, see [docs/agentic-layer.md](docs/agentic-layer.md#diagram-a--main-workflow-flow).

```
        ┌──────────── /cortex-core:refine ──────┐
        │                           │
You ──► Clarify ──► Research ──► Spec ──► Plan ──► Implement ──► Review ──► Complete
                                    │                               ▲         │
                                    └──────── /overnight ───────────┘    /morning-review
                                         agents run autonomously              │
                                               (Plan → Complete)             You

  Complexity tier — auto-detected or set in lifecycle.config.md:
    simple   ·  standard gates only
    complex  ·  /cortex-core:critical-review challenges spec before Plan begins
                (auto-escalated when research surfaces ≥2 open questions)

  Criticality — controls rigor and model selection:
    low/medium  ·  tier-based review  ·  Haiku explore, Sonnet build
    high        ·  review always required  ·  Sonnet explore, Opus build
    critical    ·  parallel research + competing plans  ·  Sonnet explore, Opus build
```

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- macOS (primary supported platform)

## Quickstart

```bash
# 1. Install the cortex CLI (bootstrap installs `uv` first if missing)
curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh

# 2. In Claude Code, add the marketplace and install plugins
claude /plugin marketplace add charleshall888/cortex-command
claude /plugin install cortex-overnight@cortex-command   # autonomous overnight runs
claude /plugin install cortex-core@cortex-command        # interactive skills + hooks

# 3. In each project where you want cortex active
cd <your-project>
cortex init
```

Once installed, the `cortex-overnight` plugin keeps the cortex CLI tag in sync — when the plugin auto-updates (or you run `/plugin update cortex-overnight@cortex-command`), the next MCP tool call reinstalls the matching CLI tag automatically.

No symlinks into `~/.claude/` are created — plugins are discovered by Claude Code directly. The [Plugin roster](#plugin-roster) below lists all 6 available plugins; install `cortex-ui-extras`, `cortex-pr-review`, `android-dev-extras`, and `cortex-dev-extras` for the extras tier.

See [`docs/setup.md`](docs/setup.md) for: alternate install (manual `uv tool install`), authentication setup, plugin-specific prerequisites, troubleshooting, and `CLAUDE_CONFIG_DIR` per-repo scoping. Verify the install with the smoke test in [Setup guide § Verify install](docs/setup.md#verify-install).

### Plugin roster

Cortex-command ships six plugins in this repo:

| Plugin | Description |
|--------|-------------|
| android-dev-extras | Android development skills vendored from Google's Android Skills (Apache 2.0): R8 analyzer, edge-to-edge migration, and Android CLI orchestration |
| cortex-dev-extras | Devil's advocate inline challenge for solo deliberation |
| cortex-core | Interactive Claude Code skills, hooks, and CLI utilities from cortex-command for day-to-day development workflows |
| cortex-overnight | Integrates the cortex MCP server and overnight skill runner hooks to drive autonomous lifecycle execution |
| cortex-pr-review | Multi-agent GitHub pull request review pipeline for Claude Code |
| cortex-ui-extras | Experimental UI design skills for Claude Code interactive workflows |

For installation specifics and per-project enablement, see [`docs/setup.md`](docs/setup.md).

## Authentication

Authentication setup (API key vs. OAuth token) is documented in [Setup guide § Authentication](docs/setup.md#authentication).

## What's Inside

| Component | Description |
|-----------|-------------|
| `skills/` | Slash commands -- `/cortex-core:commit`, `/cortex-core:pr`, `/cortex-core:lifecycle`, `/overnight`, `/cortex-core:discovery`, and more |
| `hooks/` | Event handlers -- commit validation, lifecycle state injection, desktop notifications |
| `cortex_command/overnight/` | Autonomous overnight runner -- plans work, executes in parallel, writes a morning report |
| `cortex_command/dashboard/` | FastAPI web dashboard for monitoring overnight sessions |
| `lifecycle/` | Feature state machine -- research, specify, plan, implement, review, complete |
| `backlog/` | YAML-frontmatter backlog items with overnight readiness gates |
| `plugins/cortex-core/bin/` | CLI utilities on `PATH` via the plugin -- `cortex-archive-rewrite-paths`, `cortex-archive-sample-select`, `cortex-audit-doc`, `cortex-count-tokens`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`, `cortex-git-sync-rebase`, `cortex-jcc`, `cortex-update-item` |

## Customization

Cortex-command does not own `~/.claude/settings.json`. Edit it directly as personal machine configuration; use `~/.claude/settings.local.json` for per-machine overrides. Plugin-shipped skills and hooks are enabled per project via `.claude/settings.json`'s `enabledPlugins` map.

## Distribution

The `cortex` CLI is installed as a non-editable `uv tool` from a tag-pinned git URL. To upgrade to a newer release, run `/plugin update cortex-overnight@cortex-command` from inside Claude Code (the MCP-driven path) or `uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@<tag>` from a bare shell. `cortex upgrade` itself is now an advisory printer that points at those two paths. A few operational notes:

- When cortex invokes `uv run` internally, it operates on the user's current project, not cortex's own tool venv.
- Do not run `uv tool uninstall uv` — removing uv via itself breaks the tool environment.
- Run `uv tool update-shell` once after the first `uv tool install` to add the tool bin directory to your `PATH`.
- Forkers (advanced users developing against a fork of cortex-command) install via `uv tool install git+https://github.com/<your-fork>/cortex-command.git@<branch-or-tag>` instead of the upstream URL.

## Commands

```
cortex overnight start     # Run overnight in detached tmux
cortex overnight status    # Print session status (use --format json for machine-readable)
cortex overnight cancel    # Cancel the active session
cortex overnight logs      # Read session logs
cortex init                # Scaffold a repo for cortex (run once per project)
cortex --print-root        # Verify install (prints {version, root, package_root, ...})
```

Run `cortex --help` to see all subcommands.

> **Contributors only:** operational `just` recipes (`just test`, `just dashboard`, `just validate-commit`, `just validate-skills`) require a clone of cortex-command and only work from inside the repo.

## Documentation

| Guide | Covers |
|-------|--------|
| [`docs/agentic-layer.md`](docs/agentic-layer.md) | Full skill and hook inventory, workflow diagrams, lifecycle phase map |
| [`docs/setup.md`](docs/setup.md) | Installation, plugins, authentication, customization |
| [`docs/overnight.md`](docs/overnight.md) | Autonomous overnight runner -- planning, execution, deferral, morning review |
| [`docs/dashboard.md`](docs/dashboard.md) | Web dashboard for monitoring overnight sessions |
| [`docs/backlog.md`](docs/backlog.md) | Backlog YAML schema, readiness gates, overnight eligibility |
| [`docs/interactive-phases.md`](docs/interactive-phases.md) | What to expect at each lifecycle phase -- questions, artifacts, flow |
| [`docs/skills-reference.md`](docs/skills-reference.md) | Per-skill detailed reference |

## License

[MIT](LICENSE)
