#!/bin/bash
# tests/test_overnight_main_commit_block.sh — verify the .githooks/pre-commit
# Phase 0 overnight main-branch guard.
#
# Four canonical cases (Req 3 a–d) across two scaffolds:
#
#   Scaffold A (worktree-on-main path): home repo on `trunk`, `main` is a ref,
#   one worktree checks out `main`, a second worktree checks out
#   `integration`. Tests run from inside the worktrees.
#
#   Scaffold B ($REPO_ROOT-on-main path, the actual session-1708 vector):
#   home repo on `main`, a sibling worktree on `integration`. Tests run from
#   inside the home repo.
#
#   (a) Scaffold A worktree on main + CORTEX_RUNNER_CHILD=1 → exit non-zero,
#       stderr matches "Phase 0", "refs/heads/main", "CORTEX_RUNNER_CHILD".
#   (b) Scaffold B home repo on main + CORTEX_RUNNER_CHILD=1 → exit non-zero,
#       same three substrings in stderr.
#   (c) Scaffold A worktree on main, no CORTEX_RUNNER_CHILD → exit 0
#       (interactive case allowed).
#   (d) Scaffold A worktree on integration + CORTEX_RUNNER_CHILD=1 → exit 0
#       (legitimate runner commit on integration branch allowed).
#
# Two hardening cases (close B-class critical-review residue):
#
#   (f) Scaffold A worktree on main + CORTEX_RUNNER_CHILD=0 → exit 0
#       (strict-equality preserved; residue B-3).
#   (e) Scaffold A home repo on detached HEAD + CORTEX_RUNNER_CHILD=1 → exit 0
#       (fail-open on detached HEAD; residue B-4).
#
#   Ordering invariant: case (f) MUST run before case (e); see comment block
#   above the case (f) section for rationale.
#
# Two structural assertions:
#   - Gitdir sharing: `git -C <worktree> rev-parse --git-common-dir` resolves
#     to the home repo's `.git/`. Verifies hook resolution flows through the
#     shared gitdir.
#   - `extensions.worktreeConfig` is unset/empty in the test repo, confirming
#     the hook-resolution path is not subverted by per-worktree config.
#
# Exit 0 iff all four cases and both structural assertions pass.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_SRC="$REPO_ROOT/.githooks/pre-commit"

# Use a unique workdir under TMPDIR so parallel test runs don't collide and
# leftover state from a killed run doesn't corrupt this run.
WORK="${TMPDIR:-/tmp}/test_overnight_main_commit_block_$$"
SCAFF_A="$WORK/scaffA"
SCAFF_A_WT="$WORK/scaffA-wt"
SCAFF_A_WT_INT="$WORK/scaffA-wt-int"
SCAFF_B="$WORK/scaffB"
SCAFF_B_WT="$WORK/scaffB-wt"

PASS_COUNT=0
FAIL_COUNT=0

report_pass() {
    echo "[PASS] $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

report_fail() {
    echo "[FAIL] $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

cleanup_on_exit() {
    rm -rf \
        "$SCAFF_A" \
        "$SCAFF_A_WT" \
        "$SCAFF_A_WT_INT" \
        "$SCAFF_B" \
        "$SCAFF_B_WT" \
        2>/dev/null || true
    rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup_on_exit EXIT

mkdir -p "$WORK"

# Minimal justfile content: provides the two helper recipes the hook's Phase 1
# invokes (`just _list-build-output-plugins`, `just _list-hand-maintained-plugins`).
# The hook's Phase 4 loop iterates the build-output array under `set -u`, so an
# empty array would error on bash 3.2; we list one of each plugin class to keep
# Phase 1 + Phase 4 happy. The plugin dir does not need to exist on disk; the
# hook skips plugins absent from both the working tree and the index.
JUSTFILE_CONTENT='_list-build-output-plugins:
    @echo cortex-interactive

_list-hand-maintained-plugins:
    @echo cortex-pr-review
'

# Resolve a path through symlinks (macOS /var/folders → /private/var/folders).
# `realpath` on macOS BSD does not accept GNU flags; use the portable
# `cd && pwd -P` trick instead.
resolve_path() {
    (cd "$1" && pwd -P)
}

# -----------------------------------------------------------------------------
# Scaffold A — worktree-on-main path
# -----------------------------------------------------------------------------
echo "Setting up Scaffold A..."

git init --initial-branch=trunk "$SCAFF_A" >/dev/null 2>&1
git -C "$SCAFF_A" \
    -c user.email=t@t \
    -c user.name=T \
    -c commit.gpgsign=false \
    commit --allow-empty -m "init" >/dev/null 2>&1

# Commit a justfile on trunk BEFORE branching main, so the main worktree (and
# the integration worktree, which forks from HEAD) inherit it. The hook's
# `cd "$REPO_ROOT"` step lands in the worktree, where it needs to find the
# justfile.
printf '%s' "$JUSTFILE_CONTENT" > "$SCAFF_A/justfile"
git -C "$SCAFF_A" add justfile
git -C "$SCAFF_A" \
    -c user.email=t@t \
    -c user.name=T \
    -c commit.gpgsign=false \
    commit -m "add justfile" >/dev/null 2>&1

git -C "$SCAFF_A" branch main trunk
git -C "$SCAFF_A" config core.hooksPath .githooks
mkdir -p "$SCAFF_A/.githooks"
cp "$HOOK_SRC" "$SCAFF_A/.githooks/pre-commit"

git -C "$SCAFF_A" worktree add "$SCAFF_A_WT" main >/dev/null 2>&1
git -C "$SCAFF_A" worktree add "$SCAFF_A_WT_INT" -b integration >/dev/null 2>&1

# Per-worktree user config so commits would succeed if reached.
for wt in "$SCAFF_A_WT" "$SCAFF_A_WT_INT"; do
    git -C "$wt" config user.email t@t
    git -C "$wt" config user.name T
    git -C "$wt" config commit.gpgsign false
done

# -----------------------------------------------------------------------------
# Scaffold B — $REPO_ROOT-on-main path (actual session-1708 vector)
# -----------------------------------------------------------------------------
echo "Setting up Scaffold B..."

git init --initial-branch=main "$SCAFF_B" >/dev/null 2>&1
git -C "$SCAFF_B" \
    -c user.email=t@t \
    -c user.name=T \
    -c commit.gpgsign=false \
    commit --allow-empty -m "init" >/dev/null 2>&1

printf '%s' "$JUSTFILE_CONTENT" > "$SCAFF_B/justfile"
git -C "$SCAFF_B" add justfile
git -C "$SCAFF_B" \
    -c user.email=t@t \
    -c user.name=T \
    -c commit.gpgsign=false \
    commit -m "add justfile" >/dev/null 2>&1

git -C "$SCAFF_B" config core.hooksPath .githooks
mkdir -p "$SCAFF_B/.githooks"
cp "$HOOK_SRC" "$SCAFF_B/.githooks/pre-commit"

git -C "$SCAFF_B" worktree add "$SCAFF_B_WT" -b integration >/dev/null 2>&1

git -C "$SCAFF_B" config user.email t@t
git -C "$SCAFF_B" config user.name T
git -C "$SCAFF_B" config commit.gpgsign false

# -----------------------------------------------------------------------------
# Case (a) — Scaffold A worktree on main + CORTEX_RUNNER_CHILD=1
# -----------------------------------------------------------------------------
echo ""
echo "Case (a): Scaffold A worktree on main, CORTEX_RUNNER_CHILD=1"

echo "case-a-content" > "$SCAFF_A_WT/case-a.txt"
git -C "$SCAFF_A_WT" add case-a.txt

cd "$SCAFF_A_WT"
unset GIT_DIR
set +e
HOOK_OUTPUT_A="$(CORTEX_RUNNER_CHILD=1 bash "$SCAFF_A/.githooks/pre-commit" 2>&1)"
HOOK_EXIT_A=$?
set -e
cd "$WORK"

if [ "$HOOK_EXIT_A" -eq 0 ]; then
    report_fail "Case (a): hook exited 0 but Phase 0 should have rejected (expected non-zero)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_A"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_A" | grep -q "Phase 0"; then
    report_fail "Case (a): hook exit $HOOK_EXIT_A but stderr missing 'Phase 0'."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_A"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_A" | grep -q "refs/heads/main"; then
    report_fail "Case (a): hook exit $HOOK_EXIT_A but stderr missing 'refs/heads/main'."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_A"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_A" | grep -q "CORTEX_RUNNER_CHILD"; then
    report_fail "Case (a): hook exit $HOOK_EXIT_A but stderr missing 'CORTEX_RUNNER_CHILD'."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_A"
    echo "-------------------"
else
    report_pass "Case (a): Scaffold A worktree on main rejected (exit $HOOK_EXIT_A)."
fi

# -----------------------------------------------------------------------------
# Case (b) — Scaffold B home repo on main + CORTEX_RUNNER_CHILD=1
# -----------------------------------------------------------------------------
echo ""
echo "Case (b): Scaffold B home repo on main, CORTEX_RUNNER_CHILD=1"

echo "case-b-content" > "$SCAFF_B/case-b.txt"
git -C "$SCAFF_B" add case-b.txt

cd "$SCAFF_B"
unset GIT_DIR
set +e
HOOK_OUTPUT_B="$(CORTEX_RUNNER_CHILD=1 bash "$SCAFF_B/.githooks/pre-commit" 2>&1)"
HOOK_EXIT_B=$?
set -e
cd "$WORK"

if [ "$HOOK_EXIT_B" -eq 0 ]; then
    report_fail "Case (b): hook exited 0 but Phase 0 should have rejected (expected non-zero)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_B"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_B" | grep -q "Phase 0"; then
    report_fail "Case (b): hook exit $HOOK_EXIT_B but stderr missing 'Phase 0'."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_B"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_B" | grep -q "refs/heads/main"; then
    report_fail "Case (b): hook exit $HOOK_EXIT_B but stderr missing 'refs/heads/main'."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_B"
    echo "-------------------"
elif ! echo "$HOOK_OUTPUT_B" | grep -q "CORTEX_RUNNER_CHILD"; then
    report_fail "Case (b): hook exit $HOOK_EXIT_B but stderr missing 'CORTEX_RUNNER_CHILD'."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_B"
    echo "-------------------"
else
    report_pass "Case (b): Scaffold B home repo on main rejected (exit $HOOK_EXIT_B)."
fi

# -----------------------------------------------------------------------------
# Case (c) — Scaffold A worktree on main, no CORTEX_RUNNER_CHILD (interactive)
# -----------------------------------------------------------------------------
echo ""
echo "Case (c): Scaffold A worktree on main, CORTEX_RUNNER_CHILD unset"

cd "$SCAFF_A_WT"
unset GIT_DIR
unset CORTEX_RUNNER_CHILD
set +e
HOOK_OUTPUT_C="$(bash "$SCAFF_A/.githooks/pre-commit" 2>&1)"
HOOK_EXIT_C=$?
set -e
cd "$WORK"

if [ "$HOOK_EXIT_C" -ne 0 ]; then
    report_fail "Case (c): hook exited $HOOK_EXIT_C but interactive case should pass (expected 0)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_C"
    echo "-------------------"
else
    report_pass "Case (c): Scaffold A worktree on main without runner-child gate passed (exit 0)."
fi

# -----------------------------------------------------------------------------
# Case (d) — Scaffold A worktree on integration + CORTEX_RUNNER_CHILD=1
# -----------------------------------------------------------------------------
echo ""
echo "Case (d): Scaffold A worktree on integration, CORTEX_RUNNER_CHILD=1"

echo "case-d-content" > "$SCAFF_A_WT_INT/case-d.txt"
git -C "$SCAFF_A_WT_INT" add case-d.txt

cd "$SCAFF_A_WT_INT"
unset GIT_DIR
set +e
HOOK_OUTPUT_D="$(CORTEX_RUNNER_CHILD=1 bash "$SCAFF_A/.githooks/pre-commit" 2>&1)"
HOOK_EXIT_D=$?
set -e
cd "$WORK"

if [ "$HOOK_EXIT_D" -ne 0 ]; then
    report_fail "Case (d): hook exited $HOOK_EXIT_D but integration-branch commit should pass (expected 0)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_D"
    echo "-------------------"
else
    report_pass "Case (d): Scaffold A worktree on integration with runner-child gate passed (exit 0)."
fi

# -----------------------------------------------------------------------------
# Hardening cases (f) and (e) — close B-class critical-review residue findings.
#
# Ordering invariant: case (f) MUST run BEFORE case (e). Rationale: case (e)
# mutates Scaffold A's home repo state (`git checkout --detach`); while git's
# worktree-HEAD independence means the worktree at $SCAFF_A_WT is unaffected,
# this ordering guarantees case (f) operates on a known-clean scaffold.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Case (f) — CORTEX_RUNNER_CHILD=0 strict-equality (residue B-3)
#
# Why this case exists: the hook gates on `[ "${CORTEX_RUNNER_CHILD:-}" = "1" ]`
# (strict equality, 0 ≠ 1). If a future implementer replaces
# `[ "${X:-}" = "1" ]` with `[ -n "${X:-}" ]`, this case catches the change.
# -----------------------------------------------------------------------------
echo ""
echo "Case (f): Scaffold A worktree on main, CORTEX_RUNNER_CHILD=0"

echo "case-f-content" > "$SCAFF_A_WT/case-f.txt"
git -C "$SCAFF_A_WT" add case-f.txt

cd "$SCAFF_A_WT"
unset GIT_DIR
set +e
HOOK_OUTPUT_F="$(CORTEX_RUNNER_CHILD=0 bash "$SCAFF_A/.githooks/pre-commit" 2>&1)"
HOOK_EXIT_F=$?
set -e
cd "$WORK"

if [ "$HOOK_EXIT_F" -ne 0 ]; then
    report_fail "Case (f): hook exited $HOOK_EXIT_F but CORTEX_RUNNER_CHILD=0 should not trigger Phase 0 (expected 0; strict equality, 0 ≠ 1)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_F"
    echo "-------------------"
else
    report_pass "Case (f): Scaffold A worktree on main with CORTEX_RUNNER_CHILD=0 passed (exit 0; strict-equality preserved)."
fi

# -----------------------------------------------------------------------------
# Case (e) — Detached HEAD fail-open (residue B-4)
#
# Detaches Scaffold A's home repo HEAD, then invokes the hook from $SCAFF_A
# (now in detached-HEAD state) with CORTEX_RUNNER_CHILD=1. Phase 0 should
# fail open (exit 0) because `symbolic-ref HEAD` returns non-zero on detached
# HEAD, and the hook treats that as "not on main".
# -----------------------------------------------------------------------------
echo ""
echo "Case (e): Scaffold A home repo on detached HEAD, CORTEX_RUNNER_CHILD=1"

git -C "$SCAFF_A" checkout --detach >/dev/null 2>&1

echo "case-e-content" > "$SCAFF_A/case-e.txt"
git -C "$SCAFF_A" add case-e.txt

cd "$SCAFF_A"
unset GIT_DIR
set +e
HOOK_OUTPUT_E="$(CORTEX_RUNNER_CHILD=1 bash "$SCAFF_A/.githooks/pre-commit" 2>&1)"
HOOK_EXIT_E=$?
set -e
cd "$WORK"

if [ "$HOOK_EXIT_E" -ne 0 ]; then
    report_fail "Case (e): hook exited $HOOK_EXIT_E but detached HEAD should fail open (expected 0)."
    echo "--- hook output ---"
    echo "$HOOK_OUTPUT_E"
    echo "-------------------"
else
    report_pass "Case (e): Scaffold A home repo on detached HEAD with runner-child gate passed (exit 0; fail-open)."
fi

# -----------------------------------------------------------------------------
# Structural assertion: gitdir-sharing for Scaffold A
# -----------------------------------------------------------------------------
echo ""
echo "Structural assertion: gitdir-sharing"

ACTUAL_COMMON_DIR_RAW="$(git -C "$SCAFF_A_WT" rev-parse --git-common-dir)"
# `--git-common-dir` may emit a trailing slash; strip it before resolution.
ACTUAL_COMMON_DIR_RAW="${ACTUAL_COMMON_DIR_RAW%/}"

if [ ! -d "$ACTUAL_COMMON_DIR_RAW" ]; then
    report_fail "gitdir-sharing: rev-parse --git-common-dir returned '$ACTUAL_COMMON_DIR_RAW' which is not a directory."
else
    ACTUAL_COMMON_DIR="$(resolve_path "$ACTUAL_COMMON_DIR_RAW")"
    EXPECTED_COMMON_DIR="$(resolve_path "$SCAFF_A/.git")"
    if [ "$ACTUAL_COMMON_DIR" = "$EXPECTED_COMMON_DIR" ]; then
        report_pass "gitdir-sharing: worktree's git-common-dir resolves to home repo's .git/."
    else
        report_fail "gitdir-sharing: worktree git-common-dir mismatch (actual='$ACTUAL_COMMON_DIR', expected='$EXPECTED_COMMON_DIR')."
    fi
fi

# -----------------------------------------------------------------------------
# Structural assertion: extensions.worktreeConfig is unset/empty
# -----------------------------------------------------------------------------
echo ""
echo "Structural assertion: extensions.worktreeConfig is unset/empty"

set +e
WT_CFG_VALUE="$(git -C "$SCAFF_A" config --get extensions.worktreeConfig 2>/dev/null)"
WT_CFG_EXIT=$?
set -e

if [ "$WT_CFG_EXIT" -ne 0 ] && [ -z "$WT_CFG_VALUE" ]; then
    report_pass "extensions.worktreeConfig: unset (git config exit=$WT_CFG_EXIT)."
elif [ -z "$WT_CFG_VALUE" ]; then
    report_pass "extensions.worktreeConfig: empty value."
else
    report_fail "extensions.worktreeConfig: unexpectedly set to '$WT_CFG_VALUE'."
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo ""
echo "Phase 0 hook tests: $PASS_COUNT/$TOTAL passed"

if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
