#!/bin/bash
# Remote push notification via ntfy.sh HTTP API.
# Sends Android push notifications when Claude Code sessions need attention.
# Agent-agnostic: receives notification type as $1 (permission, idle, complete).
#
# Requires NTFY_TOPIC environment variable. If unset, exits silently.
# Identifies the tmux session name (or PWD basename as fallback) in the message.

# Exit silently if ntfy topic not configured
[ -z "$NTFY_TOPIC" ] && exit 0
[ -z "$TMUX" ] && exit 0
[ -n "$SKIP_NOTIFICATIONS" ] && exit 0

# Suppress notifications for subagent sessions — Stop hook JSON includes agent_id only for subagents.
if [ ! -t 0 ]; then
  _HOOK_INPUT=$(cat)
  _AGENT_ID=$(echo "$_HOOK_INPUT" | jq -r '.agent_id // empty' 2>/dev/null || echo "")
  [ -n "$_AGENT_ID" ] && exit 0
fi

TYPE="${1:-complete}"

# Detect session name for identification
if [ -n "$TMUX" ]; then
  SESSION=$(tmux display-message -p '#S' 2>/dev/null)
fi
SESSION="${SESSION:-$(basename "$PWD")}"

case "$TYPE" in
  permission)
    TITLE="⏸ $SESSION"
    MESSAGE="Permission needed"
    TAGS="lock"
    PRIORITY="default"
    ;;
  complete)
    TITLE="✅ $SESSION"
    MESSAGE="Done"
    TAGS="white_check_mark"
    PRIORITY="default"
    ;;
  idle)
    TITLE="💤 $SESSION"
    MESSAGE="Waiting for input"
    TAGS="hourglass"
    PRIORITY="low"
    ;;
  *)
    TITLE="🤖 $SESSION"
    MESSAGE="$TYPE"
    TAGS="robot"
    PRIORITY="default"
    ;;
esac

curl -s --max-time 5 \
  -d "$MESSAGE" \
  -H "Title: $TITLE" \
  -H "Tags: $TAGS" \
  -H "Priority: $PRIORITY" \
  "https://ntfy.sh/$NTFY_TOPIC" 2>/dev/null

exit 0
