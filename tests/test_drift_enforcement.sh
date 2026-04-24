#!/bin/bash
# tests/test_drift_enforcement.sh — verify the .githooks/pre-commit hook
# detects dual-source drift between top-level sources and the committed
# plugins/cortex-interactive/ tree.
#
# Two subtests:
#   A) Seed drift by editing skills/commit/SKILL.md (no-op marker comment),
#      invoke .githooks/pre-commit directly, assert non-zero exit AND that
#      the hook output mentions the drifted skill file. Restore & rebuild.
#   B) Seed drift by editing hooks/cortex-validate-commit.sh (no-op marker
#      comment), invoke the hook, assert non-zero exit AND that the hook
#      output mentions plugins/cortex-interactive/hooks/cortex-validate-commit.sh.
#      Restore & rebuild.
#
# Exit 0 iff both subtests pass. On failure, leaves the repo restored.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

HOOK="$REPO_ROOT/.githooks/pre-commit"
SKILL_SRC="skills/commit/SKILL.md"
HOOK_SRC="hooks/cortex-validate-commit.sh"

PASS_COUNT=0
FAIL_COUNT=0

restore_all() {
    git restore "$SKILL_SRC" 2>/dev/null || true
    git restore "$HOOK_SRC" 2>/dev/null || true
    just build-plugin >/dev/null 2>&1 || true
}

trap restore_all EXIT

report_pass() {
    echo "[PASS] $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

report_fail() {
    echo "[FAIL] $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

# --- Subtest A: skills drift ---
echo "Subtest A: seed drift in $SKILL_SRC"

# Seed drift: append a no-op HTML comment to the skill source.
printf '\n<!-- drift-test-marker -->\n' >> "$SKILL_SRC"

set +e
HOOK_OUTPUT_A="$("$HOOK" 2>&1)"
HOOK_EXIT_A=$?
set -e

if [ "$HOOK_EXIT_A" -eq 0 ]; then
    report_fail "Subtest A: hook exited 0 but drift was seeded (expected non-zero)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_A"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_A" | grep -q "skills/commit/SKILL.md"; then
    report_fail "Subtest A: hook exit $HOOK_EXIT_A but output does not mention skills/commit/SKILL.md."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_A"
    echo "-------------------"
else
    report_pass "Subtest A: hook detected skills drift (exit $HOOK_EXIT_A)."
fi

# Restore subtest A state before moving on.
git restore "$SKILL_SRC"
just build-plugin >/dev/null 2>&1

# --- Subtest B: hook-script drift ---
echo "Subtest B: seed drift in $HOOK_SRC"

# Seed drift: append a no-op shell comment to the hook source.
printf '\n# drift-test-marker\n' >> "$HOOK_SRC"

set +e
HOOK_OUTPUT_B="$("$HOOK" 2>&1)"
HOOK_EXIT_B=$?
set -e

if [ "$HOOK_EXIT_B" -eq 0 ]; then
    report_fail "Subtest B: hook exited 0 but drift was seeded (expected non-zero)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_B"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_B" | grep -q "plugins/cortex-interactive/hooks/cortex-validate-commit.sh"; then
    report_fail "Subtest B: hook exit $HOOK_EXIT_B but output does not mention plugins/cortex-interactive/hooks/cortex-validate-commit.sh."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_B"
    echo "-------------------"
else
    report_pass "Subtest B: hook detected hook-script drift (exit $HOOK_EXIT_B)."
fi

# Restore subtest B state.
git restore "$HOOK_SRC"
just build-plugin >/dev/null 2>&1

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo ""
echo "Drift enforcement tests: $PASS_COUNT/$TOTAL passed"

if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
