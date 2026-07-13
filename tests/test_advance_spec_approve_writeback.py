"""#378 req-7 — advance's ``spec-approve`` arm projects ONLY ``spec:``/``areas:``.

Phase 3 makes advance.py's served ``spec-approve`` verb own the spec/areas
backlog write-back that used to live in the standalone ``spec_approve.py``
(routing residue from #374). The CRITICAL boundary: status stays events-first /
``_project_status``-owned — advance already writes lattice- and
archive-shadow-guarded ``status: refined`` for the ``to_state == plan`` arm, so
the new arm projects ONLY the two fields ``_project_status`` does not touch
(``spec`` + preserve-on-omit ``areas``), never status. Re-writing status here
would demote an item already past ``refined`` on a re-approve, defeating the
hazard-4 guard.

These tests drive the full CLI (``adv.main`` over the real ``spec-approve``
subparser) so the new ``--spec-path`` / ``--backend`` / ``--backlog-file`` /
``--areas`` / ``--clear-areas`` flags are exercised end-to-end:

  (a) an approved spec-approve with the write-back flags yields ``status:
      refined`` (from ``_project_status``) PLUS ``spec:`` and ``areas:``;
  (b) an item already at a terminal/higher status is NOT demoted to ``refined``,
      yet still gains the spec/areas projection (the two writes are independent);
  (c) an emission-only caller that omits the new flags gains NO ``spec:``/
      ``areas:`` fields — the pre-req-7 behavior is unchanged.

Isolation: each test scaffolds a throwaway ``cortex/`` tree under ``tmp_path``,
neutralises ``update_item``'s best-effort index-regen subprocess and the CLI
telemetry breadcrumb so neither runs against the real repo; the frontmatter
write and the claim/commit primitive are exercised for real.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from cortex_command.lifecycle import advance as adv


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _neutralise_side_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub ``update_item``'s non-fatal index-regen subprocess and the CLI
    telemetry breadcrumb so neither touches the real repo — the frontmatter
    write itself and the claim/commit primitive stay real."""
    monkeypatch.setattr(
        "cortex_command.backlog.update_item.subprocess.run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=b""),
    )
    monkeypatch.setattr(adv._telemetry, "log_invocation", lambda *a, **k: None)


def _read_frontmatter(item_path: Path) -> dict[str, str]:
    """Parse the item's flat scalar frontmatter into a ``{key: raw-value}`` dict
    (values keep their on-disk form; only wrapping quotes are stripped)."""
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


def _scaffold(tmp_path: Path, *, status: str, extra_fm: str = "") -> tuple[Path, Path, Path]:
    """Build a cortex-backlog-backed scratch tree with the feature positioned at
    the ``specify`` phase (research→specify transition + spec.md, no spec_approved
    yet) and one backlog item at *status*. Returns (root, item_path, log_path)."""
    root = tmp_path
    feature_dir = root / "cortex" / "lifecycle" / "feat"
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text("spec body\n", encoding="utf-8")
    log_path = feature_dir / "events.log"
    log_path.write_text(
        json.dumps({"event": "phase_transition", "feature": "feat",
                    "from": "research", "to": "specify"}) + "\n",
        encoding="utf-8",
    )

    backlog_dir = root / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)
    (root / "cortex" / "lifecycle.config.md").write_text(
        "---\nbacklog:\n  backend: cortex-backlog\n---\n", encoding="utf-8"
    )
    item = backlog_dir / "900-feat.md"
    item.write_text(
        f"---\ntitle: Feat\nstatus: {status}\nlifecycle_phase: research\n{extra_fm}---\n\nBody.\n",
        encoding="utf-8",
    )
    return root, item, log_path


def _run(argv: list[str]) -> None:
    """Invoke the real CLI entrypoint and assert the never-crash exit-0 contract."""
    rc = adv.main(argv)
    assert rc == 0


# ---------------------------------------------------------------------------
# (a) approved + write-back flags → status:refined (from _project_status) + spec + areas
# ---------------------------------------------------------------------------


def test_spec_approve_projects_status_spec_and_areas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, item, log_path = _scaffold(tmp_path, status="backlog")
    _neutralise_side_channels(monkeypatch)

    _run([
        "spec-approve", "--feature", "feat", "--decision", "approved",
        "--backend", "cortex-backlog", "--backlog-file", "900-feat.md",
        "--spec-path", "cortex/lifecycle/feat/spec.md",
        "--areas", "cli", "hooks",
        "--log-path", str(log_path),
    ])

    fm = _read_frontmatter(item)
    # status:refined comes from _project_status (to_state == plan), NOT this arm.
    assert fm["status"] == "refined"
    # spec + areas come from the new spec/areas projection.
    assert fm["spec"] == "cortex/lifecycle/feat/spec.md"
    assert "cli" in fm["areas"] and "hooks" in fm["areas"]


# ---------------------------------------------------------------------------
# (b) an item already past refined is NOT demoted, but still gains spec/areas
# ---------------------------------------------------------------------------


def test_spec_approve_does_not_demote_higher_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lattice guard in _project_status keeps a ``complete`` item at complete
    (no demoting event), while the independent spec/areas projection still runs —
    proving status ownership stays with _project_status and spec/areas are separate."""
    root, item, log_path = _scaffold(tmp_path, status="complete")
    _neutralise_side_channels(monkeypatch)

    _run([
        "spec-approve", "--feature", "feat", "--decision", "approved",
        "--backend", "cortex-backlog", "--backlog-file", "900-feat.md",
        "--spec-path", "cortex/lifecycle/feat/spec.md",
        "--areas", "cli",
        "--log-path", str(log_path),
    ])

    fm = _read_frontmatter(item)
    # NOT demoted to refined — the events-first lattice guard holds.
    assert fm["status"] == "complete"
    # spec/areas projection is independent of the status demotion refusal.
    assert fm["spec"] == "cortex/lifecycle/feat/spec.md"
    assert "cli" in fm["areas"]


# ---------------------------------------------------------------------------
# (c) emission-only caller (no new flags) → no spec/areas write (unchanged)
# ---------------------------------------------------------------------------


def test_emission_only_caller_gains_no_spec_or_areas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Back-compat: a caller that omits --spec-path (and the other write-back
    flags) is unchanged — the spec/areas projection never fires, so no ``spec:``
    or ``areas:`` field is introduced. (status is still projected by the
    pre-existing _project_status seam; that is not this task's addition.)"""
    root, item, log_path = _scaffold(tmp_path, status="backlog")
    _neutralise_side_channels(monkeypatch)

    _run([
        "spec-approve", "--feature", "feat", "--decision", "approved",
        "--log-path", str(log_path),
    ])

    fm = _read_frontmatter(item)
    assert "spec" not in fm
    assert "areas" not in fm
