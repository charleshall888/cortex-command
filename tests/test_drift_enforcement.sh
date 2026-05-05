#!/bin/bash
# tests/test_drift_enforcement.sh — verify the .githooks/pre-commit hook
# detects dual-source drift under the policy-aware four-phase design
# (classification guard, staged-driven build decision, conditional rebuild,
# per-build-output-plugin drift loop).
#
# Seven subtests:
#   A) Seed drift in skills/commit/SKILL.md (top-level source) and stage it.
#      Expect non-zero exit: Phase 2 flags BUILD_NEEDED, Phase 3 rebuilds,
#      Phase 4 detects working-tree vs index drift.
#   B) Seed drift in hooks/cortex-validate-commit.sh (top-level source) and
#      stage it. Same expected behavior as A.
#   C) Seed a no-op marker in plugins/cortex-ui-extras/skills/ui-lint/SKILL.md
#      (hand-maintained plugin tree) and stage it. Expect exit 0: Phase 2 sees
#      no build-output triggers so BUILD_NEEDED=0, Phase 3 skips, Phase 4
#      iterates only BUILD_OUTPUT plugins so the hand-maintained edit is not
#      inspected.
#   D) Same as C but against plugins/cortex-pr-review/skills/pr-review/SKILL.md.
#   E) Create plugins/cortex-unclassified/.claude-plugin/plugin.json with a
#      valid name but an unclassified plugin dir. Stage it. Expect non-zero
#      exit and stderr mentioning the fail-closed guard.
#   F) Seed a no-op marker directly in plugins/cortex-core/skills/commit/SKILL.md
#      (build-output plugin tree) WITHOUT touching the top-level source, and
#      stage only the plugin-tree path. Expect non-zero exit: Phase 2's
#      build-output-plugin-path check fires, Phase 3 rebuilds from the
#      unchanged top-level source, Phase 4 detects the regenerated tree
#      diverges from the staged hand-edit.
#   G) Seed drift in claude/hooks/cortex-tool-failure-tracker.sh (top-level
#      source, mirrored into plugins/cortex-overnight/hooks/) and stage it.
#      Same expected behavior as A and B. Regression guard for the Phase 2
#      trigger pattern: claude/hooks/cortex-*.sh paths must trigger
#      BUILD_NEEDED so the mirror cannot drift silently.
#
# Exit 0 iff all seven subtests pass. On failure, leaves the repo restored.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

HOOK="$REPO_ROOT/.githooks/pre-commit"
SKILL_SRC="skills/commit/SKILL.md"
HOOK_SRC="hooks/cortex-validate-commit.sh"
CLAUDE_HOOK_SRC="claude/hooks/cortex-tool-failure-tracker.sh"
UI_EXTRAS_SKILL="plugins/cortex-ui-extras/skills/ui-lint/SKILL.md"
PR_REVIEW_SKILL="plugins/cortex-pr-review/skills/pr-review/SKILL.md"
INTERACTIVE_SKILL="plugins/cortex-core/skills/commit/SKILL.md"

PASS_COUNT=0
FAIL_COUNT=0

# Capture any pre-existing dirty state on the tracked paths the subtests
# mutate so cleanup does not clobber unrelated uncommitted work. List only
# existing tracked pathspecs — an untracked/nonexistent pathspec here would
# cause `git stash push -u` to abort fatally and save no stash.
git stash push -u -- \
    "$SKILL_SRC" \
    "$HOOK_SRC" \
    "$UI_EXTRAS_SKILL" \
    "$PR_REVIEW_SKILL" \
    "$INTERACTIVE_SKILL" \
    >/dev/null 2>&1 || true

cleanup_on_exit() {
    # Ordering is load-bearing: subtest E's untracked-from-HEAD residue must
    # be gone before stash pop runs, or pop refuses and the pre-existing
    # dirty state stash is abandoned.
    rm -rf plugins/cortex-unclassified/ 2>/dev/null || true
    git restore --staged plugins/cortex-unclassified/ 2>/dev/null || true
    git stash pop 2>/dev/null || true
}

trap cleanup_on_exit EXIT

report_pass() {
    echo "[PASS] $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

report_fail() {
    echo "[FAIL] $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

# --- Subtest A: top-level skills drift ---
echo "Subtest A: seed drift in $SKILL_SRC"

printf '\n<!-- drift-test-marker -->\n' >> "$SKILL_SRC"
git add "$SKILL_SRC"

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

git restore --staged "$SKILL_SRC" 2>/dev/null || true
git checkout -- "$SKILL_SRC" 2>/dev/null || true
just build-plugin >/dev/null 2>&1 || true

# --- Subtest B: top-level hook-script drift ---
echo "Subtest B: seed drift in $HOOK_SRC"

printf '\n# drift-test-marker\n' >> "$HOOK_SRC"
git add "$HOOK_SRC"

set +e
HOOK_OUTPUT_B="$("$HOOK" 2>&1)"
HOOK_EXIT_B=$?
set -e

if [ "$HOOK_EXIT_B" -eq 0 ]; then
    report_fail "Subtest B: hook exited 0 but drift was seeded (expected non-zero)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_B"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_B" | grep -q "plugins/cortex-core/hooks/cortex-validate-commit.sh"; then
    report_fail "Subtest B: hook exit $HOOK_EXIT_B but output does not mention plugins/cortex-core/hooks/cortex-validate-commit.sh."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_B"
    echo "-------------------"
else
    report_pass "Subtest B: hook detected hook-script drift (exit $HOOK_EXIT_B)."
fi

git restore --staged "$HOOK_SRC" 2>/dev/null || true
git checkout -- "$HOOK_SRC" 2>/dev/null || true
just build-plugin >/dev/null 2>&1 || true

# --- Subtest C: hand-maintained pass-through (cortex-ui-extras) ---
echo "Subtest C: seed no-op marker in $UI_EXTRAS_SKILL"

printf '\n<!-- drift-test-marker -->\n' >> "$UI_EXTRAS_SKILL"
git add "$UI_EXTRAS_SKILL"

set +e
HOOK_OUTPUT_C="$("$HOOK" 2>&1)"
HOOK_EXIT_C=$?
set -e

if [ "$HOOK_EXIT_C" -ne 0 ]; then
    report_fail "Subtest C: hook exited $HOOK_EXIT_C but hand-maintained edits should pass (expected 0)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_C"
    echo "-------------------"
else
    report_pass "Subtest C: hook passed hand-maintained ui-lint edit (exit 0)."
fi

git restore --staged "$UI_EXTRAS_SKILL" 2>/dev/null || true
git checkout -- "$UI_EXTRAS_SKILL" 2>/dev/null || true
just build-plugin >/dev/null 2>&1 || true

# --- Subtest D: hand-maintained pass-through (cortex-pr-review) ---
echo "Subtest D: seed no-op marker in $PR_REVIEW_SKILL"

printf '\n<!-- drift-test-marker -->\n' >> "$PR_REVIEW_SKILL"
git add "$PR_REVIEW_SKILL"

set +e
HOOK_OUTPUT_D="$("$HOOK" 2>&1)"
HOOK_EXIT_D=$?
set -e

if [ "$HOOK_EXIT_D" -ne 0 ]; then
    report_fail "Subtest D: hook exited $HOOK_EXIT_D but hand-maintained edits should pass (expected 0)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_D"
    echo "-------------------"
else
    report_pass "Subtest D: hook passed hand-maintained pr-review edit (exit 0)."
fi

git restore --staged "$PR_REVIEW_SKILL" 2>/dev/null || true
git checkout -- "$PR_REVIEW_SKILL" 2>/dev/null || true
just build-plugin >/dev/null 2>&1 || true

# --- Subtest E: unclassified-plugin fail-closed guard ---
echo "Subtest E: create unclassified plugins/cortex-unclassified/.claude-plugin/plugin.json"

mkdir -p plugins/cortex-unclassified/.claude-plugin
printf '%s\n' '{"name":"cortex-unclassified"}' > plugins/cortex-unclassified/.claude-plugin/plugin.json
git add plugins/cortex-unclassified/.claude-plugin/plugin.json

set +e
HOOK_OUTPUT_E="$("$HOOK" 2>&1)"
HOOK_EXIT_E=$?
set -e

if [ "$HOOK_EXIT_E" -eq 0 ]; then
    report_fail "Subtest E: hook exited 0 but an unclassified plugin dir was introduced (expected non-zero)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_E"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_E" | grep -qE "cortex-unclassified.*(not classified|unclassified|BUILD_OUTPUT_PLUGINS|HAND_MAINTAINED_PLUGINS)"; then
    report_fail "Subtest E: hook exit $HOOK_EXIT_E but stderr does not mention the unclassified guard."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_E"
    echo "-------------------"
else
    report_pass "Subtest E: hook fail-closed on unclassified plugin (exit $HOOK_EXIT_E)."
fi

git restore --staged plugins/cortex-unclassified/ 2>/dev/null || true
rm -rf plugins/cortex-unclassified/

# --- Subtest F: direct hand-edit to build-output plugin tree (R9 narrowing) ---
echo "Subtest F: seed no-op marker in $INTERACTIVE_SKILL without touching top-level source"

printf '\n<!-- drift-test-marker -->\n' >> "$INTERACTIVE_SKILL"
git add "$INTERACTIVE_SKILL"

set +e
HOOK_OUTPUT_F="$("$HOOK" 2>&1)"
HOOK_EXIT_F=$?
set -e

if [ "$HOOK_EXIT_F" -eq 0 ]; then
    report_fail "Subtest F: hook exited 0 but a staged hand-edit to a build-output plugin tree was seeded (expected non-zero)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_F"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_F" | grep -q "plugins/cortex-core/skills/commit/SKILL.md"; then
    report_fail "Subtest F: hook exit $HOOK_EXIT_F but output does not mention plugins/cortex-core/skills/commit/SKILL.md."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_F"
    echo "-------------------"
else
    report_pass "Subtest F: hook detected direct build-output plugin hand-edit (exit $HOOK_EXIT_F)."
fi

git restore --staged "$INTERACTIVE_SKILL" 2>/dev/null || true
git checkout -- "$INTERACTIVE_SKILL" 2>/dev/null || true
just build-plugin >/dev/null 2>&1 || true

# --- Subtest G: top-level claude/hooks/cortex-* drift ---
# Regression guard: the Phase 2 trigger pattern must include claude/hooks/cortex-
# so build-plugin runs when these sources change. The original pattern only
# covered hooks/cortex-validate-commit.sh, leaving four claude/hooks/cortex-*.sh
# sources able to drift silently.
echo "Subtest G: seed drift in $CLAUDE_HOOK_SRC"

printf '\n# drift-test-marker\n' >> "$CLAUDE_HOOK_SRC"
git add "$CLAUDE_HOOK_SRC"

set +e
HOOK_OUTPUT_G="$("$HOOK" 2>&1)"
HOOK_EXIT_G=$?
set -e

if [ "$HOOK_EXIT_G" -eq 0 ]; then
    report_fail "Subtest G: hook exited 0 but drift was seeded (expected non-zero)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_G"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_G" | grep -q "plugins/cortex-overnight/hooks/cortex-tool-failure-tracker.sh"; then
    report_fail "Subtest G: hook exit $HOOK_EXIT_G but output does not mention plugins/cortex-overnight/hooks/cortex-tool-failure-tracker.sh."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_G"
    echo "-------------------"
else
    report_pass "Subtest G: hook detected claude/hooks/cortex-* drift (exit $HOOK_EXIT_G)."
fi

git restore --staged "$CLAUDE_HOOK_SRC" 2>/dev/null || true
git checkout -- "$CLAUDE_HOOK_SRC" 2>/dev/null || true
just build-plugin >/dev/null 2>&1 || true

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo ""
echo "Drift enforcement tests: $PASS_COUNT/$TOTAL passed"

if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
