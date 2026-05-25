"""Console-script shim exposing the already-in-worktree probe.

Wired into ``pyproject.toml`` ``[project.scripts]`` as
``cortex-worktree-precondition``. Called from the lifecycle skill's
``implement.md`` §1a step v (and from pytest) to gate the
``EnterWorktree`` tool call: the tool's live schema requires "Must not
already be in a worktree", so the skill probes first and skips the call
on positive detection.

Exit codes
----------
* ``0`` — CWD is NOT inside a linked worktree (main checkout, or
  outside any git repo).
* ``1`` — CWD IS inside a linked worktree.
* ``2`` — usage error.

Probe strategy
--------------
Compares ``git rev-parse --show-toplevel`` (the current working tree's
top) against ``git rev-parse --git-common-dir``'s parent (the main
repo's checkout root). When the two resolve to the same path, the CWD
is in the main checkout; when they differ, the CWD is in a linked
worktree. ``--git-common-dir`` always points at the main ``.git``
directory regardless of whether the caller is inside a worktree, which
is the property the probe relies on.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _git_output(args: list[str]) -> str | None:
    """Run a ``git`` command and return stripped stdout, or ``None`` on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def is_in_worktree() -> bool:
    """Return ``True`` iff the current CWD is inside a linked git worktree.

    Returns ``False`` when the CWD is the main checkout, or when the
    CWD is not inside any git repository at all (the probe's contract:
    "is it safe to call EnterWorktree" — the answer is yes outside any
    repo, no inside a linked worktree).
    """
    toplevel = _git_output(["rev-parse", "--show-toplevel"])
    common_dir = _git_output(["rev-parse", "--git-common-dir"])
    if toplevel is None or common_dir is None:
        # Not inside a git repo — safe to call EnterWorktree (it will
        # surface its own error if the path is invalid). Treat as
        # "not in worktree".
        return False

    toplevel_resolved = Path(toplevel).resolve()
    # ``--git-common-dir`` resolves to the main repo's ``.git``
    # directory; its parent is the main checkout root.
    common_root = Path(common_dir).resolve().parent
    return toplevel_resolved != common_root


def main() -> int:
    """Probe entrypoint. Exit 0 if not in worktree, 1 if in worktree."""
    if len(sys.argv) != 1:
        print(
            "usage: cortex-worktree-precondition",
            file=sys.stderr,
        )
        return 2
    return 1 if is_in_worktree() else 0


if __name__ == "__main__":
    raise SystemExit(main())
