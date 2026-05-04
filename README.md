# Cortex Command

Cortex Command is an AI workflow framework for Claude Code built on a single insight: autonomous execution is only as good as the specification that precedes it. Most AI coding tools optimize for speed. The result is fast accumulation of plausible-looking code that misses the point, because the problem space was never mapped, the scope was never agreed on, and nobody was asking the hard questions before the first line was written.

The front half of the lifecycle is deliberately human-driven. You run discovery to understand the problem space, collaborate with agents to write tight specs, and mark features ready only when the scope is genuinely clear. Once that work is done, the handoff is earned. Run `/cortex-interactive:lifecycle` to stay in the loop for interactive development, or queue a batch for `/overnight` and wake up to a morning report with PRs ready to review. The overnight runner is the natural payoff of doing the front half well.

Skills are slash commands you invoke from Claude Code. Hooks wire them into the development environment at the right moments. State files let the system resume across sessions and tool invocations. Cortex-command ships as a CLI (installed via `uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0`) plus Claude Code plugins (each installed as `<name>@cortex-command` after adding the marketplace) — everything lives in version control and is distributed without host-level symlinks.

Work flows through four stages: **discovery** maps the problem space and decomposes it into backlog tickets; **backlog** items progress from draft to refined as scope is clarified; **refine/lifecycle** drives each feature through research, spec, plan, implement, and review phases; and **overnight** executes refined items autonomously in parallel so you wake up to a morning report with PRs ready to review. For a visual of the full pipeline, see [docs/agentic-layer.md](docs/agentic-layer.md#diagram-a--main-workflow-flow).

```
        ┌──────────── /cortex-interactive:refine ──────┐
        │                           │
You ──► Clarify ──► Research ──► Spec ──► Plan ──► Implement ──► Review ──► Complete
                                    │                               ▲         │
                                    └──────── /overnight ───────────┘    /morning-review
                                         agents run autonomously              │
                                               (Plan → Complete)             You

  Complexity tier — auto-detected or set in lifecycle.config.md:
    simple   ·  standard gates only
    complex  ·  /cortex-interactive:critical-review challenges spec before Plan begins
                (auto-escalated when research surfaces ≥2 open questions)

  Criticality — controls rigor and model selection:
    low/medium  ·  tier-based review  ·  Haiku explore, Sonnet build
    high        ·  review always required  ·  Sonnet explore, Opus build
    critical    ·  parallel research + competing plans  ·  Sonnet explore, Opus build
```

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- [just](https://just.systems/) command runner (`brew install just`)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager (`brew install uv`)

> These instructions target macOS.

## Quick Start

Cortex-command ships as a CLI (installed via a tag-pinned git URL — no clone required) plus Claude Code plugins (skills + hooks + utilities):

```bash
# 1. Install the `cortex` CLI from the v0.1.0 tag
uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0

# 2. One-time: ensure the uv tool bin directory is on PATH
uv tool update-shell

# 3. In Claude Code, add the plugin marketplace
claude /plugin marketplace add charleshall888/cortex-command

# 4. Install the recommended core plugins to start
claude /plugin install cortex-interactive@cortex-command
claude /plugin install cortex-overnight-integration@cortex-command
claude /plugin install cortex-ui-extras@cortex-command
claude /plugin install cortex-pr-review@cortex-command
```

If you do not have `uv` available, the `install.sh` bootstrap script installs `uv` first and then runs the same command:

```bash
curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh
```

The cortex-overnight-integration MCP server also auto-installs the CLI on first tool call when it detects `cortex` is missing from `PATH` — interactive Claude Code users who only use cortex through plugins never need to run an explicit install step.

The [Plugin roster](#plugin-roster) below lists all 6 available plugins — install `android-dev-extras@cortex-command` and `cortex-dev-extras@cortex-command` to add the extras tier.

No symlinks into `~/.claude/` are created — plugins are discovered by Claude Code directly.

Verify the install with the smoke test in [Setup guide § Verify install](docs/setup.md#verify-install).

### Plugin roster

Cortex-command ships six plugins in this repo:

| Plugin | Description |
|--------|-------------|
| android-dev-extras | Android development skills vendored from Google's Android Skills (Apache 2.0): R8 analyzer, edge-to-edge migration, and Android CLI orchestration |
| cortex-dev-extras | Devil's advocate inline challenge for solo deliberation |
| cortex-interactive | Interactive Claude Code skills, hooks, and CLI utilities from cortex-command for day-to-day development workflows |
| cortex-overnight-integration | Integrates the cortex MCP server and overnight skill runner hooks to drive autonomous lifecycle execution |
| cortex-pr-review | Multi-agent GitHub pull request review pipeline for Claude Code |
| cortex-ui-extras | Experimental UI design skills for Claude Code interactive workflows |

For installation specifics and per-project enablement, see [`docs/setup.md`](docs/setup.md).

## Authentication

Authentication setup (API key vs. OAuth token) is documented in [Setup guide § Authentication](docs/setup.md#authentication).

## What's Inside

| Component | Description |
|-----------|-------------|
| `skills/` | Slash commands -- `/cortex-interactive:commit`, `/cortex-interactive:pr`, `/cortex-interactive:lifecycle`, `/overnight`, `/cortex-interactive:discovery`, and more |
| `hooks/` | Event handlers -- commit validation, lifecycle state injection, desktop notifications |
| `cortex_command/overnight/` | Autonomous overnight runner -- plans work, executes in parallel, writes a morning report |
| `cortex_command/dashboard/` | FastAPI web dashboard for monitoring overnight sessions |
| `lifecycle/` | Feature state machine -- research, specify, plan, implement, review, complete |
| `backlog/` | YAML-frontmatter backlog items with overnight readiness gates |
| `plugins/cortex-interactive/bin/` | CLI utilities on `PATH` via the plugin -- `cortex-archive-rewrite-paths`, `cortex-archive-sample-select`, `cortex-audit-doc`, `cortex-count-tokens`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`, `cortex-git-sync-rebase`, `cortex-jcc`, `cortex-update-item` |

## Customization

Cortex-command does not own `~/.claude/settings.json`. Edit it directly as personal machine configuration; use `~/.claude/settings.local.json` for per-machine overrides. Plugin-shipped skills and hooks are enabled per project via `.claude/settings.json`'s `enabledPlugins` map.

## Distribution

The `cortex` CLI is installed as a non-editable `uv tool` from a tag-pinned git URL. To upgrade to a newer release, run `/plugin update cortex-overnight-integration@cortex-command` from inside Claude Code (the MCP-driven path) or `uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@<tag>` from a bare shell. `cortex upgrade` itself is now an advisory printer that points at those two paths. A few operational notes:

- When cortex invokes `uv run` internally, it operates on the user's current project, not cortex's own tool venv.
- Do not run `uv tool uninstall uv` — removing uv via itself breaks the tool environment.
- Run `uv tool update-shell` once after the first `uv tool install` to add the tool bin directory to your `PATH`.
- Forkers (advanced users developing against a fork of cortex-command) install via `uv tool install git+https://github.com/<your-fork>/cortex-command.git@<branch-or-tag>` instead of the upstream URL.

## Commands

Run `just --list` to see all operational recipes. Key commands:

```
just test                  # Run all test suites
just overnight-run         # Async-spawn overnight runner (detaches; returns within 5s)
cortex overnight start     # Run overnight in detached tmux
cortex overnight status    # Print session status (use --format json for machine-readable)
just dashboard             # Start the web dashboard
just validate-commit       # Test commit message hook
just validate-skills       # Check skill frontmatter
```

## Documentation

| Guide | Covers |
|-------|--------|
| [`docs/agentic-layer.md`](docs/agentic-layer.md) | Full skill and hook inventory, workflow diagrams, lifecycle phase map |
| [`docs/setup.md`](docs/setup.md) | Installation, plugins, authentication, customization |
| [`docs/overnight.md`](docs/overnight.md) | Autonomous overnight runner -- planning, execution, deferral, morning review |
| [`docs/dashboard.md`](docs/dashboard.md) | Web dashboard for monitoring overnight sessions |
| [`docs/backlog.md`](docs/backlog.md) | Backlog YAML schema, readiness gates, overnight eligibility |
| [`docs/interactive-phases.md`](docs/interactive-phases.md) | What to expect at each lifecycle phase -- questions, artifacts, flow |
| [`docs/pipeline.md`](docs/pipeline.md) | Internal pipeline orchestration module reference |
| [`docs/skills-reference.md`](docs/skills-reference.md) | Per-skill detailed reference |

## License

[MIT](LICENSE)
