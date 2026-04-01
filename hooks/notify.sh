#!/bin/bash
# Shared notification helper for AI coding agents.
# Sends macOS notification and terminal bell.
# Called by both Claude Code (Stop/Notification hooks) and Cursor (stop hook).
#
# TODO: When Ghostty adds native notification suppression (tracking:
# https://github.com/ghostty-org/ghostty/discussions/3555), replace this
# with the built-in `notification-handling-method` config option to suppress
# notifications when the terminal is focused. This will be cleaner than
# using terminal-notifier externally.

# Allow tests (and any caller) to suppress notifications without side effects.
[ "${SKIP_NOTIFICATIONS:-0}" = "1" ] && exit 0

# Suppress notifications for subagent sessions — Stop hook JSON includes agent_id only for subagents.
if [ ! -t 0 ]; then
  _HOOK_INPUT=$(cat)
  _AGENT_ID=$(echo "$_HOOK_INPUT" | jq -r '.agent_id // empty' 2>/dev/null || echo "")
  [ -n "$_AGENT_ID" ] && exit 0
fi

TYPE="${1:-complete}"

case "$TYPE" in
  permission)
    TITLE="Claude Code"
    SUBTITLE="🔐 Action Required"
    MESSAGE="Permission needed to continue"
    SOUND="Ping"
    ;;
  idle)
    TITLE="Claude Code"
    SUBTITLE="💬 Waiting"
    MESSAGE="Ready for your input"
    SOUND="Ping"
    ;;
  complete)
    TITLE="Claude Code"
    SUBTITLE="✅ Done"
    MESSAGE="Task completed"
    SOUND="Glass"
    ;;
  *)
    TITLE="Claude Code"
    SUBTITLE=""
    MESSAGE="$TYPE"
    SOUND="Glass"
    ;;
esac

# Send macOS notification (click to focus Ghostty)
if command -v terminal-notifier >/dev/null 2>&1; then
  terminal-notifier \
    -title "$TITLE" \
    -subtitle "$SUBTITLE" \
    -message "$MESSAGE" \
    -sound "$SOUND" \
    -activate "com.mitchellh.ghostty" \
    -group "claude-$TYPE"
fi

# Send terminal bell by walking up process tree to find tty
pid=$$
while [ "$pid" != "1" ] && [ -n "$pid" ]; do
  tty=$(ps -o tty= -p "$pid" 2>/dev/null | tr -d ' ')
  if [ -n "$tty" ] && [ "$tty" != "??" ]; then
    printf '\a' > "/dev/$tty" 2>/dev/null
    break
  fi
  pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
done
