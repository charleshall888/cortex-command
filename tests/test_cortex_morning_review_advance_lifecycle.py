"""Tests for cortex-morning-review-advance-lifecycle — the morning-review
walkthrough §2b per-feature lifecycle-advancement façade (checkbox counting,
the tier/criticality review gate, and the synthetic events.log appends).

``advance_lifecycle()`` reads real events.log/plan.md files under a tmp
project root and calls the real ``log_event`` writer (also against that tmp
root, via ``LIFECYCLE_SESSION_ID``-independent CWD resolution) — so these
tests chdir into the tmp root rather than monkeypatching ``log_event``,
since ``log_event`` resolves its own path internally with no override hook.
Assertions read back the appended rows from the real events.log, following
the ``test_prepare_worktree.py`` precedent of pinning the discriminated
``state`` + payload for every branch.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cortex_command.overnight import advance_lifecycle as al


def _feature_dir(root: Path, feature: str = "feat") -> Path:
    d = root / "cortex" / "lifecycle" / feature
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_events(feature_dir: Path, lines: list[dict]) -> Path:
    path = feature_dir / "events.log"
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return path


def _read_events(feature_dir: Path) -> list[dict]:
    path = feature_dir / "events.log"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture()
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """chdir into a fresh tmp project root — log_event() resolves via CWD."""
    (tmp_path / "cortex").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_no_lifecycle_dir(project_root: Path) -> None:
    r = al.advance_lifecycle("ghost", project_root=project_root)
    assert r == {"state": "no-lifecycle-dir"}


def test_already_complete_skips(project_root: Path) -> None:
    fd = _feature_dir(project_root)
    _write_events(fd, [{"event": "feature_complete", "feature": "feat"}])
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r == {"state": "already-complete"}
    # Nothing new appended.
    assert len(_read_events(fd)) == 1


def test_simple_medium_advances_with_four_events(project_root: Path) -> None:
    fd = _feature_dir(project_root)
    _write_events(
        fd,
        [{"event": "lifecycle_start", "feature": "feat", "tier": "simple", "criticality": "medium"}],
    )
    (fd / "plan.md").write_text(
        "- **Status**: [x] done\n- **Status**: [ ] todo\n- **Status**: [x] done\n"
    )
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "advanced-complete"
    assert r["tasks_total"] == 3
    assert r["rework_cycles"] == 0

    events = _read_events(fd)
    # 1 seed + 4 synthetic.
    assert len(events) == 5
    new_events = events[1:]
    assert [e["event"] for e in new_events] == [
        "phase_transition",
        "review_verdict",
        "phase_transition",
        "feature_complete",
    ]
    assert new_events[0]["from"] == "implement"
    assert new_events[0]["to"] == "review"
    assert new_events[1]["verdict"] == "APPROVED"
    assert new_events[1]["cycle"] == 0
    assert new_events[2]["from"] == "review"
    assert new_events[2]["to"] == "complete"
    assert new_events[3]["tasks_total"] == 3
    assert new_events[3]["rework_cycles"] == 0
    for e in new_events:
        assert e["feature"] == "feat"
        assert "ts" in e


def test_missing_plan_defaults_tasks_total_to_zero(project_root: Path) -> None:
    fd = _feature_dir(project_root)
    _write_events(
        fd,
        [{"event": "lifecycle_start", "feature": "feat", "tier": "simple", "criticality": "low"}],
    )
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "advanced-complete"
    assert r["tasks_total"] == 0


@pytest.mark.parametrize(
    "tier,criticality",
    [("complex", "low"), ("complex", "medium"), ("simple", "high"), ("simple", "critical")],
)
def test_review_required_tiers_gate(project_root: Path, tier: str, criticality: str) -> None:
    fd = _feature_dir(project_root)
    _write_events(
        fd,
        [{"event": "lifecycle_start", "feature": "feat", "tier": tier, "criticality": criticality}],
    )
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "missing-review"
    assert _read_events(fd) == [
        {"event": "lifecycle_start", "feature": "feat", "tier": tier, "criticality": criticality}
    ]


def test_default_tier_and_criticality_when_absent(project_root: Path) -> None:
    """No lifecycle_start event at all: defaults to simple/medium -> no review required."""
    fd = _feature_dir(project_root)
    _write_events(fd, [{"event": "some_other_event", "feature": "feat"}])
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "advanced-complete"


def test_crash_recovery_appends_two_events(project_root: Path) -> None:
    fd = _feature_dir(project_root)
    _write_events(
        fd,
        [
            {"event": "lifecycle_start", "feature": "feat", "tier": "complex", "criticality": "medium"},
            {"event": "review_verdict", "feature": "feat", "verdict": "CHANGES_REQUESTED", "cycle": 1},
            {"event": "review_verdict", "feature": "feat", "verdict": "APPROVED", "cycle": 2},
        ],
    )
    (fd / "plan.md").write_text("- **Status**: [x] done\n- **Status**: [x] done\n")
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "advanced-crash-recovery"
    assert r["tasks_total"] == 2
    assert r["rework_cycles"] == 1

    events = _read_events(fd)
    assert len(events) == 5  # 3 seed + 2 synthetic
    new_events = events[3:]
    assert [e["event"] for e in new_events] == ["phase_transition", "feature_complete"]
    assert new_events[0]["from"] == "review"
    assert new_events[0]["to"] == "complete"
    assert new_events[1]["tasks_total"] == 2
    assert new_events[1]["rework_cycles"] == 1


def test_missing_review_writes_nothing(project_root: Path) -> None:
    fd = _feature_dir(project_root)
    seed = [{"event": "lifecycle_start", "feature": "feat", "tier": "complex", "criticality": "medium"}]
    _write_events(fd, seed)
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r == {"state": "missing-review"}
    assert _read_events(fd) == seed


def test_synthetic_cycle_zero_does_not_count_as_real_review(project_root: Path) -> None:
    """A prior run's own synthetic cycle:0 APPROVED must not satisfy the
    'real review' check for the required-review path (regression guard for
    the cycle >= 1 boundary)."""
    fd = _feature_dir(project_root)
    _write_events(
        fd,
        [
            {"event": "lifecycle_start", "feature": "feat", "tier": "complex", "criticality": "medium"},
            {"event": "review_verdict", "feature": "feat", "verdict": "APPROVED", "cycle": 0},
        ],
    )
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "missing-review"


def test_malformed_line_is_skipped_not_fatal(project_root: Path) -> None:
    fd = _feature_dir(project_root)
    path = fd / "events.log"
    path.write_text(
        '{"event": "lifecycle_start", "feature": "feat", "tier": "simple", "criticality": "medium"}\n'
        "not-json-at-all\n"
    )
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "advanced-complete"


def test_every_state_is_known(project_root: Path) -> None:
    seen = set()

    seen.add(al.advance_lifecycle("ghost", project_root=project_root)["state"])

    fd1 = _feature_dir(project_root, "f1")
    _write_events(fd1, [{"event": "feature_complete", "feature": "f1"}])
    seen.add(al.advance_lifecycle("f1", project_root=project_root)["state"])

    fd2 = _feature_dir(project_root, "f2")
    _write_events(
        fd2, [{"event": "lifecycle_start", "feature": "f2", "tier": "simple", "criticality": "low"}]
    )
    seen.add(al.advance_lifecycle("f2", project_root=project_root)["state"])

    fd3 = _feature_dir(project_root, "f3")
    _write_events(
        fd3,
        [{"event": "lifecycle_start", "feature": "f3", "tier": "complex", "criticality": "medium"}],
    )
    seen.add(al.advance_lifecycle("f3", project_root=project_root)["state"])

    fd4 = _feature_dir(project_root, "f4")
    _write_events(
        fd4,
        [
            {"event": "lifecycle_start", "feature": "f4", "tier": "complex", "criticality": "medium"},
            {"event": "review_verdict", "feature": "f4", "verdict": "APPROVED", "cycle": 1},
        ],
    )
    seen.add(al.advance_lifecycle("f4", project_root=project_root)["state"])

    assert seen <= set(al.KNOWN_STATES)
    assert seen == {
        "no-lifecycle-dir",
        "already-complete",
        "advanced-complete",
        "missing-review",
        "advanced-crash-recovery",
    }


def test_cli_emits_json(project_root: Path, capsys) -> None:
    fd = _feature_dir(project_root)
    _write_events(
        fd,
        [{"event": "lifecycle_start", "feature": "feat", "tier": "simple", "criticality": "medium"}],
    )
    rc = al.main(["--feature", "feat"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "advanced-complete"


def test_cli_exits_0_with_error_state_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def _boom(feature, project_root=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(al, "advance_lifecycle", _boom)
    rc = al.main(["--feature", "feat"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "boom" in obj["message"]
