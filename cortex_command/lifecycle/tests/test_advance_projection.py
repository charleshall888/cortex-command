"""Task 14a — advance's in-repo status projection.

Covers the two safety properties bolted onto Task 14's ``_project_status`` seam:

  * **Monotonic on the status lattice (hazard 4)** — projection only moves a
    feature FORWARD on ``advance._STATUS_RANK``; a strictly-demoting move is
    refused unless a demoting event backs it. The mandatory monotonic-lattice
    unit test (:func:`test_monotonic_demotion_without_demoting_event_refused`)
    pins the refusal; :func:`test_demotion_with_demoting_event_is_written` pins
    the backed-demotion escape.
  * **Archive-shadow guard (hazard 7)** — when an archived duplicate of the
    feature dir shadows the live one, the append path refuses and the projector
    no-ops (:func:`test_archive_shadow_refuses`).

Scope is the cortex-backlog backend only (ADR-0016): an external backend is left
untouched (:func:`test_external_backend_untouched`).

Isolation: tests use a synthetic scratch feature slug and a scaffolded scratch
``cortex/`` tree under ``tmp_path`` — the real ``cortex/backlog/374-*.md`` is
never touched. The single genuine end-to-end write test stubs only
``update_item``'s best-effort index-regen subprocess (so it never runs against
the real repo); every other test captures the ``update_item`` seam and asserts
the decision via its call/no-call plus ``_project_status``'s outcome tag.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from cortex_command.lifecycle import advance as adv
from cortex_command.lifecycle import transition_table as tt

_FEATURE = "scratch-feat"


def _scaffold(tmp_path: Path, backend: str | None = None) -> tuple[Path, Path, Path]:
    """Build a scratch ``cortex/`` tree; return (root, log_path, backlog_dir)."""
    root = tmp_path
    (root / "cortex" / "lifecycle" / _FEATURE).mkdir(parents=True)
    backlog_dir = root / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)
    if backend is not None:
        (root / "cortex" / "lifecycle.config.md").write_text(
            f"---\nbacklog:\n  backend: {backend}\n---\n", encoding="utf-8"
        )
    log_path = root / "cortex" / "lifecycle" / _FEATURE / "events.log"
    log_path.write_text("", encoding="utf-8")
    return root, log_path, backlog_dir


def _write_item(backlog_dir: Path, status: str, item_id: str = "900") -> Path:
    """Write a scratch backlog item with *status*; return its path."""
    p = backlog_dir / f"{item_id}-{_FEATURE}.md"
    p.write_text(
        f"---\ntitle: Scratch feature\nstatus: {status}\n---\n\nBody.\n",
        encoding="utf-8",
    )
    return p


def _capture_update_item(monkeypatch: pytest.MonkeyPatch) -> list:
    """Patch ``advance.update_item`` to capture calls (never touch disk)."""
    calls: list = []
    monkeypatch.setattr(
        adv,
        "update_item",
        lambda item, fields, backlog_dir, session_id=None: calls.append(
            (item, fields, backlog_dir, session_id)
        ),
    )
    return calls


def _status_of(item_path: Path) -> str | None:
    for line in item_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return None


# ---------------------------------------------------------------------------
# Genuine end-to-end forward write (project_root derived from the log path).
# ---------------------------------------------------------------------------


def test_forward_promotion_writes_real_frontmatter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forward projection (backlog → refined on specify→plan) writes the real
    scratch frontmatter. Only update_item's index-regen subprocess is stubbed;
    the root is derived from the standard events.log layout (project_root=None)."""
    root, log_path, backlog_dir = _scaffold(tmp_path)
    item = _write_item(backlog_dir, "backlog")
    # Neutralise update_item's non-fatal index regen so it never runs against the
    # real repo — the frontmatter write itself is exercised for real.
    monkeypatch.setattr(
        "cortex_command.backlog.update_item.subprocess.run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=b""),
    )
    transition = tt.transition_by_id("spec.approved")

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[], project_root=None,
    )

    assert outcome == "wrote:refined"
    assert _status_of(item) == "refined"


# ---------------------------------------------------------------------------
# Monotonic lattice (hazard 4).
# ---------------------------------------------------------------------------


def test_monotonic_demotion_without_demoting_event_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MANDATORY: a projection that would demote status (complete → in_progress)
    with NO demoting event in the log is refused — update_item is never called
    and the frontmatter is untouched."""
    root, log_path, backlog_dir = _scaffold(tmp_path)
    item = _write_item(backlog_dir, "complete")
    calls = _capture_update_item(monkeypatch)
    # to_state=implement projects in_progress (rank 2) < complete (rank 3).
    transition = tt.transition_by_id("plan.branch-mode-approved")

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[{"event": "phase_transition", "to": "implement"}],
        project_root=root,
    )

    assert outcome == "refused:demotion"
    assert calls == []
    assert _status_of(item) == "complete"


def test_demotion_with_demoting_event_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same demoting move IS projected when a demoting event backs it."""
    root, log_path, backlog_dir = _scaffold(tmp_path)
    item = _write_item(backlog_dir, "complete")
    calls = _capture_update_item(monkeypatch)
    transition = tt.transition_by_id("plan.branch-mode-approved")

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[{"event": "lifecycle_cancelled"}], project_root=root,
    )

    assert outcome == "wrote:in_progress"
    assert len(calls) == 1
    assert calls[0][1] == {"status": "in_progress"}


def test_forward_move_needs_no_demoting_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forward move (refined → in_progress) writes with no demoting event."""
    root, log_path, backlog_dir = _scaffold(tmp_path)
    _write_item(backlog_dir, "refined")
    calls = _capture_update_item(monkeypatch)
    transition = tt.transition_by_id("plan.branch-mode-approved")

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[], project_root=root,
    )

    assert outcome == "wrote:in_progress"
    assert calls[0][1] == {"status": "in_progress"}


def test_normalized_current_status_ranks_on_lattice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy current status (``done`` → complete) normalizes before ranking, so
    a lower projection is still caught as a demotion."""
    root, log_path, backlog_dir = _scaffold(tmp_path)
    _write_item(backlog_dir, "done")  # normalize_status → complete (rank 3)
    calls = _capture_update_item(monkeypatch)
    transition = tt.transition_by_id("plan.branch-mode-approved")  # in_progress (2)

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[], project_root=root,
    )

    assert outcome == "refused:demotion"
    assert calls == []


def test_cancelled_projects_abandoned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cancel transition projects the terminal ``abandoned`` (a forward move to
    the top rank from in_progress)."""
    root, log_path, backlog_dir = _scaffold(tmp_path)
    _write_item(backlog_dir, "in_progress")
    calls = _capture_update_item(monkeypatch)
    transition = tt.transition_by_id("plan.cancelled")  # to_state cancelled

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[{"event": "lifecycle_cancelled"}], project_root=root,
    )

    assert outcome == "wrote:abandoned"
    assert calls[0][1] == {"status": "abandoned"}


# ---------------------------------------------------------------------------
# Archive-shadow guard (hazard 7).
# ---------------------------------------------------------------------------


def test_archive_shadow_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MANDATORY: an archived duplicate of the feature dir shadows the live one —
    the append path refuses and the projector no-ops (never writes status)."""
    root, log_path, backlog_dir = _scaffold(tmp_path)
    item = _write_item(backlog_dir, "backlog")
    # Archive shadow at <lifecycle_root>/archive/<feature> (wontfix's destination).
    (root / "cortex" / "lifecycle" / "archive" / _FEATURE).mkdir(parents=True)
    calls = _capture_update_item(monkeypatch)
    transition = tt.transition_by_id("spec.approved")  # would project refined

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[], project_root=root,
    )

    assert outcome == "refused:archive-shadow"
    assert calls == []
    assert _status_of(item) == "backlog"


# ---------------------------------------------------------------------------
# Backend scoping (ADR-0016) and no-op arms.
# ---------------------------------------------------------------------------


def test_external_backend_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-cortex-backlog backend is left untouched (ADR-0016) — no write."""
    root, log_path, backlog_dir = _scaffold(tmp_path, backend="github-issues")
    _write_item(backlog_dir, "backlog")
    calls = _capture_update_item(monkeypatch)
    transition = tt.transition_by_id("spec.approved")

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[], project_root=root,
    )

    assert outcome == "skip:backend"
    assert calls == []


def test_unmapped_to_state_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A to_state with no backlog-status meaning (escalated) projects nothing."""
    root, log_path, backlog_dir = _scaffold(tmp_path)
    _write_item(backlog_dir, "in_progress")
    calls = _capture_update_item(monkeypatch)
    transition = tt.transition_by_id("review.escalated")  # to_state escalated

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[], project_root=root,
    )

    assert outcome == "skip:no-mapping"
    assert calls == []


def test_unresolved_item_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No matching backlog item → silent skip (never a crash)."""
    root, log_path, backlog_dir = _scaffold(tmp_path)  # empty backlog dir
    calls = _capture_update_item(monkeypatch)
    transition = tt.transition_by_id("spec.approved")

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[], project_root=root,
    )

    assert outcome == "skip:not_found"
    assert calls == []


def test_projection_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A projection failure is swallowed (best-effort post-commit side channel)."""
    root, log_path, backlog_dir = _scaffold(tmp_path)
    _write_item(backlog_dir, "backlog")

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(adv, "update_item", _boom)
    transition = tt.transition_by_id("spec.approved")

    outcome = adv._project_status(
        feature=_FEATURE, transition=transition, log_path=log_path,
        rows=[], project_root=root,
    )

    assert outcome == "error"


def test_short_road_approval_still_projects_spec_and_areas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The approved-direct arm (specify→implement short road) must reach the
    spec/areas projection seam exactly as the approved arm does — the seam gates
    on the approval arms, not on the literal "approved" state. Regression pin:
    the seam originally tested decision_state == "approved" only, silently
    skipping the spec: write for every short-roaded feature."""
    root, log_path, backlog_dir = _scaffold(tmp_path)
    item = _write_item(backlog_dir, "backlog")
    (root / "cortex" / "lifecycle" / _FEATURE / "research.md").write_text("r", encoding="utf-8")
    (root / "cortex" / "lifecycle" / _FEATURE / "spec.md").write_text("s", encoding="utf-8")
    monkeypatch.setattr(
        "cortex_command.backlog.update_item.subprocess.run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=b""),
    )
    monkeypatch.chdir(root)

    r = adv.advance(
        verb="spec-approve", feature=_FEATURE, decision="approved",
        emit_transition=True, from_state="specify", log_path=log_path,
        spec_path=f"cortex/lifecycle/{_FEATURE}/spec.md",
        backlog_file=item.name, areas=["lifecycle"], project_root=root,
    )

    # No tier recorded → reducer defaults (simple/medium) → the short road.
    assert r["state"] == "approved-direct" and r["to_state"] == "implement"
    text = item.read_text(encoding="utf-8")
    assert f"spec: cortex/lifecycle/{_FEATURE}/spec.md" in text
    assert "lifecycle" in text
    # Status projected from to_state=implement (in_progress), not plan/refined.
    assert "status: in_progress" in text
