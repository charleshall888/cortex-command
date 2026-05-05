#!/bin/bash
# PostToolUse hook: track Bash tool failures via exit code inspection.
#
# On non-zero exit code: captures tool name, exit code, and stderr to a
# session-scoped log under /tmp/.
# On >=3 failures for the same tool in one session: surfaces a warning via
# additionalContext so it appears in the conversation and morning report.
#
# Non-blocking advisory — always exits 0.
set -euo pipefail

INPUT=$(cat)

# --- Parse PostToolUse payload ---
# Expected shape:
#   { "tool_name": "Bash",
#     "tool_input": { "command": "..." },
#     "tool_response": { "exit_code": N, "stdout": "...", "stderr": "..." },
#     "session_id": "..." }
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
EXIT_CODE=$(echo "$INPUT" | jq -r '.tool_response.exit_code // 0')
STDERR_TEXT=$(echo "$INPUT" | jq -r '.tool_response.stderr // empty')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')

# Only act on Bash tool calls
if [[ "$TOOL_NAME" != "Bash" ]]; then
  exit 0
fi

# Only act on non-zero exit codes
if [[ -z "$EXIT_CODE" || "$EXIT_CODE" == "0" || "$EXIT_CODE" == "null" ]]; then
  exit 0
fi

# --- Session-scoped failure tracking ---
# Prefer the session_id field provided by Claude Code; fall back to a
# date-based key (day granularity is a reasonable session proxy).
if [[ -n "$SESSION_ID" && "$SESSION_ID" != "null" ]]; then
  SESSION_KEY="$SESSION_ID"
else
  SESSION_KEY="date-$(date -u +%Y%m%d)"
fi

TRACK_DIR="/tmp/claude-tool-failures-${SESSION_KEY}"
mkdir -p "$TRACK_DIR" 2>/dev/null || true

# Use a safe filename key (lowercase alphanumeric; extra chars → underscore).
# Use printf '%s' (not echo) to avoid a trailing newline being converted to '_'.
TOOL_KEY=$(printf '%s' "$TOOL_NAME" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '_')
COUNT_FILE="$TRACK_DIR/${TOOL_KEY}.count"
LOG_FILE="$TRACK_DIR/${TOOL_KEY}.log"

# --- Increment failure counter ---
CURRENT=0
if [[ -f "$COUNT_FILE" ]]; then
  CURRENT=$(cat "$COUNT_FILE" 2>/dev/null || echo 0)
  # Guard against non-numeric content
  [[ "$CURRENT" =~ ^[0-9]+$ ]] || CURRENT=0
fi
CURRENT=$(( CURRENT + 1 ))
echo "$CURRENT" > "$COUNT_FILE"

# --- Append structured entry to failure log (for morning report) ---
{
  printf -- '---\n'
  printf 'failure_num: %d\n' "$CURRENT"
  printf 'tool: %s\n' "$TOOL_NAME"
  printf 'exit_code: %s\n' "$EXIT_CODE"
  printf 'timestamp: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ -n "$STDERR_TEXT" && "$STDERR_TEXT" != "null" ]]; then
    printf 'stderr: |\n'
    echo "$STDERR_TEXT" | head -20 | sed 's/^/  /'
  fi
} >> "$LOG_FILE" 2>/dev/null || true

# --- Notify at threshold (exactly 3) ---
# Emit additionalContext so the failure pattern is visible in the conversation.
if (( CURRENT == 3 )); then
  ALERT="⚠️ Repeated tool failures: '${TOOL_NAME}' has failed ${CURRENT} times this session (last exit code: ${EXIT_CODE}). Details logged to ${LOG_FILE}."
  jq -n --arg ctx "$ALERT" '{
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: $ctx
    }
  }'
fi

exit 0
