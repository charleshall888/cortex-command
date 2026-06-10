#!/usr/bin/env python3
"""Parity tests: bin/cortex-lifecycle-state and bin/cortex-lifecycle-counters vs Python helpers.

Pins bash-script vs Python-helper equality at CI (spec Edge Cases:
"Bin-script vs Python-helper drift"). For each fixture under
tests/fixtures/bin_parity/<slug>/, the test:

  1. Stages the fixture into a tmp_path with the layout the bin scripts
     expect (`<cwd>/cortex/lifecycle/<slug>/...`).
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
import os
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
from cortex_command.lifecycle.counters import count_rework_cycles
from cortex_command.refine import _reduce_current_state


REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "bin_parity"
BIN_STATE = REPO_ROOT / "bin" / "cortex-lifecycle-state"
BIN_COUNTERS = REPO_ROOT / "bin" / "cortex-lifecycle-counters"

# Pinned task regexes — mirror cortex_command/common.py:182-183 exactly so this
# test reflects the source-of-truth contract. rework_cycles is no longer
# regex-sourced; it is computed via count_rework_cycles over events.log.
RE_TASKS_TOTAL = re.compile(r"\*\*Status\*\*:.*\[[ x]\]")
RE_TASKS_CHECKED = re.compile(r"\*\*Status\*\*:.*\[x\]")


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
    """Copy tests/fixtures/bin_parity/<slug>/ into tmp_path/cortex/lifecycle/<slug>/.

    Returns the tmp_path (to use as cwd for subprocess invocations). Staging is
    byte-oriented (shutil.copy2), so fixtures carrying non-UTF-8 bytes survive
    intact — a prerequisite for Task 10's non-UTF-8 axes.
    """
    src = FIXTURES_DIR / slug
    dst = tmp_path / "cortex" / "lifecycle" / slug
    dst.mkdir(parents=True)
    for item in src.iterdir():
        shutil.copy2(item, dst / item.name)
    return tmp_path


def _pinned_env() -> dict[str, str]:
    """Pin the bin subprocess to working-tree code.

    The bin wrapper's dual-channel logic otherwise prefers an ambient-importable
    wheel over the working tree, so during implementation the subprocess could
    exec stale wheel code. CORTEX_COMMAND_FORCE_SOURCE=1 forces the wrapper's
    branch (a) (exec the working-tree module), and prepending REPO_ROOT to
    PYTHONPATH makes that module the local source under test. Mirrors the sibling
    golden harness (test_cortex_lifecycle_state_parity.py).
    """
    env = dict(os.environ)
    env["CORTEX_COMMAND_FORCE_SOURCE"] = "1"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}{os.pathsep}{existing}" if existing else str(REPO_ROOT)
    )
    return env


@pytest.mark.parametrize("slug", ["feat1", "feat2"])
def test_bin_lifecycle_state_matches_python(slug: str, tmp_path: Path) -> None:
    cwd = _stage_fixture(slug, tmp_path)

    result = subprocess.run(
        [str(BIN_STATE), "--feature", slug],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env=_pinned_env(),
    )
    bin_out = json.loads(result.stdout)

    assert isinstance(bin_out, dict), (
        f"bin emitted non-object stdout for {slug}: {result.stdout!r} "
        f"(parsed {bin_out!r}). The harness compares dict fields, so a null or "
        f"scalar reduction must fail with this diagnostic rather than "
        f"AttributeError on None.get(...)."
    )

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
        env=_pinned_env(),
    )
    bin_out = json.loads(result.stdout)

    feat_dir = cwd / "cortex" / "lifecycle" / slug
    plan_path = feat_dir / "plan.md"
    events_log_path = feat_dir / "events.log"

    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""

    expected_total = len(RE_TASKS_TOTAL.findall(plan_text))
    expected_checked = len(RE_TASKS_CHECKED.findall(plan_text))
    # rework_cycles is sourced from events.log via the same module the bin
    # wrapper execs, so this verifies wrapper<->module plumbing parity.
    # Counter correctness is owned by cortex_command/lifecycle/tests/test_counters.py.
    expected_rework = count_rework_cycles(events_log_path)

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


# ---------------------------------------------------------------------------
# Multi-reader agreement matrix (R12) — state_cli (via the bin wrapper),
# read_tier/read_criticality, and refine._reduce_current_state must return
# identical EFFECTIVE values (each reader's value after its own default
# projection) across the corruption/encoding/override axes. Non-UTF-8 axes are
# built with write_bytes because they cannot live as git text fixtures.
# ---------------------------------------------------------------------------

# axis id, events.log bytes (None → no file), expected tier, criticality, corrupted
_AGREEMENT_AXES = [
    (
        "torn-mid-file",
        b'{"event":"lifecycle_start","tier":"complex","criticality":"high"}\n'
        b'{"event":"phase_transition","from":"resea\n',
        "complex",
        "high",
        False,
    ),
    (
        "torn-start-only",
        b'{"event":"lifecycle_start","tier":"comp\n',
        "simple",
        "medium",
        True,
    ),
    (
        "non-utf8-structure",
        b"\xff\xfe structure-break \xfa\n",
        "simple",
        "medium",
        True,
    ),
    (
        "non-utf8-in-string-vocab",
        b'{"event":"lifecycle_start","tier":"\xff","criticality":"high"}\n',
        "simple",
        "high",
        True,
    ),
    (
        "to-keyed-override",
        b'{"event":"lifecycle_start","tier":"simple","criticality":"medium"}\n'
        b'{"event":"complexity_override","to":"complex"}\n'
        b'{"event":"criticality_override","to":"high"}\n',
        "complex",
        "high",
        False,
    ),
    ("missing-file", None, "simple", "medium", False),
    ("empty-valid", b"", "simple", "medium", False),
]


def _stage_events_bytes(slug: str, tmp_path: Path, data: bytes | None) -> Path:
    """Write events.log bytes under tmp_path/cortex/lifecycle/<slug>/.

    ``data is None`` creates the feature directory without an events.log (the
    missing-file axis). Byte-oriented so non-UTF-8 axes survive intact.
    """
    fdir = tmp_path / "cortex" / "lifecycle" / slug
    fdir.mkdir(parents=True, exist_ok=True)
    if data is not None:
        (fdir / "events.log").write_bytes(data)
    return tmp_path


@pytest.mark.parametrize(
    "axis,data,exp_tier,exp_crit,exp_corrupted",
    _AGREEMENT_AXES,
    ids=[a[0] for a in _AGREEMENT_AXES],
)
def test_all_readers_agree_on_effective_state(
    axis: str,
    data: bytes | None,
    exp_tier: str,
    exp_crit: str,
    exp_corrupted: bool,
    tmp_path: Path,
) -> None:
    slug = f"feat-{axis}"
    cwd = _stage_events_bytes(slug, tmp_path, data)
    lifecycle_base = cwd / "cortex" / "lifecycle"
    events_log = lifecycle_base / slug / "events.log"

    # state_cli via the bin wrapper, pinned to working-tree code.
    result = subprocess.run(
        [str(BIN_STATE), "--feature", slug],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env=_pinned_env(),
    )
    bin_out = json.loads(result.stdout)
    assert isinstance(bin_out, dict), (
        f"bin emitted non-object for {axis}: {result.stdout!r}"
    )
    bin_tier = bin_out.get("tier", "simple")
    bin_crit = bin_out.get("criticality", "medium")

    # Python readers, each with its own default projection.
    py_tier = read_tier(slug, lifecycle_base=lifecycle_base)
    py_crit = read_criticality(slug, lifecycle_base=lifecycle_base)
    refine_tier, refine_crit = _reduce_current_state(events_log)

    assert bin_tier == py_tier == refine_tier == exp_tier, (
        f"tier disagreement on {axis}: bin={bin_tier!r} read_tier={py_tier!r} "
        f"refine={refine_tier!r} expected={exp_tier!r}"
    )
    assert bin_crit == py_crit == refine_crit == exp_crit, (
        f"criticality disagreement on {axis}: bin={bin_crit!r} "
        f"read_criticality={py_crit!r} refine={refine_crit!r} expected={exp_crit!r}"
    )

    # The machine-readable corruption signal is pinned on the bin output.
    assert (bin_out.get("corrupted") is True) == exp_corrupted, (
        f"corruption signal mismatch on {axis}: bin_out={bin_out!r} "
        f"expected_corrupted={exp_corrupted}"
    )
