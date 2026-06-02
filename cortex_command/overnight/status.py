"""Live status display for overnight orchestration sessions.

Reads cortex/lifecycle/overnight-state.json and the session events log to
produce a single-screen status snapshot. Designed to be run in a
refresh loop via `just overnight-status`.

Usage:
    python3 -m cortex_command.overnight.status
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional

from cortex_command.common import _resolve_user_project_root
from cortex_command.overnight import ipc
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    latest_symlink_path,
    load_state,
    session_dir,
)


class FeatureBuckets(NamedTuple):
    """Per-feature grouping for the live status view.

    A feature with ``recoverable_branch`` set is the built-but-merge-blocked
    recoverable sub-case and is bucketed into ``recoverable`` rather than
    ``failed`` — surfaced distinctly so the operator sees it as recoverable on
    its branch, not as a plain failure.
    """

    running: list[tuple[str, Optional[str]]]
    pending: list[str]
    completed: list[str]
    failed: list[str]
    recoverable: list[str]


def bucket_features(features: dict[str, OvernightFeatureStatus]) -> FeatureBuckets:
    """Group features by status for the live status view.

    The ``recoverable_branch`` discriminator is checked first so a recoverable
    feature is never lumped into ``failed``.
    """
    running: list[tuple[str, Optional[str]]] = []
    pending: list[str] = []
    completed: list[str] = []
    failed: list[str] = []
    recoverable: list[str] = []

    for name, fs in features.items():
        if fs.recoverable_branch is not None:
            recoverable.append(name)
        elif fs.status == "running":
            running.append((name, fs.started_at))
        elif fs.status == "pending":
            pending.append(name)
        elif fs.status in ("merged",):
            completed.append(name)
        elif fs.status in ("failed", "deferred", "paused"):
            failed.append(name)

    return FeatureBuckets(running, pending, completed, failed, recoverable)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WATCHDOG_TIMEOUT_MINUTES = 30


def _events_symlink_path() -> Path:
    """Resolve the latest-overnight events.log symlink path at call time.

    Spec R3c forbids module-level capture of `_resolve_user_project_root()`;
    every consumer must invoke this function so the user's project root is
    resolved at the moment the path is needed.
    """
    lifecycle_root = _resolve_user_project_root() / "cortex" / "lifecycle"
    return latest_symlink_path("overnight", lifecycle_root=lifecycle_root) / "overnight-events.log"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp string (with timezone) into a datetime."""
    return datetime.fromisoformat(ts)


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as a human-readable string (e.g. '1h 23m 45s')."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def _resolve_events_log(session_id: str) -> Path | None:
    """Return the events log path to use, or None if unavailable.

    Tries the symlink first. If the symlink exists but its target is
    missing (broken), falls back to the per-session file derived from
    session_id. Returns None if neither is readable.
    """
    events_symlink = _events_symlink_path()
    # Check if symlink exists and its target is readable
    if events_symlink.is_symlink():
        target = events_symlink.resolve() if events_symlink.exists() else None
        if target is not None and target.exists():
            return events_symlink
        # Symlink is broken — fall back to per-session file
    elif events_symlink.exists():
        # Regular file (pre-Task-1 layout) — use it directly
        return events_symlink

    # Fall back to per-session file
    per_session = session_dir(session_id, lifecycle_root=_resolve_user_project_root() / "cortex" / "lifecycle") / "overnight-events.log"
    if per_session.exists():
        return per_session

    return None


def _is_runner_pid_live(session_dir_path: Path) -> bool:
    """Return True iff a live runner has claimed ``runner.pid`` in the dir.

    Reads the explicit per-session ``runner.pid`` and validates it via
    :func:`ipc.verify_runner_pid`. Returns False when no PID file exists,
    the payload is malformed, or the recorded process is not alive.
    """
    pid_data = ipc.read_runner_pid(session_dir_path)
    if pid_data is None:
        return False
    return ipc.verify_runner_pid(pid_data)


def _is_scheduled_dormant(state, session_dir_path: Path, now: datetime) -> bool:
    """Return True iff the session should render as scheduled-dormant.

    Display-only state inferred at read time (Task 11 / R12). The predicate
    is **conjunctive** (F5) so a just-fired run — which clears
    ``scheduled_start`` (R13) and/or claims ``runner.pid`` — is never shown
    dormant despite clock skew near the fire boundary:

      1. ``scheduled_start`` is set and strictly in the future, AND
      2. no live ``runner.pid`` claims the session, AND
      3. the session is not executing or complete.

    No value is added to the persisted ``PHASES`` tuple and no new ``phase``
    field value is written — the dormant state is purely a render-time
    inference, mirroring the ``starting`` display precedent.
    """
    scheduled_start = getattr(state, "scheduled_start", None)
    if not scheduled_start:
        return False
    try:
        fires_at = _parse_iso(scheduled_start)
    except ValueError:
        return False
    if fires_at <= now:
        return False
    if state.phase in ("executing", "complete"):
        return False
    return not _is_runner_pid_live(session_dir_path)


def _read_last_event(log_path: Path) -> dict | None:
    """Return the last parseable JSON event from the log, or None."""
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        return None

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in reversed(lines):
        try:
            evt = json.loads(line)
            if isinstance(evt, dict) and "event" in evt:
                return evt
        except json.JSONDecodeError:
            continue
    return None


def _read_last_event_ts(log_path: Path) -> datetime | None:
    """Return the timestamp of the last parseable event in the log, or None.

    Returns None if the log is unavailable, the last event lacks a ``ts``
    field, or the timestamp cannot be parsed.
    """
    evt = _read_last_event(log_path)
    if evt is None:
        return None
    ts_str = evt.get("ts", "")
    if not ts_str:
        return None
    try:
        return _parse_iso(ts_str)
    except ValueError:
        return None


def _read_session_start(log_path: Path) -> dict | None:
    """Return the last session_start event details from the log, or None."""
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        return None

    last_start = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(evt, dict) and evt.get("event", "").lower() == "session_start":
            last_start = evt
    return last_start


def _count_zero_progress_rounds(log_path: Path) -> int:
    """Count consecutive zero-progress rounds (stall counter) from events."""
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        return 0

    # Collect feature_complete events in order
    round_merges: dict[int, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(evt, dict):
            continue
        event_type = evt.get("event", "").lower()
        round_num = evt.get("round", 0)
        if event_type == "feature_complete":
            round_merges[round_num] = round_merges.get(round_num, 0) + 1

    if not round_merges:
        return 0

    # Count consecutive zero-merge rounds from the end
    max_round = max(round_merges.keys())
    stall = 0
    for r in range(max_round, 0, -1):
        if round_merges.get(r, 0) == 0:
            stall += 1
        else:
            break
    return stall


# ---------------------------------------------------------------------------
# Main display
# ---------------------------------------------------------------------------

def _find_latest_state_path() -> Optional[Path]:
    """Find the most relevant overnight state file.

    Prefers the most recently modified session with phase 'executing'.
    Falls back to the most recently modified session of any phase.
    Never reads through the latest-overnight symlink to avoid stale data.
    """
    sessions_dir = _resolve_user_project_root() / "cortex" / "lifecycle" / "sessions"
    if not sessions_dir.exists():
        return None

    candidates = sorted(
        (
            p for p in sessions_dir.glob("*/overnight-state.json")
            # Skip the symlink entry to avoid stale-symlink races
            if not p.parent.is_symlink()
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    # Prefer executing session
    for path in candidates:
        try:
            import json as _json
            if _json.loads(path.read_text()).get("phase") == "executing":
                return path
        except Exception:
            continue

    # Fall back to most recently modified
    return candidates[0] if candidates else None


def render_status() -> None:
    """Print a single status snapshot to stdout."""
    # --- Load state ---
    state_path = _find_latest_state_path()
    if state_path is None or not state_path.exists():
        print("No active session")
        return

    try:
        state = load_state(state_path)
    except Exception as exc:
        print(f"Error reading state: {exc}")
        return

    # --- Resolve events log ---
    log_path = _resolve_events_log(state.session_id)

    # --- Session-level metadata ---
    now = _now()
    session_elapsed = (now - _parse_iso(state.started_at)).total_seconds()

    # --- Scheduled-dormant inference (Task 11 / R12) ---
    # Display-only state inferred at read time from the explicit per-session
    # state path (state_path.parent is the session dir holding runner.pid).
    # When dormant, the session is merely waiting to fire — so the
    # executing/elapsed-watchdog block is suppressed and a dormant line is
    # rendered instead.
    is_dormant = _is_scheduled_dormant(state, state_path.parent, now)

    # Read SESSION_START for time_limit_hours and max_rounds
    time_limit_hours: int | None = None
    max_rounds: int | None = None
    if log_path is not None:
        session_start_evt = _read_session_start(log_path)
        if session_start_evt:
            details = session_start_evt.get("details", {})
            time_limit_hours = details.get("time_limit_hours")
            max_rounds = details.get("max_rounds")

    # Time remaining
    time_remaining_str = "unknown"
    if time_limit_hours is not None:
        time_limit_seconds = time_limit_hours * 3600
        remaining = time_limit_seconds - session_elapsed
        if remaining > 0:
            time_remaining_str = _format_elapsed(remaining)
        else:
            time_remaining_str = "0s (expired)"

    # --- Feature grouping ---
    running, pending, completed, failed, recoverable = bucket_features(state.features)

    # --- Last event ---
    last_event_str = "none"
    if log_path is not None:
        last_evt = _read_last_event(log_path)
        if last_evt:
            ts_str = last_evt.get("ts", "")
            event_type = last_evt.get("event", "?")
            feature = last_evt.get("feature", "")
            if ts_str:
                try:
                    ts_dt = _parse_iso(ts_str)
                    ago = (now - ts_dt).total_seconds()
                    ago_str = _format_elapsed(ago)
                    if feature:
                        last_event_str = f"{event_type} ({feature}) — {ago_str} ago"
                    else:
                        last_event_str = f"{event_type} — {ago_str} ago"
                except ValueError:
                    last_event_str = f"{event_type}"
            else:
                last_event_str = event_type

    # --- Stall counter ---
    stall_count = 0
    if log_path is not None:
        stall_count = _count_zero_progress_rounds(log_path)

    # --- Watchdog ---
    # Suppressed in the scheduled-dormant state: a run merely waiting to fire
    # has no live runner, so an "elapsed since last event" watchdog would be a
    # misleading alarm (R12).
    watchdog_str: str | None = None
    if not is_dormant and state.phase == "executing" and log_path is not None:
        last_ts = _read_last_event_ts(log_path)
        if last_ts is not None:
            try:
                since_last = (now - last_ts).total_seconds()
                watchdog_str = (
                    f"{_format_elapsed(since_last)} since last event"
                    f" (fires at {WATCHDOG_TIMEOUT_MINUTES}m)"
                )
            except Exception:
                pass

    # --- Render ---
    round_display = str(state.current_round)
    if max_rounds is not None:
        round_display = f"{state.current_round}/{max_rounds}"

    print(f"Overnight Session: {state.session_id}")
    print(f"Phase            : {state.phase}")
    print(f"Round            : {round_display}")
    if is_dormant:
        # Display-only scheduled-dormant render: no live runner, fire pending.
        # Suppress the Elapsed/Time-remaining/Stall/Watchdog block — those are
        # executing-run metrics that would read as an alarm while merely
        # waiting to fire (R12).
        print(f"Scheduled (dormant) — fires at {state.scheduled_start}")
    else:
        print(f"Elapsed          : {_format_elapsed(session_elapsed)}")
        print(f"Time remaining   : {time_remaining_str}")
        print(f"Stall counter    : {stall_count}/2")
        print(f"Last event       : {last_event_str}")
        if watchdog_str is not None:
            print(f"Watchdog         : {watchdog_str}")
    print()

    if running:
        print(f"Running ({len(running)}):")
        for name, started_at in running:
            if started_at:
                try:
                    elapsed = (now - _parse_iso(started_at)).total_seconds()
                    elapsed_str = _format_elapsed(elapsed)
                except ValueError:
                    elapsed_str = "?"
            else:
                elapsed_str = "?"
            print(f"  - {name}  [{elapsed_str}]")
    else:
        print("Running (0): —")

    print()

    if pending:
        print(f"Pending ({len(pending)}):")
        for name in pending:
            print(f"  - {name}")
    else:
        print("Pending (0): —")

    print()

    if completed:
        print(f"Completed ({len(completed)}):")
        for name in completed:
            print(f"  - {name}")
    else:
        print("Completed (0): —")

    if failed:
        print()
        print(f"Failed/Deferred ({len(failed)}):")
        for name in failed:
            fs = state.features[name]
            suffix = f"  [{fs.status}]"
            if fs.error:
                suffix += f"  error: {fs.error[:60]}"
            print(f"  - {name}{suffix}")

    if recoverable:
        print()
        print(f"Recoverable ({len(recoverable)}):")
        for name in recoverable:
            fs = state.features[name]
            print(f"  - {name}  built, merge-blocked, recoverable on {fs.recoverable_branch}")


def main() -> None:
    """Entry point: render one status snapshot and exit."""
    try:
        render_status()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
