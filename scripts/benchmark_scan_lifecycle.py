#!/usr/bin/env python3
"""Latency microbenchmark for cortex_command.hooks.scan_lifecycle.main().

Synthesizes a fixture set of N candidate lifecycles (mix of mismatched,
aligned, paused), invokes ``scan_lifecycle.main()`` end-to-end ``ITERS``
times, and reports wall-clock p50/p99 in a machine-readable form for
PR-description capture (per T16's no-fixed-numeric-target rule —
the benchmark grounds the Plan-phase decision rule about whether to
move diagnostic emission to a background thread or batch reads).

Usage::

    python3 scripts/benchmark_scan_lifecycle.py

Output shape::

    iterations=10 p50=120ms p99=450ms n_candidates=90
"""

from __future__ import annotations

import io
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

# Make the repo importable when run from any cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cortex_command.hooks import scan_lifecycle as scan_lifecycle_mod  # noqa: E402


N_CANDIDATES = 90
ITERS = 10


def _synthesize_repo(repo: Path, n: int) -> None:
    """Create ``n`` lifecycle dirs (mix of mismatched / aligned / paused)
    plus a synthetic ``cortex/backlog/index.json``.

    Distribution:
      - 1/3 mismatched (events implement + backlog complete)
      - 1/3 paused (events ending with feature_paused + plan.md unchecked)
      - 1/3 clean alignment (events implement + backlog in_progress)
    """
    lifecycle_dir = repo / "cortex" / "lifecycle"
    lifecycle_dir.mkdir(parents=True, exist_ok=True)
    backlog_dir = repo / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)

    plan_md = (
        "# Plan\n\n## Tasks\n\n"
        "### Task 1\n- **Status**: [x] done\n\n"
        "### Task 2\n- **Status**: [ ] pending\n\n"
        "### Task 3\n- **Status**: [ ] pending\n"
    )
    plan_md_paused = (
        "# Plan\n\n## Tasks\n\n"
        "### Task 1\n- **Status**: [ ] pending\n\n"
        "### Task 2\n- **Status**: [ ] pending\n"
    )

    index_entries: list[dict] = []
    for i in range(n):
        slug = f"feat-{i:03d}"
        feat_dir = lifecycle_dir / slug
        feat_dir.mkdir(exist_ok=True)
        kind = i % 3
        if kind == 0:  # mismatched
            (feat_dir / "events.log").write_text(
                json.dumps({"ts": "2026-01-01T00:00:01Z", "event": "spec_approved", "feature": slug}) + "\n"
                + json.dumps({"ts": "2026-01-01T00:00:02Z", "event": "plan_approved", "feature": slug}) + "\n",
                encoding="utf-8",
            )
            (feat_dir / "plan.md").write_text(plan_md, encoding="utf-8")
            status = "complete"
        elif kind == 1:  # paused
            (feat_dir / "events.log").write_text(
                json.dumps({"ts": "2026-01-01T00:00:01Z", "event": "spec_approved", "feature": slug}) + "\n"
                + json.dumps({"ts": "2026-01-01T00:00:02Z", "event": "plan_approved", "feature": slug}) + "\n"
                + json.dumps({"ts": "2026-01-01T00:00:03Z", "event": "feature_paused", "feature": slug}) + "\n",
                encoding="utf-8",
            )
            (feat_dir / "plan.md").write_text(plan_md_paused, encoding="utf-8")
            status = "in_progress"
        else:  # clean
            (feat_dir / "events.log").write_text(
                json.dumps({"ts": "2026-01-01T00:00:01Z", "event": "spec_approved", "feature": slug}) + "\n"
                + json.dumps({"ts": "2026-01-01T00:00:02Z", "event": "plan_approved", "feature": slug}) + "\n",
                encoding="utf-8",
            )
            (feat_dir / "plan.md").write_text(plan_md, encoding="utf-8")
            status = "in_progress"
        index_entries.append({
            "id": i,
            "title": slug,
            "lifecycle_slug": slug,
            "status": status,
        })
    (backlog_dir / "index.json").write_text(
        json.dumps(index_entries), encoding="utf-8"
    )


def _run_once(repo: Path) -> float:
    """Invoke scan_lifecycle.main() once and return wall-clock seconds."""
    stdin_payload = json.dumps({"session_id": "bench", "cwd": str(repo)})
    captured_stdin = io.StringIO(stdin_payload)
    captured_stdout = io.StringIO()
    with patch.object(sys, "stdin", captured_stdin), patch.object(
        sys, "stdout", captured_stdout
    ):
        t0 = time.perf_counter()
        scan_lifecycle_mod.main()
        elapsed = time.perf_counter() - t0
    return elapsed


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="scan-bench-") as tmp:
        repo = Path(tmp) / "repo"
        _synthesize_repo(repo, N_CANDIDATES)

        # Disable staleness filter so synthetic dates aren't excluded.
        os.environ["CORTEX_SCAN_LIFECYCLE_STALE_DAYS"] = "0"
        env_file = repo / ".claude-env"
        env_file.write_text("", encoding="utf-8")
        os.environ["CLAUDE_ENV_FILE"] = str(env_file)
        os.environ.pop("LIFECYCLE_SESSION_ID", None)

        # Warm-up (cache lazy imports, etc.) — one untimed run.
        _run_once(repo)

        samples = [_run_once(repo) for _ in range(ITERS)]

    samples_ms = sorted(s * 1000.0 for s in samples)
    p50 = statistics.median(samples_ms)
    # p99 over only ITERS samples reduces to max for ITERS=10.
    p99 = samples_ms[-1]
    # Two-line output so `grep -cE 'p50=|p99='` reports >=2 lines (the
    # T16 verification gate). The single-line summary is preserved on
    # the third line for human-friendly PR-description capture.
    print(f"p50={p50:.0f}ms")
    print(f"p99={p99:.0f}ms")
    print(
        f"iterations={ITERS} "
        f"p50={p50:.0f}ms "
        f"p99={p99:.0f}ms "
        f"n_candidates={N_CANDIDATES}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
