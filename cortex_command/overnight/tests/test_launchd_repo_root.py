"""Launchd fire-path regression: resolved ``repo_path`` is the session root, not ``/``.

Reproduces the launchd condition (CWD=``/`` + a bare environment with no
``CORTEX_REPO_ROOT``) under which a naive resolver — plain
``git rev-parse``/``cwd`` — would resolve the filesystem root. Task 3 made
``handle_start`` re-resolve ``repo_path`` from the ``--state`` file's persisted
``project_root`` via the ``_repo_path_from_state()`` closure. This test asserts
the corrected root reaches BOTH processes launchd traverses (R2, R4):

  - Case A — the ``--launchd`` inline child (the process that calls
    ``runner.run`` via ``_run_runner_inline``);
  - Case B — the ``--scheduled`` parent (the launchd entry, which resolves its
    own ``repo_path`` independently and threads it into ``_spawn_runner_async``).

Neither case monkeypatches the repo-path resolver: both exercise the *real*
resolver and only spy the *downstream* sink (``runner.run`` / the async-spawn
helper). A fire-path test that never references the resolver symbol at all
cannot accidentally short-circuit the very resolution it is meant to verify.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from cortex_command.overnight import cli_handler
from cortex_command.overnight import runner as runner_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_state(session_dir: Path, session_id: str, *, project_root: Path) -> Path:
    """Write an ``overnight-state.json`` whose ``project_root`` is ``project_root``.

    The persisted ``project_root`` is what the ``_repo_path_from_state()`` closure
    feeds into the real resolver as the highest-precedence candidate, so it must
    point at a marker-bearing directory for resolution to land there.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "plan_ref": "cortex/lifecycle/test/plan.md",
        "current_round": 1,
        "phase": "executing",
        "features": {},
        "round_history": [],
        "started_at": "2026-05-04T10:00:00",
        "updated_at": "2026-05-04T10:00:00",
        "project_root": str(project_root),
        "schema_version": 1,
    }
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return state_path


def _make_args(state_path: Path, **overrides) -> argparse.Namespace:
    """Namespace mimicking ``cortex overnight start`` for the fire path."""
    base = dict(
        state=str(state_path),
        time_limit=None,
        max_rounds=None,
        tier="simple",
        dry_run=False,
        format="json",
        force=True,
        launchd=False,
        scheduled=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _simulate_launchd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproduce the launchd fire condition: CWD=``/`` and a bare environment.

    With no ``CORTEX_REPO_ROOT`` and CWD at the filesystem root, the resolver's
    unguarded ``git rev-parse``/``cwd`` tail would yield ``/`` — only the
    persisted ``project_root`` (highest precedence) can rescue resolution.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.chdir("/")


# ---------------------------------------------------------------------------
# Case A — ``--launchd`` inline child (calls ``runner.run``)
# ---------------------------------------------------------------------------


def test_launchd_inline_child_resolves_session_root_not_filesystem_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ``--launchd`` child threads the session root into ``runner.run``, not ``/``."""
    # Marker-bearing project root (a ``.git`` entry makes it a valid repo root).
    (tmp_path / ".git").mkdir()
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_id = "overnight-2026-05-04-2200"
    state_path = _write_state(
        sessions_root / session_id, session_id, project_root=tmp_path
    )

    _simulate_launchd(monkeypatch)

    captured: dict = {}

    def spy_run(**kwargs):  # type: ignore[no-untyped-def]
        captured["repo_path"] = kwargs.get("repo_path")
        return 0

    # Spy the downstream sink only — NOT the resolver.
    monkeypatch.setattr(runner_module, "run", spy_run)

    args = _make_args(state_path, launchd=True)
    rc = cli_handler.handle_start(args)

    assert rc == 0
    assert "repo_path" in captured, "runner.run was never reached"
    resolved = captured["repo_path"]
    assert resolved == Path(tmp_path).resolve()
    assert resolved != Path("/")


# ---------------------------------------------------------------------------
# Case B — ``--scheduled`` parent (the launchd entry; feeds the fork)
# ---------------------------------------------------------------------------


def test_scheduled_parent_resolves_session_root_not_filesystem_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ``--scheduled`` parent threads the session root into ``_spawn_runner_async``."""
    (tmp_path / ".git").mkdir()
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_id = "overnight-2026-05-04-2300"
    state_path = _write_state(
        sessions_root / session_id, session_id, project_root=tmp_path
    )

    _simulate_launchd(monkeypatch)

    captured: dict = {}

    def spy_spawn(**kwargs):  # type: ignore[no-untyped-def]
        captured["repo_path"] = kwargs.get("repo_path")
        # Benign success so ``handle_start`` completes its return path.
        return {
            "started": True,
            "session_id": session_id,
            "pid": 4242,
        }

    # Spy the downstream sink only — NOT the resolver.
    monkeypatch.setattr(cli_handler, "_spawn_runner_async", spy_spawn)

    args = _make_args(state_path, scheduled=True)
    rc = cli_handler.handle_start(args)

    assert rc == 0
    assert "repo_path" in captured, "_spawn_runner_async was never reached"
    resolved = captured["repo_path"]
    assert resolved == Path(tmp_path).resolve()
    assert resolved != Path("/")
