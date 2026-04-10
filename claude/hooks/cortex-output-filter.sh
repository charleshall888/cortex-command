#!/bin/bash
# PreToolUse hook: filter test runner output to reduce context window usage.
#
# Detects test runner commands via configurable regex patterns, then rewrites
# the command using a subshell-capture pattern with exit-code-conditional
# filtering. On success: summary line + suppression note. On failure: failure
# blocks with generous context. Failure-path fallback: tail -20 when no
# markers match.
#
# Config loading:
#   1. Check $CWD/.claude/output-filters.conf (project-local)
#   2. If project config exists and first non-comment line is "# disable-globals",
#      use project patterns only
#   3. Otherwise merge project patterns with ~/.claude/hooks/output-filters.conf
#
# Non-blocking — always exits 0. On any error, produces no output so the
# original command runs unmodified.
set -euo pipefail

INPUT=$(cat)

# --- Graceful degradation: require jq ---
if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

# --- Parse PreToolUse payload ---
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty') || exit 0
if [[ "$TOOL_NAME" != "Bash" ]]; then
  exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty') || exit 0
if [[ -z "$COMMAND" ]]; then
  exit 0
fi

# --- Determine project CWD ---
# Prefer cwd from hook input JSON; fall back to working directory.
HOOK_CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null) || true
if [[ -z "$HOOK_CWD" || "$HOOK_CWD" == "null" ]]; then
  HOOK_CWD="${PWD}"
fi

# --- Load patterns from config files ---
GLOBAL_CONF="${OUTPUT_FILTERS_CONF:-$HOME/.claude/hooks/output-filters.conf}"
PROJECT_CONF="${HOOK_CWD}/.claude/output-filters.conf"

PATTERNS=""
USE_GLOBALS=true

# Check project config first
if [[ -f "$PROJECT_CONF" ]]; then
  # Check for disable-globals directive: first non-comment, non-blank line
  FIRST_LINE=$(grep -v '^\s*$' "$PROJECT_CONF" | head -1)
  if [[ "$FIRST_LINE" == "# disable-globals" ]]; then
    USE_GLOBALS=false
  fi
  # Read project patterns (skip comments and blank lines)
  PROJECT_PATTERNS=$(grep -vE '^\s*#|^\s*$' "$PROJECT_CONF" 2>/dev/null) || true
  PATTERNS="$PROJECT_PATTERNS"
fi

# Merge global patterns unless disabled
if [[ "$USE_GLOBALS" == true && -f "$GLOBAL_CONF" ]]; then
  GLOBAL_PATTERNS=$(grep -vE '^\s*#|^\s*$' "$GLOBAL_CONF" 2>/dev/null) || true
  if [[ -n "$PATTERNS" && -n "$GLOBAL_PATTERNS" ]]; then
    PATTERNS="${PATTERNS}"$'\n'"${GLOBAL_PATTERNS}"
  elif [[ -n "$GLOBAL_PATTERNS" ]]; then
    PATTERNS="$GLOBAL_PATTERNS"
  fi
fi

# No patterns loaded — nothing to do
if [[ -z "$PATTERNS" ]]; then
  exit 0
fi

# --- Match command against patterns (line-by-line) ---
MATCHED=false
while IFS= read -r PATTERN; do
  [[ -z "$PATTERN" ]] && continue
  # grep -qE can fail with exit 2 on bad regex — skip silently
  if echo "$COMMAND" | grep -qE "$PATTERN" 2>/dev/null; then
    MATCHED=true
    break
  fi
done <<< "$PATTERNS"

if [[ "$MATCHED" != true ]]; then
  exit 0
fi

# --- Build wrapped command ---
# The wrapped command:
#   1. Captures all output (stdout+stderr) in a variable
#   2. Preserves the original exit code
#   3. Counts total lines for the suppression note
#   4. On success: extracts summary line or falls back to tail -5
#   5. On failure: extracts failure blocks with context, or falls back to tail -20
#   6. Exits with the original exit code
#
# Shell-safe embedding: the original command is quoted via jq's @sh filter
# and embedded with eval, so special characters are handled correctly.

SAFE_COMMAND=$(printf '%s' "$COMMAND" | jq -Rrs '@sh')
# SAFE_COMMAND is now a shell-safe single-quoted string (e.g., 'npm test')

WRAPPED_COMMAND="OUTPUT=\$(eval ${SAFE_COMMAND} 2>&1); EXIT_CODE=\$?; TOTAL=\$(echo \"\$OUTPUT\" | wc -l | tr -d \" \"); if [ \"\$EXIT_CODE\" -eq 0 ]; then SUMMARY=\$(echo \"\$OUTPUT\" | grep -E 'passed|failed|test result:|Tests:|ok' | tail -1); if [ -z \"\$SUMMARY\" ]; then SUMMARY=\$(echo \"\$OUTPUT\" | tail -5); fi; echo \"\$SUMMARY\"; echo \"(output filtered — \$TOTAL lines suppressed)\"; else FAILURES=\$(echo \"\$OUTPUT\" | grep -B 2 -A 20 -E 'FAIL|FAILED|ERROR|error:|failures:|--- FAIL:' | head -200); if [ -z \"\$FAILURES\" ]; then FAILURES=\$(echo \"\$OUTPUT\" | tail -20); fi; echo \"\$FAILURES\"; echo \"(output filtered — \$TOTAL lines suppressed)\"; exit \$EXIT_CODE; fi"

# --- Emit JSON with updatedInput ---
# Must include ALL fields from original tool_input, replacing only command.
echo "$INPUT" | jq --arg cmd "$WRAPPED_COMMAND" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "allow",
    updatedInput: (.tool_input | .command = $cmd)
  }
}'

exit 0
