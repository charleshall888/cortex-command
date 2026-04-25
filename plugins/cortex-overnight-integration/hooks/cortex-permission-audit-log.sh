#!/bin/bash
# Notification hook: audit log for permission_prompt events.
#
# Every time a permission prompt fires, appends one line to a session-scoped
# log file under $TMPDIR so operators can diagnose sandbox tuning issues.
#
# Log line format:
#   {ISO8601 timestamp} REQUESTED type={notification_type} title={title} message={truncated_message}
#
# Log file path:
#   $TMPDIR/claude-permissions-{session_key}.log
#
# Non-blocking advisory — always exits 0.

INPUT=$(cat)

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TMPDIR="${TMPDIR:-/tmp}"
LOG_DIR="$TMPDIR"

# --- Determine session key ---
# Prefer $LIFECYCLE_SESSION_ID (injected by SessionStart hook), then
# session_id from payload, then a date-based fallback.
if [[ -n "${LIFECYCLE_SESSION_ID:-}" && "$LIFECYCLE_SESSION_ID" != "null" ]]; then
  SESSION_KEY="$LIFECYCLE_SESSION_ID"
else
  # Try to extract session_id from payload
  if command -v jq >/dev/null 2>&1; then
    SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  else
    SESSION_ID=""
  fi

  if [[ -n "$SESSION_ID" && "$SESSION_ID" != "null" ]]; then
    SESSION_KEY="$SESSION_ID"
  else
    SESSION_KEY="date-$(date -u +%Y%m%d)"
  fi
fi

LOG_FILE="$LOG_DIR/claude-permissions-${SESSION_KEY}.log"

# Guard: if log dir is not writable, exit silently (non-blocking advisory).
if ! touch "$LOG_FILE" 2>/dev/null; then
  exit 0
fi

# --- Parse payload ---
# Only handle permission_prompt events; skip others silently.
if ! command -v jq >/dev/null 2>&1; then
  printf '%s REQUESTED jq_unavailable\n' "$TIMESTAMP" >> "$LOG_FILE" 2>/dev/null || true
  exit 0
fi

# Bail out gracefully on empty input.
if [[ -z "$INPUT" ]]; then
  printf '%s PARSE_ERROR\n' "$TIMESTAMP" >> "$LOG_FILE" 2>/dev/null || true
  exit 0
fi

# Check event type — only log permission_prompt events.
EVENT=$(echo "$INPUT" | jq -r '.notification_type // empty' 2>/dev/null || true)
if [[ -n "$EVENT" && "$EVENT" != "null" && "$EVENT" != "permission_prompt" ]]; then
  exit 0
fi

# Extract fields — fall back gracefully if absent.
NOTIF_TYPE=$(echo "$INPUT" | jq -r '.notification_type // "unknown"' 2>/dev/null || echo "unknown")
if [[ -z "$NOTIF_TYPE" || "$NOTIF_TYPE" == "null" ]]; then
  NOTIF_TYPE="unknown"
fi

TITLE=$(echo "$INPUT" | jq -r '.title // "unknown"' 2>/dev/null || echo "unknown")
if [[ -z "$TITLE" || "$TITLE" == "null" ]]; then
  TITLE="unknown"
fi

MESSAGE=$(echo "$INPUT" | jq -r '.message // ""' 2>/dev/null || true)
if [[ -z "$MESSAGE" || "$MESSAGE" == "null" ]]; then
  MESSAGE=""
fi

# Truncate message to 200 chars.
TRUNCATED_MESSAGE="${MESSAGE:0:200}"

# --- Write log line ---
printf '%s REQUESTED type=%s title=%s message=%s\n' "$TIMESTAMP" "$NOTIF_TYPE" "$TITLE" "$TRUNCATED_MESSAGE" >> "$LOG_FILE" 2>/dev/null || true

exit 0
