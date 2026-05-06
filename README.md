# Cortex Command

Cortex Command is an AI workflow framework for Claude Code built on a single insight: autonomous execution is only as good as the specification that precedes it.

The front half of the lifecycle is human-driven — discovery maps the problem space, refine clarifies scope, and lifecycle drives features through research, spec, plan, implement, and review. Once scope is genuinely clear, run `/cortex-core:lifecycle` for interactive development or queue refined items for `/overnight` and wake up to a morning report with PRs ready to review. For a visual of the full pipeline, see [docs/agentic-layer.md](docs/agentic-layer.md#diagram-a--main-workflow-flow).

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

Verify the install with the smoke test in [Setup guide § Verify install](docs/setup.md#verify-install).

### Plugin roster

| Plugin | Description |
|--------|-------------|
| android-dev-extras | Android development skills vendored from Google's Android Skills (Apache 2.0): R8 analyzer, edge-to-edge migration, and Android CLI orchestration |
| cortex-dev-extras | Devil's advocate inline challenge for solo deliberation |
| cortex-core | Interactive Claude Code skills, hooks, and CLI utilities from cortex-command for day-to-day development workflows |
| cortex-overnight | Integrates the cortex MCP server and overnight skill runner hooks to drive autonomous lifecycle execution |
| cortex-pr-review | Multi-agent GitHub pull request review pipeline for Claude Code |
| cortex-ui-extras | Experimental UI design skills for Claude Code interactive workflows |

## Documentation

| Guide | Covers |
|-------|--------|
| [`docs/agentic-layer.md`](docs/agentic-layer.md) | Full skill and hook inventory, workflow diagrams, lifecycle phase map |
| [`docs/setup.md`](docs/setup.md) | Installation, plugins, customization |
| [`docs/setup.md#authentication`](docs/setup.md#authentication) | Authentication setup (API key vs. OAuth token) |
| [`docs/setup.md#upgrade--maintenance`](docs/setup.md#upgrade--maintenance) | Upgrade & maintenance (CLI reinstall, plugin update, foot-guns) |
| [`docs/overnight.md`](docs/overnight.md) | Autonomous overnight runner -- planning, execution, deferral, morning review |
| [`docs/dashboard.md`](docs/dashboard.md) | Web dashboard for monitoring overnight sessions |
| [`docs/backlog.md`](docs/backlog.md) | Backlog YAML schema, readiness gates, overnight eligibility |
| [`docs/interactive-phases.md`](docs/interactive-phases.md) | What to expect at each lifecycle phase -- questions, artifacts, flow |
| [`docs/skills-reference.md`](docs/skills-reference.md) | Per-skill detailed reference |

## License

[MIT](LICENSE)
