#!/bin/bash
# tests/test_output_filter.sh — tests for claude/hooks/cortex-output-filter.sh
#
# Config-level tests:
#   (a) matched command produces wrapped output
#   (b) non-matched command produces no output
#   (c) missing config degrades gracefully (exit 0, empty stdout)
#   (d) malformed regex in config is skipped silently
#   (e) project config merge with global
#   (f) # disable-globals directive works
#
# Runtime behavioral tests:
#   (g) exit code preservation — wrapped command returns original exit code
#   (h) success-path summary extraction — summary line + suppression note
#   (i) failure-path marker filtering — FAIL/ERROR markers show filtered blocks
#   (j) failure-path fallback — non-zero exit with no markers shows last 20 lines
#
# Exit 0 if all tests pass, 1 if any fail.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/claude/hooks/cortex-output-filter.sh"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo "PASS $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "FAIL $1: $2"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Create a temp directory for this test run
TEST_TMPDIR="${TMPDIR%/}/test-output-filter-$$"
mkdir -p "$TEST_TMPDIR"

cleanup() {
  rm -rf "$TEST_TMPDIR" 2>/dev/null || true
}
trap cleanup EXIT

# Build a PreToolUse JSON payload for a given command
make_payload() {
  local cmd="$1"
  local cwd="${2:-$TEST_TMPDIR}"
  jq -n --arg cmd "$cmd" --arg cwd "$cwd" '{
    tool_name: "Bash",
    tool_input: { command: $cmd },
    cwd: $cwd
  }'
}

# Run the hook with a given payload and optional env overrides
# Usage: run_hook <payload> [env_var=value ...]
run_hook() {
  local payload="$1"
  shift
  env "$@" bash "$HOOK" <<< "$payload"
}

# ---------------------------------------------------------------------------
# (a) Matched command produces wrapped output
# ---------------------------------------------------------------------------

PAYLOAD_A=$(make_payload "npm test")
output_a=$(run_hook "$PAYLOAD_A" "OUTPUT_FILTERS_CONF=$REPO_ROOT/claude/hooks/output-filters.conf" 2>/dev/null)
exit_a=$?

if [[ $exit_a -eq 0 ]]; then
  decision_a=$(echo "$output_a" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null)
  updated_cmd_a=$(echo "$output_a" | jq -r '.hookSpecificOutput.updatedInput.command // empty' 2>/dev/null)
  if [[ "$decision_a" == "allow" && -n "$updated_cmd_a" && "$updated_cmd_a" != "npm test" ]]; then
    pass "config/matched-command-produces-wrapped-output"
  else
    fail "config/matched-command-produces-wrapped-output" \
      "expected decision=allow with wrapped command; got decision='$decision_a', cmd starts with '${updated_cmd_a:0:30}'"
  fi
else
  fail "config/matched-command-produces-wrapped-output" "hook exited $exit_a, expected 0"
fi

# ---------------------------------------------------------------------------
# (b) Non-matched command produces no output
# ---------------------------------------------------------------------------

PAYLOAD_B=$(make_payload "ls -la")
output_b=$(run_hook "$PAYLOAD_B" "OUTPUT_FILTERS_CONF=$REPO_ROOT/claude/hooks/output-filters.conf" 2>/dev/null)
exit_b=$?

if [[ $exit_b -eq 0 && -z "$output_b" ]]; then
  pass "config/non-matched-command-no-output"
else
  fail "config/non-matched-command-no-output" \
    "expected exit 0 with empty output; got exit $exit_b, output='${output_b:0:60}'"
fi

# ---------------------------------------------------------------------------
# (c) Missing config degrades gracefully (exit 0, empty stdout)
# ---------------------------------------------------------------------------

# Point to a non-existent config, and use a CWD that has no .claude/ dir
MISSING_CONF="$TEST_TMPDIR/nonexistent-filters.conf"
PAYLOAD_C=$(make_payload "npm test" "$TEST_TMPDIR")
output_c=$(run_hook "$PAYLOAD_C" "OUTPUT_FILTERS_CONF=$MISSING_CONF" 2>/dev/null)
exit_c=$?

if [[ $exit_c -eq 0 && -z "$output_c" ]]; then
  pass "config/missing-config-graceful-degradation"
else
  fail "config/missing-config-graceful-degradation" \
    "expected exit 0 with empty output; got exit $exit_c, output='${output_c:0:60}'"
fi

# ---------------------------------------------------------------------------
# (d) Malformed regex in config is skipped silently
# ---------------------------------------------------------------------------

# Create a config with one malformed regex and one valid pattern
MALFORMED_CONF="$TEST_TMPDIR/malformed-filters.conf"
printf '%s\n' '[invalid(regex' '\bnpm test\b' > "$MALFORMED_CONF"

PAYLOAD_D=$(make_payload "npm test" "$TEST_TMPDIR")
output_d=$(run_hook "$PAYLOAD_D" "OUTPUT_FILTERS_CONF=$MALFORMED_CONF" 2>/dev/null)
exit_d=$?

if [[ $exit_d -eq 0 ]]; then
  decision_d=$(echo "$output_d" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null)
  if [[ "$decision_d" == "allow" ]]; then
    pass "config/malformed-regex-skipped-silently"
  else
    fail "config/malformed-regex-skipped-silently" \
      "expected match via valid pattern after skipping bad regex; got decision='$decision_d'"
  fi
else
  fail "config/malformed-regex-skipped-silently" "hook exited $exit_d, expected 0"
fi

# ---------------------------------------------------------------------------
# (e) Project config merge with global
# ---------------------------------------------------------------------------

# Create a project-local config with a custom pattern
PROJECT_DIR_E="$TEST_TMPDIR/project-merge"
mkdir -p "$PROJECT_DIR_E/.claude"
printf '%s\n' '\bmy-custom-test\b' > "$PROJECT_DIR_E/.claude/output-filters.conf"

# Global config has standard patterns; project adds custom one
# The command matches only the project pattern, not global — proves merge
PAYLOAD_E=$(make_payload "my-custom-test run" "$PROJECT_DIR_E")
output_e=$(run_hook "$PAYLOAD_E" "OUTPUT_FILTERS_CONF=$REPO_ROOT/claude/hooks/output-filters.conf" 2>/dev/null)
exit_e=$?

if [[ $exit_e -eq 0 ]]; then
  decision_e=$(echo "$output_e" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null)
  if [[ "$decision_e" == "allow" ]]; then
    pass "config/project-config-merge-with-global"
  else
    fail "config/project-config-merge-with-global" \
      "expected project pattern to match after merge; got decision='$decision_e'"
  fi
else
  fail "config/project-config-merge-with-global" "hook exited $exit_e, expected 0"
fi

# ---------------------------------------------------------------------------
# (f) # disable-globals directive works
# ---------------------------------------------------------------------------

# Create a project config with disable-globals + a custom pattern only
PROJECT_DIR_F="$TEST_TMPDIR/project-disable"
mkdir -p "$PROJECT_DIR_F/.claude"
printf '%s\n' '# disable-globals' '\bonly-local-test\b' > "$PROJECT_DIR_F/.claude/output-filters.conf"

# Command matches global pattern (npm test) but NOT the project pattern
# With disable-globals, global patterns should not be loaded
PAYLOAD_F=$(make_payload "npm test" "$PROJECT_DIR_F")
output_f=$(run_hook "$PAYLOAD_F" "OUTPUT_FILTERS_CONF=$REPO_ROOT/claude/hooks/output-filters.conf" 2>/dev/null)
exit_f=$?

if [[ $exit_f -eq 0 && -z "$output_f" ]]; then
  pass "config/disable-globals-directive"
else
  fail "config/disable-globals-directive" \
    "expected no match with globals disabled; got exit $exit_f, output='${output_f:0:60}'"
fi

# Also verify the local pattern still works with disable-globals
PAYLOAD_F2=$(make_payload "only-local-test" "$PROJECT_DIR_F")
output_f2=$(run_hook "$PAYLOAD_F2" "OUTPUT_FILTERS_CONF=$REPO_ROOT/claude/hooks/output-filters.conf" 2>/dev/null)
exit_f2=$?

if [[ $exit_f2 -eq 0 ]]; then
  decision_f2=$(echo "$output_f2" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null)
  if [[ "$decision_f2" == "allow" ]]; then
    pass "config/disable-globals-local-still-works"
  else
    fail "config/disable-globals-local-still-works" \
      "expected local pattern to match with disable-globals; got decision='$decision_f2'"
  fi
else
  fail "config/disable-globals-local-still-works" "hook exited $exit_f2, expected 0"
fi

# ===========================================================================
# Runtime behavioral tests
# ===========================================================================
# These tests pipe a matched command through the hook, extract the wrapped
# command from the JSON output, then execute it to verify filtering behavior.

# Helper: get the wrapped command from hook output for a given original command
get_wrapped_command() {
  local original_cmd="$1"
  local payload
  payload=$(make_payload "$original_cmd")
  local hook_output
  hook_output=$(run_hook "$payload" "OUTPUT_FILTERS_CONF=$REPO_ROOT/claude/hooks/output-filters.conf" 2>/dev/null)
  echo "$hook_output" | jq -r '.hookSpecificOutput.updatedInput.command // empty' 2>/dev/null
}

# ---------------------------------------------------------------------------
# (g) Exit code preservation — wrapped command returns original exit code
# ---------------------------------------------------------------------------

# Use "just test" as the matched command pattern, but the wrapped command
# will eval the original. We need a command that matches our config AND
# will exit with code 1. We'll use a command that matches "npm test" pattern.
# The hook wraps: eval '<original_cmd>' — so we use sh -c as the "test command".
# But we need the ORIGINAL command to match a pattern. So we craft a command
# that looks like "npm test" to the pattern matcher but actually runs our test.
#
# Simpler approach: create a temp config that matches our test command.
RUNTIME_CONF="$TEST_TMPDIR/runtime-filters.conf"
printf '%s\n' '\bsh -c\b' > "$RUNTIME_CONF"

get_runtime_wrapped() {
  local original_cmd="$1"
  local payload
  payload=$(make_payload "$original_cmd")
  local hook_output
  hook_output=$(run_hook "$payload" "OUTPUT_FILTERS_CONF=$RUNTIME_CONF" 2>/dev/null)
  echo "$hook_output" | jq -r '.hookSpecificOutput.updatedInput.command // empty' 2>/dev/null
}

WRAPPED_G=$(get_runtime_wrapped "sh -c 'echo test output; exit 1'")

if [[ -n "$WRAPPED_G" ]]; then
  runtime_output_g=$(eval "$WRAPPED_G" 2>&1)
  runtime_exit_g=$?

  if [[ $runtime_exit_g -eq 1 ]]; then
    pass "runtime/exit-code-preservation"
  else
    fail "runtime/exit-code-preservation" \
      "expected exit code 1; got $runtime_exit_g"
  fi
else
  fail "runtime/exit-code-preservation" "hook did not produce wrapped command"
fi

# ---------------------------------------------------------------------------
# (h) Success-path summary extraction — summary line + suppression note
# ---------------------------------------------------------------------------

WRAPPED_H=$(get_runtime_wrapped "sh -c 'echo line1; echo line2; echo line3; echo \"10 passed, 0 failed\"'")

if [[ -n "$WRAPPED_H" ]]; then
  runtime_output_h=$(eval "$WRAPPED_H" 2>&1)
  runtime_exit_h=$?

  if [[ $runtime_exit_h -eq 0 ]]; then
    if echo "$runtime_output_h" | grep -q "10 passed, 0 failed"; then
      if echo "$runtime_output_h" | grep -q "output filtered"; then
        pass "runtime/success-path-summary-extraction"
      else
        fail "runtime/success-path-summary-extraction" \
          "expected suppression note in output; got: $(echo "$runtime_output_h" | head -3)"
      fi
    else
      fail "runtime/success-path-summary-extraction" \
        "expected summary line '10 passed, 0 failed' in output; got: $(echo "$runtime_output_h" | head -3)"
    fi
  else
    fail "runtime/success-path-summary-extraction" \
      "expected exit 0; got $runtime_exit_h"
  fi
else
  fail "runtime/success-path-summary-extraction" "hook did not produce wrapped command"
fi

# ---------------------------------------------------------------------------
# (i) Failure-path marker filtering — FAIL/ERROR markers show filtered blocks
# ---------------------------------------------------------------------------

FAIL_CMD='sh -c '"'"'echo "Running tests..."; echo "test_a: ok"; echo "FAIL: test_something"; echo "Expected 1 got 2"; echo "test_c: ok"; exit 1'"'"''
WRAPPED_I=$(get_runtime_wrapped "$FAIL_CMD")

if [[ -n "$WRAPPED_I" ]]; then
  runtime_output_i=$(eval "$WRAPPED_I" 2>&1)
  runtime_exit_i=$?

  if [[ $runtime_exit_i -eq 1 ]]; then
    if echo "$runtime_output_i" | grep -q "FAIL: test_something"; then
      if echo "$runtime_output_i" | grep -q "output filtered"; then
        pass "runtime/failure-path-marker-filtering"
      else
        fail "runtime/failure-path-marker-filtering" \
          "expected suppression note; got: $runtime_output_i"
      fi
    else
      fail "runtime/failure-path-marker-filtering" \
        "expected FAIL marker in output; got: $runtime_output_i"
    fi
  else
    fail "runtime/failure-path-marker-filtering" \
      "expected exit 1; got $runtime_exit_i"
  fi
else
  fail "runtime/failure-path-marker-filtering" "hook did not produce wrapped command"
fi

# ---------------------------------------------------------------------------
# (j) Failure-path fallback — no markers, shows last 20 lines
# ---------------------------------------------------------------------------

FALLBACK_CMD='sh -c '"'"'echo "Segmentation fault"; exit 139'"'"''
WRAPPED_J=$(get_runtime_wrapped "$FALLBACK_CMD")

if [[ -n "$WRAPPED_J" ]]; then
  runtime_output_j=$(eval "$WRAPPED_J" 2>&1)
  runtime_exit_j=$?

  if [[ $runtime_exit_j -eq 139 ]]; then
    if echo "$runtime_output_j" | grep -q "Segmentation fault"; then
      if echo "$runtime_output_j" | grep -q "output filtered"; then
        pass "runtime/failure-path-fallback"
      else
        fail "runtime/failure-path-fallback" \
          "expected suppression note; got: $runtime_output_j"
      fi
    else
      fail "runtime/failure-path-fallback" \
        "expected 'Segmentation fault' in fallback output; got: $runtime_output_j"
    fi
  else
    fail "runtime/failure-path-fallback" \
      "expected exit 139; got $runtime_exit_j"
  fi
else
  fail "runtime/failure-path-fallback" "hook did not produce wrapped command"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo ""
echo "$PASS_COUNT passed, $FAIL_COUNT failed (out of $TOTAL)"

if [[ $FAIL_COUNT -gt 0 ]]; then
  exit 1
fi
exit 0
