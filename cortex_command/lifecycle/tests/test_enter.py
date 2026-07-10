"""Tests for cortex-lifecycle-enter — the Step-2 entry façade composing
create-index, start-sync, init-ensure, and the ``.session`` write into one
``{state, backlog_status, ...}`` envelope.

The composed primitives are tested at their own sites; here we monkeypatch them
on the verb's own module namespace (the ``test_prepare_worktree.py`` pattern) to
drive the composition seam and assert the discriminated ``state`` +
``backlog_status`` payload, the exit-1/exit-2 propagation, and the never-crash
CLI contract. Root resolution uses the env-var flavor
(``monkeypatch.setenv("CORTEX_REPO_ROOT", ...)``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.lifecycle import enter as en


def _patch_primitives(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ensure_code: int = 0,
    sync_calls: list | None = None,
) -> None:
    """Patch create-index / start-sync / init-ensure to succeed in-process.

    ``ensure_code`` drives the ``cortex init --ensure`` return; ``sync_calls``,
    when provided, records the keyword args ``sync`` was invoked with.
    """
    monkeypatch.setattr(
        en, "create_index", lambda feature, backlog_file, root: {"signal": "created", "path": "p"}
    )

    def _fake_sync(**kwargs):
        if sync_calls is not None:
            sync_calls.append(kwargs)
        return {"signal": "synced"}

    monkeypatch.setattr(en, "sync", _fake_sync)
    monkeypatch.setattr(en.init_ensure, "main", lambda argv: ensure_code)


# ---------------------------------------------------------------------------
# State discriminant
# ---------------------------------------------------------------------------


def test_ready_state_writes_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_primitives(monkeypatch, ensure_code=0)
    r = en.enter(
        feature="feat",
        session_id="sess-123",
        backend="cortex-backlog",
        phase="none",
        backlog_file="",
        root=tmp_path,
    )
    assert r["state"] == "ready"
    session = tmp_path / "cortex" / "lifecycle" / "feat" / ".session"
    assert session.read_text(encoding="utf-8") == "sess-123"


def test_blocked_state_does_not_write_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init-ensure exit 2 (user-correctable gate) → blocked, no .session write —
    the environment must be fixed and the idempotent verb re-run."""
    _patch_primitives(monkeypatch, ensure_code=2)
    r = en.enter(
        feature="feat",
        session_id="sess-123",
        backend="cortex-backlog",
        phase="none",
        backlog_file="",
        root=tmp_path,
    )
    assert r["state"] == "blocked"
    assert not (tmp_path / "cortex" / "lifecycle" / "feat" / ".session").exists()


def test_ensure_failed_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_primitives(monkeypatch, ensure_code=1)
    r = en.enter(
        feature="feat",
        session_id="sess-123",
        backend="cortex-backlog",
        phase="none",
        backlog_file="",
        root=tmp_path,
    )
    assert r["state"] == "ensure-failed"


def test_every_state_is_known(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = set()
    for code, expected in ((0, "ready"), (2, "blocked"), (1, "ensure-failed")):
        _patch_primitives(monkeypatch, ensure_code=code)
        state = en.enter(
            feature="feat",
            session_id="s",
            backend="cortex-backlog",
            phase="none",
            backlog_file="",
            root=tmp_path,
        )["state"]
        assert state == expected
        seen.add(state)

    # needs-decision: an already_complete item without --acknowledge-complete
    # short-circuits before the composition (the ensure-code patch is irrelevant).
    _write_backlog(tmp_path, "370-complete.md", "complete")
    seen.add(
        en.enter(
            feature="feat",
            session_id="s",
            backend="cortex-backlog",
            phase="none",
            backlog_file="370-complete.md",
            root=tmp_path,
        )["state"]
    )

    # The error state is only reachable through main()'s never-crash guard.
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

    def _boom(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(en, "enter", _boom)
    en.main(["--feature", "f", "--session-id", "s", "--backend", "none", "--phase", "p", "--backlog-file", ""])
    seen.add("error")

    assert seen == set(en.KNOWN_STATES)


# ---------------------------------------------------------------------------
# ADR-0019: discriminants are caller-passed, never re-derived
# ---------------------------------------------------------------------------


def test_sync_receives_caller_passed_discriminants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verb forwards --backend/--phase verbatim and passes the feature as
    the lifecycle-slug — it never self-resolves the backend or new-vs-resume."""
    calls: list = []
    _patch_primitives(monkeypatch, ensure_code=0, sync_calls=calls)
    en.enter(
        feature="feat",
        session_id="sess",
        backend="external-tracker",
        phase="plan",
        backlog_file="326-foo.md",
        root=tmp_path,
    )
    assert calls == [
        {
            "backend": "external-tracker",
            "backlog_file": "326-foo.md",
            "phase": "plan",
            "session_id": "sess",
            "lifecycle_slug": "feat",
        }
    ]


# ---------------------------------------------------------------------------
# backlog_status
# ---------------------------------------------------------------------------


def test_backlog_status_no_match_on_empty_backlog_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_primitives(monkeypatch, ensure_code=0)
    r = en.enter(
        feature="feat",
        session_id="s",
        backend="none",
        phase="none",
        backlog_file="",
        root=tmp_path,
    )
    assert r["backlog_status"] == "no_match"


def _write_backlog(root: Path, name: str, status: str) -> None:
    path = root / "cortex" / "backlog" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"title: A ticket\n"
        f"status: {status}\n"
        "uuid: abc-123\n"
        "---\n\nBody\n",
        encoding="utf-8",
    )


def test_already_complete_returns_needs_decision_with_no_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ``already_complete`` item without ``--acknowledge-complete`` returns
    ``needs-decision`` and runs NO composed step — the structural form of the
    pre-verb "completed item creates no artifacts" carve-out. Primitives are
    patched to fail loudly, proving the early return fires before any of them,
    and the tmp tree is asserted unchanged (no lifecycle dir at all)."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("composition ran despite the needs-decision short-circuit")

    monkeypatch.setattr(en, "create_index", _forbidden)
    monkeypatch.setattr(en, "sync", _forbidden)
    monkeypatch.setattr(en.init_ensure, "main", _forbidden)
    _write_backlog(tmp_path, "370-foo.md", "complete")
    r = en.enter(
        feature="feat",
        session_id="s",
        backend="cortex-backlog",
        phase="none",
        backlog_file="370-foo.md",
        root=tmp_path,
    )
    assert r["state"] == "needs-decision"
    assert r["backlog_status"] == "already_complete"
    # No side effects: the verb created no lifecycle directory (hence no index,
    # no .session) and ran no backend write-back.
    assert not (tmp_path / "cortex" / "lifecycle").exists()


def test_already_complete_with_acknowledge_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With ``--acknowledge-complete`` (the caller-passed Continue decision), an
    already_complete item drives the full composition normally and still reports
    ``already_complete`` — the verb never auto-closes it."""
    _patch_primitives(monkeypatch, ensure_code=0)
    _write_backlog(tmp_path, "370-foo.md", "complete")
    r = en.enter(
        feature="feat",
        session_id="s",
        backend="cortex-backlog",
        phase="none",
        backlog_file="370-foo.md",
        root=tmp_path,
        acknowledge_complete=True,
    )
    assert r["state"] == "ready"
    assert r["backlog_status"] == "already_complete"
    assert (tmp_path / "cortex" / "lifecycle" / "feat" / ".session").read_text(
        encoding="utf-8"
    ) == "s"


def test_backlog_status_open_for_non_complete_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_primitives(monkeypatch, ensure_code=0)
    _write_backlog(tmp_path, "371-bar.md", "refined")
    r = en.enter(
        feature="feat",
        session_id="s",
        backend="cortex-backlog",
        phase="none",
        backlog_file="371-bar.md",
        root=tmp_path,
    )
    assert r["backlog_status"] == "open"


def test_backlog_status_open_when_item_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent item is ``open`` (never already_complete): a read failure must
    not be mistaken for a completed lifecycle."""
    assert en._backlog_status("999-missing.md", tmp_path) == "open"


def test_backlog_status_first_match_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the first frontmatter ``status:`` scalar decides — a later body
    line reading ``status: complete`` must not flip an open item."""
    path = tmp_path / "cortex" / "backlog" / "372-baz.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nstatus: in_progress\n---\n\nWe will set status: complete later.\n",
        encoding="utf-8",
    )
    # First match (in_progress) wins over the later body mention of complete.
    assert en._backlog_status("372-baz.md", tmp_path) == "open"


# ---------------------------------------------------------------------------
# CLI contract: exit codes + never-crash JSON
# ---------------------------------------------------------------------------


def _cli_args(backlog_file: str = "") -> list[str]:
    return [
        "--feature", "feat",
        "--session-id", "sess",
        "--backend", "none",
        "--phase", "none",
        "--backlog-file", backlog_file,
    ]


def test_cli_emits_json_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _patch_primitives(monkeypatch, ensure_code=0)
    rc = en.main(_cli_args())
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "ready"
    assert obj["backlog_status"] == "no_match"


def test_cli_exits_0_with_error_state_on_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Regression pin: any exception escaping ``enter`` (other than the
    exit-1/exit-2 contract errors) must not crash the CLI — ``main`` emits a
    {"state": "error", ...} struct and exits 0."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

    def _boom(**kwargs):
        raise RuntimeError("root not found")

    monkeypatch.setattr(en, "enter", _boom)
    rc = en.main(_cli_args())
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "root not found" in obj["message"]


def test_cli_needs_decision_on_already_complete_emits_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The CLI surfaces the needs-decision short-circuit as a JSON envelope
    (exit 0) with no composed step run."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _write_backlog(tmp_path, "370-foo.md", "complete")

    def _forbidden(*args, **kwargs):
        raise AssertionError("composition ran despite the needs-decision short-circuit")

    monkeypatch.setattr(en, "create_index", _forbidden)
    monkeypatch.setattr(en, "sync", _forbidden)
    monkeypatch.setattr(en.init_ensure, "main", _forbidden)
    rc = en.main(_cli_args(backlog_file="370-foo.md"))
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "needs-decision"
    assert obj["backlog_status"] == "already_complete"


def test_cli_acknowledge_complete_flag_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The --acknowledge-complete flag drives the full composition for an
    already_complete item (exit 0, state ready)."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _patch_primitives(monkeypatch, ensure_code=0)
    _write_backlog(tmp_path, "370-foo.md", "complete")
    rc = en.main(_cli_args(backlog_file="370-foo.md") + ["--acknowledge-complete"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "ready"
    assert obj["backlog_status"] == "already_complete"


def test_cli_exits_1_on_create_index_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-empty --backlog-file that create-index cannot resolve is a contract
    violation propagated as exit 1 (no envelope)."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

    def _raise(feature, backlog_file, root):
        raise OSError("no such ticket")

    monkeypatch.setattr(en, "create_index", _raise)
    rc = en.main(_cli_args(backlog_file="404-gone.md"))
    assert rc == 1


def test_cli_exits_2_on_sync_ambiguous_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A start-sync exit-2 (ambiguous slug) propagates as exit 2."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(
        en, "create_index", lambda feature, backlog_file, root: {"signal": "created"}
    )

    def _raise(**kwargs):
        raise en._Exit2()

    monkeypatch.setattr(en, "sync", _raise)
    rc = en.main(_cli_args(backlog_file="326-foo.md"))
    assert rc == 2
