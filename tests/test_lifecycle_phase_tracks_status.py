"""#378 req-5 — ``lifecycle_phase`` tracks ``status`` at completion.

Before this fix the ``status: complete`` writers advanced ``status`` but never
``lifecycle_phase``, so a completed item stayed frozen at its prior phase (e.g.
``research``). These tests drive an item to ``status: complete`` through BOTH
completion writers and assert the paired ``lifecycle_phase`` advances to
``complete``:

  * the finalize path (:func:`cortex_command.lifecycle.finalize.finalize`, the
    unconditional Complete-phase writer), and
  * the served-loop ``review→complete`` path
    (:func:`cortex_command.lifecycle.advance._project_status`, the events-first
    status/phase projection).

A third test pins the derive-not-blindly guard: a cancel transition
(``to_state`` ``cancelled``, ``status`` ``abandoned``) must NOT be mislabelled
``lifecycle_phase: complete`` — the phase is derived from the committed
transition, not written whenever the projector runs.

Isolation: each test scaffolds a throwaway ``cortex/`` tree under ``tmp_path``
and stubs ``update_item``'s best-effort index-regen subprocess so it never runs
against the real repo; the frontmatter write itself is exercised for real.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from cortex_command.lifecycle import advance as adv
from cortex_command.lifecycle import finalize as fin
from cortex_command.lifecycle import transition_table as tt


def _stub_index_regen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise ``update_item``'s non-fatal index-regen subprocess so it never
    runs against the real repo — the frontmatter write itself stays real."""
    monkeypatch.setattr(
        "cortex_command.backlog.update_item.subprocess.run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=b""),
    )


def _read_frontmatter(item_path: Path) -> dict[str, str]:
    """Parse the item's flat scalar frontmatter into a ``{key: value}`` dict."""
    out: dict[str, str] = {}
    lines = item_path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return out
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip().strip("\"'")
    return out


# ---------------------------------------------------------------------------
# Finalize path — the unconditional Complete-phase writer.
# ---------------------------------------------------------------------------


def test_finalize_advances_lifecycle_phase_to_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The finalize write-back sets ``status: complete`` AND advances
    ``lifecycle_phase`` from ``research`` to ``complete`` in the same write."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    (tmp_path / "cortex" / "lifecycle" / "feat").mkdir(parents=True)
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)
    item = backlog_dir / "326-feat.md"
    item.write_text(
        "---\ntitle: Feat\nstatus: refined\nlifecycle_phase: research\n---\n\nBody.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    _stub_index_regen(monkeypatch)

    r = fin.finalize(feature="feat", backend="cortex-backlog", backlog_file="326-feat.md")

    assert r["backlog"] == "updated"
    fm = _read_frontmatter(item)
    assert fm["status"] == "complete"
    assert fm["lifecycle_phase"] != "research"
    assert fm["lifecycle_phase"] == "complete"


# ---------------------------------------------------------------------------
# Served-loop review→complete path — advance's status/phase projection.
# ---------------------------------------------------------------------------


def _scaffold_advance(tmp_path: Path, status: str) -> tuple[Path, Path, Path]:
    """Build a cortex-backlog-backed scratch tree with one item at *status* and
    ``lifecycle_phase: research``; return (root, item_path, log_path)."""
    root = tmp_path
    (root / "cortex" / "lifecycle" / "feat").mkdir(parents=True)
    backlog_dir = root / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)
    (root / "cortex" / "lifecycle.config.md").write_text(
        "---\nbacklog:\n  backend: cortex-backlog\n---\n", encoding="utf-8"
    )
    item = backlog_dir / "900-feat.md"
    item.write_text(
        f"---\ntitle: Feat\nstatus: {status}\nlifecycle_phase: research\n---\n\nBody.\n",
        encoding="utf-8",
    )
    log_path = root / "cortex" / "lifecycle" / "feat" / "events.log"
    log_path.write_text("", encoding="utf-8")
    return root, item, log_path


def test_advance_review_to_complete_advances_lifecycle_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The served-loop ``review.approved`` (review→complete) projection sets
    ``status: complete`` AND advances ``lifecycle_phase`` off ``research``."""
    root, item, log_path = _scaffold_advance(tmp_path, "in_progress")
    _stub_index_regen(monkeypatch)
    transition = tt.transition_by_id("review.approved")  # review → complete
    assert transition is not None and transition.to_state == "complete"

    outcome = adv._project_status(
        feature="feat", transition=transition, log_path=log_path,
        rows=[], project_root=root,
    )

    assert outcome == "wrote:complete"
    fm = _read_frontmatter(item)
    assert fm["status"] == "complete"
    assert fm["lifecycle_phase"] != "research"
    assert fm["lifecycle_phase"] == "complete"


def test_advance_cancel_does_not_mislabel_phase_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Derive-not-blindly guard: a cancel transition projects ``abandoned`` but
    must NOT write ``lifecycle_phase: complete`` — the phase is derived from the
    committed transition, so a wontfix/cancel move leaves the phase untouched."""
    root, item, log_path = _scaffold_advance(tmp_path, "in_progress")
    _stub_index_regen(monkeypatch)
    transition = tt.transition_by_id("plan.cancelled")  # plan → cancelled
    assert transition is not None and transition.to_state == "cancelled"

    outcome = adv._project_status(
        feature="feat", transition=transition, log_path=log_path,
        rows=[{"event": "lifecycle_cancelled"}], project_root=root,
    )

    assert outcome == "wrote:abandoned"
    fm = _read_frontmatter(item)
    assert fm["status"] == "abandoned"
    assert fm["lifecycle_phase"] == "research"  # unchanged — never mislabelled complete
