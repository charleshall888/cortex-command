#!/usr/bin/env python3
"""Tests for ``cortex_command.common.lifecycle_staleness`` (resume-only
staleness signals consumed by the lifecycle SKILL.md resume offer).

Covers artifact-age computation, the missing-artifact → None mapping, and
graceful degradation when the working tree is not a git repository (a
pytest ``tmp_path`` is never a repo, so ``commits_since_spec`` is None there
rather than raising).
"""

from pathlib import Path

from cortex_command.common import lifecycle_staleness


def test_spec_age_zero_and_no_plan(tmp_path: Path) -> None:
    fdir = tmp_path / "feature"
    fdir.mkdir()
    (fdir / "spec.md").write_text("spec")
    result = lifecycle_staleness(fdir)
    assert result["spec_age_days"] == 0
    assert result["plan_age_days"] is None
    # tmp_path is not a git repo → graceful None, not an exception.
    assert result["commits_since_spec"] is None


def test_missing_spec_yields_none(tmp_path: Path) -> None:
    fdir = tmp_path / "feature"
    fdir.mkdir()
    result = lifecycle_staleness(fdir)
    assert result["spec_age_days"] is None
    assert result["plan_age_days"] is None
    assert result["commits_since_spec"] is None


def test_plan_age_reported_when_present(tmp_path: Path) -> None:
    fdir = tmp_path / "feature"
    fdir.mkdir()
    (fdir / "spec.md").write_text("spec")
    (fdir / "plan.md").write_text("plan")
    result = lifecycle_staleness(fdir)
    assert result["spec_age_days"] == 0
    assert result["plan_age_days"] == 0
