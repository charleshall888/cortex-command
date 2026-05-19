"""Bidirectional concurrency contract integration tests (R15).

Exercises the full bidirectional contract through PRODUCTION code paths — no
Python stubs of ``cortex-interactive-lock`` or ``compute_eligible_features``.

Sub-tests:
  A — interactive → interactive: two ``cortex-interactive-lock acquire X``
      subprocesses with different CLAUDE_CODE_SESSION_ID values; first exits 0,
      second exits non-zero with stderr containing ``"work on a different
      feature"``.

  B — interactive → overnight (per-round scan): synthetic live
      ``interactive.pid`` for feature Y; ``scan_live_locks`` returns ``{"Y"}``;
      ``compute_eligible_features(["Y","Z"], tmp_path)`` returns
      ``(["Z"], [<one skip-event with rationale containing test-session-B>])``.

  C — overnight → interactive rejection mirror (actual sidecar bash):
      synthetic ``active-session.json`` + ``runner.pid``; sidecar at
      ``skills/lifecycle/references/_interactive_overnight_check.sh`` invoked
      via ``cat ... | bash -s -- '<wording>' '<repo>'``; asserts non-zero exit
      AND stderr contains ``"the run to complete"``.

  D — lock release: ``acquire X`` → file exists → ``release X`` → file absent
      → ``cortex/lifecycle/X/events.log`` contains ``interactive_lock_released``.

Coupling notes (documented in spec R15):
  - Sub-test A's grep target ``"work on a different feature"`` is anchored to
    R5's rejection wording. If R5 changes, this test must update in lockstep.
  - Sub-test C's grep target ``"the run to complete"`` is anchored to R7's
    rejection wording (spec.md R15 note: use this substring, not the
    spec-drift ``"work to complete"``).

Out-of-scope per R15 / Non-Requirements:
  The principal TOCTOU window (owner acquires after scan but before round-N
  dispatch) is NOT exercised here; that path surfaces via ``git worktree add``
  failure in the orchestrator's existing error handling.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Production imports (no stubs)
from cortex_command.interactive_lock import scan_live_locks
from cortex_command.overnight.orchestrator import compute_eligible_features


# ---------------------------------------------------------------------------
# Repo root helper
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Capability probe for sub-test C
# ---------------------------------------------------------------------------


def _bash_herestring_available() -> bool:
    """Return True if bash can create temp files needed for herestrings.

    The sidecar script uses ``<<<`` (herestring) syntax which bash implements
    via temp files.  In some restricted sandbox environments (e.g. Claude Code
    Seatbelt with write-deny on /tmp) bash cannot create these temp files.
    Sub-test C is skipped when this probe returns False.
    """
    try:
        result = subprocess.run(
            ["bash", "-c", "echo probe <<< test"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _cortex_interactive_lock_argv() -> list[str]:
    """Return the argv prefix for invoking the cortex-interactive-lock
    console script.

    Prefers the venv's installed console script if available; falls back to
    ``[sys.executable, "-m", "cortex_command.interactive_lock"]``.
    """
    venv_bin = Path(sys.executable).parent / "cortex-interactive-lock"
    if venv_bin.exists():
        return [str(venv_bin)]
    return [sys.executable, "-m", "cortex_command.interactive_lock"]


# ---------------------------------------------------------------------------
# Sub-test A — interactive → interactive conflict
# ---------------------------------------------------------------------------


def test_bidirectional_contract_A_interactive_interactive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two concurrent acquire calls with different session IDs: first wins,
    second is rejected with the R5 wording.

    No Python stubs — each acquire goes through the real console-script
    subprocess.  CORTEX_REPO_ROOT is redirected to tmp_path so lock files
    land in an isolated directory rather than the live repo.
    """
    # Ensure the cortex/ umbrella exists so the helper can write into it.
    (tmp_path / "cortex").mkdir(parents=True, exist_ok=True)

    base_env = os.environ.copy()
    base_env["CORTEX_REPO_ROOT"] = str(tmp_path)

    argv = _cortex_interactive_lock_argv()

    # First acquire: session-A
    env_a = {**base_env, "CLAUDE_CODE_SESSION_ID": "test-session-A"}
    result_a = subprocess.run(
        argv + ["acquire", "X"],
        env=env_a,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result_a.returncode == 0, (
        f"First acquire (session-A) should succeed; "
        f"stdout={result_a.stdout!r}, stderr={result_a.stderr!r}"
    )

    # Second acquire: session-B — must be rejected
    env_b = {**base_env, "CLAUDE_CODE_SESSION_ID": "test-session-B"}
    result_b = subprocess.run(
        argv + ["acquire", "X"],
        env=env_b,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result_b.returncode != 0, (
        f"Second acquire (session-B) should fail with non-zero exit; "
        f"stdout={result_b.stdout!r}, stderr={result_b.stderr!r}"
    )

    # Stderr must contain the R5 rejection wording (coupling point per spec R15).
    assert "work on a different feature" in result_b.stderr, (
        f"Second acquire stderr must contain 'work on a different feature' "
        f"(R5 coupling); got stderr={result_b.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Sub-test B — interactive → overnight (per-round scan)
# ---------------------------------------------------------------------------


def test_bidirectional_contract_B_interactive_overnight_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthetic live interactive.pid for Y causes compute_eligible_features
    to exclude Y and include only Z.

    Production code path: ``scan_live_locks`` (real function, called
    internally by ``compute_eligible_features``).  No stubs.
    """
    # Build the synthetic project root under tmp_path.
    feature_y_dir = tmp_path / "cortex" / "lifecycle" / "Y"
    feature_y_dir.mkdir(parents=True, exist_ok=True)

    # Write a live interactive.pid for feature Y.
    # Use test process's own PID so liveness checks succeed (same process
    # is alive, and CLAUDE_CODE_SESSION_ID env-var will match via monkeypatch).
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-B")

    import psutil
    pid = os.getpid()
    start_time = round(psutil.Process(pid).create_time(), 3)
    acquired_at = datetime.now(tz=timezone.utc).isoformat()

    lock_payload = {
        "schema_version": 1,
        "magic": "cortex-interactive-lock",
        "session_id": "test-session-B",
        "pid": pid,
        "start_time": start_time,
        "acquired_at": acquired_at,
    }
    lock_path = feature_y_dir / "interactive.pid"
    lock_path.write_text(json.dumps(lock_payload), encoding="utf-8")

    # scan_live_locks must report Y as live.
    live_set = scan_live_locks(tmp_path)
    assert "Y" in live_set, (
        f"scan_live_locks should detect Y as live; got {live_set!r}"
    )

    # compute_eligible_features must exclude Y and return one skip event.
    eligible, skip_events = compute_eligible_features(["Y", "Z"], tmp_path)

    assert "Y" not in eligible, (
        f"Y should be excluded from eligible; got eligible={eligible!r}"
    )
    assert "Z" in eligible, (
        f"Z should remain eligible; got eligible={eligible!r}"
    )

    assert len(skip_events) == 1, (
        f"Exactly one skip event expected; got {len(skip_events)}: {skip_events!r}"
    )
    skip_event = skip_events[0]
    assert skip_event.get("event") == "feature_skipped_interactive_active", (
        f"Unexpected event name: {skip_event.get('event')!r}"
    )
    rationale = skip_event.get("rationale", "")
    assert rationale, "skip event must have a non-empty rationale"
    assert "test-session-B" in rationale, (
        f"rationale must contain 'test-session-B'; got {rationale!r}"
    )


# ---------------------------------------------------------------------------
# Sub-test C — overnight → interactive rejection mirror (actual sidecar bash)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _bash_herestring_available(),
    reason=(
        "bash cannot create temp files for herestrings in this environment "
        "(Seatbelt write-deny on /tmp); test is designed for unrestricted CI"
    ),
)
def test_bidirectional_contract_C_overnight_interactive_rejection(
    tmp_path: Path,
) -> None:
    """Synthetic active-session.json + runner.pid causes the sidecar to exit 1
    with the R7 rejection wording on stderr.

    The sidecar at ``skills/lifecycle/references/_interactive_overnight_check.sh``
    is invoked via ``cat ... | bash -s -- '<wording>' '<repo>'`` — the same
    invocation shape used in implement.md §1 Step A.  No re-implementation of
    the four-bash-call logic in Python.
    """
    # Set up a synthetic HOME so the sidecar reads from our tmp dir.
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    # Session dir for the synthetic overnight session
    session_dir = tmp_path / "session-dir"
    session_dir.mkdir(parents=True)

    # The repo path that the sidecar will match against our $2 argument.
    fake_repo_path = str(tmp_path / "repo")

    # Write active-session.json under the fake home.
    active_sessions_dir = fake_home / ".local" / "share" / "overnight-sessions"
    active_sessions_dir.mkdir(parents=True)
    active_session_path = active_sessions_dir / "active-session.json"
    active_session_payload = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": os.getpid(),
        "pgid": os.getpid(),
        "session_id": "overnight-session-C",
        "session_dir": str(session_dir),
        "repo_path": fake_repo_path,
        "phase": "executing",
    }
    active_session_path.write_text(
        json.dumps(active_session_payload), encoding="utf-8"
    )

    # Write runner.pid in the session dir with the test process's PID so
    # kill -0 in the sidecar sees a live process.
    runner_pid_payload = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": os.getpid(),
        "pgid": os.getpid(),
        "session_id": "overnight-session-C",
        "session_dir": str(session_dir),
        "repo_path": fake_repo_path,
    }
    (session_dir / "runner.pid").write_text(
        json.dumps(runner_pid_payload), encoding="utf-8"
    )

    # Rejection wording that contains the R7 coupling substring.
    rejection_wording = (
        "Overnight runner is active (session overnight-session-C, PID {pid}, "
        "phase: executing) — wait for the run to complete "
        "(`cortex overnight status`), or open a different feature."
    ).format(pid=os.getpid())

    # Sidecar path — relative to repo root; the bash -c below CWDs to repo root.
    sidecar_rel = "skills/lifecycle/references/_interactive_overnight_check.sh"

    # Build the env with HOME redirected so the sidecar reads from tmp dir.
    # Set TMPDIR to a writable sandbox path so bash can create the temp files
    # it needs for herestring (<<<) constructs — the sidecar uses herestrings
    # when piping JSON into python3 for parsing.
    bash_tmpdir = tmp_path / "bash-tmp"
    bash_tmpdir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["TMPDIR"] = str(bash_tmpdir)

    result = subprocess.run(
        [
            "bash",
            "-c",
            f"cat {sidecar_rel} | bash -s -- '{rejection_wording}' '{fake_repo_path}'",
        ],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=30,
    )

    assert result.returncode != 0, (
        f"Sidecar should exit non-zero when overnight runner is live; "
        f"got returncode={result.returncode}, "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )

    # Stderr must contain the R7 coupling substring (spec R15 note).
    assert "the run to complete" in result.stderr, (
        f"Sidecar stderr must contain 'the run to complete' (R7 coupling); "
        f"got stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Sub-test D — lock release
# ---------------------------------------------------------------------------


def test_bidirectional_contract_D_lock_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """acquire X → file exists → release X → file absent → events.log has
    interactive_lock_released row.

    No Python stubs — both acquire and release go through the real
    console-script subprocess.
    """
    (tmp_path / "cortex").mkdir(parents=True, exist_ok=True)

    base_env = os.environ.copy()
    base_env["CORTEX_REPO_ROOT"] = str(tmp_path)
    base_env["CLAUDE_CODE_SESSION_ID"] = "test-session-D"

    argv = _cortex_interactive_lock_argv()
    lock_path = tmp_path / "cortex" / "lifecycle" / "X" / "interactive.pid"
    events_log_path = tmp_path / "cortex" / "lifecycle" / "X" / "events.log"

    # Acquire
    result_acq = subprocess.run(
        argv + ["acquire", "X"],
        env=base_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result_acq.returncode == 0, (
        f"acquire X should succeed; "
        f"stdout={result_acq.stdout!r}, stderr={result_acq.stderr!r}"
    )
    assert lock_path.exists(), (
        f"Lock file should exist after acquire; path={lock_path}"
    )

    # Release
    result_rel = subprocess.run(
        argv + ["release", "X"],
        env=base_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result_rel.returncode == 0, (
        f"release X should succeed; "
        f"stdout={result_rel.stdout!r}, stderr={result_rel.stderr!r}"
    )
    assert not lock_path.exists(), (
        f"Lock file should be absent after release; path={lock_path}"
    )

    # events.log must contain an interactive_lock_released event row.
    assert events_log_path.exists(), (
        f"events.log should exist after acquire+release; path={events_log_path}"
    )

    found_release_event = False
    for line in events_log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event") == "interactive_lock_released":
            found_release_event = True
            break

    assert found_release_event, (
        f"events.log must contain an 'interactive_lock_released' event row; "
        f"contents:\n{events_log_path.read_text(encoding='utf-8')}"
    )
