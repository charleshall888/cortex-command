"""cortex-lifecycle-init-ensure — skill-helper: run ``cortex init --ensure`` in-process.

Structural-separation form of the lifecycle wiring per CLAUDE.md's principle
"structural separation over prose-only enforcement for sequential gates".  The
skill calls this console-script rather than composing a Bash invocation, so the
worktree-attached refusal (R11) and the in-process delegate to
:func:`cortex_command.init.handler.main` are encoded in Python control flow, not
in prose the model must re-interpret.

Usage::

    cortex-lifecycle-init-ensure          # normal invocation
    python3 -m cortex_command.lifecycle.init_ensure

Exit codes mirror ``cortex init --ensure``:
    0 -- success / no-op (or CORTEX_AUTO_ENSURE=0 opt-out).
    2 -- user-correctable gate failure (worktree-attached, foreign-content, etc.).
    1 -- unexpected runtime failure.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def _check_not_attached_worktree() -> tuple[bool, str]:
    """Return (is_attached_worktree, diagnostic_message).

    Detects the ``git worktree add`` attached-worktree case where
    ``--git-common-dir`` resolves outside the worktree's ``.git/``.

    Returns:
        A tuple ``(True, diagnostic)`` when inside an attached worktree, or
        ``(False, "")`` when in the primary worktree or not inside any git repo.
    """
    inside_proc = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    if inside_proc.returncode != 0:
        # Not inside a git repository; not our problem to gate here.
        return False, ""

    common_dir_proc = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    git_dir_proc = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=False,
    )

    if common_dir_proc.returncode != 0 or git_dir_proc.returncode != 0:
        return False, ""

    common_dir = Path(common_dir_proc.stdout.strip()).resolve()
    git_dir = Path(git_dir_proc.stdout.strip()).resolve()

    # In the primary worktree: --git-common-dir == --git-dir (both resolve to
    # <repo>/.git).  In an attached worktree: --git-dir resolves to
    # <repo>/.git/worktrees/<name> while --git-common-dir still resolves to
    # <repo>/.git.
    if common_dir == git_dir:
        return False, ""

    # Attached worktree detected: compute roots for the diagnostic.
    worktree_root = git_dir.parent.parent.parent  # .git/worktrees/<name>/../../../
    primary_root = common_dir.parent  # .git/..

    diagnostic = (
        f"cortex-lifecycle-init-ensure: invoked inside a git worktree "
        f"({worktree_root}); run from the primary worktree ({primary_root}) "
        "to bootstrap or refresh cortex/"
    )
    return True, diagnostic


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for ``cortex-lifecycle-init-ensure``.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        Exit code: 0 on success/no-op, 2 on user-correctable gate failure,
        1 on unexpected runtime failure.
    """
    # Parse a minimal --help so the console-script isn't entirely opaque.
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-init-ensure",
        description=(
            "Skill-helper: invoke ``cortex init --ensure`` in-process before "
            "lifecycle phase dispatch.  Refuses inside an attached git worktree "
            "(R11).  Honors CORTEX_AUTO_ENSURE=0."
        ),
        add_help=True,
    )
    # parse_known_args so unrecognized flags surface a clean error rather than
    # crashing into the handler.
    _ns, unknown = parser.parse_known_args(argv)
    if unknown:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")

    # R11: refuse inside an attached worktree BEFORE any other check.
    is_attached, diagnostic = _check_not_attached_worktree()
    if is_attached:
        sys.stderr.write(diagnostic + "\n")
        return 2

    # Delegate to the in-process handler.  Import style is intentionally
    # ``from cortex_command.init import handler`` (module reference, not the
    # function directly) so Task 9's tests can monkeypatch handler.main without
    # reaching through an already-bound local name.
    from cortex_command.init import handler  # noqa: PLC0415

    ns = argparse.Namespace(
        ensure=True,
        update=False,
        force=False,
        unregister=False,
        path=None,
    )
    return handler.main(ns)


if __name__ == "__main__":
    sys.exit(main())
