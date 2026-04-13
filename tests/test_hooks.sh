#!/bin/bash
# tests/test_hooks.sh — hook regression tests
# Runs cortex-cleanup-session.sh against its fixtures and reports PASS/FAIL per case.
# Designed as an extensible umbrella: add additional hook test sections below.
# Exit 0 if all tests pass, 1 if any fail.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/hooks/cortex-cleanup-session.sh"
FIXTURE_DIR="$REPO_ROOT/tests/fixtures/hooks/cleanup-session"

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

# Substitute __TMPDIR__ placeholder with the actual temp dir path and feed to
# the hook via stdin.
run_hook_with_fixture() {
  local fixture="$1"
  local tmpdir="$2"
  sed "s|__TMPDIR__|$tmpdir|g" "$fixture" | bash "$HOOK"
}

# ---------------------------------------------------------------------------
# cortex-cleanup-session.sh tests
# ---------------------------------------------------------------------------

# Setup: create a shared temp directory for all cleanup-session tests.
CLEANUP_TMPDIR="$TMPDIR/test_hooks_cleanup_$$"
mkdir -p "$CLEANUP_TMPDIR"

cleanup_temp() {
  rm -rf "$CLEANUP_TMPDIR"
}
trap cleanup_temp EXIT

# --- Test: normal-end — .session file is removed ---

SESSION_FILE="$CLEANUP_TMPDIR/lifecycle/test-feature/.session"
mkdir -p "$(dirname "$SESSION_FILE")"
echo "test-session-123" > "$SESSION_FILE"

run_hook_with_fixture "$FIXTURE_DIR/normal-end.json" "$CLEANUP_TMPDIR"

if [[ ! -f "$SESSION_FILE" ]]; then
  pass "cleanup-session/normal-end"
else
  fail "cleanup-session/normal-end" ".session file was not removed"
fi

# --- Test: clear-end — .session file is NOT removed ---

mkdir -p "$(dirname "$SESSION_FILE")"
echo "test-session-123" > "$SESSION_FILE"

run_hook_with_fixture "$FIXTURE_DIR/clear-end.json" "$CLEANUP_TMPDIR"

if [[ -f "$SESSION_FILE" ]]; then
  pass "cleanup-session/clear-end"
else
  fail "cleanup-session/clear-end" ".session file was unexpectedly removed"
fi

# Cleanup the .session file left by the clear-end test before next test.
rm -f "$SESSION_FILE"

# --- Test: no-session-id — exits 0 without touching anything ---

# No .session file exists; hook should exit 0 silently.
run_hook_with_fixture "$FIXTURE_DIR/no-session-id.json" "$CLEANUP_TMPDIR"
EXIT_CODE=$?

if [[ $EXIT_CODE -eq 0 ]]; then
  pass "cleanup-session/no-session-id"
else
  fail "cleanup-session/no-session-id" "hook exited $EXIT_CODE, expected 0"
fi

# ---------------------------------------------------------------------------
# cortex-scan-lifecycle.sh tests
# ---------------------------------------------------------------------------

SCAN_HOOK="$REPO_ROOT/hooks/cortex-scan-lifecycle.sh"
SCAN_FIXTURE_DIR="$REPO_ROOT/tests/fixtures/hooks/scan-lifecycle"
SCAN_TMPDIR="$TMPDIR/test_hooks_scan_$$"
mkdir -p "$SCAN_TMPDIR"

# --- Test: no-lifecycle-dir — exits 0 with no output ---

output=$(sed "s|__TMPDIR__|$SCAN_TMPDIR|g" "$SCAN_FIXTURE_DIR/no-lifecycle-dir.json" \
  | bash "$SCAN_HOOK" 2>/dev/null)
exit_code=$?

if [[ $exit_code -eq 0 && -z "$output" ]]; then
  pass "scan-lifecycle/no-lifecycle-dir"
else
  fail "scan-lifecycle/no-lifecycle-dir" "expected exit 0 with no output; got exit $exit_code, output='$output'"
fi

# --- Test: single-incomplete-feature — output contains hookSpecificOutput.additionalContext ---

mkdir -p "$SCAN_TMPDIR/lifecycle/test-feature"
echo "# stub research" > "$SCAN_TMPDIR/lifecycle/test-feature/research.md"

output=$(sed "s|__TMPDIR__|$SCAN_TMPDIR|g" "$SCAN_FIXTURE_DIR/single-incomplete-feature.json" \
  | bash "$SCAN_HOOK" 2>/dev/null)
exit_code=$?

context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)

if [[ $exit_code -eq 0 && "$context" == *"test-feature"* ]]; then
  pass "scan-lifecycle/single-incomplete-feature"
else
  fail "scan-lifecycle/single-incomplete-feature" "expected exit 0 with test-feature in additionalContext; got exit $exit_code, context='$context'"
fi

# --- Test: claude-agent — output uses hookSpecificOutput key ---

output=$(sed "s|__TMPDIR__|$SCAN_TMPDIR|g" "$SCAN_FIXTURE_DIR/claude-agent.json" \
  | bash "$SCAN_HOOK" 2>/dev/null)
exit_code=$?

has_key=$(echo "$output" | jq 'has("hookSpecificOutput")' 2>/dev/null)

if [[ $exit_code -eq 0 && "$has_key" == "true" ]]; then
  pass "scan-lifecycle/claude-output-format"
else
  fail "scan-lifecycle/claude-output-format" "expected exit 0 with hookSpecificOutput key; got exit $exit_code, has_key=$has_key"
fi

# --- Test: fresh-resume-fires — handoff prompt injected first, file deleted ---

FR_TMPDIR="$TMPDIR/test_hooks_fr_$$"
mkdir -p "$FR_TMPDIR/lifecycle/test-fr-feature"
echo "# stub research" > "$FR_TMPDIR/lifecycle/test-fr-feature/research.md"
printf 'Resume test-fr-feature at specify phase. Run /lifecycle test-fr-feature.' \
  > "$FR_TMPDIR/lifecycle/.fresh-resume"

output=$(sed "s|__TMPDIR__|$FR_TMPDIR|g" "$SCAN_FIXTURE_DIR/pending-resume.json" \
  | bash "$SCAN_HOOK" 2>/dev/null)
exit_code=$?

context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)

if [[ $exit_code -eq 0 && "$context" == *"test-fr-feature"* && ! -f "$FR_TMPDIR/lifecycle/.fresh-resume" ]]; then
  pass "scan-lifecycle/fresh-resume-fires"
else
  fail "scan-lifecycle/fresh-resume-fires" "expected handoff prompt in context and file deleted; got exit $exit_code, context='$context', file_exists=$(test -f "$FR_TMPDIR/lifecycle/.fresh-resume" && echo yes || echo no)"
fi

rm -rf "$FR_TMPDIR"

# --- Test: fresh-resume-absent — no handoff injection when no marker file ---

output=$(sed "s|__TMPDIR__|$SCAN_TMPDIR|g" "$SCAN_FIXTURE_DIR/pending-resume.json" \
  | bash "$SCAN_HOOK" 2>/dev/null)
exit_code=$?

context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)

if [[ $exit_code -eq 0 && "$context" != *"Resume test-fr-feature"* ]]; then
  pass "scan-lifecycle/fresh-resume-absent"
else
  fail "scan-lifecycle/fresh-resume-absent" "expected no handoff prompt without marker; got exit $exit_code, context='$context'"
fi

# ---------------------------------------------------------------------------
# cortex-worktree-create.sh tests
# ---------------------------------------------------------------------------

WT_CREATE_HOOK="$REPO_ROOT/claude/hooks/cortex-worktree-create.sh"
WT_CREATE_FIXTURE_DIR="$REPO_ROOT/tests/fixtures/hooks/worktree-create"
WT_TMPDIR="$TMPDIR/test_hooks_wt_$$"
mkdir -p "$WT_TMPDIR"

# --- Test: valid-input — creates worktree, prints path to stdout ---

# Set up a minimal git repo with main branch so `git worktree add ... main` works.
# Pass commit.gpgsign=false and user config inline — this is a test fixture repo,
# not a user commit, so bypassing the global signing config is intentional here.
(cd "$WT_TMPDIR" \
  && git init >/dev/null 2>&1 \
  && git symbolic-ref HEAD refs/heads/main >/dev/null 2>&1 \
  && git -c commit.gpgsign=false -c user.email="test@test.com" -c user.name="Test" commit --allow-empty -m "init" >/dev/null 2>&1)

expected_path="$WT_TMPDIR/.claude/worktrees/my-feature"
output=$(sed "s|__TMPDIR__|$WT_TMPDIR|g" "$WT_CREATE_FIXTURE_DIR/valid-input.json" \
  | SKIP_NOTIFICATIONS=1 bash "$WT_CREATE_HOOK" 2>/dev/null)
exit_code=$?

if [[ $exit_code -eq 0 && "$output" == "$expected_path" ]]; then
  pass "worktree-create/valid-stdout"
else
  fail "worktree-create/valid-stdout" "expected exit 0 and stdout='$expected_path'; got exit $exit_code, stdout='$output'"
fi

# --- Test: missing-cwd — exits 1 with error on stderr ---

stderr_out=$(bash "$WT_CREATE_HOOK" < "$WT_CREATE_FIXTURE_DIR/missing-cwd.json" 2>&1 >/dev/null)
exit_code=$?

if [[ $exit_code -eq 1 && "$stderr_out" == *"missing 'cwd'"* ]]; then
  pass "worktree-create/missing-cwd-exit1"
else
  fail "worktree-create/missing-cwd-exit1" "expected exit 1 with 'missing cwd' on stderr; got exit $exit_code, stderr='$stderr_out'"
fi

# --- Test: missing-name — exits 1 with error on stderr ---

stderr_out=$(bash "$WT_CREATE_HOOK" < "$WT_CREATE_FIXTURE_DIR/missing-name.json" 2>&1 >/dev/null)
exit_code=$?

if [[ $exit_code -eq 1 && "$stderr_out" == *"missing 'name'"* ]]; then
  pass "worktree-create/missing-name-exit1"
else
  fail "worktree-create/missing-name-exit1" "expected exit 1 with 'missing name' on stderr; got exit $exit_code, stderr='$stderr_out'"
fi

# --- Test: path-already-exists — exits 1 ---

WT_PREEXIST="$WT_TMPDIR/.claude/worktrees/my-feature"
mkdir -p "$WT_PREEXIST"

stderr_out=$(sed "s|__TMPDIR__|$WT_TMPDIR|g" "$WT_CREATE_FIXTURE_DIR/path-already-exists.json" \
  | bash "$WT_CREATE_HOOK" 2>&1 >/dev/null)
exit_code=$?

if [[ $exit_code -eq 1 && "$stderr_out" == *"already exists"* ]]; then
  pass "worktree-create/path-exists-exit1"
else
  fail "worktree-create/path-exists-exit1" "expected exit 1 with 'already exists' on stderr; got exit $exit_code, stderr='$stderr_out'"
fi

# --- Test: venv-present — .venv in repo root gets symlinked into worktree ---

mkdir -p "$WT_TMPDIR/.venv"

output=$(sed "s|__TMPDIR__|$WT_TMPDIR|g" "$WT_CREATE_FIXTURE_DIR/valid-input-venv.json" \
  | SKIP_NOTIFICATIONS=1 bash "$WT_CREATE_HOOK" 2>/dev/null)
exit_code=$?

venv_target="$WT_TMPDIR/.claude/worktrees/my-feature-venv/.venv"
if [[ $exit_code -eq 0 && -L "$venv_target" ]]; then
  pass "worktree-create/venv-symlinked"
else
  fail "worktree-create/venv-symlinked" "expected exit 0 and .venv symlink at '$venv_target'; got exit $exit_code, symlink=$(test -L "$venv_target" && echo yes || echo no)"
fi

# --- Test: venv-absent — no .venv in repo root, worktree has no .venv, exit 0 ---

rm -rf "$WT_TMPDIR/.venv"

output=$(sed "s|__TMPDIR__|$WT_TMPDIR|g" "$WT_CREATE_FIXTURE_DIR/valid-input-novenv.json" \
  | SKIP_NOTIFICATIONS=1 bash "$WT_CREATE_HOOK" 2>/dev/null)
exit_code=$?

novenv_target="$WT_TMPDIR/.claude/worktrees/my-feature-novenv/.venv"
if [[ $exit_code -eq 0 && ! -e "$novenv_target" ]]; then
  pass "worktree-create/no-venv-no-symlink"
else
  fail "worktree-create/no-venv-no-symlink" "expected exit 0 and no .venv at '$novenv_target'; got exit $exit_code, exists=$(test -e "$novenv_target" && echo yes || echo no)"
fi

# ---------------------------------------------------------------------------
# cortex-worktree-remove.sh tests
# ---------------------------------------------------------------------------

WT_REMOVE_HOOK="$REPO_ROOT/claude/hooks/cortex-worktree-remove.sh"
WT_REMOVE_FIXTURE_DIR="$REPO_ROOT/tests/fixtures/hooks/worktree-remove"

# --- Test: missing-worktree-path — exits 1 ---

bash "$WT_REMOVE_HOOK" < "$WT_REMOVE_FIXTURE_DIR/missing-worktree-path.json" >/dev/null 2>&1
exit_code=$?

if [[ $exit_code -eq 1 ]]; then
  pass "worktree-remove/missing-path-exit1"
else
  fail "worktree-remove/missing-path-exit1" "expected exit 1, got $exit_code"
fi

# --- Test: valid-input — exits 0 without sending notifications ---

SKIP_NOTIFICATIONS=1 bash "$WT_REMOVE_HOOK" < "$WT_REMOVE_FIXTURE_DIR/valid-input.json" >/dev/null 2>&1
exit_code=$?

if [[ $exit_code -eq 0 ]]; then
  pass "worktree-remove/valid-input-exit0"
else
  fail "worktree-remove/valid-input-exit0" "expected exit 0, got $exit_code"
fi

# ---------------------------------------------------------------------------
# cortex-sync-permissions.py tests
# ---------------------------------------------------------------------------

SYNC_HOOK="$REPO_ROOT/claude/hooks/cortex-sync-permissions.py"
SYNC_FIXTURE_DIR="$REPO_ROOT/tests/fixtures/hooks/sync-permissions"
SYNC_TMPDIR="$TMPDIR/test_hooks_sync_$$"

# --- Test: no-local-settings — exits 0, no settings.local.json created ---

mkdir -p "$SYNC_TMPDIR"
sed "s|__TMPDIR__|$SYNC_TMPDIR|g" "$SYNC_FIXTURE_DIR/no-local-settings.json" \
  | python3 "$SYNC_HOOK" >/dev/null 2>&1
exit_code=$?

if [[ $exit_code -eq 0 && ! -f "$SYNC_TMPDIR/.claude/settings.local.json" ]]; then
  pass "sync-permissions/no-local-settings"
else
  fail "sync-permissions/no-local-settings" "expected exit 0 with no settings.local.json; got exit $exit_code, file exists=$(test -f "$SYNC_TMPDIR/.claude/settings.local.json" && echo yes || echo no)"
fi

# --- Test: local-no-permissions-key — exits 0, no _globalPermissionsHash added ---

mkdir -p "$SYNC_TMPDIR/.claude"
echo '{"sandbox": {"enabled": true}}' > "$SYNC_TMPDIR/.claude/settings.local.json"

sed "s|__TMPDIR__|$SYNC_TMPDIR|g" "$SYNC_FIXTURE_DIR/local-no-permissions-key.json" \
  | python3 "$SYNC_HOOK" >/dev/null 2>&1
exit_code=$?

has_hash=$(jq 'has("_globalPermissionsHash")' "$SYNC_TMPDIR/.claude/settings.local.json" 2>/dev/null)

if [[ $exit_code -eq 0 && "$has_hash" == "false" ]]; then
  pass "sync-permissions/local-no-permissions-key"
else
  fail "sync-permissions/local-no-permissions-key" "expected exit 0 and no hash; got exit $exit_code, has_hash=$has_hash"
fi

# --- Conditional tests: only run if ~/.claude/settings.json exists ---

GLOBAL_SETTINGS="$HOME/.claude/settings.json"

if [[ "$(jq '(.permissions | type) == "object" and (.permissions | length > 0)' "$GLOBAL_SETTINGS" 2>/dev/null)" == "true" ]]; then
  SYNC_TMPDIR2="$TMPDIR/test_hooks_sync2_$$"
  mkdir -p "$SYNC_TMPDIR2/.claude"

  # Test: merge-fresh — local settings gains _globalPermissionsHash after sync
  echo '{"permissions": {"allow": []}}' > "$SYNC_TMPDIR2/.claude/settings.local.json"
  echo "{\"cwd\": \"$SYNC_TMPDIR2\"}" | python3 "$SYNC_HOOK" >/dev/null 2>&1
  exit_code=$?

  has_hash=$(jq 'has("_globalPermissionsHash")' "$SYNC_TMPDIR2/.claude/settings.local.json" 2>/dev/null)

  if [[ $exit_code -eq 0 && "$has_hash" == "true" ]]; then
    pass "sync-permissions/merge-fresh"
  else
    fail "sync-permissions/merge-fresh" "expected exit 0 with _globalPermissionsHash; got exit $exit_code, has_hash=$has_hash"
  fi

  # Test: already-synced — file unchanged when hash matches
  current_settings=$(jq '.' "$SYNC_TMPDIR2/.claude/settings.local.json")
  echo "{\"cwd\": \"$SYNC_TMPDIR2\"}" | python3 "$SYNC_HOOK" >/dev/null 2>&1
  exit_code=$?

  settings_after=$(jq '.' "$SYNC_TMPDIR2/.claude/settings.local.json")

  if [[ $exit_code -eq 0 && "$current_settings" == "$settings_after" ]]; then
    pass "sync-permissions/already-synced"
  else
    fail "sync-permissions/already-synced" "expected exit 0 with unchanged file; got exit $exit_code"
  fi
else
  echo "SKIP sync-permissions/merge-fresh (no global permissions configured)"
  echo "SKIP sync-permissions/already-synced (no global permissions configured)"
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
