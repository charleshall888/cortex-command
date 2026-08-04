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

LIFECYCLE_DIR="$CWD/cortex/lifecycle"

# No cortex/lifecycle directory — nothing to clean
[[ -d "$LIFECYCLE_DIR" ]] || exit 0

# --- Scan for .session files matching this session ---
for session_file in "$LIFECYCLE_DIR"/*/.session; do
  [[ -f "$session_file" ]] || continue
  file_id=$(cat "$session_file" 2>/dev/null) || continue
  if [[ "$file_id" == "$SESSION_ID" ]]; then
    rm -f "$session_file"
    rm -f "${session_file%.session}.session-owner"
    # Stop-hook auto-continue state is session-scoped: a stale counter would
    # spend the next session's cap, and a stale hand-back marker would
    # silently disable auto-continue for a session that never asked for it.
    rm -f "${session_file%.session}.autocontinue"
    rm -f "${session_file%.session}.autocontinue-off"
  fi
done

exit 0
