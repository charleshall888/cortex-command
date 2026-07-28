#!/bin/bash
# tests/test_drift_enforcement.sh — verify the .githooks/pre-commit hook keeps
# the plugin mirrors consistent under the policy-aware three-phase design
# (classification guard, staged-driven build decision, staged-blob mirror
# reconciliation).
#
# The reconciliation phase does NOT block on drift. It rebuilds the mirrors from
# the STAGED blobs and folds the corrections into the commit, so the expected
# outcome for a seeded source edit is exit 0 plus a staged mirror — not a
# rejection. Building from the staged tree is what makes a concurrent session's
# uncommitted work invisible here.
#
# Seven subtests:
#   A) Seed drift in skills/commit/SKILL.md (top-level source) and stage it.
#      Expect exit 0, the mirror named in the hook output, staged, and carrying
#      the seeded edit.
#   B) Seed drift in hooks/cortex-validate-commit.sh (top-level source) and
#      stage it. Same as A, and additionally asserts the mirror keeps mode
#      100755 — flattening it to 100644 would ship broken plugin binstubs.
#   C) Seed a no-op marker in plugins/cortex-ui-extras/skills/ui-lint/SKILL.md
#      (hand-maintained plugin tree) and stage it. Expect exit 0: Phase 2 sees
#      no build-output triggers so BUILD_NEEDED=0 and the reconciliation phase
#      is skipped entirely, leaving the hand-maintained edit untouched.
#   D) Same as C but against plugins/cortex-pr-review/skills/pr-review/SKILL.md.
#   E) Create plugins/cortex-unclassified/.claude-plugin/plugin.json with a
#      valid name but an unclassified plugin dir. Stage it. Expect non-zero
#      exit and stderr mentioning the fail-closed guard. This is the only
#      remaining blocking path in the hook's plugin handling.
#   F) Seed a no-op marker directly in plugins/cortex-core/skills/commit/SKILL.md
#      (build-output plugin tree) WITHOUT touching the top-level source, and
#      stage only the plugin-tree path. Expect exit 0 and the hand-edit gone
#      from the staged mirror: the rebuild regenerates it from the unchanged
#      canonical source, so the canonical side always wins.
#   G) Seed drift in claude/hooks/cortex-tool-failure-tracker.sh (top-level
#      source, mirrored into plugins/cortex-overnight/hooks/) and stage it.
#      Same expected behavior as A and B. Regression guard for the Phase 2
#      trigger pattern: claude/hooks/cortex-*.sh paths must trigger
#      BUILD_NEEDED so the mirror cannot drift silently.
#
# Exit 0 iff all seven subtests pass. On failure, leaves the repo restored.
#
# Deliberately NOT wired into `just test`, despite the `run_test "test-install"
# bash tests/test_install.sh` precedent in the justfile. This test seeds drift in
# the real working tree and brackets it with `git stash push -u`; running that on
# every test invocation, in a repo where concurrent sessions share one checkout,
# reintroduces the class of hazard this hook exists to avoid — a stash taken
# while a sibling session is mid-edit. Run it by hand when changing the hook:
#     bash tests/test_drift_enforcement.sh

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
    # dirty state stash is abandoned. The reconciliation phase stages mirrors
    # into the real index when the hook is invoked standalone (as here), so any
    # leftover staged mirror must be unstaged for the same reason — `git stash
    # pop` refuses over a staged modification, and its failure is swallowed.
    rm -rf plugins/cortex-unclassified/ 2>/dev/null || true
    git restore --staged plugins/cortex-unclassified/ 2>/dev/null || true
    git restore --staged "$INTERACTIVE_SKILL" 2>/dev/null || true
    rm -f "$(git rev-parse --git-dir)/cortex-reconciled" 2>/dev/null || true
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

if [ "$HOOK_EXIT_A" -ne 0 ]; then
    report_fail "Subtest A: hook exited $HOOK_EXIT_A (expected 0 — reconciliation folds the mirror in, it does not block)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_A"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_A" | grep -q "skills/commit/SKILL.md"; then
    report_fail "Subtest A: hook exit 0 but output does not name the reconciled skills/commit/SKILL.md mirror."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_A"
    echo "-------------------"
elif ! git diff --cached --name-only | grep -qx "$INTERACTIVE_SKILL"; then
    report_fail "Subtest A: mirror $INTERACTIVE_SKILL was not staged into the commit."
elif ! git show ":$INTERACTIVE_SKILL" 2>/dev/null | grep -q "drift-test-marker"; then
    report_fail "Subtest A: staged mirror does not carry the seeded source edit."
else
    report_pass "Subtest A: skills edit reconciled into the commit (exit 0)."
fi

git restore --staged "$SKILL_SRC" "$INTERACTIVE_SKILL" 2>/dev/null || true
git checkout -- "$SKILL_SRC" "$INTERACTIVE_SKILL" 2>/dev/null || true
rm -f "$(git rev-parse --git-dir)/cortex-reconciled"
just build-plugin >/dev/null 2>&1 || true

# --- Subtest B: top-level hook-script drift ---
echo "Subtest B: seed drift in $HOOK_SRC"

printf '\n# drift-test-marker\n' >> "$HOOK_SRC"
git add "$HOOK_SRC"

set +e
HOOK_OUTPUT_B="$("$HOOK" 2>&1)"
HOOK_EXIT_B=$?
set -e

B_MIRROR="plugins/cortex-core/hooks/cortex-validate-commit.sh"
if [ "$HOOK_EXIT_B" -ne 0 ]; then
    report_fail "Subtest B: hook exited $HOOK_EXIT_B (expected 0 — reconciliation folds the mirror in, it does not block)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_B"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_B" | grep -q "$B_MIRROR"; then
    report_fail "Subtest B: hook exit 0 but output does not name the reconciled $B_MIRROR."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_B"
    echo "-------------------"
elif ! git diff --cached --name-only | grep -qx "$B_MIRROR"; then
    report_fail "Subtest B: mirror $B_MIRROR was not staged into the commit."
elif [ "$(git ls-files -s -- "$B_MIRROR" | awk '{print $1}')" != "100755" ]; then
    report_fail "Subtest B: staged mirror lost its executable bit (expected mode 100755)."
else
    report_pass "Subtest B: hook-script edit reconciled into the commit, mode preserved (exit 0)."
fi

git restore --staged "$HOOK_SRC" "$B_MIRROR" 2>/dev/null || true
git checkout -- "$HOOK_SRC" "$B_MIRROR" 2>/dev/null || true
rm -f "$(git rev-parse --git-dir)/cortex-reconciled"
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

if [ "$HOOK_EXIT_F" -ne 0 ]; then
    report_fail "Subtest F: hook exited $HOOK_EXIT_F (expected 0 — the hand-edit is reverted from the canonical source, not blocked)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_F"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_F" | grep -q "plugins/cortex-core/skills/commit/SKILL.md"; then
    report_fail "Subtest F: hook exit 0 but output does not name the reconciled plugins/cortex-core/skills/commit/SKILL.md."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_F"
    echo "-------------------"
elif git show ":$INTERACTIVE_SKILL" 2>/dev/null | grep -q "drift-test-marker"; then
    report_fail "Subtest F: the staged mirror still carries the hand-edit — it should be rebuilt from the unchanged canonical source."
else
    report_pass "Subtest F: direct build-output hand-edit reconciled away from the canonical source (exit 0)."
fi

git restore --staged "$INTERACTIVE_SKILL" 2>/dev/null || true
git checkout -- "$INTERACTIVE_SKILL" 2>/dev/null || true
rm -f "$(git rev-parse --git-dir)/cortex-reconciled"
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

G_MIRROR="plugins/cortex-overnight/hooks/cortex-tool-failure-tracker.sh"
if [ "$HOOK_EXIT_G" -ne 0 ]; then
    report_fail "Subtest G: hook exited $HOOK_EXIT_G (expected 0 — reconciliation folds the mirror in, it does not block)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_G"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_G" | grep -q "$G_MIRROR"; then
    report_fail "Subtest G: hook exit 0 but output does not name the reconciled $G_MIRROR — the Phase 2 claude/hooks/cortex- trigger has regressed."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_G"
    echo "-------------------"
elif ! git diff --cached --name-only | grep -qx "$G_MIRROR"; then
    report_fail "Subtest G: mirror $G_MIRROR was not staged into the commit."
else
    report_pass "Subtest G: claude/hooks/cortex-* edit reconciled into the commit (exit 0)."
fi

git restore --staged "$CLAUDE_HOOK_SRC" "$G_MIRROR" 2>/dev/null || true
git checkout -- "$CLAUDE_HOOK_SRC" "$G_MIRROR" 2>/dev/null || true
rm -f "$(git rev-parse --git-dir)/cortex-reconciled"
just build-plugin >/dev/null 2>&1 || true

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo ""
echo "Drift enforcement tests: $PASS_COUNT/$TOTAL passed"

if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
