"""Tests for cortex-lifecycle-finalize — the Complete-phase finalization façade
composing the backend-gated backlog write-back, the counters read, and the
idempotent ``feature_complete`` emission into one ``{state, ...}`` envelope.

Root resolution uses the cwd flavor, so the tests ``monkeypatch.chdir(tmp_path)``
(and ``delenv CORTEX_REPO_ROOT``) and scaffold a ``cortex/`` tree there; the real
``log_event``/``counters`` then resolve the same tree the verb does. The item
resolver and ``update_item`` are patched on the verb's own module namespace (the
``test_prepare_worktree.py`` pattern) to drive the write-back seam.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.backlog.resolve_item import ResolutionResult
from cortex_command.lifecycle import finalize as fin
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


# ---------------------------------------------------------------------------
# merge_anchor emission (the load-bearing metrics-segmentation field)
# ---------------------------------------------------------------------------


def test_emits_feature_complete_with_merge_anchor_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The emitted row carries ``"merge_anchor": "merge"`` — the field
    metrics.py segments interactive vs legacy-overnight completions on, which
    advance_lifecycle.py's narrower shape omits."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = fin.finalize(feature="feat", backend="none", backlog_file="")

    assert r["state"] == "finalized"
    assert r["emitted"] is True

    raw = (feature_dir / "events.log").read_text()
    assert '"merge_anchor": "merge"' in raw
    rows = _events_rows(feature_dir)
    assert len(rows) == 1
    assert rows[0]["event"] == "feature_complete"
    assert rows[0]["merge_anchor"] == "merge"


def test_counters_feed_the_emitted_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """tasks_total/rework_cycles come from the feature's plan.md/events.log."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    (feature_dir / "plan.md").write_text(
        "**Status**: [x] done\n**Status**: [ ] todo\n**Status**: [x] done2\n",
        encoding="utf-8",
    )
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "review_verdict", "verdict": "CHANGES_REQUESTED"}) + "\n",
        encoding="utf-8",
    )
    r = fin.finalize(feature="feat", backend="none", backlog_file="")

    assert r["tasks_total"] == 3
    assert r["rework_cycles"] == 1
    row = [x for x in _events_rows(feature_dir) if x["event"] == "feature_complete"][0]
    assert row["tasks_total"] == 3
    assert row["rework_cycles"] == 1


# ---------------------------------------------------------------------------
# Idempotency — a second invocation appends no duplicate row
# ---------------------------------------------------------------------------


def test_second_invocation_emits_no_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit-retry double invocation must not append a second
    feature_complete — the guard matches a parsed ``event`` field."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    first = fin.finalize(feature="feat", backend="none", backlog_file="")
    second = fin.finalize(feature="feat", backend="none", backlog_file="")

    assert first["emitted"] is True
    assert second["emitted"] is False
    rows = [x for x in _events_rows(feature_dir) if x["event"] == "feature_complete"]
    assert len(rows) == 1


def test_idempotent_guard_is_not_substring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row that merely mentions the string ``feature_complete`` in another
    field does not suppress emission — only a parsed ``event`` match does."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "note", "text": "feature_complete pending"}) + "\n",
        encoding="utf-8",
    )
    r = fin.finalize(feature="feat", backend="none", backlog_file="")
    assert r["emitted"] is True
    assert len([x for x in _events_rows(feature_dir) if x["event"] == "feature_complete"]) == 1


# ---------------------------------------------------------------------------
# Backend gate
# ---------------------------------------------------------------------------


def test_cortex_backlog_updates_the_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cortex-backlog resolves the item and update_items it to complete with a
    null session_id; the backlog signal is ``updated``."""
    _scaffold(tmp_path, monkeypatch)
    item_path = tmp_path / "cortex" / "backlog" / "326-foo.md"
    calls: list = []
    monkeypatch.setattr(
        fin, "resolve", lambda ref, backlog_dir: ResolutionResult(status="ok", item=item_path)
    )
    monkeypatch.setattr(
        fin,
        "update_item",
        lambda path, fields, backlog_dir, session_id=None: calls.append(
            (path, fields, backlog_dir, session_id)
        ),
    )
    r = fin.finalize(feature="feat", backend="cortex-backlog", backlog_file="326-foo.md")

    assert r["backlog"] == "updated"
    assert calls == [
        (item_path, {"status": "complete"}, tmp_path / "cortex" / "backlog", None)
    ]


def test_backend_none_skips_writeback_but_emits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)

    def _boom(*a, **k):
        raise AssertionError("update_item must not be called for backend none")

    monkeypatch.setattr(fin, "update_item", _boom)
    r = fin.finalize(feature="feat", backend="none", backlog_file="326-foo.md")

    assert r["state"] == "finalized"
    assert r["backlog"] == "skipped"
    assert r["emitted"] is True
    assert len([x for x in _events_rows(feature_dir) if x["event"] == "feature_complete"]) == 1


def test_no_item_skips_writeback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty --backlog-file is ``no-item``: skip the write-back silently
    (Step 9), still emit."""
    _scaffold(tmp_path, monkeypatch)

    def _boom(*a, **k):
        raise AssertionError("update_item must not be called with no item")

    monkeypatch.setattr(fin, "update_item", _boom)
    r = fin.finalize(feature="feat", backend="cortex-backlog", backlog_file="")
    assert r["backlog"] == "no-item"
    assert r["emitted"] is True


def test_not_found_reference_skips_writeback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scaffold(tmp_path, monkeypatch)
    monkeypatch.setattr(
        fin, "resolve", lambda ref, backlog_dir: ResolutionResult(status="not_found")
    )

    def _boom(*a, **k):
        raise AssertionError("update_item must not be called for a not_found ref")

    monkeypatch.setattr(fin, "update_item", _boom)
    r = fin.finalize(feature="feat", backend="cortex-backlog", backlog_file="404-gone.md")
    assert r["backlog"] == "no-item"


def test_external_backend_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An external tracker backend skips the local write-back and returns
    external-backend for the skill's best-effort arm — the event still emits."""
    feature_dir = _scaffold(tmp_path, monkeypatch)

    def _boom(*a, **k):
        raise AssertionError("update_item must not be called for an external backend")

    monkeypatch.setattr(fin, "update_item", _boom)
    r = fin.finalize(feature="feat", backend="jira", backlog_file="326-foo.md")

    assert r["state"] == "external-backend"
    assert r["backlog"] == "external"
    assert r["emitted"] is True
    assert len([x for x in _events_rows(feature_dir) if x["event"] == "feature_complete"]) == 1


# ---------------------------------------------------------------------------
# EXIT-2 carve-out: ambiguous slug propagates (never-crash envelope exempt)
# ---------------------------------------------------------------------------


def test_ambiguous_slug_raises_exit2_with_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """An ambiguous backlog reference writes the candidate list to stderr and
    raises _Exit2 — no envelope, no emission."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    candidates = [
        tmp_path / "cortex" / "backlog" / "370-a.md",
        tmp_path / "cortex" / "backlog" / "370-b.md",
    ]
    for c in candidates:
        c.write_text("---\ntitle: A ticket\nstatus: refined\n---\n", encoding="utf-8")
    monkeypatch.setattr(
        fin,
        "resolve",
        lambda ref, backlog_dir: ResolutionResult(status="ambiguous", candidates=candidates),
    )

    with pytest.raises(fin._Exit2):
        fin.finalize(feature="feat", backend="cortex-backlog", backlog_file="370.md")

    err = capsys.readouterr().err
    assert "ambiguous: 2 matches" in err
    # No feature_complete emitted — the write-back aborted before emission.
    assert _events_rows(feature_dir) == []


def test_main_returns_2_on_ambiguous_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scaffold(tmp_path, monkeypatch)

    def _raise(**kwargs):
        raise fin._Exit2()

    monkeypatch.setattr(fin, "finalize", _raise)
    rc = fin.main(
        ["--feature", "feat", "--backend", "cortex-backlog", "--backlog-file", "370.md"]
    )
    assert rc == 2


# ---------------------------------------------------------------------------
# CLI contract: never-crash JSON + every KNOWN_STATE reachable
# ---------------------------------------------------------------------------


def test_cli_emits_json_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _scaffold(tmp_path, monkeypatch)
    rc = fin.main(["--feature", "feat", "--backend", "none", "--backlog-file", ""])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "finalized"


def test_cli_payload_carries_protocol_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The emitted payload carries the additive ``protocol`` field (two-sided
    handshake substrate)."""
    _scaffold(tmp_path, monkeypatch)
    rc = fin.main(["--feature", "feat", "--backend", "none", "--backlog-file", ""])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["protocol"] == PROTOCOL_VERSION


def test_cli_error_state_on_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Any exception escaping finalize (other than _Exit2) emits a
    {"state": "error", ...} struct and exits 0 — never a traceback."""
    _scaffold(tmp_path, monkeypatch)

    def _boom(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(fin, "finalize", _boom)
    rc = fin.main(["--feature", "feat", "--backend", "none", "--backlog-file", ""])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "kaboom" in obj["message"]


def test_every_state_is_known(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = set()
    _scaffold(tmp_path, monkeypatch)
    seen.add(fin.finalize(feature="feat", backend="none", backlog_file="")["state"])

    monkeypatch.setattr(fin, "update_item", lambda *a, **k: None)
    seen.add(
        fin.finalize(feature="feat", backend="jira", backlog_file="326-foo.md")["state"]
    )

    # The error state is only reachable through main()'s never-crash guard.
    def _boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(fin, "finalize", _boom)
    fin.main(["--feature", "feat", "--backend", "none", "--backlog-file", ""])
    seen.add("error")

    assert seen == set(fin.KNOWN_STATES)
