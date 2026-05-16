"""Thin console-script wrapper around :func:`resolve_worktree_root`.

Wired into ``pyproject.toml`` ``[project.scripts]`` as
``cortex-worktree-resolve``. Consumed by ``claude/hooks/cortex-worktree-create.sh``
so the bash dispatch path and the Python dispatch path share a single
resolver chokepoint (no duplicated path computation).

Usage::

    cortex-worktree-resolve <feature-name>

Prints the resolved worktree path to stdout and exits 0 on success.
Prints diagnostic to stderr and exits non-zero on usage errors. The
``session_id`` argument is always passed as ``None`` — the hook only
ever needs the same-repo default; cross-repo (overnight) dispatch
does not consume this wrapper.
"""

from __future__ import annotations

import sys

from cortex_command.pipeline.worktree import resolve_worktree_root


def main() -> int:
    """Print the resolved worktree path for the given feature name.

    Returns:
        0 on success, 2 on usage error.
    """
    if len(sys.argv) != 2:
        print(
            "usage: cortex-worktree-resolve <feature-name>",
            file=sys.stderr,
        )
        return 2

    name = sys.argv[1]
    if not name:
        print(
            "cortex-worktree-resolve: feature name must be non-empty",
            file=sys.stderr,
        )
        return 2

    path = resolve_worktree_root(name, session_id=None)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
