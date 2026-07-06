"""Tests for cortex-lifecycle-prepare-worktree — the Implement §1a
overnight-guard + base-branch-resolution + lock-acquire + worktree-create
façade.

The composed primitives (read_active_session / read_runner_pid / acquire_lock
/ create_worktree / release_lock_if_owner / _detect_base_branch) are tested at
their own sites (or, for ``_detect_base_branch``, exercised directly below
against a real git repo); here we monkeypatch them to drive the
composition/routing seam and assert the discriminated ``state`` + payload,
following the ``test_branch_decision.py`` precedent.

Most tests pass ``base_branch="main"`` explicitly so the composition seam
under test does not depend on git subprocess behavior against the fake
``_REPO_ROOT`` path; the auto-detection behavior itself gets its own tests
below.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from cortex_command.lifecycle import prepare_worktree as pw

_REPO_ROOT = Path("/repo")


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
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
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
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
    assert r["state"] == "ok"


def test_overnight_active_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": str(_REPO_ROOT), "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(
        pw, "read_runner_pid", lambda session_dir: {"pid": os.getpid()}
    )
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
    assert r["state"] == "overnight-active"
    assert "wait for it to complete" in r["message"]


def test_overnight_active_never_calls_acquire_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression pin for #355: a rejected overnight guard must never let a
    fresh interactive lock get acquired — the guard-then-lock ORDER inside
    the composed verb is what prevents a live overnight run and a live
    interactive session from coexisting on the same repo."""
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": str(_REPO_ROOT), "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(
        pw, "read_runner_pid", lambda session_dir: {"pid": os.getpid()}
    )
    calls: list[str] = []
    monkeypatch.setattr(
        pw, "acquire_lock", lambda feature: calls.append(feature) or True
    )
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
    assert r["state"] == "overnight-active"
    assert calls == []


def test_overnight_active_matches_resolved_but_unresolved_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard must compare canonicalized physical paths on both sides —
    a session repo_path recorded via a resolving path (e.g. through a
    symlinked tempdir) must still match a project_root passed in an
    unresolved but equivalent form, so the guard cannot fail open on a
    path-form mismatch alone."""
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": str(_REPO_ROOT) + "/.", "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(
        pw, "read_runner_pid", lambda session_dir: {"pid": os.getpid()}
    )
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
    assert r["state"] == "overnight-active"


def test_stale_runner_pid_absent_warns_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": str(_REPO_ROOT), "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(pw, "read_runner_pid", lambda session_dir: None)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x/interactive-feat")
    )
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
    assert r["state"] == "ok"
    assert "warning" in r


def test_stale_dead_pid_warns_and_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": str(_REPO_ROOT), "session_dir": "/tmp/sess"},
    )
    # A pid that (almost certainly) does not exist.
    monkeypatch.setattr(pw, "read_runner_pid", lambda session_dir: {"pid": 999999})
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x/interactive-feat")
    )
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
    assert r["state"] == "ok"
    assert "warning" in r


def test_stale_non_numeric_pid_warns_and_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-numeric pid field is malformed, not merely a string-shaped
    number — it must still be treated as stale (warn-and-continue)."""
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": str(_REPO_ROOT), "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(pw, "read_runner_pid", lambda session_dir: {"pid": "not-a-pid"})
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x/interactive-feat")
    )
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
    assert r["state"] == "ok"
    assert "warning" in r


def test_live_pid_as_numeric_string_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dual-home liveness parity (#4): the sidecar's `kill -0 "$pid"` treats
    any numeric-looking string as live, so a runner.pid whose ``pid`` field
    is a numeric STRING (not an int) must be coerced and treated as live
    here too — not misclassified as stale."""
    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": str(_REPO_ROOT), "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(
        pw, "read_runner_pid", lambda session_dir: {"pid": str(os.getpid())}
    )
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
    assert r["state"] == "overnight-active"


def test_lock_held_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: False)
    monkeypatch.setattr(
        pw, "read_lock", lambda feature: {"session_id": "s1", "acquired_at": "2026-01-01T00:00:00Z"}
    )
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
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
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="main")
    assert r["state"] == "create-failed"
    assert "disk full" in r["message"]
    assert released == ["feat"]


def test_base_branch_flag_overrides_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit --base-branch must short-circuit auto-detection entirely."""
    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)

    detect_calls = []
    monkeypatch.setattr(
        pw, "_detect_base_branch", lambda root: detect_calls.append(root) or "should-not-be-used"
    )

    seen_base_branch = {}

    def _fake_create(feature, base_branch):
        seen_base_branch["value"] = base_branch
        return _FakeWorktreeInfo("/x")

    monkeypatch.setattr(pw, "create_worktree", _fake_create)
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT, base_branch="release")
    assert r["state"] == "ok"
    assert seen_base_branch["value"] == "release"
    assert detect_calls == []


def test_base_branch_falls_back_to_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """No --base-branch given: the detected branch must reach create_worktree."""
    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(pw, "_detect_base_branch", lambda root: "master")

    seen_base_branch = {}

    def _fake_create(feature, base_branch):
        seen_base_branch["value"] = base_branch
        return _FakeWorktreeInfo("/x")

    monkeypatch.setattr(pw, "create_worktree", _fake_create)
    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT)
    assert r["state"] == "ok"
    assert seen_base_branch["value"] == "master"


def test_base_branch_detection_failure_is_create_failed_without_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No trunk branch resolvable (neither flag nor detection): the verb
    must fail before ever touching the interactive lock."""
    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "_detect_base_branch", lambda root: None)

    calls: list[str] = []
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: calls.append(feature) or True)

    r = pw.prepare_worktree("feat", project_root=_REPO_ROOT)
    assert r["state"] == "create-failed"
    assert "trunk branch" in r["message"]
    assert calls == []


def test_detect_base_branch_prefers_origin_head(tmp_path: Path) -> None:
    """Exercise ``_detect_base_branch`` against a real git repo: an
    origin/HEAD pointing at a non-main/master branch name must win over the
    main/master fallback."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "trunk"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    # Fake a remote-tracking origin/HEAD pointing at 'trunk' without a real remote.
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/trunk", "HEAD"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk"],
        cwd=repo,
        check=True,
    )
    assert pw._detect_base_branch(repo) == "trunk"


def test_detect_base_branch_falls_back_to_local_main_or_master(tmp_path: Path) -> None:
    """No origin/HEAD at all: detection must fall back to whichever of
    main/master has a local ref, rather than hardcoding 'main'."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    assert pw._detect_base_branch(repo) == "master"


def test_detect_base_branch_returns_none_when_unresolvable(tmp_path: Path) -> None:
    """A non-repository directory resolves neither origin/HEAD nor a local
    main/master ref."""
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    assert pw._detect_base_branch(empty) is None


def test_every_state_is_known(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = set()

    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x")
    )
    seen.add(
        pw.prepare_worktree("f", project_root=_REPO_ROOT, base_branch="main")["state"]
    )

    monkeypatch.setattr(pw, "acquire_lock", lambda feature: False)
    monkeypatch.setattr(pw, "read_lock", lambda feature: None)
    seen.add(
        pw.prepare_worktree("f", project_root=_REPO_ROOT, base_branch="main")["state"]
    )

    monkeypatch.setattr(
        pw,
        "read_active_session",
        lambda: {"repo_path": str(_REPO_ROOT), "session_dir": "/tmp/sess"},
    )
    monkeypatch.setattr(pw, "read_runner_pid", lambda session_dir: {"pid": os.getpid()})
    seen.add(
        pw.prepare_worktree("f", project_root=_REPO_ROOT, base_branch="main")["state"]
    )

    assert seen <= set(pw.KNOWN_STATES)
    assert seen == {"ok", "lock-held", "overnight-active"}


def test_cli_emits_json(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _patch_clear_guard(monkeypatch)
    monkeypatch.setattr(pw, "acquire_lock", lambda feature: True)
    monkeypatch.setattr(
        pw, "create_worktree", lambda feature, base_branch: _FakeWorktreeInfo("/x")
    )
    monkeypatch.setattr(pw, "_resolve_main_repo_root", lambda: _REPO_ROOT)
    rc = pw.main(["--feature", "feat", "--base-branch", "main"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "ok"


def test_cli_exits_0_with_error_state_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Regression pin: any exception escaping ``prepare_worktree`` (e.g. a
    project-root resolution failure) must not crash the CLI — ``main`` must
    still emit a {"state": "error", ...} JSON struct and exit 0."""

    def _boom(feature, project_root=None, base_branch=None):
        raise RuntimeError("root not found")

    monkeypatch.setattr(pw, "prepare_worktree", _boom)
    rc = pw.main(["--feature", "feat"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "root not found" in obj["message"]
