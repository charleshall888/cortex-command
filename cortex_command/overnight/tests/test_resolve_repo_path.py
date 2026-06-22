"""Un-patched precedence + env-branch unit tests for the repo-root resolver.

Spec R1/R3 (cortex/lifecycle/overnight-launchd-scheduled-runner-operates-from):
the resolver ``_resolve_repo_path(state_project_root=...)`` returns the home
repo by marker-validated precedence — **valid ``state_project_root`` → valid
``CORTEX_REPO_ROOT`` → ``git rev-parse --show-toplevel`` → ``Path.cwd()``** —
where a candidate is *valid* only when, after ``.resolve()``, it is an existing,
non-``/`` directory bearing a repo marker (``.git`` or ``cortex/``). The same
guard is applied uniformly to the state and env candidates so a
wrong-but-existent non-repo dir or a poisoned ``CORTEX_REPO_ROOT=/`` is rejected
and resolution falls through.

These tests call the **real** resolver via ``cli_handler._resolve_repo_path(...)``
— they MUST NOT monkeypatch it. The R5 anti-masking discipline is the point of
the task: the bug shipped precisely because every existing test patched the
resolver away. To simulate a non-git cwd we swap the module-bound
``subprocess.check_output`` so ``git rev-parse`` "fails" (``CalledProcessError``),
forcing the documented ``Path.cwd()`` tail. ``monkeypatch.chdir`` / ``setenv`` /
``delenv`` drive the cwd and env inputs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cortex_command.overnight import cli_handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_marker_repo(base: Path, *, marker: str = ".git") -> Path:
    """Create a marker-bearing repo dir under ``base`` and return it.

    ``marker`` is ``.git`` (a dir, mimicking a normal checkout) or ``cortex``
    (the alternative house-idiom marker). Both satisfy
    :func:`cli_handler._is_valid_repo_root`.
    """
    repo = base / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / marker).mkdir(parents=True, exist_ok=True)
    return repo


def _make_bare_dir(base: Path) -> Path:
    """Create a marker-less (no ``.git``/``cortex``) directory and return it."""
    bare = base / "bare"
    bare.mkdir(parents=True, exist_ok=True)
    return bare


def _fail_git_rev_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the module-bound ``subprocess.check_output`` to fail like git.

    Raises ``CalledProcessError`` so the resolver's ``git rev-parse`` tier
    falls through to ``Path.cwd()`` — the same fall-through launchd hits from
    cwd=``/`` with a bare environment.
    """

    def _raise(*_args, **_kwargs):
        raise subprocess.CalledProcessError(128, ["git", "rev-parse"])

    monkeypatch.setattr(cli_handler.subprocess, "check_output", _raise)


# ---------------------------------------------------------------------------
# (a) marker-bearing state_project_root wins over a set env
# ---------------------------------------------------------------------------

def test_valid_state_wins_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A marker-bearing ``state_project_root`` is preferred over a valid env."""
    state_repo = _make_marker_repo(tmp_path / "state")
    env_repo = _make_marker_repo(tmp_path / "env")
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(env_repo))
    _fail_git_rev_parse(monkeypatch)

    result = cli_handler._resolve_repo_path(state_project_root=state_repo)

    assert result == state_repo.resolve()
    assert result != env_repo.resolve()


def test_valid_state_with_cortex_marker_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ``cortex/`` marker (not just ``.git``) validates a state candidate."""
    state_repo = _make_marker_repo(tmp_path / "state", marker="cortex")
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    _fail_git_rev_parse(monkeypatch)

    result = cli_handler._resolve_repo_path(state_project_root=state_repo)

    assert result == state_repo.resolve()


# ---------------------------------------------------------------------------
# (b) marker-less / "/" / missing state_project_root falls through
# ---------------------------------------------------------------------------

def test_marker_less_state_falls_through_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare (marker-less) ``state_project_root`` is rejected → git → cwd."""
    bare = _make_bare_dir(tmp_path)
    cwd_repo = _make_marker_repo(tmp_path / "cwd")
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.chdir(cwd_repo)
    _fail_git_rev_parse(monkeypatch)

    result = cli_handler._resolve_repo_path(state_project_root=bare)

    assert result == cwd_repo.resolve()


def test_root_state_falls_through_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``state_project_root`` of ``/`` is rejected → falls through to cwd."""
    cwd_repo = _make_marker_repo(tmp_path / "cwd")
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.chdir(cwd_repo)
    _fail_git_rev_parse(monkeypatch)

    result = cli_handler._resolve_repo_path(state_project_root=Path("/"))

    assert result == cwd_repo.resolve()


def test_missing_state_falls_through_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-existent ``state_project_root`` is rejected → falls through."""
    missing = tmp_path / "does-not-exist"
    cwd_repo = _make_marker_repo(tmp_path / "cwd")
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.chdir(cwd_repo)
    _fail_git_rev_parse(monkeypatch)

    result = cli_handler._resolve_repo_path(state_project_root=missing)

    assert result == cwd_repo.resolve()


def test_none_state_with_no_env_falls_through_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``state_project_root=None`` + no env → git → cwd (the default call)."""
    cwd_repo = _make_marker_repo(tmp_path / "cwd")
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.chdir(cwd_repo)
    _fail_git_rev_parse(monkeypatch)

    result = cli_handler._resolve_repo_path()

    assert result == cwd_repo.resolve()


# ---------------------------------------------------------------------------
# (c) state=None + marker-bearing CORTEX_REPO_ROOT returns env, even cwd=/ (R3)
# ---------------------------------------------------------------------------

def test_env_returned_when_state_none_and_cwd_is_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 guardian-scan branch: no state arg + marker-bearing env wins from cwd=/.

    This is the launchd guardian-scan shape — ``_resolve_repo_path()`` with no
    state, ``CORTEX_REPO_ROOT`` set by the plist, and cwd=``/`` — which must
    return the env value, not ``/``.
    """
    env_repo = _make_marker_repo(tmp_path / "env")
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(env_repo))
    monkeypatch.chdir("/")
    _fail_git_rev_parse(monkeypatch)

    result = cli_handler._resolve_repo_path()

    assert result == env_repo.resolve()


def test_env_returned_when_state_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalid state + a marker-bearing env returns the env value."""
    bare = _make_bare_dir(tmp_path)
    env_repo = _make_marker_repo(tmp_path / "env")
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(env_repo))
    monkeypatch.chdir("/")
    _fail_git_rev_parse(monkeypatch)

    result = cli_handler._resolve_repo_path(state_project_root=bare)

    assert result == env_repo.resolve()


# ---------------------------------------------------------------------------
# (d) CORTEX_REPO_ROOT=/ or marker-less is rejected → falls through
# ---------------------------------------------------------------------------

def test_env_root_rejected_falls_through_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A poisoned ``CORTEX_REPO_ROOT=/`` is rejected → falls through to cwd."""
    cwd_repo = _make_marker_repo(tmp_path / "cwd")
    monkeypatch.setenv("CORTEX_REPO_ROOT", "/")
    monkeypatch.chdir(cwd_repo)
    _fail_git_rev_parse(monkeypatch)

    result = cli_handler._resolve_repo_path()

    assert result == cwd_repo.resolve()


def test_env_marker_less_rejected_falls_through_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A marker-less ``CORTEX_REPO_ROOT`` is rejected → falls through to cwd."""
    bare_env = _make_bare_dir(tmp_path)
    cwd_repo = _make_marker_repo(tmp_path / "cwd")
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(bare_env))
    monkeypatch.chdir(cwd_repo)
    _fail_git_rev_parse(monkeypatch)

    result = cli_handler._resolve_repo_path()

    assert result == cwd_repo.resolve()


# ---------------------------------------------------------------------------
# git tier: when git succeeds it is preferred over cwd (precedence order)
# ---------------------------------------------------------------------------

def test_git_tier_used_when_state_and_env_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With state+env invalid and git succeeding, the git toplevel is returned."""
    git_repo = _make_marker_repo(tmp_path / "git")
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

    def _fake_check_output(*_args, **_kwargs):
        return f"{git_repo}\n"

    monkeypatch.setattr(cli_handler.subprocess, "check_output", _fake_check_output)

    result = cli_handler._resolve_repo_path()

    assert result == Path(str(git_repo))
