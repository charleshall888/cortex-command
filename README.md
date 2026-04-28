# Cortex Command

Cortex Command is an AI workflow framework for Claude Code built on a single insight: autonomous execution is only as good as the specification that precedes it. Most AI coding tools optimize for speed. The result is fast accumulation of plausible-looking code that misses the point, because the problem space was never mapped, the scope was never agreed on, and nobody was asking the hard questions before the first line was written.

The front half of the lifecycle is deliberately human-driven. You run discovery to understand the problem space, collaborate with agents to write tight specs, and mark features ready only when the scope is genuinely clear. Once that work is done, the handoff is earned. Run `/cortex-interactive:lifecycle` to stay in the loop for interactive development, or queue a batch for `/overnight` and wake up to a morning report with PRs ready to review. The overnight runner is the natural payoff of doing the front half well.

Skills are slash commands you invoke from Claude Code. Hooks wire them into the development environment at the right moments. State files let the system resume across sessions and tool invocations. Cortex-command ships as a CLI (installed via `uv tool install -e .`) plus Claude Code plugins (each installed as `<name>@cortex-command` after adding the marketplace) — everything lives in version control and is distributed without host-level symlinks.

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

> These instructions target macOS. For Linux or Windows setup, see [`docs/setup.md`](docs/setup.md).

## Quick Start

Cortex-command ships as a CLI (installed as an editable `uv tool`) plus Claude Code plugins (skills + hooks + utilities). Installation has three steps:

```bash
# 1. Bootstrap: clones the repo to ~/.cortex and installs the `cortex` CLI
curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh

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

The [Plugin roster](#plugin-roster) below lists all 6 available plugins — install `android-dev-extras@cortex-command` and `cortex-dev-extras@cortex-command` to add the extras tier.

No symlinks into `~/.claude/` are created — plugins are discovered by Claude Code directly.

Verify the install with the smoke test in [Setup guide § Verify install](docs/setup.md#verify-install).

### Plugin roster

Cortex-command ships six plugins in this repo, split into core and extras tiers:

| Plugin | Tier | Notes |
|--------|------|-------|
| cortex-interactive | core | Interactive skills + hooks (lifecycle, commit, pr, etc.) |
| cortex-overnight-integration | core | Autonomous overnight runner integration |
| cortex-ui-extras | extras | Experimental — UI design skills |
| cortex-pr-review | extras | PR-review automation |
| android-dev-extras | extras | Android development helpers |
| cortex-dev-extras | extras | Cortex-command development helpers |

For installation specifics and per-project enablement, see [`docs/setup.md`](docs/setup.md).

## Authentication

The overnight runner and some CLI utilities need API credentials. Choose based on your account type:

### API Key (work / Console billing)

```bash
printf '%s' 'sk-ant-api03-...' > ~/.claude/work-api-key
chmod 600 ~/.claude/work-api-key
```

Add to `~/.claude/settings.local.json`:
```json
{ "apiKeyHelper": "cat ~/.claude/work-api-key" }
```

### OAuth Token (Claude Pro / Max subscription)

```bash
claude setup-token                  # opens browser, prints token (valid 1 year)
printf '%s' 'sk-ant-oat01-...' > ~/.claude/personal-oauth-token
chmod 600 ~/.claude/personal-oauth-token
```

The overnight runner reads this file automatically when no `apiKeyHelper` is configured.

### Using Both

Set `apiKeyHelper` in work repos' `.claude/settings.local.json`. Store the OAuth token at `~/.claude/personal-oauth-token`. The runner uses `apiKeyHelper` when present, falls back to the OAuth token when not. See [`docs/overnight-operations.md`](docs/overnight-operations.md#auth-resolution-apikeyhelper-and-env-var-fallback-order) for the full precedence chain.

> **Note:** OAuth tokens work with `claude -p` and the Agent SDK. Standalone utilities (`cortex-count-tokens`, `cortex-audit-doc`) call the Anthropic API directly and require an API key.

## What's Inside

| Component | Description |
|-----------|-------------|
| `skills/` | Slash commands -- `/cortex-interactive:commit`, `/cortex-interactive:pr`, `/cortex-interactive:lifecycle`, `/overnight`, `/cortex-interactive:discovery`, and more |
| `hooks/` | Event handlers -- commit validation, lifecycle state injection, desktop notifications |
| `cortex_command/overnight/` | Autonomous overnight runner -- plans work, executes in parallel, writes a morning report |
| `cortex_command/dashboard/` | FastAPI web dashboard for monitoring overnight sessions |
| `lifecycle/` | Feature state machine -- research, specify, plan, implement, review, complete |
| `backlog/` | YAML-frontmatter backlog items with overnight readiness gates |
| `plugins/cortex-interactive/bin/` | CLI utilities on `PATH` via the plugin -- `cortex-jcc` (recipe wrapper), `cortex-count-tokens`, `cortex-audit-doc`, `cortex-update-item`, `cortex-generate-backlog-index`, `cortex-create-backlog-item`, `cortex-git-sync-rebase` |

## Customization

Cortex-command does not own `~/.claude/settings.json`. Edit it directly as personal machine configuration; use `~/.claude/settings.local.json` for per-machine overrides. Plugin-shipped skills and hooks are enabled per project via `.claude/settings.json`'s `enabledPlugins` map.

## Distribution

The `cortex` CLI is installed as an editable `uv tool`; a few constraints apply:

- When cortex invokes `uv run` internally, it operates on the user's current project, not cortex's own tool venv.
- Do not run `uv tool uninstall uv` — removing uv via itself breaks the tool environment.
- Adding or renaming `[project.scripts]` entries requires re-running `uv tool install -e . --force` to refresh shims.
- Run `uv tool update-shell` once after the first `uv tool install` to add the tool bin directory to your `PATH`.

## Commands

Run `just --list` to see all operational recipes. Key commands:

```
just test                  # Run all test suites
just overnight-run         # Run overnight in foreground
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
