#!/bin/bash
# tests/test_hook_commit.sh — validate-commit hook regression tests
# Feeds each fixture in tests/fixtures/hooks/validate-commit/ through
# hooks/cortex-validate-commit.sh and asserts the permissionDecision matches the
# expected value derived from the fixture filename prefix.
#
# Naming convention:
#   valid-*   -> expects permissionDecision "allow"
#   invalid-* -> expects permissionDecision "deny"
#
# Exit 0 if all tests pass, 1 if any fail.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/hooks/cortex-validate-commit.sh"
FIXTURE_DIR="$REPO_ROOT/tests/fixtures/hooks/commit"

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
# cortex-validate-commit.sh tests
# ---------------------------------------------------------------------------

for fixture in "$FIXTURE_DIR"/*.json; do
  name="$(basename "$fixture" .json)"

  # Derive expected decision from filename prefix
  if [[ "$name" == valid-* ]]; then
    expected="allow"
  elif [[ "$name" == invalid-* ]]; then
    expected="deny"
  else
    fail "validate-commit/$name" "unknown fixture prefix — must be valid-* or invalid-*"
    continue
  fi

  # Run the hook and capture JSON output
  output=$(bash "$HOOK" < "$fixture" 2>&1)
  exit_code=$?

  # Hook must always exit 0 (PreToolUse hook, not a blocking script)
  if [[ $exit_code -ne 0 ]]; then
    fail "validate-commit/$name" "hook exited $exit_code, expected 0"
    continue
  fi

  # Extract decision from JSON output
  decision=$(echo "$output" | jq -r '
    .hookSpecificOutput.permissionDecision // "unknown"
  ' 2>/dev/null)

  if [[ "$decision" == "$expected" ]]; then
    pass "validate-commit/$name"
  else
    fail "validate-commit/$name" "expected '$expected', got '$decision'"
  fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "$PASS_COUNT passed, $FAIL_COUNT failed (out of $TOTAL)"

if [[ $FAIL_COUNT -gt 0 ]]; then
  exit 1
fi
exit 0
