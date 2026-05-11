#!/usr/bin/env python3
"""Tests for lifecycle phase detection against state fixtures.

Iterates over tests/fixtures/state/ subdirectories, calls
detect_lifecycle_phase() from cortex_command.common, and asserts the
phase field of the returned dict matches the directory name.
"""

import os

import pytest
from pathlib import Path

from cortex_command.common import (
    _detect_lifecycle_phase_inner,
    _read_criticality_inner,
    _read_tier_inner,
    detect_lifecycle_phase,
    read_criticality,
    read_tier,
)


# ---------------------------------------------------------------------------
# Run fixture tests
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "state"

_fixture_dirs = [d for d in sorted(FIXTURES_DIR.iterdir()) if d.is_dir()]


@pytest.mark.parametrize("fixture_dir", _fixture_dirs, ids=[d.name for d in _fixture_dirs])
def test_lifecycle_phase(fixture_dir: Path) -> None:
    expected = fixture_dir.name
    result = detect_lifecycle_phase(fixture_dir)
    assert result["phase"] == expected


# ---------------------------------------------------------------------------
# lru_cache mtime-invalidation tests (spec R1 / task 3)
# ---------------------------------------------------------------------------
#
# Each test writes an events.log (or other artifact), calls the cached
# reader, mutates the file, then explicitly calls os.utime() with an
# advanced mtime_ns to force a monotonic mtime advance past filesystem
# resolution (back-to-back writes can collide on fast filesystems).


def _bump_mtime(path: Path) -> None:
    """Force mtime_ns to advance by at least 1 ms past the current value."""
    s = path.stat()
    new_ns = s.st_mtime_ns + 1_000_000
    os.utime(path, ns=(new_ns, new_ns))


@pytest.fixture
def _clear_lifecycle_caches() -> None:
    """Clear all three lru_caches before and after each test using the fixture."""
    _read_criticality_inner.cache_clear()
    _read_tier_inner.cache_clear()
    _detect_lifecycle_phase_inner.cache_clear()
    yield
    _read_criticality_inner.cache_clear()
    _read_tier_inner.cache_clear()
    _detect_lifecycle_phase_inner.cache_clear()


def test_read_criticality_mtime_invalidates(
    tmp_path: Path, _clear_lifecycle_caches: None
) -> None:
    feature = "demo"
    feature_dir = tmp_path / feature
    feature_dir.mkdir()
    events = feature_dir / "events.log"
    events.write_text('{"criticality": "low"}\n', encoding="utf-8")

    assert read_criticality(feature, lifecycle_base=tmp_path) == "low"

    events.write_text(
        '{"criticality": "low"}\n{"criticality": "high"}\n',
        encoding="utf-8",
    )
    _bump_mtime(events)

    assert read_criticality(feature, lifecycle_base=tmp_path) == "high"


def test_read_tier_mtime_invalidates(
    tmp_path: Path, _clear_lifecycle_caches: None
) -> None:
    feature = "demo"
    feature_dir = tmp_path / feature
    feature_dir.mkdir()
    events = feature_dir / "events.log"
    events.write_text(
        '{"event": "lifecycle_start", "tier": "simple"}\n',
        encoding="utf-8",
    )

    assert read_tier(feature, lifecycle_base=tmp_path) == "simple"

    events.write_text(
        '{"event": "lifecycle_start", "tier": "simple"}\n'
        '{"event": "complexity_override", "to": "complex"}\n',
        encoding="utf-8",
    )
    _bump_mtime(events)

    assert read_tier(feature, lifecycle_base=tmp_path) == "complex"


def test_detect_phase_mtime_invalidates(
    tmp_path: Path, _clear_lifecycle_caches: None
) -> None:
    """events.log mutation (adding feature_complete) must invalidate the cache."""
    feature_dir = tmp_path / "feat"
    feature_dir.mkdir()
    # Start in research phase with research.md present and a benign events.log.
    (feature_dir / "research.md").write_text("research\n", encoding="utf-8")
    events = feature_dir / "events.log"
    events.write_text('{"event": "lifecycle_start"}\n', encoding="utf-8")

    first = detect_lifecycle_phase(feature_dir)
    assert first["phase"] == "specify"

    # Append a feature_complete event and force an mtime advance.
    events.write_text(
        '{"event": "lifecycle_start"}\n{"event": "feature_complete"}\n',
        encoding="utf-8",
    )
    _bump_mtime(events)

    second = detect_lifecycle_phase(feature_dir)
    assert second["phase"] == "complete"


def test_detect_phase_invalidates_on_spec_md(
    tmp_path: Path, _clear_lifecycle_caches: None
) -> None:
    """Creating spec.md must invalidate the cache and transition phase."""
    feature_dir = tmp_path / "feat"
    feature_dir.mkdir()
    (feature_dir / "research.md").write_text("research\n", encoding="utf-8")

    first = detect_lifecycle_phase(feature_dir)
    assert first["phase"] == "specify"

    # Newly-created spec.md will have a fresh mtime, so a separate utime
    # bump is not strictly required, but we still force an advance to
    # mirror the other tests and avoid sub-resolution collisions.
    spec = feature_dir / "spec.md"
    spec.write_text("spec\n", encoding="utf-8")
    # Ensure the (False, 0, 0) -> (True, mtime, size) transition trips the
    # cache key. The exists bool alone already differs, but bumping mtime
    # is harmless and keeps parity with the other invalidation tests.
    _bump_mtime(spec)

    second = detect_lifecycle_phase(feature_dir)
    assert second["phase"] == "plan"
