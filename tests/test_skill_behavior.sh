#!/bin/bash
# tests/test_skill_behavior.sh — behavioral test harness for the commit skill
#
# Creates a git worktree, then directly invokes hooks/cortex-validate-commit.sh with
# a crafted Claude PreToolUse payload (lowercase subject — intentionally bad)
# and asserts the hook produces permissionDecision "deny".
#
# This is a behavioral test: it uses a realistic command string as Claude would
# produce it, not a synthetic fixture. The worktree is used to prove the test
# runs in an isolated git context rather than only processing a static file.
#
# Exit 0 if all assertions pass, 1 if any fail.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/hooks/cortex-validate-commit.sh"
WORKTREE_PATH="${TMPDIR}/skill-behavior-test-worktree-$$"

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
# Cleanup on exit — remove worktree even if the test fails
# ---------------------------------------------------------------------------

cleanup() {
  git -C "$REPO_ROOT" worktree remove --force "$WORKTREE_PATH" 2>/dev/null || true
  rm -rf "$WORKTREE_PATH" 2>/dev/null || true
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Setup: create a git worktree in $TMPDIR
# ---------------------------------------------------------------------------

if ! git -C "$REPO_ROOT" worktree add "$WORKTREE_PATH" HEAD >/dev/null 2>&1; then
  echo "FATAL: could not create worktree at $WORKTREE_PATH"
  exit 1
fi

# ---------------------------------------------------------------------------
# Behavioral test: lowercase commit subject must produce a deny decision
# ---------------------------------------------------------------------------
#
# Payload mirrors exactly what Claude Code sends for a PreToolUse Bash event.
# The command string is realistic — as the /commit skill would produce it when
# the agent (incorrectly) tries: git commit -m "add new feature"

PAYLOAD='{
  "tool_name": "Bash",
  "tool_input": {
    "command": "git commit -m \"add new feature\""
  }
}'

output=$(echo "$PAYLOAD" | bash "$HOOK" 2>&1)
exit_code=$?

# Hook must always exit 0 (PreToolUse hooks must not themselves error out)
if [[ $exit_code -ne 0 ]]; then
  fail "commit-skill/lowercase-subject" "hook exited $exit_code, expected 0"
else
  decision=$(echo "$output" | jq -r '.hookSpecificOutput.permissionDecision' 2>/dev/null)
  if [[ "$decision" == "deny" ]]; then
    pass "commit-skill/lowercase-subject"
  else
    fail "commit-skill/lowercase-subject" "expected permissionDecision 'deny', got '$decision'"
  fi
fi

# ---------------------------------------------------------------------------
# Cleanup verification: worktree must not appear in git worktree list
# ---------------------------------------------------------------------------
# Run cleanup explicitly (trap will also run, but we need the result before
# the summary so we can include it in pass/fail counts).

cleanup
trap - EXIT  # prevent double-cleanup from trap

worktree_list=$(git -C "$REPO_ROOT" worktree list 2>&1)
if echo "$worktree_list" | grep -qF "$WORKTREE_PATH"; then
  fail "commit-skill/worktree-cleanup" "worktree path still appears in git worktree list after cleanup"
else
  pass "commit-skill/worktree-cleanup"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "$PASS_COUNT passed, $FAIL_COUNT failed (out of $TOTAL)"

if [[ $FAIL_COUNT -gt 0 ]]; then
  exit 1
fi
exit 0
