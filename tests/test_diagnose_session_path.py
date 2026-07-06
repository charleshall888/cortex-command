"""Tests for cortex-debug-session-path — the diagnose skill's
Location-priority resolver (explicit --feature, active
$LIFECYCLE_SESSION_ID match, or cortex/debug/ fallback).

Unlike ``test_prepare_worktree.py``'s composition seam (monkeypatched
collaborator functions), this verb's logic is pure filesystem/env reads with
no injectable collaborators, so these tests build real ``tmp_path`` trees and
pass ``project_root=tmp_path`` directly, following the ``tmp_path``-based
``_detect_base_branch`` tests in that file rather than its monkeypatch-heavy
majority.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command import diagnose_session_path as dsp


def _make_lifecycle_dir(root: Path, feature: str) -> Path:
    d = root / "cortex" / "lifecycle" / feature
    d.mkdir(parents=True)
    return d


def test_explicit_feature_dir_exists_resolves_lifecycle(tmp_path: Path) -> None:
    _make_lifecycle_dir(tmp_path, "my-feature")
    r = dsp.resolve_debug_session_path(feature="my-feature", project_root=tmp_path)
    assert r["state"] == "lifecycle"
    assert r["basis"] == "explicit-feature"
    assert r["path"] == str(tmp_path / "cortex" / "lifecycle" / "my-feature" / "debug-session.md")


def test_explicit_feature_missing_falls_back_with_warning(tmp_path: Path) -> None:
    r = dsp.resolve_debug_session_path(feature="ghost-feature", project_root=tmp_path)
    assert r["state"] == "fallback"
    assert r["basis"] == "explicit-feature-missing"
    assert "ghost-feature" in r["warning"]
    assert str(tmp_path / "cortex" / "debug") in r["path"]


def test_explicit_feature_missing_skips_session_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit but nonexistent --feature must fall straight through to
    the cortex/debug/ fallback — not consult $LIFECYCLE_SESSION_ID at all
    (matches the doc's 'else warn and fall back to step 3', not step 2)."""
    other = _make_lifecycle_dir(tmp_path, "other-feature")
    (other / ".session").write_text("sess-1")
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "sess-1")
    r = dsp.resolve_debug_session_path(feature="ghost-feature", project_root=tmp_path)
    assert r["state"] == "fallback"
    assert r["basis"] == "explicit-feature-missing"


def test_session_match_resolves_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feat = _make_lifecycle_dir(tmp_path, "active-feat")
    (feat / ".session").write_text("sess-abc\n")
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "sess-abc")
    r = dsp.resolve_debug_session_path(project_root=tmp_path)
    assert r["state"] == "lifecycle"
    assert r["basis"] == "session-match"
    assert r["path"] == str(tmp_path / "cortex" / "lifecycle" / "active-feat" / "debug-session.md")


def test_session_owner_chain_migration_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No ``.session`` file but a matching ``.session-owner`` (chain
    migration) must still resolve — mirrors discovery._active_lifecycle_slug."""
    feat = _make_lifecycle_dir(tmp_path, "migrated-feat")
    (feat / ".session-owner").write_text("sess-xyz")
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "sess-xyz")
    r = dsp.resolve_debug_session_path(project_root=tmp_path)
    assert r["state"] == "lifecycle"
    assert r["basis"] == "session-match"


def test_session_id_set_but_no_match_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feat = _make_lifecycle_dir(tmp_path, "unrelated-feat")
    (feat / ".session").write_text("sess-other")
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "sess-abc")
    r = dsp.resolve_debug_session_path(project_root=tmp_path)
    assert r["state"] == "fallback"
    assert r["basis"] == "no-session"


def test_no_session_env_var_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    r = dsp.resolve_debug_session_path(project_root=tmp_path)
    assert r["state"] == "fallback"
    assert r["basis"] == "no-session"
    assert "warning" not in r


def test_archive_directory_skipped_in_session_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "cortex" / "lifecycle" / "archive"
    archive.mkdir(parents=True)
    (archive / ".session").write_text("sess-abc")
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "sess-abc")
    r = dsp.resolve_debug_session_path(project_root=tmp_path)
    assert r["state"] == "fallback"
    assert r["basis"] == "no-session"


def test_fallback_defaults_slug_to_diagnose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    r = dsp.resolve_debug_session_path(project_root=tmp_path)
    assert r["path"].endswith("-diagnose.md")


def test_fallback_uses_provided_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    r = dsp.resolve_debug_session_path(slug="stale-runner-pid", project_root=tmp_path)
    assert r["path"].endswith("-stale-runner-pid.md")


def test_feature_path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        dsp.resolve_debug_session_path(feature="../../etc", project_root=tmp_path)


def test_slug_path_traversal_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    with pytest.raises(ValueError):
        dsp.resolve_debug_session_path(slug="../escape", project_root=tmp_path)


def test_every_state_is_known(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = set()

    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    seen.add(dsp.resolve_debug_session_path(project_root=tmp_path)["state"])

    feat = _make_lifecycle_dir(tmp_path, "known-feat")
    (feat / ".session").write_text("sess-known")
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "sess-known")
    seen.add(dsp.resolve_debug_session_path(project_root=tmp_path)["state"])

    seen.add(
        dsp.resolve_debug_session_path(feature="ghost", project_root=tmp_path)["state"]
    )

    assert seen <= set(dsp.KNOWN_STATES)
    assert seen == {"fallback", "lifecycle"}


def test_cli_emits_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(dsp, "_resolve_user_project_root", lambda: tmp_path)
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    rc = dsp.main([])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "fallback"
    assert obj["basis"] == "no-session"


def test_cli_exits_0_with_error_state_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Regression pin: any exception escaping ``resolve_debug_session_path``
    (e.g. a project-root resolution failure, or a rejected --feature/--slug)
    must not crash the CLI — ``main`` must still emit a {"state": "error",
    ...} JSON struct and exit 0."""

    def _boom(feature=None, slug=None, project_root=None):
        raise RuntimeError("root not found")

    monkeypatch.setattr(dsp, "resolve_debug_session_path", _boom)
    rc = dsp.main([])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "root not found" in obj["message"]
