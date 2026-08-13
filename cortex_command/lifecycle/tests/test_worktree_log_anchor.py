"""#484: every appending lifecycle verb resolves ONE events.log, and says which.

The observed failure ran a whole lifecycle from a git worktree. ``next`` and
``advance`` used the main root (``advance_contract.anchor: main-root``) while
``cortex-lifecycle-event`` and ``cortex-lifecycle-review-brief`` used the CWD, so
the history split across two plausible-looking files and **nothing reported it**:
three closing events landed in the worktree copy while the authoritative log
still ended at ``escalated``, and a cycle-2 review brief derived "cycle 1" from
the worktree's stale committed log.

These tests drive the two CWD-anchored verbs from a worktree CWD and assert the
main-root log is the one that grows. The worktree gitfile/``commondir`` fixture
is hand-built for the same reason ``test_log_resolver`` builds one — ``git
rev-parse`` exits 128 against a synthetic worktree (#271).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command import lifecycle_event
from cortex_command.lifecycle import log_resolver, review_brief

_SLUG = "wet-sand-darkening-on-the-terrain"


def _worktree_fixture(root: Path) -> tuple[Path, Path]:
    """Main repo + linked worktree, each with a co-located ``cortex/`` tree."""
    root = root.resolve()
    main, wt = root / "main", root / "wt"

    admin = main / ".git" / "worktrees" / "wt1"
    admin.mkdir(parents=True)
    (admin / "commondir").write_text("../..\n", encoding="utf-8")
    (main / "cortex" / "lifecycle" / _SLUG).mkdir(parents=True)

    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (wt / "cortex" / "lifecycle" / _SLUG).mkdir(parents=True)
    return main, wt


def _rows(log: Path) -> list[dict]:
    if not log.is_file():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture
def worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    main, wt = _worktree_fixture(tmp_path)
    monkeypatch.chdir(wt)
    return main, wt


# --- the event writer --------------------------------------------------------

def test_event_append_from_a_worktree_lands_in_the_main_root_log(
    worktree, capsys
) -> None:
    """The closing events reach the log ``next``/``advance`` read.

    This is failure 2 verbatim: ``phase-transition`` and ``feature-complete``
    run from a worktree appended to the worktree copy, so the authoritative log
    still ended at ``escalated`` and the three events had to be re-run by hand.
    """
    code = lifecycle_event._run(
        ["log", "--event", "feature_complete", "--feature", _SLUG]
    )
    assert code == 0

    main, wt = worktree
    main_log = main / "cortex" / "lifecycle" / _SLUG / "events.log"
    wt_log = wt / "cortex" / "lifecycle" / _SLUG / "events.log"

    assert [r["event"] for r in _rows(main_log)] == ["feature_complete"]
    assert not wt_log.exists(), "the worktree copy must not be written at all"


def test_event_append_names_the_file_it_wrote(worktree, capsys) -> None:
    """Silence was the sharpest part of the bug: both failures printed nothing."""
    main, _ = worktree
    lifecycle_event._run(["log", "--event", "escalated", "--feature", _SLUG])

    err = capsys.readouterr().err
    expected = str(main / "cortex" / "lifecycle" / _SLUG / "events.log")
    assert expected in err
    assert "escalated" in err


def test_event_append_warns_when_a_divergent_log_already_exists(
    worktree, capsys
) -> None:
    """An already-forked lifecycle is named, not silently bypassed."""
    main, wt = worktree
    stale = wt / "cortex" / "lifecycle" / _SLUG / "events.log"
    stale.write_text('{"event": "phase_transition"}\n', encoding="utf-8")

    lifecycle_event._run(["log", "--event", "feature_complete", "--feature", _SLUG])

    err = capsys.readouterr().err
    assert "WARNING" in err
    assert str(stale) in err
    assert "split" in err
    # The stale copy is reported, never repaired or written to.
    assert [r["event"] for r in _rows(stale)] == ["phase_transition"]


# --- the review brief --------------------------------------------------------

def _review(cycle: int, issue: str) -> str:
    return "\n".join(
        [
            f"# Review — cycle {cycle}",
            "",
            "```json",
            json.dumps(
                {
                    "verdict": "CHANGES_REQUESTED",
                    "cycle": cycle,
                    "issues": [issue],
                    "requirements_drift": "none",
                }
            ),
            "```",
            "",
        ]
    )


def test_review_brief_derives_its_cycle_from_the_main_root_log(
    worktree, capsys
) -> None:
    """Failure 1: a cycle-2 dispatch was labelled cycle 1 off the stale copy.

    The worktree's log is the *committed* one, so it lags by exactly the rows
    the live phase just wrote — here zero ``review_verdict`` rows against the
    authoritative log's one. Deriving the cycle from it under-counts, and the
    cycle drives both the archive and the rework/full mode selection.
    """
    main, wt = worktree
    main_dir = main / "cortex" / "lifecycle" / _SLUG
    wt_dir = wt / "cortex" / "lifecycle" / _SLUG

    (main_dir / "events.log").write_text(
        json.dumps(
            {"event": "review_verdict", "feature": _SLUG, "verdict": "CHANGES_REQUESTED"}
        )
        + "\n"
        + json.dumps(
            {
                "event": "review_dispatched",
                "feature": _SLUG,
                "cycle": 1,
                "mode": "full",
                "baseline_sha": "0" * 40,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (wt_dir / "events.log").write_text("", encoding="utf-8")  # stale committed copy
    (wt_dir / "review.md").write_text(_review(1, "the defect cycle 1 caught"), encoding="utf-8")

    code = review_brief.main(["--feature", _SLUG])
    captured = capsys.readouterr()

    # cycle 2, not cycle 1 — the whole point.
    assert "cycle 2" in captured.out
    assert "cycle 1 " not in captured.err
    assert code in (0, 3)  # scoped when the baseline resolves, degraded otherwise


def test_review_brief_archives_the_prior_review_before_serving(
    worktree, capsys
) -> None:
    """The cycle-1 findings survive the dispatch that would overwrite them."""
    main, wt = worktree
    main_dir = main / "cortex" / "lifecycle" / _SLUG
    wt_dir = wt / "cortex" / "lifecycle" / _SLUG

    (main_dir / "events.log").write_text(
        json.dumps(
            {"event": "review_verdict", "feature": _SLUG, "verdict": "CHANGES_REQUESTED"}
        )
        + "\n",
        encoding="utf-8",
    )
    original = _review(1, "the defect cycle 1 caught")
    (wt_dir / "review.md").write_text(original, encoding="utf-8")

    review_brief.main(["--feature", _SLUG])

    # Archived beside the artifact, in the worktree where the reviewer writes it.
    assert (wt_dir / "review-cycle-1.md").read_text(encoding="utf-8") == original
    assert (wt_dir / "review.md").read_text(encoding="utf-8") == original


def test_review_brief_reports_the_log_it_read(worktree, capsys) -> None:
    """A caller could not detect the fault from the brief alone (#485)."""
    main, _ = worktree
    review_brief.main(["--feature", _SLUG])

    err = capsys.readouterr().err
    assert str(main / "cortex" / "lifecycle" / _SLUG / "events.log") in err
    assert "cycle 1" in err
