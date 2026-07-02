"""Runtime gate for the implement-phase picker.

This module exposes exactly three public symbols:

- :data:`REASONS` — the closed set of reason strings returned by
  :func:`should_fire_picker`.
- :func:`should_fire_picker` — predicate that decides whether the
  implement-phase picker should fire for a given repo + slug + branch_mode.
- :func:`read_dispatch_choice` — resolve the line-position-last
  ``plan_approved`` event's ``dispatch_choice`` from a feature's events.log
  (the carry-forward channel the merged Plan §4 surface writes).

All other names are underscore-prefixed to keep the public API surface
closed (see spec R3/R4 of ``lifecycle-implement-auto-enter-worktree-drop``).

Negative scope: this module contains nothing for other §1a guards
(overnight detection, sandbox preflight, settings drift, etc.) — those
belong to separate lifecycles.
"""

from __future__ import annotations as _annotations

import json as _json
import pathlib as _pathlib
import subprocess as _subprocess
import typing as _typing

from cortex_command.interactive_lock import scan_live_locks as _scan_live_locks


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
    """Return True iff ``slug`` currently holds a live interactive lock.

    Delegates to ``cortex_command.interactive_lock.scan_live_locks`` — the
    single source of truth for the real per-feature lock — which returns the
    set of slugs whose lock owner process is live. See ``implement.md`` §1a-i.
    """
    return slug in _scan_live_locks(_pathlib.Path(repo_root))


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
    (iv)  ``slug`` holds a live interactive lock per
          ``cortex_command.interactive_lock.scan_live_locks`` (§1a-i)
          → ``"live_interactive_worktree_session"``.

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


def read_dispatch_choice(events_path: _pathlib.Path) -> str | None:
    """Return the line-position-last ``plan_approved`` event's ``dispatch_choice``.

    Scans ``events_path`` in **line order** (never timestamp-sorted — matching
    the reducer convention in ``cortex_command.common``, which warns that
    torn/missing ``ts`` fields would otherwise mis-sort). The last
    ``plan_approved`` row wins; its ``dispatch_choice`` value (or ``None`` when
    that row carries no such field) is returned. Returns ``None`` when the file
    is absent/unreadable or contains no ``plan_approved`` event.

    The three "no recorded branch mode" shapes the Implement consumer must treat
    as picker-fallback all map to a non-branch-mode result here:

    - no ``plan_approved`` event (migration-sentinel / legacy log) → ``None``;
    - latest ``plan_approved`` with no ``dispatch_choice`` field → ``None``;
    - latest ``plan_approved`` with ``dispatch_choice: "wait"`` → ``"wait"``.

    Torn or non-object JSON lines are skipped, never collapsing the scan.
    """
    try:
        text = events_path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return None

    result: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = _json.loads(line)
        except (ValueError, _json.JSONDecodeError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get("event") == "plan_approved":
            # Line-position-last wins. Reassign on every match — including the
            # field-absent case (resets to None) — so a later field-less
            # plan_approved correctly supersedes an earlier recorded choice.
            choice = event.get("dispatch_choice")
            result = choice if isinstance(choice, str) else None
    return result
