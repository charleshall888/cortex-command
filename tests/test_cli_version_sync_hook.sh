#!/bin/bash
# tests/test_cli_version_sync_hook.sh — regression tests for the
# SessionStart drift-detector hook (#235).
#
# Eleven scenarios, each isolated under $TMPDIR with its own state dir,
# plugin root, cortex shim, and clean-tree git repo on main:
#   (a) no-drift              — installed == expected → no additionalContext, sentinel written
#   (b) drift-golden          — installed < expected  → drift message matches checked-in fixture
#   (c) schema-floor          — wheel + major mismatch → schema-floor message with --refresh-package
#   (d) dev-mode-skip         — CORTEX_DEV_MODE=1     → silent, NO sentinel write
#   (e) probe-failure         — cortex absent on PATH → R27 warn-only additionalContext (T12)
#   (f) throttle-hit          — sentinel within 1800s → silent, fast exit
#   (g) marker-prior-session  — install.in-progress marker fresh + drift → "prior session" line (R24, T12)
#   (h) prior-failure-recent  — session-install-failed.<ts> within 30 min + drift → "Previous … failed" line (R25, T12)
#   (i) prior-failure-stale   — session-install-failed.<ts> older than 30 min + drift → no failure line (R25, T12)
#   (j) first-install-warn    — cortex absent → R27 warn-only additionalContext, no install spawned (T12)
#   (k) dirty-tree-narrowing  — dirty non-cortex repo does NOT skip; dirty cortex-command repo DOES skip (R26, T12)
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
# R27 (T12) changed the probe-failure branch from silent-skip to warn-only:
# when ``cortex --print-root`` fails (binary missing / non-zero exit), the
# hook emits a warn-only ``additionalContext`` pointing at the manual
# remediation command. The hook does NOT trigger a SessionStart install.
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
  ctx=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
  if [[ $exit_code -eq 0 && "$ctx" == *"cortex CLI is not installed"* && "$ctx" == *"uv tool install"* ]]; then
    pass "$N"
  else
    fail "$N" "exit=$exit_code ctx='$ctx'"
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

# --- (g) marker-prior-session ----------------------------------------------
# R24 (T12): when the install-in-progress marker exists with fresh mtime
# (<600s) AND drift is detected, the hook appends a "prior session" warning
# line to ``additionalContext``. The marker write happens inside the async
# install hook's flock — by the time the sync hook composes its context,
# any marker it sees necessarily belongs to a prior session's in-flight
# install (the current session's marker, if any, races ahead concurrently).
{
  N="cli-version-sync/marker-prior-session"
  T="$CV_BASE/g"
  mkdir -p "$T"
  make_clean_repo "$T/repo"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  CORTEX_SRC="$T/cortex-source"
  mkdir -p "$CORTEX_SRC/.git"
  make_cortex_shim "$T/bin" "$FIXTURE_DIR/cortex-print-root-drifted.json" "$CORTEX_SRC"
  mkdir -p "$T/state/cortex-command"
  # Touch marker with current mtime (well within the 600s freshness window).
  touch "$T/state/cortex-command/install.in-progress"
  output=$(run_hook "$T/repo" "$T/plugin-root" "$T/state" "$T/bin" 2>/dev/null)
  exit_code=$?
  ctx=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
  if [[ $exit_code -eq 0 && "$ctx" == *"prior session"* && "$ctx" == *"bash \`cortex"* ]]; then
    pass "$N"
  else
    fail "$N" "exit=$exit_code ctx='$ctx'"
  fi
}

# --- (h) prior-failure-recent ----------------------------------------------
# R25 (T12): a ``session-install-failed.<ts>`` sentinel within the 1800s
# (30-min) window — aligned to R22's retry-throttle — surfaces a "Previous
# background install attempt failed" line on the next session's drift
# warning, citing the failure timestamp and manual remediation command.
{
  N="cli-version-sync/prior-failure-recent"
  T="$CV_BASE/h"
  mkdir -p "$T"
  make_clean_repo "$T/repo"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  CORTEX_SRC="$T/cortex-source"
  mkdir -p "$CORTEX_SRC/.git"
  make_cortex_shim "$T/bin" "$FIXTURE_DIR/cortex-print-root-drifted.json" "$CORTEX_SRC"
  mkdir -p "$T/state/cortex-command"
  # Sentinel with mtime 5 minutes in the past (well within the 1800s window).
  # Python used for cross-platform mtime control — BSD ``touch -d`` lacks
  # relative-time support.
  SENTINEL_RECENT="$T/state/cortex-command/session-install-failed.111111"
  touch "$SENTINEL_RECENT"
  python3 -c "import os, time; os.utime('$SENTINEL_RECENT', (time.time() - 300, time.time() - 300))"
  output=$(run_hook "$T/repo" "$T/plugin-root" "$T/state" "$T/bin" 2>/dev/null)
  exit_code=$?
  ctx=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
  if [[ $exit_code -eq 0 && "$ctx" == *"Previous background install attempt failed"* && "$ctx" == *"uv tool install"* ]]; then
    pass "$N"
  else
    fail "$N" "exit=$exit_code ctx='$ctx'"
  fi
}

# --- (i) prior-failure-stale -----------------------------------------------
# R25 (T12) boundary: a ``session-install-failed.<ts>`` sentinel older than
# 1800s does NOT produce the "Previous … failed" warning. Aligned to R22 so
# the warning fires only while retries are also throttled.
{
  N="cli-version-sync/prior-failure-stale"
  T="$CV_BASE/i"
  mkdir -p "$T"
  make_clean_repo "$T/repo"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  CORTEX_SRC="$T/cortex-source"
  mkdir -p "$CORTEX_SRC/.git"
  make_cortex_shim "$T/bin" "$FIXTURE_DIR/cortex-print-root-drifted.json" "$CORTEX_SRC"
  mkdir -p "$T/state/cortex-command"
  # Sentinel mtime ~31 minutes ago (just past the 1800s cutoff).
  SENTINEL_STALE="$T/state/cortex-command/session-install-failed.222222"
  touch "$SENTINEL_STALE"
  python3 -c "import os, time; os.utime('$SENTINEL_STALE', (time.time() - 1860, time.time() - 1860))"
  output=$(run_hook "$T/repo" "$T/plugin-root" "$T/state" "$T/bin" 2>/dev/null)
  exit_code=$?
  ctx=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
  # Drift line still present (sanity), but the prior-failure line is absent.
  if [[ $exit_code -eq 0 && "$ctx" == *"cortex CLI is drifted"* && "$ctx" != *"Previous background install attempt failed"* ]]; then
    pass "$N"
  else
    fail "$N" "exit=$exit_code ctx='$ctx'"
  fi
}

# --- (j) first-install-warn ------------------------------------------------
# R27 (T12): ``cortex`` not installed → warn-only ``additionalContext``
# pointing at the manual ``uv tool install`` remediation OR the MCP-call
# auto-install path. SessionStart does NOT spawn an install. Distinct from
# scenario (e) (which exercises the same branch) by being a labelled T12-
# coverage test independent of the pre-existing probe-failure regression.
{
  N="cli-version-sync/first-install-warn"
  T="$CV_BASE/j"
  mkdir -p "$T"
  make_clean_repo "$T/repo"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  mkdir -p "$T/bin-empty"  # no cortex shim → probe failure → R27 warn branch
  mkdir -p "$T/state"
  output=$(run_hook "$T/repo" "$T/plugin-root" "$T/state" "$T/bin-empty" 2>/dev/null)
  exit_code=$?
  ctx=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
  # Warn-only assertions: the message names the missing CLI and cites the
  # remediation command; the hook does NOT spawn ``uv tool install`` (the
  # absence of any uv invocation is enforced by the sync hook never
  # calling subprocess for install — visibility-only contract).
  if [[ $exit_code -eq 0 \
        && "$ctx" == *"cortex CLI is not installed"* \
        && "$ctx" == *"uv tool install --reinstall --refresh-package cortex-command"* \
        && "$ctx" == *"cortex-overnight MCP"* ]]; then
    pass "$N"
  else
    fail "$N" "exit=$exit_code ctx='$ctx'"
  fi
}

# --- (k) dirty-tree-narrowing ----------------------------------------------
# R26 (T12): the dirty-tree skip predicate now only fires when ``cwd``
# resolves into the cortex-command source repo (detected via the origin
# remote URL matching ``cortex-command.git`` or
# ``charleshall888/cortex-command``). Verified in two halves:
#   (k1) dirty NON-cortex-command tree does NOT skip → drift line emitted
#   (k2) dirty cortex-command tree DOES skip       → no additionalContext
{
  N="cli-version-sync/dirty-tree-narrowing"
  T="$CV_BASE/k"
  mkdir -p "$T"
  make_plugin_root "$T/plugin-root" "v9.9.9" "2.0"
  CORTEX_SRC="$T/cortex-source"
  mkdir -p "$CORTEX_SRC/.git"
  make_cortex_shim "$T/bin" "$FIXTURE_DIR/cortex-print-root-drifted.json" "$CORTEX_SRC"

  # (k1) Dirty non-cortex-command repo (origin remote points elsewhere).
  OTHER_REPO="$T/other-repo"
  mkdir -p "$OTHER_REPO"
  (
    cd "$OTHER_REPO"
    git init -q -b main
    git -c commit.gpgsign=false \
        -c user.email="cv@cv.test" \
        -c user.name="cv-test" \
        -c core.hooksPath=/dev/null \
        commit --allow-empty -q -m "Init non-cortex repo"
    git remote add origin "https://example.com/some-other-repo.git"
    # Make the tree dirty so the (narrowed) dirty-tree predicate would
    # fire if R26 narrowing were missing.
    echo "dirty" > untracked.txt
  )
  mkdir -p "$T/state-k1"
  output_k1=$(run_hook "$OTHER_REPO" "$T/plugin-root" "$T/state-k1" "$T/bin" 2>/dev/null)
  exit_k1=$?
  ctx_k1=$(echo "$output_k1" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
  k1_ok=0
  if [[ $exit_k1 -eq 0 && "$ctx_k1" == *"cortex CLI is drifted"* ]]; then
    k1_ok=1
  fi

  # (k2) Dirty cortex-command repo (origin remote matches canonical URL).
  CORTEX_REPO="$T/cortex-command-repo"
  mkdir -p "$CORTEX_REPO"
  (
    cd "$CORTEX_REPO"
    git init -q -b main
    git -c commit.gpgsign=false \
        -c user.email="cv@cv.test" \
        -c user.name="cv-test" \
        -c core.hooksPath=/dev/null \
        commit --allow-empty -q -m "Init cortex-command repo"
    git remote add origin "https://github.com/charleshall888/cortex-command.git"
    echo "dirty" > untracked.txt
  )
  mkdir -p "$T/state-k2"
  output_k2=$(run_hook "$CORTEX_REPO" "$T/plugin-root" "$T/state-k2" "$T/bin" 2>/dev/null)
  exit_k2=$?
  # Skip predicate fires → empty stdout, exit 0, no sentinel (sentinel
  # write happens after probe; skip-predicate gate is before probe).
  k2_ok=0
  if [[ $exit_k2 -eq 0 && -z "$output_k2" && ! -f "$T/state-k2/cortex-command/last-version-check" ]]; then
    k2_ok=1
  fi

  if (( k1_ok == 1 && k2_ok == 1 )); then
    pass "$N"
  else
    fail "$N" "k1_ok=$k1_ok (exit=$exit_k1 ctx_k1='$ctx_k1') k2_ok=$k2_ok (exit=$exit_k2 stdout='$output_k2')"
  fi
}

# --- Summary ---------------------------------------------------------------
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "$PASS_COUNT passed, $FAIL_COUNT failed (out of $TOTAL)"

if [[ $FAIL_COUNT -gt 0 ]]; then
  exit 1
fi
exit 0
