#!/bin/bash
# tests/test_skill_edit_advisor_scope.sh — verify cortex-skill-edit-advisor's
# scoped sub-suite invocation and stdout-cap behavior (#193 Sub-item 4).
#
# Asserts:
#   (1) the advisor invokes exactly the recipe set {test-skill-contracts,
#       test-skill-design} — never `test-skills`, `test-hook-commit`,
#       `test-hooks`, or `test-lifecycle-state`.
#   (2) hookSpecificOutput.additionalContext length ≤ 500 chars on both
#       pass and fail paths (measurement is post-suffix — the final emitted
#       field, including any truncation marker).
#
# Exit 0 if all assertions pass, 1 otherwise.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/claude/hooks/cortex-skill-edit-advisor.sh"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo "PASS $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "FAIL $1: $2" >&2
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

TMPROOT="${TMPDIR:-/tmp}/test_skill_edit_advisor_scope_$$"
mkdir -p "$TMPROOT"

cleanup() {
  rm -rf "$TMPROOT"
}
trap cleanup EXIT

# Build a `just` shim that:
#   - On `just --list`: prints a synthetic listing containing both
#     `test-skill-contracts` and `test-skill-design` so the existence probe
#     at L36 of the hook succeeds regardless of how the probe is shaped.
#   - On any other invocation: records every argv token (one per line) to
#     a trace file and emits a controllable amount of stdout, exits with
#     a controllable status.
#
# The shim distinguishes invocations via its argv. Trace file accumulates
# across all invocations within one hook run; the `--list` invocation is
# intentionally excluded from the trace.
make_shim() {
  local shim_dir="$1"
  local trace_file="$2"
  local recipe_output="$3"
  local recipe_exit="$4"

  mkdir -p "$shim_dir"
  cat > "$shim_dir/just" <<SHIM
#!/bin/bash
# generated test shim
if [[ "\${1:-}" == "--list" ]]; then
  # Synthesize a listing that contains both scoped recipes.
  cat <<LIST
Available recipes:
    test-skill-contracts
    test-skill-design
    test-skill-behavior
    test-skill-pressure skill
LIST
  exit 0
fi
# Record each argv token (one per line) to the trace.
for arg in "\$@"; do
  printf '%s\n' "\$arg" >> "$trace_file"
done
# Emit the configured recipe output and exit status.
printf '%s' "$recipe_output"
exit $recipe_exit
SHIM
  chmod +x "$shim_dir/just"
}

# Tokenize a trace file into the SET of invoked-recipe names. Drops:
#   - empty lines (defensive)
#   - flag-like tokens (any beginning with `-`)
# Returns the unique sorted set on stdout, one recipe per line.
trace_to_recipe_set() {
  local trace_file="$1"
  if [ ! -s "$trace_file" ]; then
    return 0
  fi
  grep -vE '^(-|$)' "$trace_file" | sort -u
}

# Build a synthetic PostToolUse payload for an Edit on a SKILL.md.
make_payload() {
  cat <<'EOF'
{"tool_name":"Edit","tool_input":{"file_path":"skills/example/SKILL.md"},"tool_response":{}}
EOF
}

# Drive the hook with the shim on PATH and capture its JSON output.
run_hook() {
  local shim_dir="$1"
  local payload
  payload="$(make_payload)"
  PATH="$shim_dir:$PATH" bash "$HOOK" <<< "$payload"
}

# ---------------------------------------------------------------------------
# Test 1 — recipe set is exactly {test-skill-contracts, test-skill-design}
#          on a passing path.
# ---------------------------------------------------------------------------

T1_DIR="$TMPROOT/t1"
T1_TRACE="$T1_DIR/trace"
mkdir -p "$T1_DIR"
: > "$T1_TRACE"
# Short pass-path output so cap test is unrelated here.
make_shim "$T1_DIR/bin" "$T1_TRACE" "5 passed" 0

T1_OUT="$(run_hook "$T1_DIR/bin")"

T1_RECIPES="$(trace_to_recipe_set "$T1_TRACE")"
T1_EXPECTED="$(printf 'test-skill-contracts\ntest-skill-design\n' | sort -u)"

if [ "$T1_RECIPES" = "$T1_EXPECTED" ]; then
  pass "T1: invoked recipe set equals {test-skill-contracts, test-skill-design}"
else
  fail "T1" "recipe set mismatch; got: $(echo "$T1_RECIPES" | tr '\n' ',' ); expected: $(echo "$T1_EXPECTED" | tr '\n' ',')"
fi

# Bonus check: ensure no forbidden recipe leaked.
if echo "$T1_RECIPES" | grep -qE '^(test-skills|test-hook-commit|test-hooks|test-lifecycle-state)$'; then
  fail "T1-forbidden" "forbidden recipe in trace: $T1_RECIPES"
else
  pass "T1-forbidden: no forbidden recipe invoked"
fi

# ---------------------------------------------------------------------------
# Test 2 — additionalContext length ≤ 500 chars on the PASS path with a
#          large recipe-output payload (drives truncation).
# ---------------------------------------------------------------------------

T2_DIR="$TMPROOT/t2"
T2_TRACE="$T2_DIR/trace"
mkdir -p "$T2_DIR"
: > "$T2_TRACE"
T2_BIG="$(printf 'x%.0s' $(seq 1 2000))"  # 2000-char output
make_shim "$T2_DIR/bin" "$T2_TRACE" "$T2_BIG" 0

T2_OUT="$(run_hook "$T2_DIR/bin")"
T2_LEN="$(printf '%s' "$T2_OUT" | jq -r '.hookSpecificOutput.additionalContext // ""' | wc -c | tr -d ' ')"
# wc -c counts a trailing newline that jq -r adds; allow up to 501 to cover it.
if [ "$T2_LEN" -le 501 ]; then
  pass "T2: PASS-path additionalContext length=$T2_LEN ≤ 501 (≤500 + trailing newline)"
else
  fail "T2" "PASS-path additionalContext length=$T2_LEN > 501"
fi

# ---------------------------------------------------------------------------
# Test 3 — additionalContext length ≤ 500 chars on the FAIL path with a
#          large recipe-output payload (drives truncation in failure case).
# ---------------------------------------------------------------------------

T3_DIR="$TMPROOT/t3"
T3_TRACE="$T3_DIR/trace"
mkdir -p "$T3_DIR"
: > "$T3_TRACE"
T3_BIG="$(printf 'y%.0s' $(seq 1 2000))"
make_shim "$T3_DIR/bin" "$T3_TRACE" "$T3_BIG" 1

T3_OUT="$(run_hook "$T3_DIR/bin")"
T3_LEN="$(printf '%s' "$T3_OUT" | jq -r '.hookSpecificOutput.additionalContext // ""' | wc -c | tr -d ' ')"
if [ "$T3_LEN" -le 501 ]; then
  pass "T3: FAIL-path additionalContext length=$T3_LEN ≤ 501"
else
  fail "T3" "FAIL-path additionalContext length=$T3_LEN > 501"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "----- Summary -----"
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
