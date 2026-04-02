<!-- Sandbox-specific behaviors: rules that apply when Claude Code runs in a sandboxed environment with Bash allow/deny rules -->

## Git Commands: Never Use `git -C`

- Run `git status`, `git diff`, `git log`, etc. directly -- do NOT use `git -C <path>`
- The `-C` flag causes commands to not match permission allow rules like `Bash(git status *)`
- It also bypasses deny rules (e.g., `git -C /path push --force` won't match `Bash(git push --force *)`)
- The working directory is already the repo root, so `-C` is unnecessary

## Compound Commands: Avoid Chaining

- Do NOT chain commands with `&&`, `;`, or `|` -- the permission system evaluates the full string as one unit
- Individual allow rules like `Bash(git add *)` and `Bash(git commit *)` won't match `git add file && git commit -m msg`
- Use separate sequential tool calls instead

## Git Commits: Sandbox Constraints

- Do NOT use `$(cat <<'EOF' ... EOF)` for commit messages -- it creates temp files that fail in sandboxed environments
