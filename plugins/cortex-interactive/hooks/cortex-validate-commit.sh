#!/bin/bash
# Hook: validate git commit messages before execution (PreToolUse).
set -euo pipefail

INPUT=$(cat)

# --- Command extraction ---
# Claude sends: {"tool_name": "Bash", "tool_input": {"command": "..."}}

TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only validate git commit commands from Bash tool
[[ "$TOOL" == "Bash" ]] || exit 0

# Only validate git commit commands
[[ "$COMMAND" == *"git commit"* ]] || exit 0
# Skip amend commits — different workflow
[[ "$COMMAND" != *"--amend"* ]] || exit 0

# --- Extract commit message ---

extract_message() {
  local cmd="$1"

  # HEREDOC format: git commit -m "$(cat <<'EOF' ... EOF )"
  if [[ "$cmd" == *"<<'EOF'"* ]] || [[ "$cmd" == *'<<"EOF"'* ]] || [[ "$cmd" == *"<<EOF"* ]]; then
    echo "$cmd" | awk '/<<.*EOF/{found=1; next} /^EOF/{found=0; next} found{print}'
    return
  fi

  # Double-quoted: git commit -m "message" (match first -m, not last)
  if [[ "$cmd" =~ -m\ \"([^\"]+)\" ]]; then
    echo "${BASH_REMATCH[1]}"
    return
  fi

  # Single-quoted: git commit -m 'message' (match first -m, not last)
  if [[ "$cmd" =~ -m\ \'([^\']+)\' ]]; then
    echo "${BASH_REMATCH[1]}"
    return
  fi

  # No -m flag (interactive or --allow-empty-message) — skip validation
  echo ""
}

MESSAGE=$(extract_message "$COMMAND")

# No message extracted — not a format we validate
[[ -n "$MESSAGE" ]] || exit 0

SUBJECT=$(echo "$MESSAGE" | head -n1)
ERRORS=()

# --- Validation rules ---

# 1. Subject must start with a capital letter
if [[ ! "$SUBJECT" =~ ^[A-Z] ]]; then
  ERRORS+=("Subject must start with a capital letter")
fi

# 2. No trailing period on subject
if [[ "$SUBJECT" =~ \.$ ]]; then
  ERRORS+=("Subject must not end with a period")
fi

# 4. Subject must be meaningful (at least 10 chars)
if (( ${#SUBJECT} < 10 )); then
  ERRORS+=("Subject too short — provide a meaningful description (≥10 chars)")
fi

# 5. Must use imperative mood (reject past tense openers)
LOWER_SUBJECT=$(echo "$SUBJECT" | tr '[:upper:]' '[:lower:]')
PAST_TENSE_RE='^(added|fixed|removed|updated|changed|modified|improved|merged|moved|renamed|deleted|refactored|cleaned|bumped) '
if [[ "$LOWER_SUBJECT" =~ $PAST_TENSE_RE ]]; then
  VERB=$(echo "$LOWER_SUBJECT" | awk '{print $1}')
  ERRORS+=("Use imperative mood ('Add' not 'Added') — found '$VERB'")
fi

# 6. Body must be separated from subject by a blank line
LINE_COUNT=$(echo "$MESSAGE" | wc -l | tr -d ' ')
if (( LINE_COUNT > 1 )); then
  SECOND_LINE=$(echo "$MESSAGE" | sed -n '2p')
  if [[ -n "$SECOND_LINE" ]]; then
    ERRORS+=("Body must be separated from subject by a blank line")
  fi
fi

# --- Output (agent-specific format) ---

if (( ${#ERRORS[@]} > 0 )); then
  REASON=$(printf "• %s\n" "${ERRORS[@]}")

  jq -n --arg reason "$REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: ("Commit message validation failed:\n" + $reason)
    }
  }'
else
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow"
    }
  }'
fi

exit 0
