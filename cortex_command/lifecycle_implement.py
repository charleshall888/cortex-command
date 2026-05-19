"""Runtime gate for the implement-phase picker.

This module exposes exactly two public symbols:

- :data:`REASONS` — the closed set of reason strings returned by
  :func:`should_fire_picker`.
- :func:`should_fire_picker` — predicate that decides whether the
  implement-phase picker should fire for a given repo + slug + branch_mode.

All other names are underscore-prefixed to keep the public API surface
closed (see spec R3/R4 of ``lifecycle-implement-auto-enter-worktree-drop``).

Negative scope: this module contains nothing for other §1a guards
(overnight detection, sandbox preflight, settings drift, etc.) — those
belong to separate lifecycles.
"""

from __future__ import annotations as _annotations

import os as _os
import pathlib as _pathlib
import subprocess as _subprocess
import typing as _typing


REASONS: _typing.Final[frozenset[str]] = frozenset(
    {
        "branch_mode_unset_or_invalid",
        "branch_mode_prompt",
        "dirty_tree",
        "live_interactive_worktree_session",
        "suppressed",
    }
)


_VALID_BRANCH_MODES: _typing.Final[frozenset[str]] = frozenset(
    {"worktree-interactive", "trunk", "feature-branch", "prompt"}
)

_SESSIONS_RELDIR = "cortex/lifecycle/sessions"


def _is_dirty_tree(repo_root: _pathlib.Path) -> bool:
    """Return True iff ``git status --porcelain`` returns non-empty stdout.

    If git exits non-zero (e.g., not a git repo), treat as clean — this
    matches the implement.md uncommitted-changes-guard fallback behavior.
    """
    try:
        result = _subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, _subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


def _has_live_interactive_session(
    repo_root: _pathlib.Path, slug: str
) -> bool:
    """Return True iff the slug's interactive PID file references a live PID.

    File format: simple text containing the PID, optionally with trailing
    whitespace (matches the ``cat``-then-``kill -0`` invocation in
    ``implement.md:78–82``). If the file is missing, empty, or contains an
    unparseable value, return False. If the PID is parseable, use
    ``os.kill(pid, 0)`` to probe liveness: any OSError means dead; success
    means live.
    """
    pid_path = (
        _pathlib.Path(repo_root)
        / _SESSIONS_RELDIR
        / f"{slug}.interactive.pid"
    )
    try:
        text = pid_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return False

    stripped = text.strip()
    if not stripped:
        return False

    try:
        pid = int(stripped)
    except ValueError:
        return False

    try:
        _os.kill(pid, 0)
    except OSError:
        return False
    return True


def should_fire_picker(
    repo_root: _pathlib.Path,
    slug: str,
    branch_mode: str | None,
) -> tuple[bool, str]:
    """Decide whether the implement-phase picker should fire.

    Returns ``(True, reason)`` to fire, or ``(False, "suppressed")`` to
    suppress. The returned ``reason`` is always a member of :data:`REASONS`.

    Fire conditions (evaluated in order; first match wins):

    (i)   ``branch_mode`` is ``None`` or not in the closed set
          ``{"worktree-interactive", "trunk", "feature-branch", "prompt"}``
          → ``"branch_mode_unset_or_invalid"``.
    (ii)  ``branch_mode == "prompt"`` → ``"branch_mode_prompt"``.
    (iii) ``git status --porcelain`` returns non-empty stdout
          → ``"dirty_tree"``.
    (iv)  ``{repo_root}/cortex/lifecycle/sessions/{slug}.interactive.pid``
          exists AND its PID is live → ``"live_interactive_worktree_session"``.

    Otherwise → ``(False, "suppressed")``.
    """
    if branch_mode is None or branch_mode not in _VALID_BRANCH_MODES:
        return True, "branch_mode_unset_or_invalid"

    if branch_mode == "prompt":
        return True, "branch_mode_prompt"

    if _is_dirty_tree(repo_root):
        return True, "dirty_tree"

    if _has_live_interactive_session(repo_root, slug):
        return True, "live_interactive_worktree_session"

    return False, "suppressed"
