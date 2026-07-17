"""Tests for the clarify_critic events.log schema gate (#186).

The gate validates the v3 counts-only write shape documented in
``skills/refine/references/clarify-critic.md`` §Event Logging — field
presence/typing plus the one invariant that survived the v3 schema:
``dismissals_count == dispositions.dismiss``. Legacy pre-v3 shapes are
readers'-tolerance territory and are skipped, never flagged.
"""

from __future__ import annotations

import json
from pathlib import Path

from cortex_command.lint.clarify_critic_events import check_file, main


def _v3_event(**overrides: object) -> dict:
    """A valid v3 clarify_critic row; ``overrides`` mutate it into violations."""
    event = {
        "schema_version": 3,
        "ts": "2026-07-17T00:00:00Z",
        "event": "clarify_critic",
        "feature": "some-feature",
        "parent_epic_loaded": False,
        "findings_count": 4,
        "dispositions": {"apply": 2, "dismiss": 1, "ask": 1},
        "applied_fixes_count": 2,
        "dismissals_count": 1,
        "status": "ok",
    }
    event.update(overrides)
    return event


def _write_log(tmp_path: Path, *rows: object) -> Path:
    log = tmp_path / "events.log"
    log.write_text(
        "".join(
            (row if isinstance(row, str) else json.dumps(row)) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    return log


def test_valid_v3_event_passes(tmp_path: Path) -> None:
    log = _write_log(tmp_path, _v3_event())
    assert check_file(log) == []
    assert main([str(log)]) == 0


def test_dismissals_invariant_violation_fails_with_pointer(
    tmp_path: Path, capsys
) -> None:
    """The ticket's core check: a count/disposition mismatch fails closed
    with a pointer to the violating line."""
    log = _write_log(
        tmp_path,
        _v3_event(),
        _v3_event(dismissals_count=2),  # dispositions.dismiss is 1
    )
    findings = check_file(log)
    assert len(findings) == 1
    assert findings[0].startswith(f"{log}:2:")
    assert "dismissals_count" in findings[0]
    assert "dispositions.dismiss" in findings[0]

    assert main([str(log)]) == 1
    err = capsys.readouterr().err
    assert f"{log}:2:" in err


def test_missing_and_mistyped_fields_flagged(tmp_path: Path) -> None:
    row = _v3_event(parent_epic_loaded="yes", status="done")
    del row["findings_count"]
    log = _write_log(tmp_path, row)
    findings = check_file(log)
    joined = "\n".join(findings)
    assert "parent_epic_loaded" in joined
    assert "findings_count" in joined
    assert "status" in joined


def test_failed_status_event_with_zero_counts_is_valid(tmp_path: Path) -> None:
    """The documented failure-handling shape (status: failed, all-zero counts)
    satisfies the gate."""
    log = _write_log(
        tmp_path,
        _v3_event(
            status="failed",
            findings_count=0,
            applied_fixes_count=0,
            dismissals_count=0,
            dispositions={"apply": 0, "dismiss": 0, "ask": 0},
        ),
    )
    assert check_file(log) == []


def test_legacy_shapes_and_foreign_lines_skipped(tmp_path: Path) -> None:
    """Pre-v3 rows (tolerated forever), other events, and non-JSON lines are
    out of scope — the gate never flags history it postdates."""
    legacy_v1 = {
        "event": "clarify_critic",
        "feature": "old",
        "findings_count": 3,
        # v1 carried no schema_version, no dispositions — must not flag.
    }
    legacy_v2 = _v3_event(schema_version=2, dismissals_count=9)
    other_event = {"event": "phase_transition", "from": "clarify", "to": "research"}
    log = _write_log(
        tmp_path,
        legacy_v1,
        legacy_v2,
        other_event,
        "not json at all {",
    )
    assert check_file(log) == []
    assert main([str(log)]) == 0


def test_sweep_covers_lifecycle_tree(tmp_path: Path) -> None:
    """No explicit paths → every events.log under cortex/lifecycle (archive
    included) is swept."""
    live = tmp_path / "cortex" / "lifecycle" / "feat-a"
    archived = tmp_path / "cortex" / "lifecycle" / "archive" / "feat-b"
    live.mkdir(parents=True)
    archived.mkdir(parents=True)
    (live / "events.log").write_text(
        json.dumps(_v3_event()) + "\n", encoding="utf-8"
    )
    (archived / "events.log").write_text(
        json.dumps(_v3_event(dismissals_count=5)) + "\n", encoding="utf-8"
    )
    assert main(["--root", str(tmp_path)]) == 1


def test_repo_audit_is_clean() -> None:
    """The gate holds over this repo's own recorded history — the continuous
    enforcement the ticket asked for, wired through the test suite."""
    repo_root = Path(__file__).resolve().parent.parent
    assert main(["--root", str(repo_root)]) == 0
