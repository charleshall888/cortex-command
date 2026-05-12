"""Perf-budget regression test for ``bin/cortex-log-invocation`` (#198).

Two assertions gate the trim:

1. ``test_log_invocation_fast_path_budget`` — on the cooperating-parent
   fast path (``CORTEX_REPO_ROOT`` set and validated), p50 wall time
   stays under 15ms, mean under 18ms, and p95 under 25ms. Multi-statistic
   gating catches additive single-fork regressions and tail-latency
   growth that a median-only assertion would miss.

2. ``test_log_invocation_fast_path_faster_than_slow`` — the fast path's
   median is at least 2ms below the slow path's median. This delta
   assertion catches silent fall-through: if a future commit breaks the
   env-var branch, both paths converge and the delta disappears, tripping
   the test even when the absolute fast-path budget would still pass.

Both functions discard the first 5 invocations (warm-up; the first call
in a fresh tmp repo pays the ``mkdir`` cost which is excluded from the
hot-path measurement per spec).
"""

from __future__ import annotations

import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BASH_SHIM = REPO_ROOT / "bin" / "cortex-log-invocation"

WARMUP = 5
FAST_PATH_N = 30
DELTA_N = 20
P50_BUDGET = 0.015
MEAN_BUDGET = 0.018
P95_BUDGET = 0.025
MIN_DELTA = 0.002


def _run_shim(env: dict[str, str], cwd: Path) -> float:
    """Invoke the shim once; return wall-time seconds via perf_counter."""
    start = time.perf_counter()
    result = subprocess.run(
        [str(BASH_SHIM), "cortex-perf-probe", "arg1", "arg2"],
        env=env,
        cwd=str(cwd),
        capture_output=True,
    )
    elapsed = time.perf_counter() - start
    assert result.returncode == 0, f"shim returned {result.returncode}"
    return elapsed


def _make_fake_repo(tmp_path: Path) -> Path:
    """Build a tmp repo with a real .git directory so git rev-parse works."""
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", str(fake_repo)],
        check=True,
        capture_output=True,
    )
    return fake_repo


def _p95(samples: list[float]) -> float:
    """Return the 95th percentile via nearest-rank on a sorted copy."""
    sorted_samples = sorted(samples)
    index = max(0, min(len(sorted_samples) - 1, int(0.95 * len(sorted_samples)) - 1))
    return sorted_samples[index]


@pytest.mark.skipif(
    not BASH_SHIM.is_file(),
    reason="bin/cortex-log-invocation not present (CLI tier not installed)",
)
@pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git not on PATH",
)
def test_log_invocation_fast_path_budget(tmp_path: Path) -> None:
    """Fast-path median <= 15ms, mean <= 18ms, p95 <= 25ms."""
    fake_repo = _make_fake_repo(tmp_path)
    session_id = "perf-test-fast"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path / "home"),
        "LIFECYCLE_SESSION_ID": session_id,
        "CORTEX_REPO_ROOT": str(fake_repo),
    }
    Path(env["HOME"]).mkdir(parents=True, exist_ok=True)

    durations: list[float] = []
    for _ in range(FAST_PATH_N):
        durations.append(_run_shim(env, fake_repo))

    samples = durations[WARMUP:]
    p50 = statistics.median(samples)
    mean = statistics.mean(samples)
    p95 = _p95(samples)

    assert p50 <= P50_BUDGET, (
        f"fast-path p50 budget exceeded: {p50*1000:.2f}ms > {P50_BUDGET*1000}ms"
    )
    assert mean <= MEAN_BUDGET, (
        f"fast-path mean budget exceeded: {mean*1000:.2f}ms > {MEAN_BUDGET*1000}ms"
    )
    assert p95 <= P95_BUDGET, (
        f"fast-path p95 budget exceeded: {p95*1000:.2f}ms > {P95_BUDGET*1000}ms"
    )


@pytest.mark.skipif(
    not BASH_SHIM.is_file(),
    reason="bin/cortex-log-invocation not present (CLI tier not installed)",
)
@pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git not on PATH",
)
def test_log_invocation_fast_path_faster_than_slow(tmp_path: Path) -> None:
    """Fast-path median is at least MIN_DELTA seconds below slow-path median.

    Detects silent fall-through: if a future edit breaks the env-var
    branch, both paths converge to the same git-rev-parse cost and the
    delta vanishes. Absolute budgets alone cannot catch that regression.
    """
    fake_repo = _make_fake_repo(tmp_path)
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)

    fast_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(fake_home),
        "LIFECYCLE_SESSION_ID": "perf-test-fast",
        "CORTEX_REPO_ROOT": str(fake_repo),
    }
    slow_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(fake_home),
        "LIFECYCLE_SESSION_ID": "perf-test-slow",
    }

    fast_durations = [_run_shim(fast_env, fake_repo) for _ in range(DELTA_N)]
    slow_durations = [_run_shim(slow_env, fake_repo) for _ in range(DELTA_N)]

    fast_median = statistics.median(fast_durations[WARMUP:])
    slow_median = statistics.median(slow_durations[WARMUP:])
    delta = slow_median - fast_median

    assert delta >= MIN_DELTA, (
        f"fast-path/slow-path delta below {MIN_DELTA*1000}ms: "
        f"fast={fast_median*1000:.2f}ms slow={slow_median*1000:.2f}ms "
        f"delta={delta*1000:.2f}ms — silent fall-through suspected"
    )
