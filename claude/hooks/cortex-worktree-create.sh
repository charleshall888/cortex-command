#!/bin/bash
# WorktreeCreate hook for Claude Code interactive --worktree sessions.
# Called by Claude Code instead of the default `git worktree add`.
# Receives JSON on stdin with fields: session_id, cwd, hook_event_name, name
#
# Outputs the absolute worktree path to stdout (used by Claude Code).
# All status/debug messages go to stderr only.
# Exit 0 on success; non-zero causes `claude --worktree` to fail.

set -euo pipefail

# PATH bootstrap: when Claude Code is launched via macOS Dock/Finder, the
# session inherits launchd's minimal PATH, which excludes the user-site bin
# directories where cortex-command's console scripts (cortex-worktree-resolve)
# live. Prepend the dominant cortex-tool bin layouts so the resolver is
# reachable regardless of launch context. This does NOT mask a genuinely
# uninstalled tool — see the diagnostic below.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# Read stdin once into a variable so we can parse multiple fields
INPUT=$(cat)

# Extract fields from JSON
CWD=$(echo "$INPUT" | jq -r '.cwd')
NAME=$(echo "$INPUT" | jq -r '.name')

if [ -z "$CWD" ] || [ "$CWD" = "null" ]; then
  echo "WorktreeCreate hook error: missing 'cwd' in hook input" >&2
  exit 1
fi

if [ -z "$NAME" ] || [ "$NAME" = "null" ]; then
  echo "WorktreeCreate hook error: missing 'name' in hook input" >&2
  exit 1
fi

# Single-chokepoint path resolution: shell out to the Python resolver via
# the cortex-worktree-resolve console script. Both Python and bash dispatch
# paths share one source of truth (cortex_command.pipeline.worktree
# .resolve_worktree_root). Do NOT duplicate the path logic inline — the hook
# fails loud if the resolver is unreachable.
if ! command -v cortex-worktree-resolve >/dev/null 2>&1; then
  echo "WorktreeCreate hook error: cortex-worktree-resolve not on PATH or failed. Possible causes: (1) cortex-command not installed (install via 'uv tool install git+https://github.com/charleshall888/cortex-command.git@<tag>'); (2) Claude Code launched via Dock/Finder on macOS — launchd's minimal PATH may not include the cortex-tool bin dir; try launching Claude Code from Terminal, OR add the cortex-tool bin path to a launchd plist (see docs/setup.md)." >&2
  exit 1
fi

if ! WORKTREE_PATH=$(cortex-worktree-resolve "$NAME"); then
  echo "WorktreeCreate hook error: cortex-worktree-resolve not on PATH or failed. Possible causes: (1) cortex-command not installed (install via 'uv tool install git+https://github.com/charleshall888/cortex-command.git@<tag>'); (2) Claude Code launched via Dock/Finder on macOS — launchd's minimal PATH may not include the cortex-tool bin dir; try launching Claude Code from Terminal, OR add the cortex-tool bin path to a launchd plist (see docs/setup.md)." >&2
  exit 1
fi
BRANCH="worktree/$NAME"

# Edge case: worktree path already exists — fail clearly
if [ -e "$WORKTREE_PATH" ]; then
  echo "WorktreeCreate hook error: worktree path already exists: $WORKTREE_PATH" >&2
  exit 1
fi

echo "Creating worktree '$NAME' at $WORKTREE_PATH (branch: $BRANCH)" >&2

# Ensure the parent directory exists
mkdir -p "$(dirname "$WORKTREE_PATH")" >&2

# Create the worktree with a new branch from HEAD
# Run git from the repo root so worktree add resolves correctly
(cd "$CWD" && git worktree add "$WORKTREE_PATH" -b "$BRANCH" HEAD) >&2

echo "Worktree created successfully" >&2

# Symlink .venv into the worktree so Python tooling (runner.sh venv check) works
if [ -d "$CWD/.venv" ]; then
  ln -sf "$CWD/.venv" "$WORKTREE_PATH/.venv"
  echo "Symlinked .venv into worktree" >&2
fi

# Print the absolute worktree path to stdout — this is the return value Claude Code uses.
#
# NOTE (updatedPermissions research, 2026-03-27):
# WorktreeCreate command hooks MUST output a plain-text path on stdout.
# JSON stdout (and therefore updatedPermissions/addRules) is NOT supported
# for this hook type. The updatedPermissions mechanism is exclusive to
# PermissionRequest hooks, where it lives inside hookSpecificOutput.decision.
# There is no way for a WorktreeCreate hook to inject allow rules into the
# owning session. Any permission-rule injection for worktree paths must use
# a separate PermissionRequest hook or pre-configured allow rules in settings.
# See: https://code.claude.com/docs/en/hooks (WorktreeCreate, PermissionRequest)
echo "$WORKTREE_PATH"
