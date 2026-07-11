"""Tests for cortex-lifecycle-spec-approve — the spec-approval decision verb
whose function body encodes the exact per-arm ordered emission sequence AND the
backend-gated backlog write-back (status:refined + spec + areas).

Root resolution uses the cwd flavor, so the tests ``monkeypatch.chdir(tmp_path)``
(and ``delenv CORTEX_REPO_ROOT``) and scaffold a ``cortex/`` tree there; the real
``log_event`` then resolves and writes the same tree the verb reads for its
presence checks. The item resolver and ``update_item`` are patched on the verb's
own module namespace (the ``test_finalize.py`` pattern) to drive the write-back
seam without touching the real backlog.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.backlog.resolve_item import ResolutionResult
from cortex_command.lifecycle import spec_approve as sa
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION


def _scaffold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, feature: str = "feat") -> Path:
    """chdir into a scaffolded cortex/ project root and return the feature dir."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    feature_dir = tmp_path / "cortex" / "lifecycle" / feature
    feature_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "cortex" / "backlog").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    return feature_dir


def _events_rows(feature_dir: Path) -> list[dict]:
    log = feature_dir / "events.log"
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def _event_names(feature_dir: Path) -> list[str]:
    return [r["event"] for r in _events_rows(feature_dir)]


def _patch_writeback(monkeypatch: pytest.MonkeyPatch, item_path: Path) -> list:
    """Patch resolve→ok and capture update_item calls; return the calls list."""
    calls: list = []
    monkeypatch.setattr(
        sa, "resolve", lambda ref, backlog_dir: ResolutionResult(status="ok", item=item_path)
    )
    monkeypatch.setattr(
        sa,
        "update_item",
        lambda path, fields, backlog_dir, session_id=None: calls.append(
            (path, fields, backlog_dir, session_id)
        ),
    )
    return calls


def _boom(*a, **k):
    raise AssertionError("update_item must not be called on this arm")


# ---------------------------------------------------------------------------
# approved arm — ordered emissions × both flag states
# ---------------------------------------------------------------------------


def test_approved_emit_transition_orders_spec_approved_then_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lifecycle-wrapped refine (--emit-transition): spec_approved{decision}
    THEN phase_transition specify->plan, in that order."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = sa.spec_approve(
        feature="feat",
        decision="approved",
        backend="none",
        backlog_file="",
        spec_path="cortex/lifecycle/feat/spec.md",
        emit_transition=True,
    )

    assert r["state"] == "approved"
    assert r["decision"] == "approved"
    assert r["emit_transition"] is True
    assert r["emitted"] == ["spec_approved", "phase_transition"]

    rows = _events_rows(feature_dir)
    assert [x["event"] for x in rows] == ["spec_approved", "phase_transition"]
    assert rows[0]["decision"] == "approved"
    assert rows[1]["from"] == "specify"
    assert rows[1]["to"] == "plan"


def test_approved_no_emit_transition_suppresses_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Standalone refine (--no-emit-transition): spec_approved only, NO
    specify->plan row (preserving today's standalone behavior)."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = sa.spec_approve(
        feature="feat",
        decision="approved",
        backend="none",
        backlog_file="",
        spec_path="p",
        emit_transition=False,
    )

    assert r["state"] == "approved"
    assert r["emit_transition"] is False
    assert r["emitted"] == ["spec_approved"]
    assert _event_names(feature_dir) == ["spec_approved"]
    assert "phase_transition" not in _event_names(feature_dir)


# ---------------------------------------------------------------------------
# approved arm — backend matrix × both flag states
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("emit_transition", [True, False])
def test_approved_cortex_backlog_writes_refined_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, emit_transition: bool
) -> None:
    """cortex-backlog resolves the item and update_items it with status:refined +
    spec + areas and a null session_id; the backlog signal is ``updated``. Runs
    under both flag states."""
    _scaffold(tmp_path, monkeypatch)
    item_path = tmp_path / "cortex" / "backlog" / "326-foo.md"
    calls = _patch_writeback(monkeypatch, item_path)

    r = sa.spec_approve(
        feature="feat",
        decision="approved",
        backend="cortex-backlog",
        backlog_file="326-foo.md",
        spec_path="cortex/lifecycle/feat/spec.md",
        emit_transition=emit_transition,
        areas=["cli", "lifecycle"],
    )

    assert r["backlog"] == "updated"
    assert calls == [
        (
            item_path,
            {
                "status": "refined",
                "spec": "cortex/lifecycle/feat/spec.md",
                "areas": ["cli", "lifecycle"],
            },
            tmp_path / "cortex" / "backlog",
            None,
        )
    ]


@pytest.mark.parametrize("emit_transition", [True, False])
def test_approved_backend_none_skips_writeback_but_emits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, emit_transition: bool
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    monkeypatch.setattr(sa, "update_item", _boom)
    r = sa.spec_approve(
        feature="feat",
        decision="approved",
        backend="none",
        backlog_file="326-foo.md",
        spec_path="p",
        emit_transition=emit_transition,
    )
    assert r["state"] == "approved"
    assert r["backlog"] == "skipped"
    assert "spec_approved" in _event_names(feature_dir)


@pytest.mark.parametrize("emit_transition", [True, False])
def test_approved_external_backend_skips_writeback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, emit_transition: bool
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    monkeypatch.setattr(sa, "update_item", _boom)
    r = sa.spec_approve(
        feature="feat",
        decision="approved",
        backend="jira",
        backlog_file="326-foo.md",
        spec_path="p",
        emit_transition=emit_transition,
    )
    assert r["backlog"] == "external"
    assert "spec_approved" in _event_names(feature_dir)


@pytest.mark.parametrize("emit_transition", [True, False])
def test_approved_not_found_reference_skips_writeback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, emit_transition: bool
) -> None:
    _scaffold(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sa, "resolve", lambda ref, backlog_dir: ResolutionResult(status="not_found")
    )
    monkeypatch.setattr(sa, "update_item", _boom)
    r = sa.spec_approve(
        feature="feat",
        decision="approved",
        backend="cortex-backlog",
        backlog_file="404-gone.md",
        spec_path="p",
        emit_transition=emit_transition,
    )
    assert r["backlog"] == "no-item"


@pytest.mark.parametrize("emit_transition", [True, False])
def test_approved_empty_backlog_file_is_no_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, emit_transition: bool
) -> None:
    """An empty --backlog-file is ``no-item``: skip the write-back silently."""
    _scaffold(tmp_path, monkeypatch)
    monkeypatch.setattr(sa, "update_item", _boom)
    r = sa.spec_approve(
        feature="feat",
        decision="approved",
        backend="cortex-backlog",
        backlog_file="",
        spec_path="p",
        emit_transition=emit_transition,
    )
    assert r["backlog"] == "no-item"


# ---------------------------------------------------------------------------
# cancelled + revise arms × both flag states
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("emit_transition", [True, False])
def test_cancelled_emits_only_lifecycle_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, emit_transition: bool
) -> None:
    """cancelled emits lifecycle_cancelled only — no transition, no write-back,
    regardless of the flag state."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    monkeypatch.setattr(sa, "update_item", _boom)
    r = sa.spec_approve(
        feature="feat",
        decision="cancelled",
        backend="cortex-backlog",
        backlog_file="326-foo.md",
        spec_path="p",
        emit_transition=emit_transition,
    )
    assert r["state"] == "cancelled"
    assert r["emitted"] == ["lifecycle_cancelled"]
    assert _event_names(feature_dir) == ["lifecycle_cancelled"]


@pytest.mark.parametrize("emit_transition", [True, False])
def test_revise_emits_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, emit_transition: bool
) -> None:
    """revise short-circuits before any mutation — no events.log write, no
    write-back — regardless of the flag state."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    monkeypatch.setattr(sa, "update_item", _boom)
    r = sa.spec_approve(
        feature="feat",
        decision="revise",
        backend="cortex-backlog",
        backlog_file="326-foo.md",
        spec_path="p",
        emit_transition=emit_transition,
    )
    assert r["state"] == "revise"
    assert r["emitted"] == []
    assert not (feature_dir / "events.log").exists()


# ---------------------------------------------------------------------------
# EXIT-2 carve-out: ambiguous slug propagates (never-crash envelope exempt)
# ---------------------------------------------------------------------------


def test_ambiguous_slug_raises_exit2_with_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """An ambiguous backlog reference writes the candidate list to stderr and
    raises _Exit2 — no write-back call. The verb still emits the approval events
    BEFORE the write-back, matching the emit-then-write-back order."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    candidates = [
        tmp_path / "cortex" / "backlog" / "370-a.md",
        tmp_path / "cortex" / "backlog" / "370-b.md",
    ]
    for c in candidates:
        c.write_text("---\ntitle: A ticket\nstatus: refined\n---\n", encoding="utf-8")
    monkeypatch.setattr(
        sa,
        "resolve",
        lambda ref, backlog_dir: ResolutionResult(status="ambiguous", candidates=candidates),
    )
    monkeypatch.setattr(sa, "update_item", _boom)

    with pytest.raises(sa._Exit2):
        sa.spec_approve(
            feature="feat",
            decision="approved",
            backend="cortex-backlog",
            backlog_file="370.md",
            spec_path="p",
            emit_transition=True,
        )

    err = capsys.readouterr().err
    assert "ambiguous: 2 matches" in err
    # Emissions ran before the write-back aborted (emit-then-write-back order).
    assert _event_names(feature_dir) == ["spec_approved", "phase_transition"]


def test_main_returns_2_on_ambiguous_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scaffold(tmp_path, monkeypatch)

    def _raise(**kwargs):
        raise sa._Exit2()

    monkeypatch.setattr(sa, "spec_approve", _raise)
    rc = sa.main(
        [
            "--feature", "feat",
            "--decision", "approved",
            "--backend", "cortex-backlog",
            "--backlog-file", "370.md",
            "--spec-path", "p",
        ]
    )
    assert rc == 2


# ---------------------------------------------------------------------------
# --areas preserve-on-omit vs --clear-areas
# ---------------------------------------------------------------------------


def test_areas_omitted_preserves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omitting --areas drops the areas key from the update_item fields — the
    item's existing areas are left untouched (preserve-on-omit)."""
    _scaffold(tmp_path, monkeypatch)
    item_path = tmp_path / "cortex" / "backlog" / "326-foo.md"
    calls = _patch_writeback(monkeypatch, item_path)

    sa.spec_approve(
        feature="feat",
        decision="approved",
        backend="cortex-backlog",
        backlog_file="326-foo.md",
        spec_path="p",
        emit_transition=False,
        areas=None,
    )
    _, fields, _, _ = calls[0]
    assert "areas" not in fields
    assert fields == {"status": "refined", "spec": "p"}


def test_clear_areas_writes_empty_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--clear-areas is the explicit sentinel: it writes an empty areas list."""
    _scaffold(tmp_path, monkeypatch)
    item_path = tmp_path / "cortex" / "backlog" / "326-foo.md"
    calls = _patch_writeback(monkeypatch, item_path)

    sa.spec_approve(
        feature="feat",
        decision="approved",
        backend="cortex-backlog",
        backlog_file="326-foo.md",
        spec_path="p",
        emit_transition=False,
        areas=None,
        clear_areas=True,
    )
    _, fields, _, _ = calls[0]
    assert fields["areas"] == []


# ---------------------------------------------------------------------------
# Idempotency + mid-sequence-crash repair
# ---------------------------------------------------------------------------


def test_double_invocation_is_idempotent_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-running the whole verb appends no duplicate — the second run reports
    nothing emitted (the write-back is idempotent by update_item's nature)."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    monkeypatch.setattr(sa, "update_item", lambda *a, **k: None)
    first = sa.spec_approve(
        feature="feat", decision="approved", backend="none",
        backlog_file="", spec_path="p", emit_transition=True,
    )
    second = sa.spec_approve(
        feature="feat", decision="approved", backend="none",
        backlog_file="", spec_path="p", emit_transition=True,
    )
    assert first["emitted"] == ["spec_approved", "phase_transition"]
    assert second["emitted"] == []
    assert _event_names(feature_dir) == ["spec_approved", "phase_transition"]


def test_resume_after_partial_emits_only_the_missing_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash after spec_approved but before phase_transition is repaired: the
    re-run emits ONLY the missing transition, never a second spec_approved, and
    the log ends with exactly one of each row."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    monkeypatch.setattr(sa, "update_item", lambda *a, **k: None)
    # Pre-seed the partial state: spec_approved present, transition absent.
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "spec_approved", "feature": "feat", "decision": "approved"})
        + "\n",
        encoding="utf-8",
    )
    r = sa.spec_approve(
        feature="feat", decision="approved", backend="none",
        backlog_file="", spec_path="p", emit_transition=True,
    )
    assert r["emitted"] == ["phase_transition"]
    names = _event_names(feature_dir)
    assert names == ["spec_approved", "phase_transition"]
    assert names.count("spec_approved") == 1
    assert names.count("phase_transition") == 1


def test_phase_transition_guard_ignores_earlier_transitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The feature's log already carries an earlier lifecycle transition under the
    same event name; the specify->plan emission must still fire (the guard matches
    on from/to, not the bare event name)."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "phase_transition", "feature": "feat", "from": "research", "to": "specify"})
        + "\n",
        encoding="utf-8",
    )
    r = sa.spec_approve(
        feature="feat", decision="approved", backend="none",
        backlog_file="", spec_path="p", emit_transition=True,
    )
    assert "phase_transition" in r["emitted"]
    transitions = [x for x in _events_rows(feature_dir) if x["event"] == "phase_transition"]
    assert {"from": "research", "to": "specify"}.items() <= transitions[0].items()
    assert {"from": "specify", "to": "plan"}.items() <= transitions[1].items()


# ---------------------------------------------------------------------------
# Substring false-positive negative control for the presence check
# ---------------------------------------------------------------------------


def test_presence_check_is_not_substring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row that merely mentions ``spec_approved`` in another field does not
    suppress emission — only a parsed ``event`` match does."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "note", "text": "spec_approved pending"}) + "\n",
        encoding="utf-8",
    )
    r = sa.spec_approve(
        feature="feat", decision="approved", backend="none",
        backlog_file="", spec_path="p", emit_transition=False,
    )
    assert "spec_approved" in r["emitted"]
    assert _event_names(feature_dir) == ["note", "spec_approved"]


# ---------------------------------------------------------------------------
# Slug guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "..", ""])
def test_unsafe_slug_errors_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    _scaffold(tmp_path, monkeypatch)
    r = sa.spec_approve(
        feature=bad, decision="approved", backend="none",
        backlog_file="", spec_path="p", emit_transition=True,
    )
    assert r["state"] == "error"
    assert list((tmp_path / "cortex" / "lifecycle").rglob("events.log")) == []


# ---------------------------------------------------------------------------
# KNOWN_STATES exhaustiveness + never-crash CLI
# ---------------------------------------------------------------------------


def test_every_state_is_known(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sa, "update_item", lambda *a, **k: None)
    seen = set()
    for feat, kwargs in [
        ("f1", {"decision": "approved"}),
        ("f2", {"decision": "cancelled"}),
        ("f3", {"decision": "revise"}),
    ]:
        _scaffold(tmp_path, monkeypatch, feature=feat)
        seen.add(
            sa.spec_approve(
                feature=feat, backend="none", backlog_file="",
                spec_path="p", emit_transition=False, **kwargs
            )["state"]
        )

    # error is reachable via the slug guard.
    _scaffold(tmp_path, monkeypatch, feature="f4")
    seen.add(
        sa.spec_approve(
            feature="../x", decision="approved", backend="none",
            backlog_file="", spec_path="p", emit_transition=False,
        )["state"]
    )

    assert seen == set(sa.KNOWN_STATES)


def test_cli_emits_json_and_exits_0_no_write_on_revise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The verification smoke command: revise exits 0 with a JSON envelope and no
    events.log write."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    rc = sa.main(
        [
            "--feature", "feat",
            "--decision", "revise",
            "--backend", "none",
            "--backlog-file", "",
            "--spec-path", "p",
            "--no-emit-transition",
        ]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "revise"
    assert not (feature_dir / "events.log").exists()


def test_cli_default_flag_state_suppresses_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """With neither transition flag passed, the default suppresses the
    specify->plan row (standalone behavior)."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    rc = sa.main(
        [
            "--feature", "feat",
            "--decision", "approved",
            "--backend", "none",
            "--backlog-file", "",
            "--spec-path", "p",
        ]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "approved"
    assert obj["emit_transition"] is False
    assert _event_names(feature_dir) == ["spec_approved"]


def test_cli_payload_carries_protocol_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The emitted payload carries the additive ``protocol`` field (two-sided
    handshake substrate)."""
    _scaffold(tmp_path, monkeypatch)
    rc = sa.main(
        [
            "--feature", "feat",
            "--decision", "revise",
            "--backend", "none",
            "--backlog-file", "",
            "--spec-path", "p",
            "--no-emit-transition",
        ]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["protocol"] == PROTOCOL_VERSION


def test_cli_error_state_on_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Any exception escaping spec_approve (other than _Exit2) emits a
    {"state": "error", ...} struct and exits 0 — never a traceback."""
    _scaffold(tmp_path, monkeypatch)

    def _boom_fn(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(sa, "spec_approve", _boom_fn)
    rc = sa.main(
        [
            "--feature", "feat",
            "--decision", "approved",
            "--backend", "none",
            "--backlog-file", "",
            "--spec-path", "p",
        ]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "kaboom" in obj["message"]
