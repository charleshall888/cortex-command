"""Tests for cortex-lifecycle-record-pr-opened — the Complete-phase Step
4+5 façade (write pr.json + log the ADR-0020-exempt pr_opened event).

The composed primitives (_gh_repo / _atomic_write_json from complete_route,
_append_event_atomic / _now_iso from lifecycle_event) are tested at their
own sites; here we monkeypatch them to drive the composition seam and pin
the exact pr_opened row shape (schema_version-first, per ADR-0020).
"""

from __future__ import annotations

import json

import pytest

from cortex_command.lifecycle import record_pr_opened as rpo


def _patch_happy_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> list:
    monkeypatch.setattr(rpo, "_gh_repo", lambda: "owner/repo")
    monkeypatch.setattr(
        rpo,
        "_gh_pr_view",
        lambda number: {"url": f"https://github.com/owner/repo/pull/{number}", "head_branch": "interactive/feat"},
    )
    monkeypatch.setattr(rpo, "_now_iso", lambda: "2026-07-06T00:00:00Z")

    written_json: list = []
    monkeypatch.setattr(
        rpo, "_atomic_write_json", lambda path, obj: written_json.append((path, obj))
    )

    appended: list = []
    monkeypatch.setattr(
        rpo, "_append_event_atomic", lambda path, row: appended.append((path, row))
    )
    return written_json, appended


def test_ok_writes_pr_json_and_logs_event(monkeypatch, tmp_path) -> None:
    written_json, appended = _patch_happy_path(monkeypatch, tmp_path)
    r = rpo.record_pr_opened("feat", 42, project_root=tmp_path)

    assert r["state"] == "ok"
    assert r["number"] == 42
    assert r["repo"] == "owner/repo"
    assert r["head_branch"] == "interactive/feat"
    assert r["opened_at"] == "2026-07-06T00:00:00Z"

    assert len(written_json) == 1
    pr_path, pr_obj = written_json[0]
    assert pr_path == tmp_path / "cortex" / "lifecycle" / "feat" / "pr.json"
    assert list(pr_obj.keys()) == ["number", "url", "head_branch", "opened_at", "repo"]
    assert pr_obj["number"] == 42
    assert pr_obj["repo"] == "owner/repo"


def test_pr_opened_event_schema_is_exempt_shape(monkeypatch, tmp_path) -> None:
    """Pin the ADR-0020 exempt schema: schema_version precedes feature."""
    _written, appended = _patch_happy_path(monkeypatch, tmp_path)
    rpo.record_pr_opened("feat", 7, project_root=tmp_path)

    assert len(appended) == 1
    log_path, row = appended[0]
    assert log_path == tmp_path / "cortex" / "lifecycle" / "feat" / "events.log"

    parsed = json.loads(row)
    assert list(parsed.keys()) == [
        "schema_version", "ts", "event", "feature", "number", "url", "head_branch", "repo",
    ]
    assert parsed["schema_version"] == 1
    assert isinstance(parsed["schema_version"], int)
    assert parsed["event"] == "pr_opened"
    assert parsed["feature"] == "feat"
    assert parsed["number"] == 7
    assert isinstance(parsed["number"], int)
    assert row.endswith("\n")
    # Spaced json.dumps defaults (ADR-0020 canonical form), not compact.
    assert '"event": "pr_opened"' in row


def test_gh_repo_failure_returns_gh_error_and_writes_nothing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(rpo, "_gh_repo", lambda: "")
    written = []
    appended = []
    monkeypatch.setattr(rpo, "_atomic_write_json", lambda path, obj: written.append(1))
    monkeypatch.setattr(rpo, "_append_event_atomic", lambda path, row: appended.append(1))

    r = rpo.record_pr_opened("feat", 1, project_root=tmp_path)
    assert r["state"] == "gh-error"
    assert written == []
    assert appended == []


def test_gh_pr_view_failure_returns_gh_error_and_writes_nothing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(rpo, "_gh_repo", lambda: "owner/repo")
    monkeypatch.setattr(rpo, "_gh_pr_view", lambda number: None)
    written = []
    appended = []
    monkeypatch.setattr(rpo, "_atomic_write_json", lambda path, obj: written.append(1))
    monkeypatch.setattr(rpo, "_append_event_atomic", lambda path, row: appended.append(1))

    r = rpo.record_pr_opened("feat", 1, project_root=tmp_path)
    assert r["state"] == "gh-error"
    assert written == []
    assert appended == []


def test_every_state_is_known(monkeypatch, tmp_path) -> None:
    seen = set()
    _patch_happy_path(monkeypatch, tmp_path)
    seen.add(rpo.record_pr_opened("f", 1, project_root=tmp_path)["state"])

    monkeypatch.setattr(rpo, "_gh_repo", lambda: "")
    seen.add(rpo.record_pr_opened("f", 1, project_root=tmp_path)["state"])

    assert seen <= set(rpo.KNOWN_STATES)
    assert seen == {"ok", "gh-error"}


def test_cli_emits_json(monkeypatch, tmp_path, capsys) -> None:
    _patch_happy_path(monkeypatch, tmp_path)
    monkeypatch.setattr(rpo, "_resolve_user_project_root_from_cwd", lambda: tmp_path)
    rc = rpo.main(["--feature", "feat", "--number", "9"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "ok"
    assert obj["number"] == 9
