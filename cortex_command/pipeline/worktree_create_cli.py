"""Thin console-script wrapper around :func:`create_worktree`.

Wired into ``pyproject.toml`` ``[project.scripts]`` as
``cortex-worktree-create``. Consumed by ``skills/lifecycle/references/implement.md``
§1a step iii so the gate-probe (``command -v cortex-worktree-create``) and the
gated downstream call share the same surface — ensuring that what the gate
tests for and what the lifecycle actually invokes are the same binary.

Usage::

    cortex-worktree-create --feature <name> --base-branch <branch>

Prints exactly the absolute worktree path followed by a single newline to
stdout on success.  All informational output (git subprocess chatter, symlink
notices) and error traces go to stderr so the stdout contract is clean for
``$(...)`` capture.

Exit codes:
    0 — worktree created (or already existed and is valid).
    1 — creation failed; ``repr(exc)`` written to stderr.
    2 — usage error.
"""

from __future__ import annotations

import sys
from argparse import ArgumentParser

from cortex_command.pipeline.worktree import create_worktree, resolve_worktree_root


def main() -> int:
    """Create a git worktree for a feature and print its path to stdout.

    Returns:
        0 on success (new or idempotent re-entry), 1 on creation failure,
        2 on usage error.
    """
    parser = ArgumentParser(
        prog="cortex-worktree-create",
        description="Create a git worktree for a named feature.",
    )
    parser.add_argument(
        "--feature",
        required=True,
        metavar="NAME",
        help="Feature name (used for directory and branch naming).",
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        metavar="BRANCH",
        help="Branch to base the worktree on (default: main).",
    )
    args = parser.parse_args()

    if not args.feature:
        print(
            "cortex-worktree-create: --feature must be non-empty",
            file=sys.stderr,
        )
        return 2

    # Detect idempotent re-entry before calling create_worktree so we can
    # emit the "worktree already exists" signal to stderr on re-entry.
    try:
        candidate = resolve_worktree_root(args.feature, session_id=None)
        already_existed = candidate.exists()
    except Exception:  # noqa: BLE001
        already_existed = False

    try:
        info = create_worktree(feature=args.feature, base_branch=args.base_branch)
    except Exception as exc:  # noqa: BLE001
        print(repr(exc), file=sys.stderr)
        return 1

    print(info.path)
    if already_existed:
        print("worktree already exists", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
