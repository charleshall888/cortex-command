#!/bin/bash
# PostToolUse hook: auto-run `just test-skills` when SKILL.md is edited.
# Fires when a Write or Edit tool call targets a file named exactly SKILL.md.
# Non-blocking advisory — always exits 0.
set -euo pipefail

INPUT=$(cat)

# --- Parse PostToolUse payload ---
# Expected shape:
#   { "tool_name": "Write|Edit",
#     "tool_input": { "file_path": "..." },
#     "tool_response": {...} }
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only act on Write or Edit tool calls
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
  exit 0
fi

# Only act when the target filename is exactly SKILL.md (any path)
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" != "SKILL.md" ]]; then
  exit 0
fi

# --- Graceful degradation: check that `just` is available ---
if ! command -v just >/dev/null 2>&1; then
  MSG_A="skill-edit-advisor: \`just\` not found on PATH — skipping test-skills run\nReminder: verify ~/.claude/reference/context-file-authoring.md was consulted."
  jq -n --arg ctx "$MSG_A" '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$ctx}}'
  exit 0
fi

# --- Graceful degradation: check that the `test-skills` recipe exists ---
if ! just --list 2>/dev/null | grep -q 'test-skills'; then
  MSG_B="skill-edit-advisor: \`test-skills\` recipe not found in justfile — skipping test run\nReminder: verify ~/.claude/reference/context-file-authoring.md was consulted."
  jq -n --arg ctx "$MSG_B" '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$ctx}}'
  exit 0
fi

# --- Run test suite and capture output ---
TEST_OUTPUT=$(just test-skills 2>&1) && TEST_EXIT=0 || TEST_EXIT=$?

TRUNCATED=$(echo "$TEST_OUTPUT" | head -20)

if [[ "$TEST_EXIT" -eq 0 ]]; then
  # Count passing tests from output (e.g. "5 passed") if available; otherwise generic message
  PASS_COUNT=$(echo "$TEST_OUTPUT" | grep -oE '[0-9]+ passed' | tail -1 || true)
  if [[ -n "$PASS_COUNT" ]]; then
    SUMMARY="Skill tests passed (${PASS_COUNT}) after editing SKILL.md"
  else
    SUMMARY="Skill tests passed after editing SKILL.md"
  fi
  SUMMARY="$SUMMARY\nReminder: verify ~/.claude/reference/context-file-authoring.md was consulted."
  jq -n --arg ctx "$SUMMARY" '{
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: $ctx
    }
  }'
else
  FAIL_MSG="Skill tests FAILED after editing SKILL.md (exit ${TEST_EXIT}):\n${TRUNCATED}\nReminder: verify ~/.claude/reference/context-file-authoring.md was consulted."
  jq -n --arg ctx "$FAIL_MSG" '{
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: $ctx
    }
  }'
fi

exit 0
