"""cortex-morning-review-gc-demo-worktrees — sweep stale demo-overnight-* worktrees.

Port of ``bin/cortex-morning-review-gc-demo-worktrees`` (81-line bash) to a
wheel-tier Python entry point. Preserves the bash script's stdout/stderr/
exit-code contract exactly.

Usage::

    cortex-morning-review-gc-demo-worktrees <active-session-id>

Sweeps stale ``demo-overnight-*`` worktrees rooted under ``$TMPDIR``,
excluding the worktree associated with the currently-active session. Worktrees
with uncommitted state are skipped (spec R9). All per-worktree
``git worktree remove`` calls run before a single trailing
``git worktree prune`` (spec R10).

Behaviour contract:

* Wrong argument count → stderr usage message, exit 2.
* ``$TMPDIR`` unset or not resolvable → silent exit 0.
* ``git worktree list --porcelain`` fails → stderr warning, exit 0.
* Per-worktree removal pass: only paths under resolved ``$TMPDIR``
  matching the ``demo-overnight-`` prefix are candidates. The active-session
  exclusion fires before the uncommitted-state check. A worktree with
  uncommitted state is skipped with a tagged stderr line. A successful
  ``git worktree remove`` emits a tagged stderr line; a failed removal emits a
  tagged stderr warning and continues.
* Single trailing ``git worktree prune`` emits a tagged ``pruning`` line.
  If prune fails, a tagged warning is emitted and the tool exits 0 (non-fatal).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def _log(message: str) -> None:
    """Emit a tagged log line to stderr."""
    print(f"[gc-demo-worktrees] {message}", file=sys.stderr)


def _resolve_tmpdir() -> Optional[Path]:
    """Return the resolved ``$TMPDIR`` path, or None if unset/unresolvable."""
    raw = os.environ.get("TMPDIR", "")
    if not raw:
        return None
    try:
        return Path(raw).resolve(strict=True)
    except (OSError, RuntimeError):
        return None


def _git_worktree_list_porcelain(cwd: str) -> Optional[str]:
    """Run ``git worktree list --porcelain`` in *cwd*.

    Returns the stdout text on success, or None if the command fails.
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _parse_worktree_paths(porcelain: str) -> List[str]:
    """Extract the path from each ``worktree <path>`` line in porcelain output."""
    paths: List[str] = []
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            paths.append(line[len("worktree "):])
    return paths


def _is_worktree_dirty(path: str) -> bool:
    """Return True if the worktree at *path* has uncommitted state.

    Uses ``git status --porcelain --ignored=traditional``. Any non-empty
    output (including untracked/ignored files) counts as dirty. If git
    fails, returns False (conservative: do not skip on error).
    """
    result = subprocess.run(
        ["git", "-C", path, "status", "--porcelain", "--ignored=traditional"],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _git_worktree_remove(path: str) -> bool:
    """Run ``git worktree remove <path>``.

    Returns True on success, False on failure.
    Note: stdout is discarded (``>/dev/null`` in bash); stderr is captured but
    not forwarded (the bash original redirected it to ``/dev/null`` as well:
    ``git worktree remove "$path" 2>&1 >/dev/null``).
    """
    result = subprocess.run(
        ["git", "worktree", "remove", path],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _git_worktree_prune(cwd: str) -> bool:
    """Run ``git worktree prune`` in *cwd*.

    Returns True on success, False on failure.
    """
    result = subprocess.run(
        ["git", "worktree", "prune"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def gc_demo_worktrees(active_session_id: str, cwd: Optional[str] = None) -> int:
    """Core logic for sweeping stale demo-overnight-* worktrees.

    :param active_session_id: The session ID whose worktree must be preserved.
    :param cwd: Working directory for git commands. Defaults to ``os.getcwd()``.
    :returns: Exit code (0 = success, 2 = usage error).
    """
    if cwd is None:
        cwd = os.getcwd()

    # Silent skip when $TMPDIR is unset or unresolvable.
    resolved_tmpdir = _resolve_tmpdir()
    if resolved_tmpdir is None:
        return 0

    tmpdir_prefix = str(resolved_tmpdir) + os.sep

    # Best-effort: if `git worktree list` fails, log and exit 0.
    porcelain = _git_worktree_list_porcelain(cwd)
    if porcelain is None:
        _log("git worktree list failed; skipping sweep")
        return 0

    candidates = _parse_worktree_paths(porcelain)

    # Per-worktree removal pass.
    for path in candidates:
        basename = os.path.basename(path)

        # Must be under resolved $TMPDIR.
        if not path.startswith(tmpdir_prefix):
            continue

        # Must match demo-overnight- prefix.
        if not basename.startswith("demo-overnight-"):
            continue

        # Active-session exclusion (silent skip).
        if basename.startswith(f"demo-{active_session_id}-"):
            continue

        # Spec R9: skip if uncommitted state present.
        if _is_worktree_dirty(path):
            _log(f"skipping {path}: uncommitted state")
            continue

        _log(f"removing {path}")
        if not _git_worktree_remove(path):
            _log(f"removal failed for {path}; continuing")

    # Spec R10: single trailing prune AFTER all per-worktree removals.
    _log("pruning")
    if not _git_worktree_prune(cwd):
        _log("prune failed; non-fatal")
        return 0

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for ``cortex-morning-review-gc-demo-worktrees``."""
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) != 1:
        print(
            "Usage: cortex-morning-review-gc-demo-worktrees <active-session-id>",
            file=sys.stderr,
        )
        return 2

    active_session_id = argv[0]
    return gc_demo_worktrees(active_session_id)


if __name__ == "__main__":
    sys.exit(main())
