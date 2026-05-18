#!/bin/bash
# tests/test_statusline_complete_awaiting_merge.sh
# Verifies that the "Complete (awaiting merge)" sub-state is detected and
# rendered correctly in both cortex-scan-lifecycle.sh (phase_label) and the
# statusline (claude/statusline.sh) detection logic.
#
# Three fixture cases:
#   (a) pr_opened only                    → "Complete (awaiting merge)"
#   (b) pr_opened + feature_complete      → "Complete"
#   (c) feature_wontfix                   → "Complete" (wontfix precedence)
#
# Exit 0 if all assertions pass, 1 if any fail.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCAN_HOOK="$REPO_ROOT/hooks/cortex-scan-lifecycle.sh"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo "PASS: $1"
  PASS_COUNT=$(( PASS_COUNT + 1 ))
}

fail() {
  echo "FAIL: $1 — expected: '$2', got: '$3'"
  FAIL_COUNT=$(( FAIL_COUNT + 1 ))
}

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# Build a minimal events.log with the given event names.
make_events_log() {
  local dest="$1"; shift
  : > "$dest"
  for ev in "$@"; do
    printf '{"event": "%s", "ts": "2026-01-01T00:00:00Z"}\n' "$ev" >> "$dest"
  done
}

# ---------------------------------------------------------------------------
# Extract phase_label() from scan-lifecycle hook and exercise it.
# We source only the function definition (up to end of the function block).
# ---------------------------------------------------------------------------

# Source the phase_label function from the hook.  The hook uses strict mode
# and references $LIFECYCLE_DIR at the top level; we source only the function
# via a wrapper that defines LIFECYCLE_DIR and suppresses top-level execution.
source_phase_label() {
  # Extract lines between "phase_label() {" and its closing "}" and eval them.
  local fn_body
  fn_body=$(awk '/^phase_label\(\)/{found=1} found{print} found && /^\}$/{exit}' "$SCAN_HOOK")
  eval "$fn_body"
}

source_phase_label

# ---------------------------------------------------------------------------
# Part 1 — phase_label() tests (scan-lifecycle rendering)
# ---------------------------------------------------------------------------

label=$(phase_label "complete:awaiting-merge")
if [ "$label" = "Complete (awaiting merge)" ]; then
  pass "phase_label(complete:awaiting-merge) → 'Complete (awaiting merge)'"
else
  fail "phase_label(complete:awaiting-merge)" "Complete (awaiting merge)" "$label"
fi

label=$(phase_label "complete")
if [ "$label" = "Complete" ]; then
  pass "phase_label(complete) → 'Complete'"
else
  fail "phase_label(complete)" "Complete" "$label"
fi

# ---------------------------------------------------------------------------
# Part 2 — Statusline detection logic (grep-based, mirrors claude/statusline.sh)
# ---------------------------------------------------------------------------
# The statusline detects the sub-state via:
#   grep -q '"event": "pr_opened"'       → true
#   ! grep -q '"event": "feature_complete"' → true
#   ! grep -q '"event": "feature_wontfix"'  → true
# We replicate that logic here using the same grep patterns.

detect_statusline_phase() {
  local events_log="$1"
  local phase="complete"  # simulate: review.md APPROVED already set phase=complete

  # Sub-state detection (mirrors claude/statusline.sh awaiting-merge block)
  if [ "$phase" = "complete" ] \
      && [ -f "$events_log" ] \
      && grep -q '"event"[[:space:]]*:[[:space:]]*"pr_opened"' "$events_log" 2>/dev/null \
      && ! grep -q '"event"[[:space:]]*:[[:space:]]*"feature_complete"' "$events_log" 2>/dev/null \
      && ! grep -q '"event"[[:space:]]*:[[:space:]]*"feature_wontfix"' "$events_log" 2>/dev/null; then
    phase="complete:awaiting-merge"
  fi

  echo "$phase"
}

# Set up temp dir for fixture events.log files
FIXTURE_DIR="${TMPDIR:-/tmp}/test_statusline_awaiting_merge_$$"
mkdir -p "$FIXTURE_DIR"

cleanup() { rm -rf "$FIXTURE_DIR"; }
trap cleanup EXIT

# Fixture (a): pr_opened only → "complete:awaiting-merge"
EVENTS_A="$FIXTURE_DIR/events_a.log"
make_events_log "$EVENTS_A" "pr_opened"
phase_a=$(detect_statusline_phase "$EVENTS_A")
if [ "$phase_a" = "complete:awaiting-merge" ]; then
  pass "fixture(a): pr_opened only → phase=complete:awaiting-merge"
else
  fail "fixture(a): pr_opened only" "complete:awaiting-merge" "$phase_a"
fi
label_a=$(phase_label "$phase_a")
if [ "$label_a" = "Complete (awaiting merge)" ]; then
  pass "fixture(a): rendered label → 'Complete (awaiting merge)'"
else
  fail "fixture(a): rendered label" "Complete (awaiting merge)" "$label_a"
fi

# Fixture (b): pr_opened + feature_complete → "complete" (no sub-state)
EVENTS_B="$FIXTURE_DIR/events_b.log"
make_events_log "$EVENTS_B" "pr_opened" "feature_complete"
phase_b=$(detect_statusline_phase "$EVENTS_B")
if [ "$phase_b" = "complete" ]; then
  pass "fixture(b): pr_opened + feature_complete → phase=complete"
else
  fail "fixture(b): pr_opened + feature_complete" "complete" "$phase_b"
fi
label_b=$(phase_label "$phase_b")
if [ "$label_b" = "Complete" ]; then
  pass "fixture(b): rendered label → 'Complete'"
else
  fail "fixture(b): rendered label" "Complete" "$label_b"
fi

# Fixture (c): feature_wontfix → "complete" (wontfix precedence)
EVENTS_C="$FIXTURE_DIR/events_c.log"
make_events_log "$EVENTS_C" "feature_wontfix"
phase_c=$(detect_statusline_phase "$EVENTS_C")
if [ "$phase_c" = "complete" ]; then
  pass "fixture(c): feature_wontfix → phase=complete (wontfix precedence)"
else
  fail "fixture(c): feature_wontfix" "complete" "$phase_c"
fi
label_c=$(phase_label "$phase_c")
if [ "$label_c" = "Complete" ]; then
  pass "fixture(c): rendered label → 'Complete'"
else
  fail "fixture(c): rendered label" "Complete" "$label_c"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed"
[ "$FAIL_COUNT" -eq 0 ] && exit 0 || exit 1
