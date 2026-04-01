#!/bin/bash
# Hook: clean up .session file when a Claude Code session ends.
# Registered on SessionEnd. Skips cleanup when reason is "clear"
# (session continues after /clear).
set -euo pipefail

INPUT=$(cat)

# --- Parse input ---
REASON=$(echo "$INPUT" | jq -r '.reason // ""')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
[[ -n "$CWD" ]] || CWD="$(pwd)"

# Skip cleanup on /clear — session continues
[[ "$REASON" != "clear" ]] || exit 0

# Nothing to match without a session ID
[[ -n "$SESSION_ID" ]] || exit 0

LIFECYCLE_DIR="$CWD/lifecycle"

# No lifecycle directory — nothing to clean
[[ -d "$LIFECYCLE_DIR" ]] || exit 0

# --- Scan for .session files matching this session ---
for session_file in "$LIFECYCLE_DIR"/*/.session; do
  [[ -f "$session_file" ]] || continue
  file_id=$(cat "$session_file" 2>/dev/null) || continue
  if [[ "$file_id" == "$SESSION_ID" ]]; then
    rm -f "$session_file"
    rm -f "${session_file%.session}.session-owner"
  fi
done

# --- Prune stale agent isolation worktrees and branches ---
(
  cd "$CWD"
  git rev-parse --show-toplevel > /dev/null 2>&1 || exit 0
  # Remove physical agent worktrees (directory + git registration)
  while IFS= read -r wt_path; do
    [[ -n "$wt_path" ]] || continue
    git worktree remove --force "$wt_path" 2>/dev/null \
      || echo "Warning: could not remove worktree $wt_path" >&2
  done < <(git worktree list --porcelain 2>/dev/null \
    | awk '/^worktree/ && $2 ~ /\.claude\/worktrees\/agent-/ { print $2 }' \
    || { echo "Warning: git worktree list failed" >&2; })
  git worktree prune 2>/dev/null \
    || echo "Warning: git worktree prune failed" >&2
  ACTIVE_BRANCHES=$(git worktree list --porcelain 2>/dev/null \
    | awk '/^branch/ { print $2 }')
  while IFS= read -r branch; do
    [[ -n "$branch" ]] || continue
    if ! echo "$ACTIVE_BRANCHES" | grep -qF "refs/heads/$branch"; then
      git branch -D "$branch" 2>/dev/null \
        && echo "Deleted agent worktree branch: $branch" \
        || echo "Warning: could not delete branch $branch" >&2
    fi
  done < <(git branch --list 'worktree/agent-*' --format='%(refname:short)' 2>/dev/null)
) || true

exit 0
