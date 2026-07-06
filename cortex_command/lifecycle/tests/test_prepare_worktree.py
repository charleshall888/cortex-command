"""Tests for cortex-lifecycle-prepare-worktree — the Implement §1a
overnight-guard + lock-acquire + worktree-create façade.

The composed primitives (read_active_session / read_runner_pid / acquire_lock
/ create_worktree / release_lock_if_owner) are tested at their own sites; here
we monkeypatch them to drive the composition/routing seam and assert the
discriminated ``state`` + payload, following the
``test_branch_decision.py`` precedent.
"""

from __future__ import annotations

import json
import os

import pytest

from cortex_command.lifecycle import prepare_worktree as pw


class _FakeWorktreeInfo:
    def __init__(self, path: str) -> None:
        self.path = path


def _patch_clear_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """No active overnight session at all — guard state 'clear'."""
    monkeypatch.setattr(pw, "read_active_session", lambda: None)


def test_no_active_session_proceeds_to_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x/interactive-feat")
    )
    r = pw.prepare_worktree("feat", project_root=__import__("pathlib").Path("/repo"))
    assert r["state"] == "ok"
    assert r["worktree_path"] == "/x/interactive-feat"
    assert "warning" not in r


def test_different_repo_path_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": "/other-repo", "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x/interactive-feat")
    )
    r = pw.prepare_worktree("feat", project_root=__import__("pathlib").Path("/repo"))
    assert r["state"] == "ok"


def test_overnight_active_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": "/repo", "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(
        pw, "read_runner_pid", lambda session_dir: {"pid": os.getpid()}
    )
    r = pw.prepare_worktree("feat", project_root=__import__("pathlib").Path("/repo"))
    assert r["state"] == "overnight-active"
    assert "wait for it to complete" in r["message"]


def test_stale_runner_pid_absent_warns_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": "/repo", "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(pw, "read_runner_pid", lambda session_dir: None)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x/interactive-feat")
    )
    r = pw.prepare_worktree("feat", project_root=__import__("pathlib").Path("/repo"))
    assert r["state"] == "ok"
    assert "warning" in r


def test_stale_dead_pid_warns_and_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": "/repo", "session_dir": "/tmp/sess"},
    )
    # A pid that (almost certainly) does not exist.
    monkeypatch.setattr(pw, "read_runner_pid", lambda session_dir: {"pid": 999999})
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x/interactive-feat")
    )
    r = pw.prepare_worktree("feat", project_root=__import__("pathlib").Path("/repo"))
    assert r["state"] == "ok"
    assert "warning" in r


def test_lock_held_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: False)
    monkeypatch.setattr(
        pw, "read_lock", lambda feature: {"session_id": "s1", "acquired_at": "2026-01-01T00:00:00Z"}
    )
    r = pw.prepare_worktree("feat", project_root=__import__("pathlib").Path("/repo"))
    assert r["state"] == "lock-held"
    assert "s1" in r["message"]
    assert "already active on this feature" in r["message"]


def test_create_failed_releases_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)

    released = []
    monkeypatch.setattr(pw, "release_lock_if_owner", lambda feature: released.append(feature))

    def _raise(feature, base_branch):
        raise RuntimeError("disk full")

    monkeypatch.setattr(pw, "create_worktree", _raise)
    r = pw.prepare_worktree("feat", project_root=__import__("pathlib").Path("/repo"))
    assert r["state"] == "create-failed"
    assert "disk full" in r["message"]
    assert released == ["feat"]


def test_every_state_is_known(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = set()

    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x")
    )
    seen.add(pw.prepare_worktree("f", project_root=__import__("pathlib").Path("/repo"))["state"])

    monkeypatch.setattr(pw, "acquire_lock", lambda feature: False)
    monkeypatch.setattr(pw, "read_lock", lambda feature: None)
    seen.add(pw.prepare_worktree("f", project_root=__import__("pathlib").Path("/repo"))["state"])

    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": "/repo", "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(pw, "read_runner_pid", lambda session_dir: {"pid": os.getpid()})
    seen.add(pw.prepare_worktree("f", project_root=__import__("pathlib").Path("/repo"))["state"])

    assert seen <= set(pw.KNOWN_STATES)
    assert seen == {"ok", "lock-held", "overnight-active"}


def test_cli_emits_json(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x")
    )
    monkeypatch.setattr(pw, "_resolve_user_project_root", lambda: __import__("pathlib").Path("/repo"))
    rc = pw.main(["--feature", "feat"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "ok"
