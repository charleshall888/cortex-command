#!/bin/bash
# tests/test_runner_auth.sh — regression tests for runner.sh auth block
# Asserts all three exit-code branches of the capture + case-statement that
# runner.sh uses to delegate auth resolution to
# `python3 -m claude.overnight.auth --shell`:
#
#   0 -> eval stdout, token exported into the shell
#   1 -> no vector available, continue past the block silently
#   2 -> helper-internal failure, abort with exit 2 and stderr message
#
# Each scenario stubs `python3` by prepending a temp dir with a fake script
# to PATH, then runs the auth block in a clean subshell.
#
# Exit 0 if all scenarios pass, 1 if any fail.

set -uo pipefail

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
# The auth block extracted verbatim from claude/overnight/runner.sh. Each
# scenario below sources this into a subshell after staging a stubbed
# `python3` on PATH. Keep in sync with runner.sh if the block changes.
# ---------------------------------------------------------------------------
AUTH_BLOCK='
set +e
_AUTH_STDOUT=$(python3 -m claude.overnight.auth --shell)
_AUTH_EXIT=$?
set -e
case "$_AUTH_EXIT" in
  0) eval "$_AUTH_STDOUT" ;;
  1) : ;;
  2) echo "Error: auth helper internal failure" >&2; exit 2 ;;
esac
unset _AUTH_STDOUT _AUTH_EXIT
'

# Stage a stubbed `python3` script in a fresh temp dir and echo the dir path.
# Args: stub_body (a string; a shebang is prepended).
make_stub_dir() {
  local body="$1"
  local dir
  dir="$(mktemp -d "${TMPDIR:-/tmp}/test_runner_auth.XXXXXX")"
  {
    echo '#!/bin/bash'
    echo "$body"
  } > "$dir/python3"
  chmod +x "$dir/python3"
  echo "$dir"
}

cleanup_dirs=()
trap 'for d in "${cleanup_dirs[@]}"; do rm -rf "$d"; done' EXIT

# ---------------------------------------------------------------------------
# Scenario 1: success — helper prints an export line and exits 0
# ---------------------------------------------------------------------------
stub_dir=$(make_stub_dir 'echo "export CLAUDE_CODE_OAUTH_TOKEN=abc"; exit 0')
cleanup_dirs+=("$stub_dir")

output=$(PATH="$stub_dir:$PATH" bash -c "
  $AUTH_BLOCK
  echo \"TOKEN=\${CLAUDE_CODE_OAUTH_TOKEN:-unset}\"
" 2>&1)
exit_code=$?

if [[ $exit_code -ne 0 ]]; then
  fail "auth/success" "subshell exited $exit_code, expected 0; output: $output"
elif [[ "$output" != *"TOKEN=abc"* ]]; then
  fail "auth/success" "expected TOKEN=abc in output, got: $output"
else
  pass "auth/success"
fi

# ---------------------------------------------------------------------------
# Scenario 2: no-vector — helper exits 1 with empty stdout; block is a no-op
# ---------------------------------------------------------------------------
stub_dir=$(make_stub_dir 'exit 1')
cleanup_dirs+=("$stub_dir")

output=$(PATH="$stub_dir:$PATH" bash -c "
  $AUTH_BLOCK
  echo SENTINEL_REACHED
" 2>&1)
exit_code=$?

if [[ $exit_code -ne 0 ]]; then
  fail "auth/no-vector" "subshell exited $exit_code, expected 0; output: $output"
elif [[ "$output" != *"SENTINEL_REACHED"* ]]; then
  fail "auth/no-vector" "sentinel not reached; output: $output"
else
  pass "auth/no-vector"
fi

# ---------------------------------------------------------------------------
# Scenario 3: helper-internal failure — helper exits 2; block aborts with 2
# ---------------------------------------------------------------------------
stub_dir=$(make_stub_dir 'exit 2')
cleanup_dirs+=("$stub_dir")

output=$(PATH="$stub_dir:$PATH" bash -c "
  $AUTH_BLOCK
  echo SENTINEL_REACHED
" 2>&1)
exit_code=$?

if [[ $exit_code -ne 2 ]]; then
  fail "auth/internal-failure" "subshell exited $exit_code, expected 2; output: $output"
elif [[ "$output" != *"Error: auth helper internal failure"* ]]; then
  fail "auth/internal-failure" "expected stderr message, got: $output"
elif [[ "$output" == *"SENTINEL_REACHED"* ]]; then
  fail "auth/internal-failure" "block did not abort; sentinel was reached"
else
  pass "auth/internal-failure"
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
