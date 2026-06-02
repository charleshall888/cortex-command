"""Tests for the top-level ``overnight-state.json`` symlink (Task 17, R19).

``bootstrap_session`` writes the per-session state file at
``cortex/lifecycle/sessions/<session_id>/overnight-state.json`` and now also
points the top-level ``cortex/lifecycle/overnight-state.json`` symlink at it.
Without that pointer, a no-arg ``load_state()`` — which defaults to
``_default_state_path()`` — raises ``FileNotFoundError`` in the
bootstrap→fire window (state.py:331).

The symlink is a single-active-session pointer, overwritten on each bootstrap
(consistent with the host-global active-session model). These tests drive the
real ``bootstrap_session`` with ``initialize_overnight_state`` stubbed so no
real git worktree is created; the symlink-writing tail of ``bootstrap_session``
is the code under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.overnight import plan as plan_module
from cortex_command.overnight.backlog import SelectionResult
from cortex_command.overnight.state import OvernightState, load_state, session_dir


def _stub_initialize(monkeypatch: pytest.MonkeyPatch, session_id: str) -> OvernightState:
    """Patch ``initialize_overnight_state`` to return a minimal state.

    Avoids the real git-worktree side effect so the test isolates the
    state-write + symlink tail of ``bootstrap_session``.
    """
    state = OvernightState(session_id=session_id, phase="executing")

    def _fake_initialize(selection, *, plan_content, project_root=None):  # noqa: ANN001
        return state

    monkeypatch.setattr(plan_module, "initialize_overnight_state", _fake_initialize)
    return state


def _empty_selection() -> SelectionResult:
    return SelectionResult(batches=[], ineligible=[], summary="stub")


def test_bootstrap_session_creates_top_level_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The top-level ``overnight-state.json`` symlink points at the session file."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    session_id = "overnight-2026-06-01-2200"
    _stub_initialize(monkeypatch, session_id)

    state, state_dir = plan_module.bootstrap_session(
        _empty_selection(), plan_content="# plan\n", project_root=tmp_path
    )

    per_session_state = state_dir / "overnight-state.json"
    assert per_session_state.is_file()

    top_level = tmp_path / "cortex" / "lifecycle" / "overnight-state.json"
    assert top_level.is_symlink()
    assert top_level.resolve() == per_session_state.resolve()
    # The pointer targets the canonical per-session state path.
    assert state_dir == session_dir(session_id)


def test_no_arg_load_state_returns_session_state_after_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No-arg ``load_state()`` resolves via the symlink, not ``FileNotFoundError``."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    session_id = "overnight-2026-06-01-2300"
    _stub_initialize(monkeypatch, session_id)

    plan_module.bootstrap_session(
        _empty_selection(), plan_content="# plan\n", project_root=tmp_path
    )

    loaded = load_state()  # no args → _default_state_path() → top-level symlink
    assert loaded.session_id == session_id
    assert loaded.phase == "executing"


def test_symlink_overwritten_on_repeat_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second bootstrap repoints the single-active-session symlink."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

    first_id = "overnight-2026-06-01-2200"
    _stub_initialize(monkeypatch, first_id)
    plan_module.bootstrap_session(
        _empty_selection(), plan_content="# plan\n", project_root=tmp_path
    )

    second_id = "overnight-2026-06-02-2200"
    _stub_initialize(monkeypatch, second_id)
    _, second_dir = plan_module.bootstrap_session(
        _empty_selection(), plan_content="# plan\n", project_root=tmp_path
    )

    top_level = tmp_path / "cortex" / "lifecycle" / "overnight-state.json"
    assert top_level.is_symlink()
    assert top_level.resolve() == (second_dir / "overnight-state.json").resolve()
    assert load_state().session_id == second_id
