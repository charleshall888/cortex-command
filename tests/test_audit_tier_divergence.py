"""Tests for ``bin/cortex-audit-tier-divergence``.

Covers spec R2b (script behavior) and R2c (pre-commit gate contract — the
stderr token ``tier-divergence:`` must appear on every divergent lifecycle).

Three scenarios:
  (a) clean corpus exits 0;
  (b) divergent OPEN lifecycle exits 1 with stderr matching ``tier-divergence:``;
  (c) divergent CLOSED lifecycle (carries ``feature_complete``) exits 0 by
      default but exits 1 with ``--include-closed``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "bin" / "cortex-audit-tier-divergence"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "audit_tier"


def _run(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def _stage_fixture(tmp_path: Path, fixture_name: str) -> Path:
    """Copy the named fixture corpus into ``tmp_path`` and return the root."""
    src = FIXTURES / fixture_name
    dst = tmp_path / fixture_name
    shutil.copytree(src, dst)
    return dst


def test_clean_corpus_exits_zero(tmp_path: Path) -> None:
    root = _stage_fixture(tmp_path, "clean")
    result = _run(root)
    assert result.returncode == 0, result.stderr
    assert "tier-divergence" not in result.stderr


def test_divergent_open_lifecycle_exits_one(tmp_path: Path) -> None:
    root = _stage_fixture(tmp_path, "divergent")
    result = _run(root)
    assert result.returncode == 1, (result.returncode, result.stderr)
    assert "tier-divergence:" in result.stderr
    assert "last_wins=complex" in result.stderr
    assert "canonical=simple" in result.stderr


def test_divergent_closed_lifecycle_skipped_by_default(tmp_path: Path) -> None:
    """A divergent lifecycle carrying feature_complete is closed; default exits 0."""
    root = _stage_fixture(tmp_path, "divergent")
    # Append a feature_complete event to close the lifecycle.
    events = root / "lifecycle" / "foo" / "events.log"
    with events.open("a", encoding="utf-8") as f:
        f.write('{"event":"feature_complete","feature":"foo"}\n')
    result = _run(root)
    assert result.returncode == 0, result.stderr
    assert "tier-divergence" not in result.stderr


def test_divergent_closed_lifecycle_with_include_closed(tmp_path: Path) -> None:
    """``--include-closed`` flag re-includes closed lifecycles in the audit."""
    root = _stage_fixture(tmp_path, "divergent")
    events = root / "lifecycle" / "foo" / "events.log"
    with events.open("a", encoding="utf-8") as f:
        f.write('{"event":"feature_complete","feature":"foo"}\n')
    result = _run(root, "--include-closed")
    assert result.returncode == 1, (result.returncode, result.stderr)
    assert "tier-divergence:" in result.stderr


def test_closed_with_spaced_json_serialization_also_skipped(tmp_path: Path) -> None:
    """Both ``"event":"feature_complete"`` and ``"event": "feature_complete"``
    serializations appear in the in-tree corpus — the closed-detector must
    handle the spaced form too."""
    root = _stage_fixture(tmp_path, "divergent")
    events = root / "lifecycle" / "foo" / "events.log"
    with events.open("a", encoding="utf-8") as f:
        f.write('{"event": "feature_complete", "feature": "foo"}\n')
    result = _run(root)
    assert result.returncode == 0, result.stderr
