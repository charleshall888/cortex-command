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

## Global Allow List: Keep Minimal

- The `settings.json` allow list applies across ALL projects on this machine — don't auto-allow write operations that other projects' users may not want
- Read-only allows (git log, gh pr view) are safe globally; write operations (gh pr create, git push) should fall through to prompt
- Overnight runs with `--dangerously-skip-permissions`, so the allow list only affects interactive sessions

## Excluded Commands Run Fully Unsandboxed

- `sandbox.excludedCommands` in `claude/settings.json` is `["gh:*", "git:*", "WebFetch", "WebSearch"]` — these tools and all their child processes bypass the Seatbelt sandbox entirely
- When git runs a commit hook, the hook and anything it spawns (e.g., `gpg`) all have host-level access; their `TMPDIR` is the host `/var/folders/...`, not the sandbox TMPDIR
- Direct Bash invocations (`gpg ...`, `cat ~/.gnupg/...`) ARE sandboxed — this asymmetry can mislead diagnosis: git children are NOT sandboxed even though isolated Bash calls are
- Before diagnosing "sandbox blocks git X": check `excludedCommands` first; do NOT design workarounds (redirect schemes, proxied sockets, `GNUPGHOME=$TMPDIR/...`) that assume git children are sandboxed
