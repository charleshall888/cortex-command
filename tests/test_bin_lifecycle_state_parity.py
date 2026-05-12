#!/usr/bin/env python3
"""Parity tests: bin/cortex-lifecycle-state and bin/cortex-lifecycle-counters vs Python helpers.

Pins bash-script vs Python-helper equality at CI (spec Edge Cases:
"Bin-script vs Python-helper drift"). For each fixture under
tests/fixtures/bin_parity/<slug>/, the test:

  1. Stages the fixture into a tmp_path with the layout the bin scripts
     expect (`<cwd>/lifecycle/<slug>/...`).
  2. Invokes the bin scripts via subprocess with cwd=tmp_path.
  3. Compares each JSON output field against the Python source-of-truth
     (`cortex_command.common.read_tier`, `read_criticality`, and the
     pinned counters regexes from common.py:182-183).

Treats bin-side omitted keys as equivalent to Python-side defaults:
- bin tier absent -> read_tier defaults "simple"
- bin criticality absent -> read_criticality defaults "medium"
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cortex_command.common import (
    _detect_lifecycle_phase_inner,
    _read_criticality_inner,
    _read_tier_inner,
    read_criticality,
    read_tier,
)


REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "bin_parity"
BIN_STATE = REPO_ROOT / "bin" / "cortex-lifecycle-state"
BIN_COUNTERS = REPO_ROOT / "bin" / "cortex-lifecycle-counters"

# Pinned regexes — mirror cortex_command/common.py:182-183 exactly so this
# test reflects the source-of-truth contract.
RE_TASKS_TOTAL = re.compile(r"\*\*Status\*\*:.*\[[ x]\]")
RE_TASKS_CHECKED = re.compile(r"\*\*Status\*\*:.*\[x\]")
RE_VERDICT = re.compile(r'"verdict"\s*:\s*"[A-Z_]+"')


@pytest.fixture(autouse=True)
def _clear_lifecycle_caches() -> None:
    """Clear lifecycle lru_caches before and after each test."""
    _read_criticality_inner.cache_clear()
    _read_tier_inner.cache_clear()
    _detect_lifecycle_phase_inner.cache_clear()
    yield
    _read_criticality_inner.cache_clear()
    _read_tier_inner.cache_clear()
    _detect_lifecycle_phase_inner.cache_clear()


def _stage_fixture(slug: str, tmp_path: Path) -> Path:
    """Copy tests/fixtures/bin_parity/<slug>/ into tmp_path/lifecycle/<slug>/.

    Returns the tmp_path (to use as cwd for subprocess invocations).
    """
    src = FIXTURES_DIR / slug
    dst = tmp_path / "cortex" / "lifecycle" / slug
    dst.mkdir(parents=True)
    for item in src.iterdir():
        shutil.copy2(item, dst / item.name)
    return tmp_path


@pytest.mark.parametrize("slug", ["feat1", "feat2"])
def test_bin_lifecycle_state_matches_python(slug: str, tmp_path: Path) -> None:
    cwd = _stage_fixture(slug, tmp_path)

    result = subprocess.run(
        [str(BIN_STATE), "--feature", slug],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    bin_out = json.loads(result.stdout)

    lifecycle_base = cwd / "cortex" / "lifecycle"
    expected_tier = read_tier(slug, lifecycle_base=lifecycle_base)
    expected_criticality = read_criticality(slug, lifecycle_base=lifecycle_base)

    # bin omits keys when no relevant event found; Python defaults to
    # "simple" / "medium". Apply the same default-fallback on the bin side
    # to compare semantic equivalence.
    assert bin_out.get("tier", "simple") == expected_tier, (
        f"tier mismatch for {slug}: bin={bin_out!r} python={expected_tier!r}"
    )
    assert bin_out.get("criticality", "medium") == expected_criticality, (
        f"criticality mismatch for {slug}: "
        f"bin={bin_out!r} python={expected_criticality!r}"
    )


@pytest.mark.parametrize("slug", ["feat1", "feat2"])
def test_bin_lifecycle_counters_matches_python(slug: str, tmp_path: Path) -> None:
    cwd = _stage_fixture(slug, tmp_path)

    result = subprocess.run(
        [str(BIN_COUNTERS), "--feature", slug],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    bin_out = json.loads(result.stdout)

    feat_dir = cwd / "cortex" / "lifecycle" / slug
    plan_path = feat_dir / "plan.md"
    review_path = feat_dir / "review.md"

    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""
    review_text = review_path.read_text(encoding="utf-8") if review_path.exists() else ""

    expected_total = len(RE_TASKS_TOTAL.findall(plan_text))
    expected_checked = len(RE_TASKS_CHECKED.findall(plan_text))
    expected_rework = len(RE_VERDICT.findall(review_text))

    assert bin_out["tasks_total"] == expected_total, (
        f"tasks_total mismatch for {slug}: "
        f"bin={bin_out['tasks_total']} python={expected_total}"
    )
    assert bin_out["tasks_checked"] == expected_checked, (
        f"tasks_checked mismatch for {slug}: "
        f"bin={bin_out['tasks_checked']} python={expected_checked}"
    )
    assert bin_out["rework_cycles"] == expected_rework, (
        f"rework_cycles mismatch for {slug}: "
        f"bin={bin_out['rework_cycles']} python={expected_rework}"
    )
