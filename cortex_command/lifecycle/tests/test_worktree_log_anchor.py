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

import io
import json
from pathlib import Path

import pytest

from cortex_command import lifecycle_event
from cortex_command.hooks import scan_lifecycle
from cortex_command.lifecycle import complete_route, log_resolver, review_brief
from cortex_command.lifecycle import record_pr_opened as rpo

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


# --- writer → reader, across verbs (#487) ------------------------------------
#
# The two cases below are the ones no single-module test can express: each
# drives a *writer* from the worktree CWD and then asks a *different* verb,
# reading the same lifecycle, what it sees. #484 anchored the writers; a reader
# left on the CWD walk turns an anchored write into a silently empty read.


def test_finalize_event_from_a_worktree_is_visible_to_the_complete_route(
    worktree,
) -> None:
    """The row ``finalize`` writes is the row ``complete-route`` classifies on.

    ``finalize.py:198`` emits ``feature_complete`` through
    ``lifecycle_event.log_event``, which lands at the main root. While
    ``complete_route`` resolved its own artifacts from the CWD walk, a
    worktree finalization left the route reading an empty log — and "no
    events.log, no pr.json" is indistinguishable from a fresh lifecycle, which
    is how a feature with an open PR reached ``on_main``/step9 and was
    silently completed unmerged.
    """
    main, wt = worktree

    # Verbatim finalize.py:198-207, including the merge_anchor field.
    lifecycle_event.log_event(
        event="feature_complete",
        feature=_SLUG,
        fields=[
            ("json", "tasks_total", 3),
            ("json", "rework_cycles", 0),
            ("str", "merge_anchor", "merge"),
        ],
    )
    main_log = main / "cortex" / "lifecycle" / _SLUG / "events.log"
    assert [r["event"] for r in _rows(main_log)] == ["feature_complete"]

    # *root* is what ``complete_route.main`` resolves from this CWD — the
    # worktree. The artifacts must still resolve to the main root.
    verdict = complete_route.classify(_SLUG, wt)

    assert verdict["route"] == "already_complete"
    assert verdict["continue_to"] == "step12"


def test_pr_opened_from_a_worktree_promotes_the_main_root_session_scan(
    worktree, monkeypatch, capsys
) -> None:
    """The relocated ``pr_opened`` row reaches its downstream consumer.

    ``record_pr_opened`` now writes both artifacts at the main root, which
    moves the ``pr_opened`` row out of the worktree copy. ``scan_lifecycle``
    is strictly CWD-anchored (``lifecycle_dir = cwd / "cortex" / "lifecycle"``)
    and gates the ``complete`` → ``complete:awaiting-merge`` promotion on that
    row, so a main-root session now sees the awaiting-merge state it used to
    miss — the feature was previously filtered out entirely as complete-no-PR.

    The worktree half is pinned by the sibling test below (#494).
    """
    main, wt = worktree
    main_dir = main / "cortex" / "lifecycle" / _SLUG

    # A lifecycle that reached Complete: the machine row events-first phase
    # resolution reads, with no terminal event yet.
    (main_dir / "events.log").write_text(
        json.dumps(
            {
                "ts": "2026-08-13T12:00:00Z",
                "event": "phase_transition",
                "feature": _SLUG,
                "from": "review",
                "to": "complete",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(rpo, "_gh_repo", lambda: "owner/repo")
    monkeypatch.setattr(
        rpo,
        "_gh_pr_view",
        lambda number, repo: {
            "url": "https://github.com/owner/repo/pull/42",
            "head_branch": f"interactive/{_SLUG}",
        },
    )
    assert rpo.record_pr_opened(_SLUG, 42, project_root=None)["state"] == "ok"
    assert "pr_opened" in [r["event"] for r in _rows(main_dir / "events.log")]

    # A SessionStart scan for a session sitting at the main root.
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(main / ".claude-env"))
    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "sess-487", "cwd": str(main)})),
    )

    assert scan_lifecycle.main() == 0

    out = capsys.readouterr().out
    assert out, "the feature was filtered out of the scan entirely (complete-no-PR)"
    hook_output = json.loads(out)["hookSpecificOutput"]
    assert hook_output["sessionTitle"] == _SLUG
    # ``complete:awaiting-merge``, rendered — not filtered out as complete-no-PR.
    assert "Complete (awaiting merge)" in hook_output["additionalContext"]


def test_a_worktree_session_reads_the_badge_from_the_main_root_log(
    worktree, monkeypatch, capsys
) -> None:
    """#494: the badge follows the pinned log, not the worktree's stale copy.

    ``scan_lifecycle`` enumerates lifecycle *directories* from the payload cwd,
    which is right — they are tracked artifacts. Its ``events.log`` reads were
    anchored the same way, which is wrong: post-#484 no verb writes there. A
    worktree session therefore resolved phase and the ``pr_opened`` promotion
    from a committed snapshot, and the awaiting-merge badge never appeared.

    The worktree copy here carries a *contradicting* row — ``feature_complete``,
    which suppresses the promotion — so reading the right file is the only way
    the badge can render.
    """
    main, wt = worktree
    main_dir = main / "cortex" / "lifecycle" / _SLUG
    wt_dir = wt / "cortex" / "lifecycle" / _SLUG
    wt_dir.mkdir(parents=True, exist_ok=True)

    def _row(**kw):
        return json.dumps({"ts": "2026-08-13T12:00:00Z", "feature": _SLUG, **kw}) + "\n"

    (main_dir / "events.log").write_text(
        _row(event="phase_transition", **{"from": "review", "to": "complete"})
        + _row(event="pr_opened", pr_number=42),
        encoding="utf-8",
    )
    # The stale committed snapshot the worktree still carries.
    (wt_dir / "events.log").write_text(
        _row(event="phase_transition", **{"from": "review", "to": "complete"})
        + _row(event="feature_complete"),
        encoding="utf-8",
    )

    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(wt / ".claude-env"))
    monkeypatch.setenv("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "0")
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"session_id": "sess-494", "cwd": str(wt)})),
    )

    assert scan_lifecycle.main() == 0

    out = capsys.readouterr().out
    assert out, "the worktree session was filtered out entirely"
    hook_output = json.loads(out)["hookSpecificOutput"]
    assert "Complete (awaiting merge)" in hook_output["additionalContext"]
