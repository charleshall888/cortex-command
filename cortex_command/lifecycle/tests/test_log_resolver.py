"""Tests for the pinned machine-verb events.log resolver (374 Task 5, R4).

Covers the three flavours of :mod:`cortex_command.lifecycle.log_resolver`:

  * ``CORTEX_REPO_ROOT`` honoured verbatim (overnight env-pin);
  * ``events.log`` / flock-sibling path shape;
  * the load-bearing **worktree** case — the resolver picks the *main-root* log
    while ``common._resolve_user_project_root_from_cwd`` from the *same* CWD
    would pick the worktree-local copy. That divergence is hazard 1; this test
    is the structural tripwire that the two paths do NOT collapse into one.

The worktree gitfile / ``commondir`` fixture is hand-built (pure-Python parse,
no ``git`` subprocess), mirroring ``interactive_lock._main_root_from_gitfile``
and the #271 research finding that ``git rev-parse`` exits 128 against a
hand-built worktree fixture. The fixture is legitimate test scaffolding — it
exercises the resolver's worktree walk; it is not the artifact under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.common import _resolve_user_project_root_from_cwd
from cortex_command.lifecycle import log_resolver


_SLUG = "374-served-next-advance-loop"


def _make_worktree_fixture(root: Path) -> tuple[Path, Path]:
    """Build a main-repo + linked-worktree fixture under *root*.

    Layout::

        root/
          main/
            .git/                         (real-repo boundary: a directory)
              worktrees/wt1/commondir     -> "../.."  (=> main/.git)
            cortex/lifecycle/             (main-root cortex tree)
          wt/
            .git                          (worktree gitfile: "gitdir: .../wt1")
            cortex/lifecycle/             (co-located worktree-local cortex tree)

    Returns ``(main_root, worktree_root)``, both ``.resolve()``-canonicalized so
    comparisons are symlink-stable (macOS ``/var`` vs ``/private/var``).
    """
    root = root.resolve()
    main = root / "main"
    wt = root / "wt"

    # Main repo: a real .git *directory* (a repo boundary) plus the worktree
    # admin dir carrying the commondir back-pointer, and a main-root cortex/.
    git_dir = main / ".git"
    wt_admin = git_dir / "worktrees" / "wt1"
    wt_admin.mkdir(parents=True)
    # commondir resolves relative to the admin dir: ../.. => main/.git.
    (wt_admin / "commondir").write_text("../..\n", encoding="utf-8")
    (main / "cortex" / "lifecycle").mkdir(parents=True)

    # Worktree: a .git *file* pointing at the admin dir, plus a co-located
    # (git-tracked) cortex/ — the shape that makes the CWD-only resolver pick
    # the worktree copy.
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {wt_admin}\n", encoding="utf-8")
    (wt / "cortex" / "lifecycle").mkdir(parents=True)

    return main, wt


def test_resolve_main_repo_root_honours_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``CORTEX_REPO_ROOT`` is honoured verbatim (resolved), no walk."""
    root = (tmp_path / "explicit").resolve()
    root.mkdir()
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    assert log_resolver.resolve_main_repo_root() == root


def test_resolve_events_log_path_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """events.log is anchored under ``<root>/cortex/lifecycle/<slug>/``."""
    root = (tmp_path / "proj").resolve()
    root.mkdir()
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    events = log_resolver.resolve_events_log(_SLUG)
    assert events == root / "cortex" / "lifecycle" / _SLUG / "events.log"


def test_resolve_flock_path_is_sibling_lockfile(tmp_path: Path) -> None:
    """The flock domain is the ``{events.log}.lock`` sibling of the resolved path."""
    events = tmp_path / "cortex" / "lifecycle" / _SLUG / "events.log"
    flock = log_resolver.resolve_flock_path(events)
    assert flock == events.parent / "events.log.lock"
    assert flock.parent == events.parent


def test_worktree_resolver_picks_main_root_log_while_cwd_resolver_splits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hazard 1 tripwire: from a worktree CWD the pinned resolver picks the
    MAIN-root log, while ``_resolve_user_project_root_from_cwd`` from the same
    CWD picks the worktree-local copy. The two MUST diverge — collapsing them
    would silently re-introduce the two-logs / two-flock-domains split.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    main, wt = _make_worktree_fixture(tmp_path)
    monkeypatch.chdir(wt)

    # Pinned machine-verb resolver: main-root anchored via the worktree gitfile.
    resolved_root = log_resolver.resolve_main_repo_root()
    resolved_events = log_resolver.resolve_events_log(_SLUG)

    # Legacy CWD-only resolver (what log_event's typed subcommands use).
    cwd_root = _resolve_user_project_root_from_cwd()
    cwd_events = (
        cwd_root / "cortex" / "lifecycle" / _SLUG / "events.log"
    )

    # The resolver reaches the MAIN root; the CWD resolver stays in the worktree.
    assert resolved_root == main
    assert cwd_root == wt
    assert resolved_root != cwd_root

    # And therefore the two would target DIFFERENT physical logs (the split the
    # single pinned resolver exists to prevent).
    assert resolved_events == main / "cortex" / "lifecycle" / _SLUG / "events.log"
    assert cwd_events == wt / "cortex" / "lifecycle" / _SLUG / "events.log"
    assert resolved_events != cwd_events

    # The flock domains are correspondingly distinct siblings — same-log iff
    # same-flock-domain, so distinct logs mean distinct flock domains.
    assert (
        log_resolver.resolve_flock_path(resolved_events)
        != log_resolver.resolve_flock_path(cwd_events)
    )
