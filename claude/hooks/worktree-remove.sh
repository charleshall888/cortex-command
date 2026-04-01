#!/bin/bash
# Hook: send a notification when Claude Code removes a --worktree session worktree.
# Registered on WorktreeRemove. Exit codes are ignored by Claude Code — this hook
# cannot block removal. Errors are handled gracefully (no set -e).

INPUT=$(cat)

WORKTREE_PATH=$(echo "$INPUT" | jq -r '.worktree_path // empty' 2>/dev/null)

if [ -z "$WORKTREE_PATH" ]; then
  echo "worktree-remove: missing worktree_path in hook input" >&2
  exit 1
fi

NAME=$(basename "$WORKTREE_PATH")

NOTIFY="$HOME/.claude/notify.sh"
if [ -x "$NOTIFY" ]; then
  "$NOTIFY" "Worktree removed: $NAME"
else
  echo "worktree-remove: notify.sh not found or not executable at $NOTIFY" >&2
fi

exit 0
