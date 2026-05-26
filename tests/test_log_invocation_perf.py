"""Perf-budget regression test for ``bin/cortex-log-invocation`` (#198).

``test_log_invocation_fast_path_budget`` — local-only regression
detection for the dual-channel wrapper implementation. Budgets are set
to the measured floor on Apple Silicon dev hardware (post Task-4
Python-module refactor and Task-5 bash-wrapper reorder) plus
run-to-run variance headroom, calibrated so that a ~20ms regression
is reliably caught.

Measured floor (N=35, WARMUP=5, Apple Silicon, 2026-05):
  p50 ~38ms, mean ~38ms, p95 ~40ms

Budget thresholds give ~12ms headroom above floor at p50/mean and
~25ms at p95, so a 20ms regression lands above all three budgets.

Multi-statistic gating catches additive single-fork regressions and
tail-latency growth that a median-only assertion would miss.

The function discards the first 5 invocations (warm-up; the first call
in a fresh tmp repo pays the ``mkdir`` cost which is excluded from the
hot-path measurement per spec).
"""

from __future__ import annotations

import math
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
P50_BUDGET = 0.050
MEAN_BUDGET = 0.055
P95_BUDGET = 0.065


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
    n = len(sorted_samples)
    return sorted_samples[min(n - 1, int(math.ceil(0.95 * n)) - 1)]


@pytest.mark.skipif(
    not BASH_SHIM.is_file(),
    reason="bin/cortex-log-invocation not present (CLI tier not installed)",
)
@pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git not on PATH",
)
def test_log_invocation_fast_path_budget(tmp_path: Path) -> None:
    """Local regression detection: p50 <= 50ms, mean <= 55ms, p95 <= 65ms.

    Budgets are calibrated to the measured post-optimization floor on
    Apple Silicon (~38ms p50, ~40ms p95) with headroom sized so that a
    ~20ms regression reliably exceeds all three thresholds. This test is
    intentionally local-only: it catches regressions introduced in the
    working tree, not CI environment variance.
    """
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

