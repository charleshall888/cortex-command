<!-- Cortex-command-specific instructions: applies only when the full cortex-command framework is installed (repo owner via just setup-force) -->

# Global Agent Instructions

These instructions apply to all projects on this machine.

## Git Commits: Always Use the `/commit` Skill

- **Always invoke the `/commit` skill** -- never run `git commit` manually outside of the skill
- The skill handles message formatting, validation, and sandbox GPG signing correctly

## Settings Architecture

- Global Claude Code settings live at `~/.claude/settings.json` (managed as a regular file; repo defaults merged via `/setup-merge`)
- Global settings include: curated allow/deny list + `sandbox.autoAllowBashIfSandboxed: true`
- Projects opt into sandbox individually; non-sandboxed projects use the allow/deny rules

## Subagent Model Selection

When spawning subagents via the Agent tool, use `model: "sonnet"` by default. Subagents start with fresh context and don't need the 1M window -- Sonnet is sufficient for exploration, research, review, and planning tasks. Reserve Opus (via `model: "opus"` or omitting `model` to inherit) for implementation sub-tasks on high/critical features only.

Do NOT set `CLAUDE_CODE_SUBAGENT_MODEL` -- the env var overrides all per-invocation model params, preventing Opus escalation when needed.

## Conditional Loading

| Trigger | Read |
|---------|------|
| Modifying SKILL.md files, Agents.md, CLAUDE.md, or reference docs | `~/.claude/reference/context-file-authoring.md` and `~/.claude/reference/claude-skills.md` |
| About to claim success, tests pass, build succeeds, bug fixed, or agent completed | `~/.claude/reference/verification-mindset.md` |
| Deciding whether to dispatch agents in parallel | `~/.claude/reference/parallel-agents.md` |

When creating or editing SKILL.md files, invoke `/skill-creator`. For editing existing skills, focus on Step 4 (authoring rules + pattern check) -- not the full new-skill workflow.
