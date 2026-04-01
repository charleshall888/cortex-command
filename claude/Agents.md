# Global Agent Instructions

These instructions apply to all projects on this machine.

## Git Commands: Never Use `git -C`

- Run `git status`, `git diff`, `git log`, etc. directly -- do NOT use `git -C <path>`
- The `-C` flag causes commands to not match permission allow rules like `Bash(git status *)`
- It also bypasses deny rules (e.g., `git -C /path push --force` won't match `Bash(git push --force *)`)
- The working directory is already the repo root, so `-C` is unnecessary

## Compound Commands: Avoid Chaining

- Do NOT chain commands with `&&`, `;`, or `|` -- the permission system evaluates the full string as one unit
- Individual allow rules like `Bash(git add *)` and `Bash(git commit *)` won't match `git add file && git commit -m msg`
- Use separate sequential tool calls instead

## Git Commits: Always Use the `/commit` Skill

- **Always invoke the `/commit` skill** -- never run `git commit` manually outside of the skill
- The skill handles message formatting, validation, and sandbox GPG signing correctly
- Do NOT use `$(cat <<'EOF' ... EOF)` for commit messages -- it creates temp files that fail in sandboxed environments
- For single-line commits: `git commit -m "Subject line here"`
- For multi-line commits, use multiple `-m` flags -- git inserts a blank line between each:
  ```
  git commit -m "Subject line" -m "- Bullet one
  - Bullet two"
  ```

## Settings Architecture

- Global Claude Code settings live at `~/.claude/settings.json` (symlinked from `cortex-command/claude/settings.json`)
- Global settings include: curated allow/deny list + `sandbox.autoAllowBashIfSandboxed: true`
- Projects opt into sandbox individually; non-sandboxed projects use the allow/deny rules

## Conditional Loading

| Trigger | Read |
|---------|------|
| Modifying SKILL.md files, Agents.md, CLAUDE.md, or reference docs | `~/.claude/reference/context-file-authoring.md` and `~/.claude/reference/claude-skills.md` |
| About to claim success, tests pass, build succeeds, bug fixed, or agent completed | `~/.claude/reference/verification-mindset.md` |
| Deciding whether to dispatch agents in parallel | `~/.claude/reference/parallel-agents.md` |

When creating or editing SKILL.md files, invoke `/skill-creator`. For editing existing skills, focus on Step 4 (authoring rules + pattern check) -- not the full new-skill workflow.
