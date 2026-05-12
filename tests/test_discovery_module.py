"""Unit tests for ``cortex_command.discovery`` (spec R9 Task 6).

Covers, per spec R9 acceptance:

  (i)   each emit-* subcommand's validation + emission
  (ii)  ``resolve-events-log-path`` honors the ``-N`` re-run slug suffix
  (iii) ``resolve-events-log-path`` honors the active-lifecycle env override
  (iv)  emit-* subcommands invoke ``resolve-events-log-path`` rather than
        hardcoding ``research/{topic}/events.log``

Each scenario is its own ``def test_*`` for granular failure reporting.
The test count is >= 7 per the spec acceptance bar.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.discovery import (
    emit_architecture_written,
    emit_checkpoint_response,
    emit_prescriptive_check,
    resolve_events_log_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """A bare tmp repo root with empty research/ and lifecycle/ subdirs."""
    (tmp_path / "research").mkdir()
    (tmp_path / "lifecycle").mkdir()
    return tmp_path


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


# ---------------------------------------------------------------------------
# (ii) resolve-events-log-path honors -N slug suffix per R13
# ---------------------------------------------------------------------------


def test_resolve_path_plain_slug_routes_to_research_topic(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    target = resolve_events_log_path("plugin-system", repo_root)
    assert target == repo_root / "research" / "plugin-system" / "events.log"


def test_resolve_path_n_suffix_keeps_n_in_slug(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R13: re-run slug ``foo-2`` writes to ``research/foo-2/events.log``.

    The resolver must NOT strip the ``-N`` suffix; downstream consumers
    expect the suffixed directory.
    """
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    target = resolve_events_log_path("plugin-system-2", repo_root)
    assert target == repo_root / "research" / "plugin-system-2" / "events.log"
    # And N >= 3 path:
    target3 = resolve_events_log_path("plugin-system-7", repo_root)
    assert target3 == repo_root / "research" / "plugin-system-7" / "events.log"


# ---------------------------------------------------------------------------
# (iii) resolve-events-log-path honors active-lifecycle env override
# ---------------------------------------------------------------------------


def test_resolve_path_active_lifecycle_overrides_topic(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When LIFECYCLE_SESSION_ID matches a lifecycle/<slug>/.session file,
    events route to ``lifecycle/<slug>/events.log`` per EVT-1, regardless
    of the topic slug shape.
    """
    feature_dir = repo_root / "lifecycle" / "some-active-feature"
    feature_dir.mkdir()
    (feature_dir / ".session").write_text("sess-abc-123", encoding="utf-8")
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "sess-abc-123")

    target = resolve_events_log_path("standalone-topic", repo_root)
    assert target == feature_dir / "events.log"


def test_resolve_path_active_lifecycle_matches_via_session_owner(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SessionStart hook chain-migrates via ``.session-owner`` after
    ``/clear``; the resolver must also recognize ``.session-owner`` as a
    valid match marker for the original stale session id.
    """
    feature_dir = repo_root / "lifecycle" / "migrated-feature"
    feature_dir.mkdir()
    # Fresh .session has the NEW id; .session-owner holds the original.
    (feature_dir / ".session").write_text("new-session-id", encoding="utf-8")
    (feature_dir / ".session-owner").write_text(
        "original-stale-id", encoding="utf-8"
    )
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "original-stale-id")

    target = resolve_events_log_path("any-topic", repo_root)
    assert target == feature_dir / "events.log"


def test_resolve_path_env_unset_falls_back_to_research(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unset env var must NOT match an empty .session file."""
    feature_dir = repo_root / "lifecycle" / "orphan-feature"
    feature_dir.mkdir()
    (feature_dir / ".session").write_text("", encoding="utf-8")
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)

    target = resolve_events_log_path("topic-foo", repo_root)
    assert target == repo_root / "research" / "topic-foo" / "events.log"


# ---------------------------------------------------------------------------
# (i) emit-* validation + emission
# ---------------------------------------------------------------------------


def test_emit_architecture_written_writes_jsonl(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    target = emit_architecture_written(
        topic="my-topic",
        piece_count=9,
        has_why_n_justification=True,
        status="approved",
        repo_root=repo_root,
        re_walk_attempt=1,
    )
    assert target == repo_root / "research" / "my-topic" / "events.log"
    events = _read_jsonl(target)
    assert len(events) == 1
    ev = events[0]
    assert ev["event"] == "architecture_section_written"
    assert ev["topic"] == "my-topic"
    assert ev["piece_count"] == 9
    assert ev["has_why_n_justification"] is True
    assert ev["status"] == "approved"
    assert ev["re_walk_attempt"] == 1
    assert "ts" in ev


def test_emit_architecture_written_validation_rejects_negative_piece_count(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    with pytest.raises(ValueError, match="piece_count"):
        emit_architecture_written(
            topic="my-topic",
            piece_count=-1,
            has_why_n_justification=False,
            status="draft",
            repo_root=repo_root,
        )


def test_emit_checkpoint_response_writes_jsonl_and_validates_response(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    target = emit_checkpoint_response(
        topic="my-topic",
        checkpoint="research-decompose",
        response="approve",
        revision_round=0,
        repo_root=repo_root,
    )
    events = _read_jsonl(target)
    assert len(events) == 1
    ev = events[0]
    assert ev["event"] == "approval_checkpoint_responded"
    assert ev["checkpoint"] == "research-decompose"
    assert ev["response"] == "approve"
    assert ev["revision_round"] == 0

    # Invalid response value is rejected.
    with pytest.raises(ValueError, match="response"):
        emit_checkpoint_response(
            topic="my-topic",
            checkpoint="research-decompose",
            response="bogus-response",
            revision_round=0,
            repo_root=repo_root,
        )

    # Invalid checkpoint value is rejected.
    with pytest.raises(ValueError, match="checkpoint"):
        emit_checkpoint_response(
            topic="my-topic",
            checkpoint="bogus-checkpoint",
            response="approve",
            revision_round=0,
            repo_root=repo_root,
        )


def test_emit_prescriptive_check_writes_nested_flag_locations(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    flag_locations = [
        {"ticket": "210", "section": "Edges", "signal": "path:line"},
        {"ticket": "210", "section": "Integration", "signal": "section-index"},
    ]
    target = emit_prescriptive_check(
        topic="my-topic",
        tickets_checked=3,
        flagged_count=2,
        flag_locations=flag_locations,
        repo_root=repo_root,
    )
    events = _read_jsonl(target)
    assert len(events) == 1
    ev = events[0]
    assert ev["event"] == "prescriptive_check_run"
    assert ev["tickets_checked"] == 3
    assert ev["flagged_count"] == 2
    assert ev["flag_locations"] == flag_locations


def test_emit_prescriptive_check_rejects_malformed_flag_locations(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    # Missing the 'signal' key.
    with pytest.raises(ValueError, match="signal"):
        emit_prescriptive_check(
            topic="my-topic",
            tickets_checked=1,
            flagged_count=1,
            flag_locations=[{"ticket": "210", "section": "Edges"}],
            repo_root=repo_root,
        )
    # Non-list payload.
    with pytest.raises(ValueError, match="flag_locations"):
        emit_prescriptive_check(
            topic="my-topic",
            tickets_checked=1,
            flagged_count=1,
            flag_locations="not-a-list",  # type: ignore[arg-type]
            repo_root=repo_root,
        )


# ---------------------------------------------------------------------------
# (iv) emit-* subcommands route through resolve-events-log-path, NOT a
#      hardcoded research/{topic}/events.log path. We assert this by
#      activating the lifecycle env override and verifying every emit-*
#      writes to the lifecycle/<slug>/events.log target.
# ---------------------------------------------------------------------------


def test_emit_subcommands_honor_resolve_events_log_path(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the emit-* helpers hardcoded ``research/{topic}/events.log``, an
    active-lifecycle env override would NOT redirect their output. This
    test fails any such hardcode by activating the env override and
    asserting all three emit-* targets resolve under ``lifecycle/<slug>/``.
    """
    feature_dir = repo_root / "lifecycle" / "active-feature"
    feature_dir.mkdir()
    (feature_dir / ".session").write_text("active-id", encoding="utf-8")
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "active-id")

    arch_target = emit_architecture_written(
        topic="some-topic",
        piece_count=1,
        has_why_n_justification=False,
        status="draft",
        repo_root=repo_root,
    )
    chk_target = emit_checkpoint_response(
        topic="some-topic",
        checkpoint="research-decompose",
        response="approve",
        revision_round=0,
        repo_root=repo_root,
    )
    pre_target = emit_prescriptive_check(
        topic="some-topic",
        tickets_checked=0,
        flagged_count=0,
        flag_locations=[],
        repo_root=repo_root,
    )

    # All three write to the SAME lifecycle events.log -- proves the path
    # is shared via resolve_events_log_path and not derived per-emitter.
    expected = feature_dir / "events.log"
    assert arch_target == expected
    assert chk_target == expected
    assert pre_target == expected

    # And NOT to research/some-topic/events.log.
    standalone = repo_root / "research" / "some-topic" / "events.log"
    assert not standalone.exists()

    # All three events landed in the lifecycle log.
    events = _read_jsonl(expected)
    assert len(events) == 3
    names = {e["event"] for e in events}
    assert names == {
        "architecture_section_written",
        "approval_checkpoint_responded",
        "prescriptive_check_run",
    }


# ---------------------------------------------------------------------------
# CLI smoke tests (the four subcommands are addressable end-to-end)
# ---------------------------------------------------------------------------


def test_cli_help_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "cortex_command.discovery", "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    for sub in (
        "resolve-events-log-path",
        "emit-architecture-written",
        "emit-checkpoint-response",
        "emit-prescriptive-check",
    ):
        assert sub in proc.stdout


def test_cli_resolve_events_log_path_standalone_topic(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cortex_command.discovery",
            "resolve-events-log-path",
            "--repo-root",
            str(repo_root),
            "--topic",
            "my-topic",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(
        repo_root / "research" / "my-topic" / "events.log"
    )


def test_cli_emit_architecture_written_appends_event(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cortex_command.discovery",
            "emit-architecture-written",
            "--repo-root",
            str(repo_root),
            "--topic",
            "cli-topic",
            "--piece-count",
            "3",
            "--has-why-n-justification",
            "false",
            "--status",
            "approved",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    events_log = repo_root / "research" / "cli-topic" / "events.log"
    events = _read_jsonl(events_log)
    assert len(events) == 1
    assert events[0]["event"] == "architecture_section_written"
    assert events[0]["has_why_n_justification"] is False
