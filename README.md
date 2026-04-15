# Cortex Command

Cortex Command is an AI workflow framework for Claude Code built on a single insight: autonomous execution is only as good as the specification that precedes it. Most AI coding tools optimize for speed. The result is fast accumulation of plausible-looking code that misses the point, because the problem space was never mapped, the scope was never agreed on, and nobody was asking the hard questions before the first line was written.

The front half of the lifecycle is deliberately human-driven. You run discovery to understand the problem space, collaborate with agents to write tight specs, and mark features ready only when the scope is genuinely clear. Once that work is done, the handoff is earned. Run `/lifecycle` to stay in the loop for interactive development, or queue a batch for `/overnight` and wake up to a morning report with PRs ready to review. The overnight runner is the natural payoff of doing the front half well.

Skills are slash commands you invoke from Claude Code. Hooks wire them into the development environment at the right moments. State files let the system resume across sessions and tool invocations. All config is deployed via symlinks so the whole thing lives in version control.

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  REQUIREMENTS   requirements/project.md  ·  requirements/{area}.md       │
 └────────────────────────────────────┬─────────────────────────────────────┘
                                      │ informs scope
 ┌────────────────────────────────────▼─────────────────────────────────────┐
 │  DISCOVERY   /discovery [topic]                                          │
 │  Researches problem space, decomposes into epics and backlog tickets     │
 └────────────────────────────────────┬─────────────────────────────────────┘
                                      │
 ┌────────────────────────────────────▼─────────────────────────────────────┐
 │  BACKLOG   backlog/NNN-feature.md                                        │
 │  status: draft → refined → complete                                      │
 └──────────────────────┬───────────────────────────┬───────────────────────┘
                        │ interactive               │ autonomous
                        │                  ┌────────▼─────────────────────┐
                        │                  │  /refine [item] × N          │
                        │                  │  each in a separate session  │
                        │                  │  run in parallel per ticket  │
                        │                  │  Clarify → Research → Spec   │
                        │                  │  sets status:refined         │
                        │                  └────────┬─────────────────────┘
          ┌─────────────▼────────────┐    ┌─────────▼────────────────────┐
          │  /lifecycle              │    │  /overnight                  │
          │  one feature at a time   │    │  selects status:refined items│
          │  human-in-the-loop       │    │  runs features in parallel   │
          └──────────────────────────┘    └───────────────┬──────────────┘
                                                          │
                                         ┌────────────────▼───────────────┐
                                         │  /morning-review               │
                                         │  review artifacts              │
                                         │  answer deferred Q&A           │
                                         │  advance to complete           │
                                         └────────────────────────────────┘
```

```
        ┌──────────── /refine ──────┐
        │                           │
You ──► Clarify ──► Research ──► Spec ──► Plan ──► Implement ──► Review ──► Complete
                                    │                               ▲         │
                                    └──────── /overnight ───────────┘    /morning-review
                                         agents run autonomously              │
                                               (Plan → Complete)             You

  Complexity tier — auto-detected or set in lifecycle.config.md:
    simple   ·  standard gates only
    complex  ·  /critical-review challenges spec before Plan begins
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

> **Back up first.** `just setup` creates symlinks that replace existing files in `~/.claude/`. If you already have Claude Code configured:
> ```bash
> cp -r ~/.claude/settings.json ~/.claude/settings.json.backup 2>/dev/null
> cp -r ~/.claude/settings.local.json ~/.claude/settings.local.json.backup 2>/dev/null
> cp -r ~/.claude/skills ~/.claude/skills.backup 2>/dev/null
> cp -r ~/.claude/hooks ~/.claude/hooks.backup 2>/dev/null
> ```
> `just setup` does **not** touch `~/.claude/CLAUDE.md` — it deploys to `~/.claude/rules/` only.

```bash
git clone https://github.com/charleshall888/cortex-command.git ~/cortex-command
cd ~/cortex-command
just setup
```

Then add to your shell profile (`.zshrc`, `.bashrc`, etc.):

```bash
export CORTEX_COMMAND_ROOT="$HOME/cortex-command"
```

Restart your shell. Run `just check-symlinks` to verify.

### Optional plugins

UI design skills and PR-review automation are available as opt-in Claude Code plugins in a companion repo:

```bash
claude /plugin marketplace add https://github.com/charleshall888/cortex-command-plugins
```

Then enable per project in `.claude/settings.json`:

```json
{ "enabledPlugins": { "cortex-ui-extras": true } }
```

See [cortex-command-plugins](https://github.com/charleshall888/cortex-command-plugins) for the full skill list and install instructions.

### Limited / custom installation

`just setup` deploys the full agentic layer. One thing composes cleanly when omitted:

- **Three optional hooks** (sandbox GPG, desktop notifications, remote notifications) — run `/setup-merge` in Claude Code after `just setup` and answer `n` to the ones you don't want.

Anything narrower needs reading the `justfile` and skill sources directly — see [`docs/setup.md#limited--custom-installation`](docs/setup.md#limited--custom-installation) for the rationale.

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

> **Note:** OAuth tokens work with `claude -p` and the Agent SDK. Standalone utilities (`count-tokens`, `audit-doc`) call the Anthropic API directly and require an API key.

## What's Inside

| Component | Description |
|-----------|-------------|
| `skills/` | Slash commands -- `/commit`, `/pr`, `/lifecycle`, `/overnight`, `/discovery`, and more |
| `hooks/` | Event handlers -- commit validation, lifecycle state injection, desktop notifications |
| `claude/overnight/` | Autonomous overnight runner -- plans work, executes in parallel, writes a morning report |
| `claude/dashboard/` | FastAPI web dashboard for monitoring overnight sessions |
| `lifecycle/` | Feature state machine -- research, specify, plan, implement, review, complete |
| `backlog/` | YAML-frontmatter backlog items with overnight readiness gates |
| `claude/reference/` | Reference docs loaded conditionally by agent instructions |
| `bin/` | CLI utilities deployed to `~/.local/bin/` -- `jcc` (recipe wrapper), `count-tokens`, `audit-doc`, `overnight-start` |

## Customization

`claude/settings.json` is the repo defaults template — `just setup` copies it to `~/.claude/settings.json` on first install. Run `/setup-merge` to pull updated repo defaults into your settings. Use `settings.local.json` for per-machine overrides.

## Commands

Run `just` to see all recipes (30+). Key commands:

```
just setup                 # Full install (symlinks + Python deps)
just check-symlinks        # Verify all symlinks are intact
just test                  # Run all test suites
just overnight-run         # Run overnight in foreground
just overnight-start       # Run overnight in detached tmux
just overnight-status      # Live status display
just dashboard             # Start the web dashboard
just validate-commit       # Test commit message hook
just validate-skills       # Check skill frontmatter
```

## Documentation

| Guide | Covers |
|-------|--------|
| [`docs/agentic-layer.md`](docs/agentic-layer.md) | Full skill and hook inventory, workflow diagrams, lifecycle phase map |
| [`docs/setup.md`](docs/setup.md) | Installation, symlinks, authentication, customization |
| [`docs/overnight.md`](docs/overnight.md) | Autonomous overnight runner -- planning, execution, deferral, morning review |
| [`docs/dashboard.md`](docs/dashboard.md) | Web dashboard for monitoring overnight sessions |
| [`docs/backlog.md`](docs/backlog.md) | Backlog YAML schema, readiness gates, overnight eligibility |
| [`docs/interactive-phases.md`](docs/interactive-phases.md) | What to expect at each lifecycle phase -- questions, artifacts, flow |
| [`docs/pipeline.md`](docs/pipeline.md) | Internal pipeline orchestration module reference |
| [`docs/skills-reference.md`](docs/skills-reference.md) | Per-skill detailed reference |

## License

[MIT](LICENSE)
