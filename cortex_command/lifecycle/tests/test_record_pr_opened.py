"""Tests for cortex-lifecycle-record-pr-opened — the Complete-phase Step
4+5 façade (write pr.json + log the ADR-0020-exempt pr_opened event).

The composed primitives (_gh_repo / _atomic_write_json / _run from
complete_route, _append_event_atomic / _now_iso from lifecycle_event) are
tested at their own sites; here we monkeypatch them to drive the composition
seam and pin the exact pr_opened row shape (schema_version-first, per
ADR-0020), the exit-0 contract on every failure mode, and the --url/
--head-branch dumb-arg-actor shortcut (ADR-0019).
"""

from __future__ import annotations

import json
from typing import Tuple

import pytest

from cortex_command.common import CortexProjectRootError
from cortex_command.lifecycle import record_pr_opened as rpo


def _patch_happy_path(monkeypatch: pytest.MonkeyPatch) -> Tuple[list, list]:
    monkeypatch.setattr(rpo, "_gh_repo", lambda: "owner/repo")
    monkeypatch.setattr(
        rpo,
        "_gh_pr_view",
        lambda number, repo: {
            "url": f"https://github.com/owner/repo/pull/{number}",
            "head_branch": "interactive/feat",
        },
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
    written_json, appended = _patch_happy_path(monkeypatch)
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
    _written, appended = _patch_happy_path(monkeypatch)
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
    monkeypatch.setattr(rpo, "_gh_pr_view", lambda number, repo: None)
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
    _patch_happy_path(monkeypatch)
    seen.add(rpo.record_pr_opened("f", 1, project_root=tmp_path)["state"])

    monkeypatch.setattr(rpo, "_gh_repo", lambda: "")
    seen.add(rpo.record_pr_opened("f", 1, project_root=tmp_path)["state"])

    assert seen <= set(rpo.KNOWN_STATES)
    assert seen == {"ok", "gh-error"}


def test_cli_emits_json(monkeypatch, tmp_path, capsys) -> None:
    _patch_happy_path(monkeypatch)
    monkeypatch.setattr(rpo, "_resolve_user_project_root_from_cwd", lambda: tmp_path)
    rc = rpo.main(["--feature", "feat", "--number", "9"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "ok"
    assert obj["number"] == 9


# ---------------------------------------------------------------------------
# --url/--head-branch dumb-arg-actor shortcut (ADR-0019): skip gh pr view.
# ---------------------------------------------------------------------------


def test_url_and_head_branch_skip_gh_pr_view_round_trip(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(rpo, "_gh_repo", lambda: "owner/repo")
    monkeypatch.setattr(rpo, "_now_iso", lambda: "2026-07-06T00:00:00Z")

    calls: list = []
    monkeypatch.setattr(
        rpo, "_gh_pr_view", lambda number, repo: calls.append((number, repo)) or None
    )
    written_json: list = []
    monkeypatch.setattr(
        rpo, "_atomic_write_json", lambda path, obj: written_json.append((path, obj))
    )
    appended: list = []
    monkeypatch.setattr(
        rpo, "_append_event_atomic", lambda path, row: appended.append((path, row))
    )

    r = rpo.record_pr_opened(
        "feat",
        42,
        project_root=tmp_path,
        url="https://github.com/owner/repo/pull/42",
        head_branch="interactive/feat",
    )

    assert calls == [], "gh pr view must not be called when --url/--head-branch are both given"
    assert r["state"] == "ok"
    assert r["url"] == "https://github.com/owner/repo/pull/42"
    assert r["head_branch"] == "interactive/feat"
    assert len(written_json) == 1
    assert len(appended) == 1


def test_url_without_head_branch_falls_back_to_gh_pr_view(monkeypatch, tmp_path) -> None:
    """Only one of --url/--head-branch given -> falls back to gh pr view."""
    written_json, appended = _patch_happy_path(monkeypatch)

    r = rpo.record_pr_opened(
        "feat", 42, project_root=tmp_path, url="https://github.com/owner/repo/pull/42"
    )

    assert r["state"] == "ok"
    # head_branch came from the (patched) gh pr view fallback, not the caller.
    assert r["head_branch"] == "interactive/feat"
    assert len(written_json) == 1


def test_gh_pr_view_passes_resolved_repo(monkeypatch, tmp_path) -> None:
    """The gh pr view fallback passes --repo using the already-resolved repo."""
    monkeypatch.setattr(rpo, "_gh_repo", lambda: "owner/repo")
    monkeypatch.setattr(rpo, "_now_iso", lambda: "2026-07-06T00:00:00Z")
    monkeypatch.setattr(rpo, "_atomic_write_json", lambda path, obj: None)
    monkeypatch.setattr(rpo, "_append_event_atomic", lambda path, row: None)

    seen_cmds: list = []

    def _fake_run(cmd, cwd=None, timeout=30):
        seen_cmds.append(cmd)

        class _P:
            returncode = 0
            stdout = json.dumps({"url": "https://x/pull/9", "headRefName": "featbranch"})

        return _P()

    monkeypatch.setattr(rpo, "_run", _fake_run)

    r = rpo.record_pr_opened("feat", 9, project_root=tmp_path)
    assert r["state"] == "ok"
    assert len(seen_cmds) == 1
    assert "--repo" in seen_cmds[0]
    assert "owner/repo" in seen_cmds[0]


# ---------------------------------------------------------------------------
# Exit-0 contract: every internal failure returns a state, never raises.
# ---------------------------------------------------------------------------


def test_project_root_error_returns_state_not_traceback(monkeypatch) -> None:
    monkeypatch.setattr(rpo, "_gh_repo", lambda: "owner/repo")
    monkeypatch.setattr(
        rpo, "_gh_pr_view", lambda number, repo: {"url": "u", "head_branch": "h"}
    )

    def _raise():
        raise CortexProjectRootError("no cortex/ found")

    monkeypatch.setattr(rpo, "_resolve_user_project_root_from_cwd", _raise)

    r = rpo.record_pr_opened("feat", 1, project_root=None)
    assert r["state"] == "project-root-error"
    assert "no cortex/ found" in r["message"]


def test_pr_json_write_failure_returns_state_not_traceback(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(rpo, "_gh_repo", lambda: "owner/repo")
    monkeypatch.setattr(
        rpo, "_gh_pr_view", lambda number, repo: {"url": "u", "head_branch": "h"}
    )
    appended: list = []
    monkeypatch.setattr(rpo, "_append_event_atomic", lambda path, row: appended.append(1))

    def _raise(path, obj):
        raise OSError("disk full")

    monkeypatch.setattr(rpo, "_atomic_write_json", _raise)

    r = rpo.record_pr_opened("feat", 1, project_root=tmp_path)
    assert r["state"] == "pr-json-write-failed"
    assert "disk full" in r["message"]
    assert appended == [], "event must not be appended when pr.json write failed"


def test_event_append_failure_returns_state_naming_partial_write(
    monkeypatch, tmp_path
) -> None:
    """pr.json IS written; the event append failing must not strand it silently."""
    monkeypatch.setattr(rpo, "_gh_repo", lambda: "owner/repo")
    monkeypatch.setattr(
        rpo,
        "_gh_pr_view",
        lambda number, repo: {"url": "https://x/pull/1", "head_branch": "h"},
    )
    monkeypatch.setattr(rpo, "_now_iso", lambda: "2026-07-06T00:00:00Z")
    written_json: list = []
    monkeypatch.setattr(
        rpo, "_atomic_write_json", lambda path, obj: written_json.append((path, obj))
    )

    def _raise(path, row):
        raise OSError("lock timeout")

    monkeypatch.setattr(rpo, "_append_event_atomic", _raise)

    r = rpo.record_pr_opened("feat", 1, project_root=tmp_path)
    assert r["state"] == "event-append-failed"
    assert "lock timeout" in r["message"]
    assert len(written_json) == 1, "pr.json must still have been written"
    # Names what WAS written so the caller can retry the event append precisely.
    assert r["number"] == 1
    assert r["repo"] == "owner/repo"
    assert r["head_branch"] == "h"


def test_cli_never_raises_and_always_exits_zero(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(rpo, "_gh_repo", lambda: "")  # forces gh-error, no writes
    rc = rpo.main(["--feature", "feat", "--number", "1"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "gh-error"


def test_cli_accepts_url_and_head_branch_flags(monkeypatch, tmp_path, capsys) -> None:
    _patch_happy_path(monkeypatch)
    monkeypatch.setattr(rpo, "_resolve_user_project_root_from_cwd", lambda: tmp_path)
    calls: list = []
    monkeypatch.setattr(
        rpo, "_gh_pr_view", lambda number, repo: calls.append(1) or None
    )
    rc = rpo.main(
        [
            "--feature", "feat",
            "--number", "9",
            "--url", "https://github.com/owner/repo/pull/9",
            "--head-branch", "interactive/feat",
        ]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "ok"
    assert obj["url"] == "https://github.com/owner/repo/pull/9"
    assert obj["head_branch"] == "interactive/feat"
    assert calls == [], "gh pr view must be skipped when both flags are passed via the CLI"
