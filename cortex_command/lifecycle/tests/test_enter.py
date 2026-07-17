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

import hashlib
import json
from pathlib import Path

import pytest

from cortex_command.lifecycle import enter as en
from cortex_command.lifecycle.create_index import create_index as real_create_index
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION


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
    # --phase plan is a resume, so the existence guard requires the dir to be
    # there; this test is about the sync seam, not the guard.
    (tmp_path / "cortex" / "lifecycle" / "feat").mkdir(parents=True)
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
# Fail-loud guards (stderr + exit 3, no side effect)
#
# The guards run inside ``enter`` BEFORE the composed primitives, so these need
# no ``_patch_primitives`` seam — reaching a primitive at all would be the bug.
# ---------------------------------------------------------------------------


def test_resume_of_nonexistent_lifecycle_exits_3_and_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """R1: --phase != none with no lifecycle dir is a resume of nothing — fail
    loud on stderr with exit 3 rather than silently materializing a shadow dir
    the morning report can never find (#379)."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    rc = en.main([
        "--feature", "no-such-thing",
        "--session-id", "X",
        "--backend", "cortex-backlog",
        "--phase", "research",
        "--backlog-file", "",
    ])
    assert rc == 3
    err = capsys.readouterr().err
    assert err.startswith("cortex-lifecycle-enter: ")
    assert "no such lifecycle" in err
    assert not (tmp_path / "cortex" / "lifecycle" / "no-such-thing").exists()


def test_guard_message_names_feature_and_both_causes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """R7: one trip, two remediations — the message must name the feature and
    distinguish "dir vanished mid-flight" (TOCTOU) from "caller mis-threaded the
    identity", pointing at the served-slug remedy for the latter."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    rc = en.main([
        "--feature", "vanished-feature",
        "--session-id", "X",
        "--backend", "cortex-backlog",
        "--phase", "plan",
        "--backlog-file", "",
    ])
    assert rc == 3
    err = capsys.readouterr().err
    assert "vanished-feature" in err
    assert "vanished mid-flight" in err
    assert "mis-threaded" in err
    assert "cortex-lifecycle-next" in err


@pytest.mark.parametrize(
    "feature",
    ["../../../tmp/evil", "..", "a/b", "a\\b", ""],
)
def test_unsafe_feature_slug_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, feature: str
) -> None:
    """R3: the house blacklist predicate (empty, /, \\, ..) rejects before any
    filesystem op, via the same stderr + exit-3 channel as R1."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    rc = en.main([
        "--feature", feature,
        "--session-id", "X",
        "--backend", "cortex-backlog",
        "--phase", "none",
        "--backlog-file", "",
    ])
    assert rc == 3
    err = capsys.readouterr().err
    assert err.startswith("cortex-lifecycle-enter: ")
    assert "unsafe feature slug" in err


def test_unsafe_slug_writes_nothing_outside_the_lifecycle_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3: the traversal target is never materialized — nothing is written
    outside cortex/lifecycle/, and no filesystem op runs at all."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path / "repo"))
    escape = tmp_path / "escape"
    escape.mkdir()
    rc = en.main([
        "--feature", "../../escape/evil",
        "--session-id", "X",
        "--backend", "cortex-backlog",
        "--phase", "none",
        "--backlog-file", "",
    ])
    assert rc == 3
    assert list(escape.iterdir()) == []
    assert not (tmp_path / "repo" / "cortex").exists()


def test_guards_raise_before_any_composed_primitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guards precede _backlog_status, the needs-decision short-circuit, and
    create_index — a rejected invocation must fail loud, never return an
    envelope a caller would read as a routine outcome."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("a composed primitive ran despite a guard rejection")

    monkeypatch.setattr(en, "create_index", _forbidden)
    monkeypatch.setattr(en, "sync", _forbidden)
    monkeypatch.setattr(en.init_ensure, "main", _forbidden)
    # An already_complete item would otherwise short-circuit to needs-decision.
    _write_backlog(tmp_path, "370-foo.md", "complete")
    with pytest.raises(en._GuardRejected):
        en.enter(
            feature="../evil",
            session_id="s",
            backend="cortex-backlog",
            phase="none",
            backlog_file="370-foo.md",
            root=tmp_path,
        )


def test_guard_exception_is_not_an_oserror(tmp_path: Path) -> None:
    """Regression pin: _GuardRejected must not subclass OSError — main's
    except-OSError arm is the exit-1 create-index contract and would swallow it,
    reporting a guard rejection as a missing --backlog-file."""
    assert not issubclass(en._GuardRejected, OSError)


def test_brand_new_lifecycle_with_phase_none_still_creates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2: --phase none is the caller-passed brand-new signal — the existence
    guard must not fire, or the verb could never create a lifecycle at all."""
    _patch_primitives(monkeypatch, ensure_code=0)
    r = en.enter(
        feature="brand-new-slug",
        session_id="s",
        backend="cortex-backlog",
        phase="none",
        backlog_file="",
        root=tmp_path,
    )
    assert r["state"] == "ready"


def test_grandfathered_numeric_lifecycle_passes_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R4: a feature whose dir exists passes every guard regardless of token
    shape — the numeric-keyed corpus (374/, 378/) keeps resuming. This is why
    the guard adopts the blacklist rather than a kebab-only whitelist."""
    _patch_primitives(monkeypatch, ensure_code=0)
    (tmp_path / "cortex" / "lifecycle" / "374").mkdir(parents=True)
    r = en.enter(
        feature="374",
        session_id="s",
        backend="cortex-backlog",
        phase="specify",
        backlog_file="",
        root=tmp_path,
    )
    assert r["state"] == "ready"


def test_entering_a_dir_owned_by_a_different_item_exits_3_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """R5: item A owns the dir; entering it with item B's --backlog-file is a
    silent cross-ticket merge (create_index would skip-if-exists and B would
    adopt A's index). Fail loud with exit 3, leaving A's index.md byte-identical.

    The fixture index.md is written by the REAL create_index — the same producer
    whose ``parent_backlog_uuid`` frontmatter the guard reads in production —
    rather than by a hand-rolled lookalike that could drift from it.
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _write_backlog(tmp_path, "380-item-a.md", "refined", uuid="aaaaaaaa-1111")
    _write_backlog(tmp_path, "381-item-b.md", "refined", uuid="bbbbbbbb-2222")
    real_create_index("shared-slug", "380-item-a.md", tmp_path)
    index = tmp_path / "cortex" / "lifecycle" / "shared-slug" / "index.md"
    before = hashlib.sha256(index.read_bytes()).hexdigest()

    def _forbidden(*args, **kwargs):
        raise AssertionError("a composed primitive ran despite a guard rejection")

    monkeypatch.setattr(en, "create_index", _forbidden)
    monkeypatch.setattr(en, "sync", _forbidden)
    monkeypatch.setattr(en.init_ensure, "main", _forbidden)
    rc = en.main([
        "--feature", "shared-slug",
        "--session-id", "X",
        "--backend", "cortex-backlog",
        "--phase", "none",
        "--backlog-file", "381-item-b.md",
    ])
    assert rc == 3
    err = capsys.readouterr().err
    assert err.startswith("cortex-lifecycle-enter: ")
    assert "already belongs to backlog item" in err
    assert hashlib.sha256(index.read_bytes()).hexdigest() == before


def test_reentering_a_dir_owned_by_the_same_item_passes_the_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R5's non-fire arm: a matching uuid is the ordinary resume — the guard must
    not block a lifecycle from re-entering its own dir."""
    _patch_primitives(monkeypatch, ensure_code=0)
    _write_backlog(tmp_path, "380-item-a.md", "refined", uuid="aaaaaaaa-1111")
    real_create_index("own-slug", "380-item-a.md", tmp_path)
    r = en.enter(
        feature="own-slug",
        session_id="s",
        backend="cortex-backlog",
        phase="plan",
        backlog_file="380-item-a.md",
        root=tmp_path,
    )
    assert r["state"] == "ready"


def test_null_parent_uuid_with_empty_backlog_file_passes_the_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R5 is inert by design for the ad-hoc (Shape B / no_match) entry: the index
    records ``parent_backlog_uuid: null`` and --backlog-file is "", so there is
    no item to collide on. A stated coverage limit, pinned so the literal string
    ``null`` is never mistaken for a uuid to compare."""
    _patch_primitives(monkeypatch, ensure_code=0)
    real_create_index("adhoc-slug", "", tmp_path)
    index = tmp_path / "cortex" / "lifecycle" / "adhoc-slug" / "index.md"
    assert "parent_backlog_uuid: null" in index.read_text(encoding="utf-8")
    assert en._parent_uuid(index) is None
    r = en.enter(
        feature="adhoc-slug",
        session_id="s",
        backend="none",
        phase="plan",
        backlog_file="",
        root=tmp_path,
    )
    assert r["state"] == "ready"


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


def _write_backlog(root: Path, name: str, status: str, uuid: str = "abc-123") -> None:
    path = root / "cortex" / "backlog" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"title: A ticket\n"
        f"status: {status}\n"
        f"uuid: {uuid}\n"
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


def test_cli_payload_carries_protocol_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The emitted payload carries the additive ``protocol`` field (two-sided
    handshake substrate)."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    _patch_primitives(monkeypatch, ensure_code=0)
    rc = en.main(_cli_args())
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["protocol"] == PROTOCOL_VERSION


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
