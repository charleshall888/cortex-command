#!/bin/bash
# PostToolUse hook: auto-run the SKILL.md-load-bearing test sub-suites when
# SKILL.md is edited. Invokes `just test-skill-contracts` and
# `just test-skill-design` (~1.7s combined vs. ~10s for the full
# the full skill-test umbrella) and caps the captured stdout fed back into
# agent context to ≤500 characters (suffix-inclusive) on both pass and fail
# paths. Fires when a Write or Edit tool call targets a file named exactly
# SKILL.md. Non-blocking advisory — always exits 0.
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
  MSG_A="skill-edit-advisor: \`just\` not found on PATH — skipping scoped test run"
  jq -n --arg ctx "$MSG_A" '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$ctx}}'
  exit 0
fi

# --- Graceful degradation: check that at least one of the scoped recipes exists ---
if ! just --list 2>/dev/null | grep -qE 'test-skill-(contracts|design)'; then
  MSG_B="skill-edit-advisor: scoped \`test-skill-contracts\` / \`test-skill-design\` recipes not found in justfile — skipping scoped test run"
  jq -n --arg ctx "$MSG_B" '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$ctx}}'
  exit 0
fi

# --- Run scoped test sub-suites and capture output ---
# Combined invocation: any non-zero exit fails the advisor message.
TEST_OUTPUT=$(just test-skill-contracts test-skill-design 2>&1) && TEST_EXIT=0 || TEST_EXIT=$?

# --- Suffix-inclusive ≤500-char cap on additionalContext ---
# Apply the cap to the *output* and append the truncation suffix only when
# the output was actually truncated. SUFFIX_LEN is computed from a fixed
# suffix string; OUT_BUDGET = 500 - SUFFIX_LEN reserves room for the suffix.
SUFFIX='... [truncated; run `just test-skill-design test-skill-contracts` for full output]'
SUFFIX_LEN=${#SUFFIX}
CAP=500
OUT_BUDGET=$((CAP - SUFFIX_LEN))

RAW_LEN=${#TEST_OUTPUT}
if [ "$RAW_LEN" -gt "$OUT_BUDGET" ]; then
  TRUNCATED="$(printf '%s' "$TEST_OUTPUT" | head -c "$OUT_BUDGET")$SUFFIX"
else
  TRUNCATED="$TEST_OUTPUT"
fi

if [[ "$TEST_EXIT" -eq 0 ]]; then
  # Build a concise success summary. If the output reports a passing count
  # (e.g. "5 passed"), surface it; otherwise emit a generic success line.
  PASS_COUNT=$(echo "$TEST_OUTPUT" | grep -oE '[0-9]+ passed' | tail -1 || true)
  if [[ -n "$PASS_COUNT" ]]; then
    SUMMARY="Scoped skill tests passed (${PASS_COUNT}) after editing SKILL.md"
  else
    SUMMARY="Scoped skill tests passed after editing SKILL.md"
  fi
  # Replace TRUNCATED with the concise SUMMARY on the pass path so success
  # context stays small. (Still ≤500 chars by construction.)
  TRUNCATED="$SUMMARY"
  jq -n --arg ctx "$TRUNCATED" '{
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: $ctx
    }
  }'
else
  FAIL_MSG="Scoped skill tests FAILED after editing SKILL.md (exit ${TEST_EXIT}):
${TRUNCATED}"
  # Re-apply the cap to the composed FAIL_MSG (the prefix adds ~70 chars
  # which could push the field past 500 if the recipe output filled the
  # whole budget). Use a defensive head -c 500 here.
  FAIL_MSG_CAPPED="$(printf '%s' "$FAIL_MSG" | head -c "$CAP")"
  jq -n --arg ctx "$FAIL_MSG_CAPPED" '{
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: $ctx
    }
  }'
fi

exit 0
