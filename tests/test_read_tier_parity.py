"""Parity tests for ``cortex_command.common.read_tier`` vs
``cortex_command.overnight.report._read_tier``.

Pins R2a's four parity cases from the spec at
``lifecycle/promote-lifecycle-state-out-of-eventslog-full-reads/spec.md``:

    (i)   ``lifecycle_start tier:simple`` alone → ``simple``
    (ii)  ``lifecycle_start tier:simple`` then ``complexity_override to:complex``
          → ``complex``
    (iii) After ``complexity_override to:simple``, a stray non-override event
          carrying ``tier:complex`` (e.g. ``batch_dispatch``) → ``simple``
    (iv)  ``read_tier`` and ``_read_tier`` return identical values across both
          ``tests/fixtures/state/*/events.log`` AND the in-tree
          ``lifecycle/*/events.log`` corpus (filtered to directories that
          contain ``index.md``).

This test is expected to FAIL on cases (ii) and (iii) until ``read_tier`` is
realigned to the canonical ``lifecycle_start → complexity_override.to`` rule
that ``_read_tier`` already implements. Case (iv) may also fail on any
in-tree lifecycle whose events.log carries a stray ``tier`` field after a
``complexity_override``; today's corpus has zero such lifecycles.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cortex_command.common import read_tier
from cortex_command.overnight.report import _read_tier


# ---------------------------------------------------------------------------
# Repo root + corpus discovery
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "state"
TIER_PARITY_ROOT = FIXTURES_ROOT / "tier_parity"


def _lifecycle_features() -> list[str]:
    """Return slugs of in-tree lifecycle features (directories with both
    ``events.log`` and ``index.md``). Skips ``sessions/``, ``archive/`` and
    any other non-feature subdirectories.
    """
    base = REPO_ROOT / "lifecycle"
    if not base.is_dir():
        return []
    slugs: list[str] = []
    for path in sorted(base.glob("*/events.log")):
        feature_dir = path.parent
        if not (feature_dir / "index.md").exists():
            continue
        slugs.append(feature_dir.name)
    return slugs


def _fixture_features() -> list[str]:
    """Return slugs (subdirectory names) under ``tests/fixtures/state/*``
    that contain an ``events.log``. Unfiltered: includes ``tier_parity``'s
    nested fixtures via separate dispatch, but here we only walk one level
    deep (``state/<slug>/events.log``).
    """
    if not FIXTURES_ROOT.is_dir():
        return []
    return sorted(
        path.parent.name
        for path in FIXTURES_ROOT.glob("*/events.log")
    )


# ---------------------------------------------------------------------------
# Helper: stage a single events.log under ``<tmp>/lifecycle/<slug>/events.log``
# so both readers (one hardcodes the path, one takes lifecycle_base) can be
# invoked against it.
# ---------------------------------------------------------------------------

def _stage_fixture(tmp_path: Path, slug: str, source_events: Path) -> None:
    feature_dir = tmp_path / "lifecycle" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(source_events, feature_dir / "events.log")


def _both_readers(slug: str, lifecycle_base: Path) -> tuple[str, str]:
    """Invoke both readers from a CWD where ``lifecycle/<slug>/events.log``
    resolves. Returns ``(common_result, report_result)``.
    """
    common_result = read_tier(slug, lifecycle_base=lifecycle_base)
    report_result = _read_tier(slug)
    return common_result, report_result


# ---------------------------------------------------------------------------
# Cases (i), (ii), (iii): canonical-rule edge behavior on tier_parity fixtures
# ---------------------------------------------------------------------------

CANONICAL_CASES = [
    ("lifecycle_start_only", "simple"),
    ("start_then_override", "complex"),
    ("stray_tier_after_override", "simple"),
]


@pytest.mark.parametrize("slug,expected", CANONICAL_CASES, ids=[c[0] for c in CANONICAL_CASES])
def test_canonical_tier_rule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slug: str, expected: str) -> None:
    """Cases (i)-(iii): both readers must return the canonical tier value."""
    source = TIER_PARITY_ROOT / slug / "events.log"
    assert source.exists(), f"missing fixture: {source}"
    _stage_fixture(tmp_path, slug, source)
    monkeypatch.chdir(tmp_path)

    common_result, report_result = _both_readers(slug, lifecycle_base=tmp_path / "lifecycle")

    assert common_result == expected, (
        f"common.read_tier({slug!r}) returned {common_result!r}, expected {expected!r}"
    )
    assert report_result == expected, (
        f"report._read_tier({slug!r}) returned {report_result!r}, expected {expected!r}"
    )


# ---------------------------------------------------------------------------
# Case (iv): full-corpus parity sweep
#
# Two corpora are swept, each parametrized so individual divergences surface
# as distinct test IDs:
#   - tests/fixtures/state/*/events.log (no index.md filter)
#   - lifecycle/*/events.log filtered to directories containing index.md
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug", _fixture_features())
def test_parity_fixture_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slug: str) -> None:
    """Case (iv) part 1: both readers agree across the fixtures corpus."""
    source = FIXTURES_ROOT / slug / "events.log"
    _stage_fixture(tmp_path, slug, source)
    monkeypatch.chdir(tmp_path)

    common_result, report_result = _both_readers(slug, lifecycle_base=tmp_path / "lifecycle")

    assert common_result == report_result, (
        f"parity divergence on fixture {slug!r}: "
        f"common.read_tier={common_result!r} vs report._read_tier={report_result!r}"
    )


@pytest.mark.parametrize("slug", _lifecycle_features())
def test_parity_lifecycle_corpus(monkeypatch: pytest.MonkeyPatch, slug: str) -> None:
    """Case (iv) part 2: both readers agree across the in-tree
    ``lifecycle/*/events.log`` corpus (filtered to feature directories that
    contain ``index.md``).
    """
    monkeypatch.chdir(REPO_ROOT)

    common_result, report_result = _both_readers(slug, lifecycle_base=REPO_ROOT / "lifecycle")

    assert common_result == report_result, (
        f"parity divergence on lifecycle {slug!r}: "
        f"common.read_tier={common_result!r} vs report._read_tier={report_result!r}"
    )
