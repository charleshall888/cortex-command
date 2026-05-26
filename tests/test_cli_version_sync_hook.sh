#!/bin/bash
# tests/test_cli_version_sync_hook.sh — regression tests for the
# SessionStart drift-detector hook (#235).
#
# Six scenarios, each isolated under $TMPDIR with its own state dir,
# plugin root, cortex shim, and clean-tree git repo on main:
#   (a) no-drift          — installed == expected → no additionalContext, sentinel written
#   (b) drift-golden      — installed < expected  → drift message matches checked-in fixture
#   (c) schema-floor      — wheel + major mismatch → schema-floor message with --refresh-package
#   (d) dev-mode-skip     — CORTEX_DEV_MODE=1     → silent, NO sentinel write
#   (e) probe-failure     — cortex absent on PATH → silent, exit 0
#   (f) throttle-hit      — sentinel within 1800s → silent, fast exit
#
# Exit 0 if all pass, 1 if any fail.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/hooks/cortex-cli-version-sync.sh"
FIXTURE_DIR="$REPO_ROOT/tests/fixtures/hooks/cli-version-sync"

PASS_COUNT=0
FAIL_COUNT=0

pass() { echo "PASS $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo "FAIL $1: $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

# --- Shared scaffolding -----------------------------------------------------

CV_BASE="$TMPDIR/test_cli_version_sync_$$"
mkdir -p "$CV_BASE"
trap 'rm -rf "$CV_BASE"' EXIT

# Build a tmp git repo on main with a clean tree (so the hook's skip
# predicates — dirty_tree, non_main_branch — do NOT fire).
make_clean_repo() {
  local repo_dir="$1"
  mkdir -p "$repo_dir"
  (
    cd "$repo_dir"
    git init -q -b main
    git -c commit.gpgsign=false \
        -c user.email="cv@cv.test" \
        -c user.name="cv-test" \
        -c core.hooksPath=/dev/null \
        commit --allow-empty -q -m "Init test repo for cli-version-sync"
  )
}

# Write a fake plugin-root cli_pin.py carrying a chosen CLI_PIN tuple.
make_plugin_root() {
  local plugin_root="$1"
  local tag="$2"
  local schema="$3"
  mkdir -p "$plugin_root"
  cat > "$plugin_root/cli_pin.py" <<EOF
# Synthesized fixture for cli-version-sync hook test
CLI_PIN = ("$tag", "$schema")
EOF
}

# Install a cortex shim that echoes a fixture JSON (with __CORTEX_ROOT__
# substituted to a chosen path so the hook's is_wheel branch can be
# steered).
make_cortex_shim() {
  local bin_dir="$1"
  local fixture_path="$2"
  local cortex_root="$3"
  mkdir -p "$bin_dir"
  local rendered
  rendered=$(sed "s|__CORTEX_ROOT__|$cortex_root|g" "$fixture_path")
  cat > "$bin_dir/cortex" <<EOF
#!/bin/bash
echo '$rendered'
EOF
  chmod +x "$bin_dir/cortex"
}

# Run the hook in a clean env (env -i) with chosen PATH/HOME/XDG_STATE_HOME/
# CLAUDE_PLUGIN_ROOT plus any extra VAR=value pairs passed as trailing args.
run_hook() {
  local repo_dir="$1"; shift
  local plugin_root="$1"; shift
  local state_dir="$1"; shift
  local bin_dir="$1"; shift
  local stdin_input
  stdin_input=$(sed "s|__TMPDIR__|$repo_dir|g" "$FIXTURE_DIR/claude-agent.json")
  env -i \
    PATH="$bin_dir:/opt/homebrew/bin:/usr/bin:/bin" \
    HOME="$state_dir/home" \
    XDG_STATE_HOME="$state_dir" \
    CLAUDE_PLUGIN_ROOT="$plugin_root" \
    "$@" \
    bash "$HOOK" <<< "$stdin_input"
}

# --- (a) no-drift ----------------------------------------------------------
{
  N="cli-version-sync/no-drift"
  T="$CV_BASE/a"
  mkdir -p "$T"
  make_clean_repo "$T/repo"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  CORTEX_SRC="$T/cortex-source"
  mkdir -p "$CORTEX_SRC/.git"
  make_cortex_shim "$T/bin" "$FIXTURE_DIR/cortex-print-root-current.json" "$CORTEX_SRC"
  mkdir -p "$T/state"
  output=$(run_hook "$T/repo" "$T/plugin-root" "$T/state" "$T/bin" 2>/dev/null)
  exit_code=$?
  if [[ $exit_code -eq 0 && -z "$output" && -f "$T/state/cortex-command/last-version-check" ]]; then
    pass "$N"
  else
    fail "$N" "exit=$exit_code stdout='$output' sentinel=$(test -f "$T/state/cortex-command/last-version-check" && echo yes || echo no)"
  fi
}

# --- (b) drift, golden text match ------------------------------------------
{
  N="cli-version-sync/drift-golden"
  T="$CV_BASE/b"
  mkdir -p "$T"
  make_clean_repo "$T/repo"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  CORTEX_SRC="$T/cortex-source"
  mkdir -p "$CORTEX_SRC/.git"  # has .git → not wheel; drift branch, not schema-floor
  make_cortex_shim "$T/bin" "$FIXTURE_DIR/cortex-print-root-drifted.json" "$CORTEX_SRC"
  mkdir -p "$T/state"
  output=$(run_hook "$T/repo" "$T/plugin-root" "$T/state" "$T/bin" 2>/dev/null)
  exit_code=$?
  ctx=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
  expected=$(sed -e 's|{installed}|0.0.1|g' -e 's|{expected}|9.9.9|g' "$FIXTURE_DIR/expected-additional-context.txt")
  # Drop trailing newline if present (fixture has one; the JSON value won't).
  expected="${expected%$'\n'}"
  if [[ $exit_code -eq 0 && "$ctx" == "$expected" && -f "$T/state/cortex-command/last-version-check" ]]; then
    pass "$N"
  else
    fail "$N" "exit=$exit_code golden-match=$( [[ "$ctx" == "$expected" ]] && echo yes || echo no ) ctx='$ctx' expected='$expected'"
  fi
}

# --- (c) schema-floor ------------------------------------------------------
{
  N="cli-version-sync/schema-floor"
  T="$CV_BASE/c"
  mkdir -p "$T"
  make_clean_repo "$T/repo"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  CORTEX_WHEEL="$T/cortex-wheel"
  mkdir -p "$CORTEX_WHEEL"  # no .git → wheel install path
  make_cortex_shim "$T/bin" "$FIXTURE_DIR/cortex-print-root-schema-floor.json" "$CORTEX_WHEEL"
  mkdir -p "$T/state"
  output=$(run_hook "$T/repo" "$T/plugin-root" "$T/state" "$T/bin" 2>/dev/null)
  exit_code=$?
  ctx=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
  if [[ $exit_code -eq 0 && "$ctx" == *"Schema-floor violation"* && "$ctx" == *"--refresh-package cortex-command"* ]]; then
    pass "$N"
  else
    fail "$N" "exit=$exit_code ctx='$ctx'"
  fi
}

# --- (d) dev-mode-skip -----------------------------------------------------
{
  N="cli-version-sync/dev-mode-skip"
  T="$CV_BASE/d"
  mkdir -p "$T"
  make_clean_repo "$T/repo"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  CORTEX_SRC="$T/cortex-source"
  mkdir -p "$CORTEX_SRC/.git"
  make_cortex_shim "$T/bin" "$FIXTURE_DIR/cortex-print-root-drifted.json" "$CORTEX_SRC"
  mkdir -p "$T/state"
  output=$(run_hook "$T/repo" "$T/plugin-root" "$T/state" "$T/bin" CORTEX_DEV_MODE=1 2>/dev/null)
  exit_code=$?
  # Skip predicate fires before sentinel write — sentinel must NOT exist.
  if [[ $exit_code -eq 0 && -z "$output" && ! -f "$T/state/cortex-command/last-version-check" ]]; then
    pass "$N"
  else
    fail "$N" "exit=$exit_code stdout='$output' sentinel-exists=$(test -f "$T/state/cortex-command/last-version-check" && echo yes || echo no)"
  fi
}

# --- (e) probe-failure -----------------------------------------------------
{
  N="cli-version-sync/probe-failure"
  T="$CV_BASE/e"
  mkdir -p "$T"
  make_clean_repo "$T/repo"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  mkdir -p "$T/bin-empty"  # no cortex shim → probe FileNotFoundError
  mkdir -p "$T/state"
  output=$(run_hook "$T/repo" "$T/plugin-root" "$T/state" "$T/bin-empty" 2>/dev/null)
  exit_code=$?
  if [[ $exit_code -eq 0 && -z "$output" ]]; then
    pass "$N"
  else
    fail "$N" "exit=$exit_code stdout='$output'"
  fi
}

# --- (f) throttle-hit ------------------------------------------------------
{
  N="cli-version-sync/throttle-hit"
  T="$CV_BASE/f"
  mkdir -p "$T"
  make_clean_repo "$T/repo"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  CORTEX_SRC="$T/cortex-source"
  mkdir -p "$CORTEX_SRC/.git"
  make_cortex_shim "$T/bin" "$FIXTURE_DIR/cortex-print-root-drifted.json" "$CORTEX_SRC"
  # Pre-create the sentinel with a fresh mtime so the throttle gate fires.
  mkdir -p "$T/state/cortex-command"
  touch "$T/state/cortex-command/last-version-check"
  # Time the run. python3 used for cross-platform millisecond accuracy
  # (BSD ``date`` lacks ``%N``). 2000ms is a generous CI-flake ceiling;
  # the spec target is ≤200ms on the throttle-hit path.
  T_START=$(python3 -c "import time; print(int(time.time()*1000))")
  output=$(run_hook "$T/repo" "$T/plugin-root" "$T/state" "$T/bin" 2>/dev/null)
  exit_code=$?
  T_END=$(python3 -c "import time; print(int(time.time()*1000))")
  elapsed_ms=$((T_END - T_START))
  if [[ $exit_code -eq 0 && -z "$output" && $elapsed_ms -le 2000 ]]; then
    pass "$N (elapsed=${elapsed_ms}ms)"
  else
    fail "$N" "exit=$exit_code stdout='$output' elapsed=${elapsed_ms}ms"
  fi
}

# --- Summary ---------------------------------------------------------------
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "$PASS_COUNT passed, $FAIL_COUNT failed (out of $TOTAL)"

if [[ $FAIL_COUNT -gt 0 ]]; then
  exit 1
fi
exit 0
