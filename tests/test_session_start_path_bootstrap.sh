#!/bin/bash
# tests/test_session_start_path_bootstrap.sh
# Verifies cortex-session-start-path-bootstrap.sh behavior:
#   (a) cortex-shaped fixture: hook writes augmented PATH to CLAUDE_ENV_FILE,
#       making cortex-worktree-resolve reachable after sourcing the env file.
#   (b) non-cortex-shaped fixture: hook exits 0 silently without mutating PATH.
#
# Runs the hook under env -i HOME="$HOME" PATH=/usr/bin:/bin to simulate
# launchd's minimal PATH (the scenario this bootstrap is designed to fix).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/claude/hooks/cortex-session-start-path-bootstrap.sh"

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

TMPDIR_BASE="${TMPDIR:-/tmp}/test_path_bootstrap_$$"
mkdir -p "$TMPDIR_BASE"
cleanup() {
  rm -rf "$TMPDIR_BASE"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Test (a): cortex-shaped directory — PATH is augmented
# ---------------------------------------------------------------------------

CORTEX_FIXTURE="$TMPDIR_BASE/cortex-shaped"
mkdir -p "$CORTEX_FIXTURE/cortex/lifecycle"

# Create a fake cortex-worktree-resolve in $HOME/.local/bin within the fixture
# so we can assert it becomes reachable via the bootstrapped PATH.
FAKE_HOME="$TMPDIR_BASE/fake-home"
mkdir -p "$FAKE_HOME/.local/bin"
cat > "$FAKE_HOME/.local/bin/cortex-worktree-resolve" <<'EOF'
#!/bin/bash
echo "mock-resolve: $1"
EOF
chmod +x "$FAKE_HOME/.local/bin/cortex-worktree-resolve"

ENV_FILE="$TMPDIR_BASE/claude-env-a"

HOOK_INPUT=$(printf '{"hook_event_name":"SessionStart","session_id":"test-bootstrap-001","cwd":"%s"}' "$CORTEX_FIXTURE")

# Run hook under minimal PATH, using fake HOME and wiring CLAUDE_ENV_FILE
env -i \
  HOME="$FAKE_HOME" \
  PATH=/usr/bin:/bin \
  CLAUDE_ENV_FILE="$ENV_FILE" \
  bash "$HOOK" <<< "$HOOK_INPUT"
HOOK_EXIT=$?

if [[ $HOOK_EXIT -ne 0 ]]; then
  fail "path-bootstrap/cortex-shaped-exit0" "hook exited $HOOK_EXIT, expected 0"
else
  # Source the env file written by the hook and check PATH
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    if command -v cortex-worktree-resolve >/dev/null 2>&1; then
      pass "path-bootstrap/cortex-worktree-resolve-reachable"
    else
      fail "path-bootstrap/cortex-worktree-resolve-reachable" "cortex-worktree-resolve not found on PATH='$PATH' after sourcing env file"
    fi
  else
    fail "path-bootstrap/env-file-written" "CLAUDE_ENV_FILE was not written by the hook"
  fi
fi

# Also verify the env file contains the expected PATH prefixes
if [[ -f "$ENV_FILE" ]]; then
  if grep -qE "\.local/bin|opt/homebrew/bin" "$ENV_FILE"; then
    pass "path-bootstrap/env-file-contains-prefixes"
  else
    fail "path-bootstrap/env-file-contains-prefixes" "env file does not contain expected PATH prefixes; contents: $(cat "$ENV_FILE")"
  fi
fi

# ---------------------------------------------------------------------------
# Test (b): non-cortex-shaped directory — hook exits 0, PATH not mutated
# ---------------------------------------------------------------------------

NON_CORTEX_FIXTURE="$TMPDIR_BASE/non-cortex"
mkdir -p "$NON_CORTEX_FIXTURE"
# No cortex/lifecycle/ subdirectory

ENV_FILE_B="$TMPDIR_BASE/claude-env-b"

HOOK_INPUT_B=$(printf '{"hook_event_name":"SessionStart","session_id":"test-bootstrap-002","cwd":"%s"}' "$NON_CORTEX_FIXTURE")

env -i \
  HOME="$FAKE_HOME" \
  PATH=/usr/bin:/bin \
  CLAUDE_ENV_FILE="$ENV_FILE_B" \
  bash "$HOOK" <<< "$HOOK_INPUT_B"
HOOK_EXIT_B=$?

if [[ $HOOK_EXIT_B -ne 0 ]]; then
  fail "path-bootstrap/non-cortex-shaped-exit0" "hook exited $HOOK_EXIT_B, expected 0"
else
  pass "path-bootstrap/non-cortex-shaped-exit0"
fi

# Verify the env file was NOT written (no PATH mutation)
if [[ -f "$ENV_FILE_B" ]]; then
  fail "path-bootstrap/non-cortex-no-path-mutation" "env file was written for non-cortex-shaped fixture; hook should have exited silently without touching CLAUDE_ENV_FILE"
else
  pass "path-bootstrap/non-cortex-no-path-mutation"
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
