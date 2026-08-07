"""Tests for cortex-lifecycle-register-artifact — the skip-if-present verb that
appends a produced artifact to a feature's index.md ``artifacts:`` inline array
and bumps ``updated:``.

Covers the byte-format round-trip (only the two intended lines change; the rest
of index.md is preserved verbatim), the double-register no-op, the no-index and
error states, every KNOWN_STATES member, and the never-crash CLI contract.
"""

from __future__ import annotations

import json

import pytest

from cortex_command.common import CortexProjectRootError
from cortex_command.lifecycle import register_artifact as ra
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION


def _index_path(root, feature="feat"):
    return root / "cortex" / "lifecycle" / feature / "index.md"


_ALL_ARTIFACTS = ("research", "spec", "plan", "review")


def _write_index(
    root, artifacts_line, *, feature="feat", updated="2026-01-01", write_artifacts=True
):
    """Write a byte-faithful index.md with the given artifacts line.

    Since commit c6dca432, register_artifact refuses (state "error") unless a
    non-empty ``{artifact}.md`` sits beside index.md. By default this also
    writes a non-empty sibling file for every known artifact kind, so callers
    exercising any of research/spec/plan/review clear the precondition
    without each test having to know which one it needs. Pass
    write_artifacts=False for tests that specifically exercise the
    missing/empty-artifact refusal path.
    """
    path = _index_path(root, feature)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "---\n"
        f"feature: {feature}\n"
        "parent_backlog_uuid: null\n"
        "parent_backlog_id: null\n"
        f"{artifacts_line}\n"
        "tags: []\n"
        "created: 2026-01-01\n"
        f"updated: {updated}\n"
        "---\n"
    )
    path.write_text(content, encoding="utf-8")
    if write_artifacts:
        for name in _ALL_ARTIFACTS:
            (path.parent / f"{name}.md").write_text("placeholder\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Append + byte-format round-trip
# ---------------------------------------------------------------------------


def test_append_to_empty_array_registers(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ra, "_today", lambda: "2026-07-10")
    path = _write_index(tmp_path, "artifacts: []")

    r = ra.register_artifact("feat", "research", index_path=path)
    assert r["state"] == "registered"
    assert r["artifact"] == "research"

    text = path.read_text(encoding="utf-8")
    assert "artifacts: [research]" in text
    assert "updated: 2026-07-10" in text


def test_append_preserves_byte_format_of_untouched_lines(tmp_path, monkeypatch) -> None:
    """Only the artifacts: and updated: lines change; everything else is verbatim."""
    monkeypatch.setattr(ra, "_today", lambda: "2026-07-10")
    path = _write_index(tmp_path, "artifacts: [research, spec]")

    ra.register_artifact("feat", "plan", index_path=path)

    assert path.read_text(encoding="utf-8") == (
        "---\n"
        "feature: feat\n"
        "parent_backlog_uuid: null\n"
        "parent_backlog_id: null\n"
        "artifacts: [research, spec, plan]\n"
        "tags: []\n"
        "created: 2026-01-01\n"
        "updated: 2026-07-10\n"
        "---\n"
    )


def test_append_preserves_existing_entry_quoting(tmp_path, monkeypatch) -> None:
    """Pre-existing quoted entries keep their quotes; the new one is appended bare."""
    monkeypatch.setattr(ra, "_today", lambda: "2026-07-10")
    path = _write_index(tmp_path, 'artifacts: ["research", "spec"]')

    ra.register_artifact("feat", "plan", index_path=path)
    text = path.read_text(encoding="utf-8")
    assert 'artifacts: ["research", "spec", plan]' in text


# ---------------------------------------------------------------------------
# Double-register no-op
# ---------------------------------------------------------------------------


def test_double_register_is_byte_level_noop(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ra, "_today", lambda: "2026-07-10")
    path = _write_index(tmp_path, "artifacts: [research]", updated="2026-05-05")
    before = path.read_text(encoding="utf-8")

    r = ra.register_artifact("feat", "research", index_path=path)
    assert r["state"] == "already-present"
    # No write at all: bytes unchanged, including the stale updated: date.
    assert path.read_text(encoding="utf-8") == before
    assert "updated: 2026-05-05" in path.read_text(encoding="utf-8")


def test_register_then_reregister_second_is_noop(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ra, "_today", lambda: "2026-07-10")
    path = _write_index(tmp_path, "artifacts: []")

    first = ra.register_artifact("feat", "spec", index_path=path)
    assert first["state"] == "registered"
    after_first = path.read_text(encoding="utf-8")

    second = ra.register_artifact("feat", "spec", index_path=path)
    assert second["state"] == "already-present"
    assert path.read_text(encoding="utf-8") == after_first


# ---------------------------------------------------------------------------
# no-index / error states
# ---------------------------------------------------------------------------


def test_missing_index_returns_no_index(tmp_path) -> None:
    path = _index_path(tmp_path)
    assert not path.exists()
    r = ra.register_artifact("feat", "research", index_path=path)
    assert r["state"] == "no-index"


def test_index_without_artifacts_line_returns_no_index(tmp_path) -> None:
    path = _index_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("---\nfeature: feat\n---\n", encoding="utf-8")
    (path.parent / "research.md").write_text("content\n", encoding="utf-8")
    r = ra.register_artifact("feat", "research", index_path=path)
    assert r["state"] == "no-index"


def test_malformed_index_outranks_missing_artifact(tmp_path) -> None:
    """A malformed index wins over the artifact precondition.

    Both ``no-index`` arms — absent index and index with no ``artifacts:`` line —
    are more actionable than "artifact missing", so neither may be masked when the
    artifact is *also* missing. Without this ordering the caller is told to produce
    an artifact when the real fault is the index.
    """
    path = _index_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("---\nfeature: feat\n---\n", encoding="utf-8")
    # No research.md written: both faults present at once.
    r = ra.register_artifact("feat", "research", index_path=path)
    assert r["state"] == "no-index"


def test_project_root_error_returns_state_not_traceback(monkeypatch) -> None:
    def _raise():
        raise CortexProjectRootError("no cortex/ found")

    monkeypatch.setattr(ra, "_resolve_user_project_root_from_cwd", _raise)
    r = ra.register_artifact("feat", "research")
    assert r["state"] == "error"
    assert "no cortex/ found" in r["message"]


def test_io_failure_returns_error_state_not_traceback(tmp_path, monkeypatch) -> None:
    path = _write_index(tmp_path, "artifacts: []")

    def _raise(p, content, encoding="utf-8"):
        raise OSError("disk full")

    monkeypatch.setattr(ra, "atomic_write", _raise)
    r = ra.register_artifact("feat", "research", index_path=path)
    assert r["state"] == "error"
    assert "disk full" in r["message"]


# ---------------------------------------------------------------------------
# Artifact existence precondition (commit c6dca432)
# ---------------------------------------------------------------------------


def test_missing_artifact_file_returns_error(tmp_path) -> None:
    """No {artifact}.md next to index.md at all: refuses with "error" and
    writes nothing (the array stays exactly as it was)."""
    path = _write_index(tmp_path, "artifacts: []", write_artifacts=False)
    assert not (path.parent / "research.md").exists()

    r = ra.register_artifact("feat", "research", index_path=path)
    assert r["state"] == "error"
    assert "research.md" in r["message"]
    assert "artifacts: []" in path.read_text(encoding="utf-8")


def test_zero_byte_artifact_file_returns_error(tmp_path) -> None:
    """A {artifact}.md that exists but is zero-byte is treated the same as
    missing: "error", nothing written."""
    path = _write_index(tmp_path, "artifacts: []", write_artifacts=False)
    (path.parent / "research.md").write_text("", encoding="utf-8")

    r = ra.register_artifact("feat", "research", index_path=path)
    assert r["state"] == "error"
    assert "artifacts: []" in path.read_text(encoding="utf-8")


def test_neither_index_nor_artifact_returns_no_index_not_error(tmp_path) -> None:
    """R8 precedence: index.md is checked before the artifact precondition,
    so a feature with neither an index nor an artifact is "no-index" — the
    artifact check never runs, and "error" must not leak through here."""
    path = _index_path(tmp_path)
    assert not path.exists()

    r = ra.register_artifact("feat", "research", index_path=path)
    assert r["state"] == "no-index"


def test_artifact_check_anchors_to_index_parent_not_feature_slug(
    tmp_path, monkeypatch
) -> None:
    """artifact_path is derived from index_path.parent, not from
    cortex/lifecycle/{feature}/ (R3). A mismatched directory name on
    index_path is irrelevant as long as the artifact sits beside it; an
    artifact placed only at the feature-derived cortex/lifecycle/{feature}/
    path does not satisfy the check when index_path points elsewhere."""
    monkeypatch.setattr(ra, "_today", lambda: "2026-07-10")

    odd_dir = tmp_path / "unrelated-dir-name"
    odd_dir.mkdir()

    # Case A: artifact beside the real index_path, even though the
    # containing directory's name doesn't match feature="feat" -> registered.
    index_path = odd_dir / "index.md"
    index_path.write_text(
        "---\nfeature: feat\nartifacts: []\nupdated: 2026-01-01\n---\n",
        encoding="utf-8",
    )
    (odd_dir / "research.md").write_text("content\n", encoding="utf-8")

    r = ra.register_artifact("feat", "research", index_path=index_path)
    assert r["state"] == "registered"

    # Case B: same odd directory, but the only artifact present is under the
    # cwd-derived cortex/lifecycle/feat/ path (matching the feature slug)
    # rather than beside index_path -> the check still looks beside
    # index_path, so this refuses with "error".
    index_path2 = odd_dir / "index2.md"
    index_path2.write_text(
        "---\nfeature: feat\nartifacts: []\nupdated: 2026-01-01\n---\n",
        encoding="utf-8",
    )
    feature_dir = tmp_path / "cortex" / "lifecycle" / "feat"
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text("content\n", encoding="utf-8")

    r2 = ra.register_artifact("feat", "spec", index_path=index_path2)
    assert r2["state"] == "error"


# ---------------------------------------------------------------------------
# Root resolution via chdir (delenv CORTEX_REPO_ROOT — cwd flavor)
# ---------------------------------------------------------------------------


def test_resolves_index_from_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.setattr(ra, "_today", lambda: "2026-07-10")
    (tmp_path / "cortex").mkdir()
    _write_index(tmp_path, "artifacts: []")
    monkeypatch.chdir(tmp_path)

    r = ra.register_artifact("feat", "research")
    assert r["state"] == "registered"
    assert r["path"] == "cortex/lifecycle/feat/index.md"


# ---------------------------------------------------------------------------
# KNOWN_STATES coverage
# ---------------------------------------------------------------------------


def test_every_state_is_known(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ra, "_today", lambda: "2026-07-10")
    seen = set()

    path = _write_index(tmp_path, "artifacts: []")
    seen.add(ra.register_artifact("feat", "research", index_path=path)["state"])  # registered
    seen.add(ra.register_artifact("feat", "research", index_path=path)["state"])  # already-present
    seen.add(
        ra.register_artifact("feat", "spec", index_path=_index_path(tmp_path, "gone"))["state"]
    )  # no-index

    def _raise():
        raise CortexProjectRootError("boom")

    monkeypatch.setattr(ra, "_resolve_user_project_root_from_cwd", _raise)
    seen.add(ra.register_artifact("feat", "plan")["state"])  # error

    assert seen == {"registered", "already-present", "no-index", "error"}
    assert seen <= set(ra.KNOWN_STATES)


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


def test_cli_emits_compact_json_and_exits_zero(tmp_path, capsys) -> None:
    path = _write_index(tmp_path, "artifacts: []")
    rc = ra.main(
        ["--feature", "feat", "--artifact", "research", "--project-root", str(tmp_path)]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert ", " not in out  # compact separators (json.dumps separators=(",", ":"))
    assert '": "' not in out
    obj = json.loads(out)
    assert obj["state"] == "registered"
    assert obj["artifact"] == "research"


def test_cli_payload_carries_protocol_field(tmp_path, capsys) -> None:
    """The emitted payload carries the additive ``protocol`` field (two-sided
    handshake substrate)."""
    _write_index(tmp_path, "artifacts: []")
    rc = ra.main(
        ["--feature", "feat", "--artifact", "research", "--project-root", str(tmp_path)]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["protocol"] == PROTOCOL_VERSION


def test_cli_rejects_unknown_artifact(tmp_path) -> None:
    with pytest.raises(SystemExit):
        ra.main(["--feature", "feat", "--artifact", "bogus"])


def test_cli_decode_failure_returns_error_state_and_exits_zero(tmp_path, capsys) -> None:
    """A non-UTF-8 index.md (0xff byte) raises UnicodeDecodeError inside
    register_artifact — which is neither FileNotFoundError nor OSError, so the
    function's own handlers miss it. main's never-crash net must still surface an
    error state at exit 0 rather than a traceback."""
    path = _index_path(tmp_path)
    path.parent.mkdir(parents=True)
    # 0xff is not valid UTF-8 → read_text(encoding="utf-8") raises UnicodeDecodeError.
    path.write_bytes(b"---\nartifacts: [\xff]\n---\n")
    rc = ra.main(
        ["--feature", "feat", "--artifact", "research", "--project-root", str(tmp_path)]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"


def test_cli_never_raises_and_always_exits_zero(monkeypatch, capsys) -> None:
    def _raise():
        raise CortexProjectRootError("no cortex/ found")

    monkeypatch.setattr(ra, "_resolve_user_project_root_from_cwd", _raise)
    rc = ra.main(["--feature", "feat", "--artifact", "research"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
