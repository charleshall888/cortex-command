#!/bin/bash
# tests/test_tool_failure_tracker.sh — unit tests for claude/hooks/tool-failure-tracker.sh
#
# Verifies PostToolUse hook behaviour:
#   - Non-Bash tool input is ignored (no tracking files created)
#   - Bash tool with exit 0 is ignored (no tracking files created)
#   - Bash tool with non-zero exit writes count and log files
#   - Log file contains structured YAML fields
#   - Threshold alert emitted at exactly 3 failures (additionalContext)
#   - No alert emitted on 4th and subsequent failures
#   - Missing session_id falls back to a date-based tracking key
#   - Non-numeric count file is reset to 0 before incrementing
#
# Exit 0 if all tests pass, 1 if any fail.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/claude/hooks/tool-failure-tracker.sh"
FIXTURE_DIR="$REPO_ROOT/tests/fixtures/hooks/tool-failure-tracker"

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

# Unique per-run prefix — keeps parallel test runs from clobbering each other.
TEST_SESSION_BASE="test-tft-$$"

# Pipe a fixture through the hook, substituting __SESSION_ID__ with $2.
run_with_session() {
  local fixture="$1"
  local session_id="$2"
  sed "s|__SESSION_ID__|${session_id}|g" "$fixture" | bash "$HOOK"
}

cleanup_session_dir() {
  rm -rf "/tmp/claude-tool-failures-${1}"
}

# ---------------------------------------------------------------------------
# Test: non-Bash tool — exits 0, creates no tracking files
# ---------------------------------------------------------------------------

SESSION_NONBASH="${TEST_SESSION_BASE}-nonbash"
cleanup_session_dir "$SESSION_NONBASH"

exit_code=0
run_with_session "$FIXTURE_DIR/non-bash-tool.json" "$SESSION_NONBASH" >/dev/null 2>&1 \
  || exit_code=$?

if [[ $exit_code -eq 0 && ! -d "/tmp/claude-tool-failures-${SESSION_NONBASH}" ]]; then
  pass "tool-failure-tracker/non-bash-tool-no-files"
else
  fail "tool-failure-tracker/non-bash-tool-no-files" \
    "expected exit 0 with no tracking dir; got exit $exit_code, dir_exists=$(test -d "/tmp/claude-tool-failures-${SESSION_NONBASH}" && echo yes || echo no)"
fi

# ---------------------------------------------------------------------------
# Test: Bash with exit code 0 — exits 0, creates no tracking files
# ---------------------------------------------------------------------------

SESSION_SUCCESS="${TEST_SESSION_BASE}-success"
cleanup_session_dir "$SESSION_SUCCESS"

exit_code=0
run_with_session "$FIXTURE_DIR/bash-success.json" "$SESSION_SUCCESS" >/dev/null 2>&1 \
  || exit_code=$?

if [[ $exit_code -eq 0 && ! -d "/tmp/claude-tool-failures-${SESSION_SUCCESS}" ]]; then
  pass "tool-failure-tracker/bash-success-no-files"
else
  fail "tool-failure-tracker/bash-success-no-files" \
    "expected exit 0 with no tracking dir; got exit $exit_code, dir_exists=$(test -d "/tmp/claude-tool-failures-${SESSION_SUCCESS}" && echo yes || echo no)"
fi

# ---------------------------------------------------------------------------
# Test: Bash with non-zero exit — exits 0, creates count and log files
# ---------------------------------------------------------------------------

SESSION_FAILURE="${TEST_SESSION_BASE}-failure"
cleanup_session_dir "$SESSION_FAILURE"

TRACK_DIR="/tmp/claude-tool-failures-${SESSION_FAILURE}"

exit_code=0
run_with_session "$FIXTURE_DIR/bash-failure.json" "$SESSION_FAILURE" >/dev/null 2>&1 \
  || exit_code=$?

count_file="$TRACK_DIR/bash.count"
log_file="$TRACK_DIR/bash.log"
count_val=$(cat "$count_file" 2>/dev/null || echo "missing")

if [[ $exit_code -eq 0 && -f "$count_file" && "$count_val" == "1" && -f "$log_file" ]]; then
  pass "tool-failure-tracker/bash-failure-creates-files"
else
  fail "tool-failure-tracker/bash-failure-creates-files" \
    "expected exit 0 with count=1 and log file; got exit $exit_code, count=$count_val, log=$(test -f "$log_file" && echo yes || echo no)"
fi

cleanup_session_dir "$SESSION_FAILURE"

# ---------------------------------------------------------------------------
# Test: log file contains structured YAML entry fields
# ---------------------------------------------------------------------------

SESSION_LOG="${TEST_SESSION_BASE}-log"
cleanup_session_dir "$SESSION_LOG"

run_with_session "$FIXTURE_DIR/bash-failure.json" "$SESSION_LOG" >/dev/null 2>&1

log_content=$(cat "/tmp/claude-tool-failures-${SESSION_LOG}/bash.log" 2>/dev/null || echo "")

if [[ "$log_content" == *"exit_code: 1"* \
   && "$log_content" == *"tool: Bash"* \
   && "$log_content" == *"failure_num:"* \
   && "$log_content" == *"timestamp:"* ]]; then
  pass "tool-failure-tracker/log-contains-structured-fields"
else
  fail "tool-failure-tracker/log-contains-structured-fields" \
    "expected exit_code, tool, failure_num, and timestamp in log; got: $(echo "$log_content" | head -8)"
fi

cleanup_session_dir "$SESSION_LOG"

# ---------------------------------------------------------------------------
# Test: threshold alert emitted at exactly 3 failures
# ---------------------------------------------------------------------------

SESSION_THRESH="${TEST_SESSION_BASE}-thresh"
cleanup_session_dir "$SESSION_THRESH"

# Failures 1 and 2: no output expected.
run_with_session "$FIXTURE_DIR/bash-failure.json" "$SESSION_THRESH" >/dev/null 2>&1
run_with_session "$FIXTURE_DIR/bash-failure.json" "$SESSION_THRESH" >/dev/null 2>&1

# Failure 3: additionalContext warning must be emitted.
output=$(run_with_session "$FIXTURE_DIR/bash-failure.json" "$SESSION_THRESH" 2>/dev/null)
exit_code=$?
context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)

if [[ $exit_code -eq 0 && "$context" == *"3"* && "$context" == *"Bash"* ]]; then
  pass "tool-failure-tracker/threshold-alert-at-3"
else
  fail "tool-failure-tracker/threshold-alert-at-3" \
    "expected exit 0 with alert mentioning Bash and 3; got exit $exit_code, context='$context'"
fi

# ---------------------------------------------------------------------------
# Test: no alert emitted on 4th (and subsequent) failure
# ---------------------------------------------------------------------------

output=$(run_with_session "$FIXTURE_DIR/bash-failure.json" "$SESSION_THRESH" 2>/dev/null)
exit_code=$?
context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)

if [[ $exit_code -eq 0 && -z "$context" ]]; then
  pass "tool-failure-tracker/no-alert-after-threshold"
else
  fail "tool-failure-tracker/no-alert-after-threshold" \
    "expected exit 0 with no alert on 4th failure; got exit $exit_code, context='$context'"
fi

cleanup_session_dir "$SESSION_THRESH"

# ---------------------------------------------------------------------------
# Test: no session_id — falls back to date-based tracking key
# ---------------------------------------------------------------------------

DATE_KEY="date-$(date -u +%Y%m%d)"
DATE_TRACK_DIR="/tmp/claude-tool-failures-${DATE_KEY}"
DATE_COUNT_FILE="$DATE_TRACK_DIR/bash.count"

# Record the count before the test (in case the date dir already exists).
start_count=0
if [[ -f "$DATE_COUNT_FILE" ]]; then
  v=$(cat "$DATE_COUNT_FILE" 2>/dev/null || echo 0)
  [[ "$v" =~ ^[0-9]+$ ]] && start_count=$v
fi

exit_code=0
bash "$HOOK" < "$FIXTURE_DIR/no-session-id.json" >/dev/null 2>&1 || exit_code=$?

new_count=0
if [[ -f "$DATE_COUNT_FILE" ]]; then
  v=$(cat "$DATE_COUNT_FILE" 2>/dev/null || echo 0)
  [[ "$v" =~ ^[0-9]+$ ]] && new_count=$v
fi

if [[ $exit_code -eq 0 && $new_count -eq $((start_count + 1)) ]]; then
  pass "tool-failure-tracker/no-session-id-fallback"
else
  fail "tool-failure-tracker/no-session-id-fallback" \
    "expected exit 0 with count incremented to $((start_count + 1)); got exit $exit_code, new_count=$new_count"
fi

# ---------------------------------------------------------------------------
# Test: non-numeric count file — resets to 0 then increments to 1
# ---------------------------------------------------------------------------

SESSION_CORRUPT="${TEST_SESSION_BASE}-corrupt"
cleanup_session_dir "$SESSION_CORRUPT"

CORRUPT_TRACK_DIR="/tmp/claude-tool-failures-${SESSION_CORRUPT}"
mkdir -p "$CORRUPT_TRACK_DIR"
echo "not-a-number" > "$CORRUPT_TRACK_DIR/bash.count"

exit_code=0
run_with_session "$FIXTURE_DIR/bash-failure.json" "$SESSION_CORRUPT" >/dev/null 2>&1 \
  || exit_code=$?

count=$(cat "$CORRUPT_TRACK_DIR/bash.count" 2>/dev/null || echo "missing")

if [[ $exit_code -eq 0 && "$count" == "1" ]]; then
  pass "tool-failure-tracker/corrupt-count-resets"
else
  fail "tool-failure-tracker/corrupt-count-resets" \
    "expected exit 0 with count=1 after corrupt reset; got exit $exit_code, count=$count"
fi

cleanup_session_dir "$SESSION_CORRUPT"

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
