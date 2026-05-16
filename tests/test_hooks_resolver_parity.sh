#!/bin/bash
# tests/test_hooks_resolver_parity.sh — R8 byte-identity acceptance.
#
# Asserts that the bash hook (claude/hooks/cortex-worktree-create.sh) and
# the Python resolver (cortex_command.pipeline.worktree.resolve_worktree_root)
# emit byte-identical paths for the same feature name under a controlled
# $TMPDIR. The hook shells out to cortex-worktree-resolve, which is a thin
# wrapper around resolve_worktree_root — so structural agreement is the
# expected outcome, and any drift here means the single-chokepoint
# guarantee has regressed.
#
# Exit 0 on parity, 1 on mismatch or fixture failure.
#
# Note: this test invokes the hook's path-emission codepath, which runs
# `git worktree add`. We set up a throwaway git repo under the controlled
# $TMPDIR so the `git worktree add` succeeds and we can capture stdout.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/claude/hooks/cortex-worktree-create.sh"
FEATURE="verify-r8"

# Controlled $TMPDIR so both Python and bash dispatch surfaces resolve under
# the same root.
PARITY_TMPDIR=$(mktemp -d)
export TMPDIR="$PARITY_TMPDIR"

cleanup() {
  # Best-effort cleanup of the worktree the hook created.
  if [ -d "$PARITY_TMPDIR/cortex-worktrees/$FEATURE" ]; then
    (cd "$PARITY_TMPDIR/repo" 2>/dev/null \
      && git worktree remove --force "$PARITY_TMPDIR/cortex-worktrees/$FEATURE" >/dev/null 2>&1) || true
    rm -rf "$PARITY_TMPDIR/cortex-worktrees/$FEATURE"
  fi
  rm -rf "$PARITY_TMPDIR"
}
trap cleanup EXIT

# Minimal git repo so `git worktree add` inside the hook succeeds.
mkdir -p "$PARITY_TMPDIR/repo"
(cd "$PARITY_TMPDIR/repo" \
  && git init >/dev/null 2>&1 \
  && git symbolic-ref HEAD refs/heads/main >/dev/null 2>&1 \
  && git -c commit.gpgsign=false -c user.email="test@test.com" -c user.name="Test" \
       commit --allow-empty -m "init" >/dev/null 2>&1)

# (a) Hook-emitted path: invoke the hook with synthetic JSON on stdin.
hook_output=$(printf '{"cwd": "%s", "name": "%s"}' "$PARITY_TMPDIR/repo" "$FEATURE" \
  | SKIP_NOTIFICATIONS=1 bash "$HOOK" 2>/dev/null)
hook_exit=$?

if [[ $hook_exit -ne 0 ]]; then
  echo "FAIL: hook exited non-zero ($hook_exit)" >&2
  exit 1
fi

# (b) Python-resolver path: shell out to the same module the hook does.
python_output=$(python3 -c "from cortex_command.pipeline.worktree import resolve_worktree_root; print(resolve_worktree_root('$FEATURE', None))")
python_exit=$?

if [[ $python_exit -ne 0 ]]; then
  echo "FAIL: python3 resolver exited non-zero ($python_exit)" >&2
  exit 1
fi

# (c) Byte-identity assertion.
if diff <(printf '%s\n' "$hook_output") <(printf '%s\n' "$python_output") >/dev/null; then
  echo "PASS hooks_resolver_parity: hook='$hook_output' == python='$python_output'"
  exit 0
else
  echo "FAIL hooks_resolver_parity:" >&2
  echo "  hook   = $hook_output" >&2
  echo "  python = $python_output" >&2
  exit 1
fi
