# Cortex Command

Cortex Command is an AI workflow framework for Claude Code built on a single insight: autonomous execution is only as good as the specification that precedes it. Most AI coding tools optimize for speed. The result is fast accumulation of plausible-looking code that misses the point -- because the problem space was never mapped, the scope was never agreed on, and nobody was asking the hard questions before the first line was written.

The front half of the lifecycle is deliberately human-driven. You run discovery to understand the problem space, collaborate with agents to write tight specs, and mark features ready only when the scope is genuinely clear. Once that work is done, the handoff is earned. Run `/lifecycle` to stay in the loop for interactive, one-feature-at-a-time development, or queue a batch for `/overnight` and wake up to a morning report with PRs ready to review. The overnight runner isn't a special mode -- it's the natural payoff of doing the front half well.

Skills are the primitive units -- slash commands you invoke from Claude Code. Hooks wire them into the development environment at the right moments. State files let the system resume across sessions and tool invocations. All config is deployed via symlinks so the whole thing lives in version control.

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
 │  status: draft ──► /refine ──► ready                                     │
 │                    (Clarify + Research + Spec per ticket)                │
 └──────────────────────┬───────────────────────────┬───────────────────────┘
                        │ interactive               │ autonomous
          ┌─────────────▼────────────┐    ┌─────────▼────────────────────┐
          │  /lifecycle              │    │  /overnight                  │
          │  one feature at a time   │    │  selects status:ready items  │
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

```bash
git clone https://github.com/charleshall888/cortex-command.git ~/cortex-command
cd ~/cortex-command
just setup
```

> **Important:** Add the following to your shell profile (`.zshrc`, `.bashrc`, etc.):
>
> ```bash
> export CORTEX_COMMAND_ROOT="$HOME/cortex-command"
> ```
>
> Several components (the `jcc` wrapper, overnight runner) require this variable.
> If you clone to a different location, update the path accordingly. The sandbox
> `allowWrite` path is configured automatically by `just setup`.

### Backup Warning

`just setup` creates symlinks that **replace** existing files in `~/.claude/`. If you already have Claude Code configured, back up these files first:

- `~/.claude/settings.json`
- `~/.claude/CLAUDE.md`
- `~/.claude/statusline.sh`
- Any custom skills in `~/.claude/skills/`
- Any custom hooks in `~/.claude/hooks/`

The setup recipe will warn before overwriting non-symlink files at these locations.

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

`claude/settings.json` is tracked and symlinked to `~/.claude/settings.json`. Review and adjust the model, session retention, thinking mode, and experimental flags for your own setup. Use `settings.local.json` in any project for per-machine overrides without modifying the tracked file.

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
| [`docs/setup.md`](docs/setup.md) | Installation, symlinks, macOS caffeinate, GPG/PAT config |
| [`docs/overnight.md`](docs/overnight.md) | Autonomous overnight runner -- planning, execution, deferral, morning review |
| [`docs/dashboard.md`](docs/dashboard.md) | Web dashboard for monitoring overnight sessions |
| [`docs/backlog.md`](docs/backlog.md) | Backlog YAML schema, readiness gates, overnight eligibility |
| [`docs/interactive-phases.md`](docs/interactive-phases.md) | What to expect at each lifecycle phase -- questions, artifacts, flow |
| [`docs/pipeline.md`](docs/pipeline.md) | Internal pipeline orchestration module reference |
| [`docs/skills-reference.md`](docs/skills-reference.md) | Per-skill detailed reference |

## License

[MIT](LICENSE)
