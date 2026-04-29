"""Data parsers for the dashboard.

Pure functions that read project state files and return parsed data
structures. All file I/O is wrapped in try/except so parsers never raise
on missing or malformed files.

Functions:
    parse_overnight_state  -- reads lifecycle/overnight-state.json
    parse_pipeline_state   -- reads lifecycle/pipeline-state.json
    tail_jsonl             -- byte-offset-aware JSONL tail utility
    parse_feature_events   -- reads lifecycle/{feature}/events.log
    parse_plan_progress    -- reads lifecycle/{feature}/plan.md
    parse_agent_activity   -- reads lifecycle/{feature}/agent-activity.jsonl
    get_last_activity_ts   -- most recent event timestamp for a feature
    parse_fleet_cards      -- builds agent fleet cards for running features
    build_swim_lane_data   -- builds swim lane timeline data for a session
    parse_last_session     -- summary of the most recently completed session
    parse_session_list     -- summary rows for all completed sessions
    parse_session_detail   -- all data for a single session detail page
    parse_backlog_counts   -- counts backlog items by status
    parse_backlog_titles   -- maps lifecycle slug → human-readable backlog title
    _read_all_jsonl        -- reads all JSONL events from byte 0 (initial-read primitive)
    parse_feature_cost_delta -- incremental cost delta and new byte offset for a feature
    parse_metrics          -- reads lifecycle/metrics.json
    compute_slow_flags     -- identifies running features slower than 3x median for their phase
    parse_feature_timestamps -- extracts start/complete timestamps and duration per feature slug
    parse_round_timestamps   -- extracts start/complete timestamps per round number from overnight events
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

import markdown

from cortex_command.common import detect_lifecycle_phase, normalize_status, slugify


def parse_overnight_state(path: Path) -> dict | None:
    """Read and return the overnight session state as a plain dict.

    Args:
        path: Path to overnight-state.json (typically
            ``lifecycle/overnight-state.json``).

    Returns:
        Parsed JSON dict, or None if the file is absent or unreadable.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def parse_pipeline_state(path: Path) -> dict | None:
    """Read and return the pipeline state as a plain dict.

    The file is deleted on pipeline completion, so a missing file is the
    normal "no active pipeline" signal — return None cleanly.

    Args:
        path: Path to pipeline-state.json (typically
            ``lifecycle/pipeline-state.json``).

    Returns:
        Parsed JSON dict, or None if the file is absent or unreadable.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def tail_jsonl(
    path: Path,
    last_n: int = 200,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Read JSONL events from a file using byte-offset tracking.

    Two modes of operation:

    **Initial read** (``offset == 0``):
        Seek to the end of the file, walk backwards to find the last
        ``last_n`` newline-terminated lines, parse and return those
        events, and return the current end-of-file position as the new
        offset.

    **Incremental read** (``offset > 0``):
        Seek to ``offset``, read all bytes written since that position,
        parse each line as JSON (skipping malformed lines), and return
        the new events plus the new file size.

    Malformed JSON lines are silently skipped in both modes.

    Args:
        path: Path to the ``.jsonl`` file.
        last_n: Maximum number of events to return on initial read
            (ignored when ``offset > 0``).
        offset: Byte offset from a previous call, or 0 for initial read.

    Returns:
        A ``(events, new_offset)`` tuple. Returns ``([], 0)`` when the
        file is absent or an OS error occurs.
    """
    try:
        with path.open("rb") as fh:
            if offset == 0:
                # Seek to end to get file size
                fh.seek(0, 2)
                end = fh.tell()
                new_offset = end

                if end == 0:
                    return [], 0

                # Walk backwards through the file counting newlines.
                # We want to find the byte position just after the
                # (last_n)-th newline from the end (skipping any trailing
                # newline on the very last line so it isn't double-counted).
                #
                # Strategy: scan from (end - 1) backwards, counting \n
                # characters.  The first \n we encounter is the terminator
                # of the last line — skip it.  Each subsequent \n is a line
                # boundary.  After seeing last_n of those boundaries, the
                # start position is the byte *after* that \n.
                chunk_size = 4096
                scan_pos = end  # current scan pointer (exclusive upper bound)
                newlines_seen = 0
                start_pos = 0   # default: read from beginning

                found = False
                while scan_pos > 0 and not found:
                    read_end = scan_pos
                    read_start = max(0, scan_pos - chunk_size)
                    fh.seek(read_start)
                    chunk = fh.read(read_end - read_start)
                    # Iterate the chunk right-to-left, tracking chunk index
                    for i in range(len(chunk) - 1, -1, -1):
                        if chunk[i] == ord(b"\n"):
                            newlines_seen += 1
                            # The very first \n is the trailing newline of
                            # the last line — it doesn't delimit a new line,
                            # so don't count it toward last_n.
                            if newlines_seen > last_n:
                                # Byte after this \n is the start of the
                                # first line we want to keep.
                                start_pos = read_start + i + 1
                                found = True
                                break
                    scan_pos = read_start

                fh.seek(start_pos)
                tail_bytes = fh.read(end - start_pos)
            else:
                # Incremental: read only new bytes since last offset
                fh.seek(0, 2)
                new_offset = fh.tell()

                if new_offset <= offset:
                    return [], new_offset

                fh.seek(offset)
                tail_bytes = fh.read(new_offset - offset)

            # Decode and parse lines, normalizing event names to lowercase
            # for backward compat with older logs that used UPPERCASE names
            events: list[dict] = []
            text = tail_bytes.decode("utf-8", errors="replace")
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        if "event" in obj:
                            obj["event"] = str(obj["event"]).lower()
                        events.append(obj)
                except json.JSONDecodeError:
                    pass  # silently skip malformed lines

            return events, new_offset

    except OSError:
        return [], 0


def _read_all_jsonl(path: Path) -> tuple[list[dict], int]:
    """Read all JSONL events from a file starting at byte 0.

    Unlike ``tail_jsonl``, this always reads from the beginning of the file
    rather than seeking to the end first.  It is the initial-read primitive
    used by ``parse_feature_cost_delta`` when no prior offset exists.

    Malformed JSON lines are silently skipped.

    Args:
        path: Path to the ``.jsonl`` file.

    Returns:
        A ``(events, byte_count)`` tuple where ``byte_count`` is the total
        number of bytes read (i.e. the new byte offset).  Returns ``([], 0)``
        when the file is absent or an OS error occurs.
    """
    try:
        with path.open("rb") as fh:
            raw = fh.read()
        byte_count = len(raw)
        if byte_count == 0:
            return [], 0
        text = raw.decode("utf-8", errors="replace")
        events: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    if "event" in obj:
                        obj["event"] = str(obj["event"]).lower()
                    events.append(obj)
            except json.JSONDecodeError:
                pass
        return events, byte_count
    except OSError:
        return [], 0


def parse_feature_cost_delta(path: Path, offset: int) -> tuple[float, int]:
    """Return the incremental cost increase and new byte offset for a feature.

    Reads only new bytes since the last call (using ``offset`` as the byte
    position), sums ``cost_usd`` from ``turn_complete`` events in those new
    bytes, and returns the delta plus the updated offset.

    On the first call (``offset == 0``), all bytes are read via
    ``_read_all_jsonl``.  On subsequent calls, only bytes written since
    ``offset`` are fetched via ``tail_jsonl``.

    Args:
        path: Path to ``agent-activity.jsonl`` for the feature.
        offset: Byte offset from a previous call, or 0 for the initial read.

    Returns:
        A ``(delta_cost, new_offset)`` tuple.  ``delta_cost`` is the sum of
        ``cost_usd`` from new ``turn_complete`` events (0.0 when none).
        ``new_offset`` is unchanged when the file is absent or has no new
        data.  Returns ``(0.0, offset)`` on error or when nothing new is
        available.
    """
    if offset == 0:
        events, new_offset = _read_all_jsonl(path)
    else:
        events, new_offset = tail_jsonl(path, offset=offset)

    if not events:
        # File absent, empty, or no new bytes: keep the offset unchanged.
        # When _read_all_jsonl returns ([], 0) for a missing file, new_offset
        # is already 0 which matches the incoming offset (also 0).
        # When tail_jsonl finds no new data, new_offset >= offset, but we
        # preserve offset semantics: return the caller's offset unchanged so
        # the poller knows no progress was made.
        return 0.0, offset

    delta_cost = 0.0
    for event in events:
        if event.get("event") == "turn_complete":
            try:
                delta_cost += float(event.get("cost_usd") or 0.0)
            except (TypeError, ValueError):
                pass

    return delta_cost, new_offset


def parse_feature_events(feature_slug: str, lifecycle_dir: Path) -> dict:
    """Parse phase transitions and rework cycles from a feature's events.log.

    Reads ``lifecycle/{feature_slug}/events.log`` via
    ``cortex_command.pipeline.metrics.parse_events()``.

    Args:
        feature_slug: Feature directory name under ``lifecycle/``.
        lifecycle_dir: Path to the ``lifecycle/`` directory.

    Returns:
        Dict with keys:

        - ``current_phase`` (str | None): the ``to`` field of the most
          recent ``phase_transition`` event, or None if absent.
        - ``phase_transitions`` (list[dict]): each entry has ``from``,
          ``to``, and ``ts`` keys.
        - ``rework_cycles`` (int): count of ``to == "implement"``
          transitions that follow a ``to == "review"`` transition.

        Returns ``{"current_phase": None, "phase_transitions": [],
        "rework_cycles": 0}`` when the file is absent or unreadable.
    """
    default: dict = {"current_phase": None, "phase_transitions": [], "rework_cycles": 0}
    path = lifecycle_dir / feature_slug / "events.log"
    try:
        from cortex_command.pipeline.metrics import parse_events  # local import to stay testable

        events = parse_events(path)
    except (OSError, Exception):
        return default

    transitions = [e for e in events if e.get("event") == "phase_transition"]

    phase_transitions = [
        {"from": t.get("from"), "to": t.get("to"), "ts": t.get("ts")}
        for t in transitions
    ]

    feature_dir = lifecycle_dir / feature_slug
    current_phase: str | None = detect_lifecycle_phase(feature_dir)["phase"]

    # Count rework cycles: number of "implement" transitions that follow a
    # "review" transition immediately before them.
    rework_cycles = 0
    for i in range(1, len(transitions)):
        prev_to = transitions[i - 1].get("to")
        curr_to = transitions[i].get("to")
        if prev_to == "review" and curr_to == "implement":
            rework_cycles += 1

    return {
        "current_phase": current_phase,
        "phase_transitions": phase_transitions,
        "rework_cycles": rework_cycles,
    }


def parse_plan_progress(
    feature_slug: str, lifecycle_dir: Path
) -> tuple[int, int] | None:
    """Count completed and total checkbox items in a feature's plan.md.

    Args:
        feature_slug: Feature directory name under ``lifecycle/``.
        lifecycle_dir: Path to the ``lifecycle/`` directory.

    Returns:
        ``(completed, total)`` tuple where ``completed`` is the count of
        ``[x]`` occurrences and ``total`` is completed + pending (``[ ]``).
        Returns ``None`` if the file is absent or unreadable.
    """
    path = lifecycle_dir / feature_slug / "plan.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    completed = len(re.findall(r"\[x\]", text, re.IGNORECASE))
    pending = len(re.findall(r"\[ \]", text))
    return (completed, completed + pending)


def parse_agent_activity(
    feature_slug: str, lifecycle_dir: Path, last_n: int = 50
) -> list[dict]:
    """Return the last ``last_n`` events from a feature's agent-activity.jsonl.

    Reads lines from the end of the file without tracking a byte offset
    (non-incremental simple tail).  Malformed JSON lines are silently skipped.

    Args:
        feature_slug: Feature directory name under ``lifecycle/``.
        lifecycle_dir: Path to the ``lifecycle/`` directory.
        last_n: Maximum number of lines to return from the file end.

    Returns:
        List of parsed event dicts.  Returns ``[]`` if the file is absent
        or unreadable.
    """
    path = lifecycle_dir / feature_slug / "agent-activity.jsonl"
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            end = fh.tell()
            if end == 0:
                return []

            chunk_size = 4096
            scan_pos = end
            newlines_seen = 0
            start_pos = 0
            found = False

            while scan_pos > 0 and not found:
                read_end = scan_pos
                read_start = max(0, scan_pos - chunk_size)
                fh.seek(read_start)
                chunk = fh.read(read_end - read_start)
                for i in range(len(chunk) - 1, -1, -1):
                    if chunk[i] == ord(b"\n"):
                        newlines_seen += 1
                        if newlines_seen > last_n:
                            start_pos = read_start + i + 1
                            found = True
                            break
                scan_pos = read_start

            fh.seek(start_pos)
            tail_bytes = fh.read(end - start_pos)

        events: list[dict] = []
        text = tail_bytes.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    events.append(obj)
            except json.JSONDecodeError:
                pass
        return events

    except OSError:
        return []


def get_last_activity_ts(feature_slug: str, lifecycle_dir: Path) -> "datetime | None":
    """Return the most recent event timestamp for a feature across both log files.

    Checks ``agent-activity.jsonl`` and ``events.log`` for the feature, parses
    their most recent ``ts`` field, and returns the later of the two as a
    timezone-aware datetime.

    Args:
        feature_slug: Feature directory name under ``lifecycle/``.
        lifecycle_dir: Path to the ``lifecycle/`` directory.

    Returns:
        The most recent datetime (UTC), or None if no timestamped events exist.
    """
    def _parse_ts(ts_str: str | None) -> "datetime | None":
        if not ts_str:
            return None
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None

    candidates: list[datetime] = []

    # agent-activity.jsonl — last 1 event
    activity = parse_agent_activity(feature_slug, lifecycle_dir, last_n=1)
    if activity:
        dt = _parse_ts(activity[-1].get("ts"))
        if dt is not None:
            candidates.append(dt)

    # events.log — last 1 event via tail_jsonl
    events_path = lifecycle_dir / feature_slug / "events.log"
    events, _ = tail_jsonl(events_path, last_n=1, offset=0)
    if events:
        dt = _parse_ts(events[-1].get("ts"))
        if dt is not None:
            candidates.append(dt)

    return max(candidates) if candidates else None


def parse_fleet_cards(
    overnight: dict,
    overnight_events: list,
    feature_states: dict,
    lifecycle_dir: Path,
    agent_activity_offsets: dict,
) -> tuple[list[dict], dict]:
    """Build fleet card dicts for all currently-running features.

    For each feature with ``status == "running"`` in ``overnight["features"]``,
    constructs a card with slug, current phase, formatted duration, and last
    activity timestamp.

    Args:
        overnight: Parsed overnight-state.json dict.
        overnight_events: Accumulated list of overnight event dicts.
        feature_states: Per-feature parsed state from ``parse_feature_events``.
        lifecycle_dir: Path to the ``lifecycle/`` directory.
        agent_activity_offsets: Byte offsets per feature slug (reserved for
            incremental tailing; currently passed through unchanged).

    Returns:
        ``(fleet_cards, new_offsets)`` where ``fleet_cards`` is a list of dicts
        with ``slug``, ``current_phase``, ``duration_str``, and
        ``last_activity_str`` keys; ``new_offsets`` mirrors the input offsets.
    """
    now = datetime.now(timezone.utc)
    fleet_cards: list[dict] = []

    for slug, feat in overnight.get("features", {}).items():
        if feat.get("status") != "running":
            continue

        # Find the most-recent feature_start event for this slug
        start_ts: str | None = None
        for event in overnight_events:
            if event.get("event") == "feature_start" and event.get("feature") == slug:
                start_ts = event.get("ts")
                # Don't break — use the last matching event in case of retries

        duration_str = "—"
        if start_ts:
            try:
                start_dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                total_secs = int((now - start_dt).total_seconds())
                m, s = divmod(total_secs, 60)
                duration_str = f"{m}m {s}s"
            except (ValueError, TypeError):
                pass

        # Last activity from agent-activity.jsonl
        activity_events = parse_agent_activity(slug, lifecycle_dir, last_n=1)
        last_activity_ts = (activity_events[-1].get("ts") or None) if activity_events else None

        current_phase = (feature_states.get(slug) or {}).get("current_phase")

        fleet_cards.append({
            "slug": slug,
            "current_phase": current_phase or "—",
            "duration_str": duration_str,
            "last_activity_ts": last_activity_ts,
        })

    return fleet_cards, dict(agent_activity_offsets)


def build_swim_lane_data(
    overnight: dict | None,
    overnight_events: list,
    feature_states: dict,
    lifecycle_dir: Path,
    end_dt: datetime | None = None,
) -> dict:
    """Build swim lane timeline data for the current overnight session.

    Produces one lane per feature with positioned event boxes derived from
    ``overnight_events`` (feature_start/complete/paused/failed events) and
    ``feature_states`` phase transitions.

    Args:
        overnight: Parsed overnight-state.json dict, or None.
        overnight_events: Accumulated list of overnight event dicts.
        feature_states: Per-feature parsed state from ``parse_feature_events``.
        lifecycle_dir: Path to the ``lifecycle/`` directory (currently unused;
            reserved for future agent-activity tick integration).
        end_dt: Optional fixed "now" datetime for historical rendering; defaults
            to ``datetime.now(timezone.utc)`` when not provided.

    Returns:
        Dict with keys:
        - ``lanes`` (list[dict]): one per feature, each with ``slug``,
          ``color``, ``events`` (list[dict]), ``tool_tick_xs`` (list[float]).
        - ``summary_mode`` (bool): True when total event count > 200.
        - ``total_elapsed_secs`` (float): seconds since session_start.
        - ``session_start_ts`` (str | None): the session_start timestamp.

        Returns ``{"lanes": [], "summary_mode": False, "total_elapsed_secs": 0,
        "session_start_ts": None}`` when no overnight session or no
        session_start event is present.
    """
    _empty: dict = {
        "lanes": [],
        "summary_mode": False,
        "total_elapsed_secs": 0,
        "session_start_ts": None,
        "ticks": [],
    }

    _phase_transition_abbrev = {
        "research→specify": "→spec",
        "specify→plan": "→plan",
        "plan→implement": "→impl",
        "implement→review": "→rev",
        "review→complete": "→done",
    }

    def _format_elapsed_secs(secs: float) -> str:
        total_minutes = int(secs // 60)
        if total_minutes == 0:
            return "0m"
        if total_minutes < 60:
            return f"{total_minutes}m"
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}h {minutes}m"

    if not overnight:
        return _empty

    # Find session_start event
    session_start_ts: str | None = None
    for event in overnight_events:
        if event.get("event") == "session_start":
            session_start_ts = event.get("ts")
            break

    if not session_start_ts:
        return _empty

    try:
        session_start_dt = datetime.fromisoformat(session_start_ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return _empty

    now = end_dt if end_dt is not None else datetime.now(timezone.utc)
    total_elapsed_secs = max(1.0, (now - session_start_dt).total_seconds())

    # Summary mode: skip tool ticks when total event volume is high
    features = overnight.get("features", {})
    total_event_count = len(overnight_events) + sum(
        len((feature_states.get(s) or {}).get("phase_transitions", []))
        for s in features
    )
    summary_mode = total_event_count > 200

    _overnight_event_types = {"feature_start", "feature_complete", "feature_paused", "feature_failed"}

    lanes: list[dict] = []
    for slug, feat in features.items():
        status = feat.get("status", "pending")

        lane_events: list[dict] = []

        def _make_event(event_type: str, ts: str, label: str) -> dict | None:
            try:
                event_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                elapsed = (event_dt - session_start_dt).total_seconds()
                x_pct = min(100.0, max(0.0, (elapsed / total_elapsed_secs) * 100))
                return {
                    "event_type": event_type,
                    "ts": ts,
                    "elapsed_secs": elapsed,
                    "x_pct": x_pct,
                    "label": label,
                    "tooltip": f"{event_type} | {ts} | +{elapsed:.0f}s",
                }
            except (ValueError, TypeError):
                return None

        # feature_* events from overnight_events
        for event in overnight_events:
            if event.get("feature") == slug and event.get("event") in _overnight_event_types:
                ts = event.get("ts", "")
                event_type = event.get("event", "")
                label = event_type.replace("feature_", "")
                entry = _make_event(event_type, ts, label)
                if entry is not None:
                    lane_events.append(entry)

        # Phase transitions from feature_states
        fs = feature_states.get(slug) or {}
        for pt in fs.get("phase_transitions", []):
            ts = pt.get("ts", "")
            raw_label = f"{pt.get('from', '?')}→{pt.get('to', '?')}"
            label = _phase_transition_abbrev.get(raw_label, raw_label)
            entry = _make_event("phase_transition", ts, label)
            if entry is not None:
                lane_events.append(entry)

        lanes.append({
            "slug": slug,
            "status": status,
            "events": lane_events,
            "tool_tick_xs": [],  # reserved for future agent-activity integration
        })

    # Build time axis ticks
    ticks: list[dict] = []
    if total_elapsed_secs > 0:
        tick_count = max(3, min(8, int(total_elapsed_secs // 1800)))
        if tick_count >= 2:
            interval_secs = total_elapsed_secs / (tick_count - 1)
            for i in range(tick_count):
                x_pct = (i * interval_secs / total_elapsed_secs) * 100
                ticks.append({
                    "x_pct": x_pct,
                    "label": _format_elapsed_secs(i * interval_secs),
                })

    return {
        "session_start_ts": session_start_ts,
        "total_elapsed_secs": total_elapsed_secs,
        "summary_mode": summary_mode,
        "lanes": lanes,
        "ticks": ticks,
    }


def parse_last_session(lifecycle_dir: Path) -> dict | None:
    """Return a summary dict for the most recently completed overnight session.

    Globs ``lifecycle_dir/sessions/*/overnight-state.json``, parses each file,
    and returns a summary for the session with the latest ``updated_at``
    timestamp.

    Args:
        lifecycle_dir: Path to the ``lifecycle/`` directory.

    Returns:
        Dict with keys:
        - ``session_id`` (str)
        - ``features_merged`` (int)
        - ``features_failed`` (int)
        - ``features_total`` (int)
        - ``ended_hours_ago`` (float)

        Returns None if ``lifecycle_dir/sessions/`` is absent, empty, or all
        files are unreadable.
    """
    sessions_dir = lifecycle_dir / "sessions"
    try:
        candidates = list(sessions_dir.glob("*/overnight-state.json"))
    except OSError:
        return None

    if not candidates:
        return None

    best: dict | None = None
    best_updated: datetime | None = None

    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        updated_str = data.get("updated_at", "")
        try:
            updated_dt = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        if best_updated is None or updated_dt > best_updated:
            best = data
            best_updated = updated_dt

    if best is None or best_updated is None:
        return None

    features = best.get("features", {})
    statuses = [f.get("status", "") for f in features.values()]
    ended_hours_ago = (datetime.now(timezone.utc) - best_updated).total_seconds() / 3600

    return {
        "session_id": best.get("session_id", ""),
        "features_merged": statuses.count("merged"),
        "features_failed": statuses.count("failed"),
        "features_total": len(statuses),
        "ended_hours_ago": ended_hours_ago,
    }


def parse_session_list(lifecycle_dir: Path) -> list[dict]:
    """Return a summary row for every completed overnight session found on disk.

    Globs ``lifecycle_dir/sessions/*/overnight-state.json``, extracts a
    summary dict from each readable file, and returns all rows sorted
    most-recent-first by ``end_ts`` (sessions with no parseable ``end_ts``
    are appended at the end in arbitrary order).

    Args:
        lifecycle_dir: Path to the ``lifecycle/`` directory.

    Returns:
        List of dicts, each with keys:

        - ``session_id`` (str)
        - ``start_ts`` (str | None) -- ISO-8601 value of ``started_at``
        - ``end_ts`` (str | None) -- ISO-8601 value of ``updated_at``
        - ``duration_secs`` (int | None) -- whole seconds between start and end
        - ``features_merged`` (int)
        - ``features_paused`` (int)
        - ``features_failed`` (int)
        - ``features_total`` (int)

        Returns ``[]`` if the sessions directory is absent, empty, or all
        files are unreadable.
    """
    sessions_dir = lifecycle_dir / "sessions"
    try:
        candidates = list(sessions_dir.glob("*/overnight-state.json"))
    except OSError:
        return []

    rows: list[dict] = []

    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(data, dict):
            continue

        session_id: str = data.get("session_id", path.parent.name)

        start_ts: str | None = data.get("started_at") or None
        end_ts: str | None = data.get("updated_at") or None

        duration_secs: int | None = None
        if start_ts is not None and end_ts is not None:
            try:
                start_dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
                duration_secs = int((end_dt - start_dt).total_seconds())
            except (ValueError, TypeError):
                pass

        features = data.get("features", {})
        if not isinstance(features, dict):
            features = {}
        statuses = [f.get("status", "") for f in features.values() if isinstance(f, dict)]

        rows.append({
            "session_id": session_id,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "duration_secs": duration_secs,
            "features_merged": statuses.count("merged"),
            "features_paused": statuses.count("paused"),
            "features_failed": statuses.count("failed"),
            "features_total": len(statuses),
        })

    def _sort_key(row: dict):
        ts = row["end_ts"]
        if ts is None:
            return (1, "")
        return (0, ts)

    rows.sort(key=_sort_key, reverse=True)
    return rows


def parse_session_detail(session_id: str, lifecycle_dir: Path) -> dict | None:
    """Load all data for a single session detail page.

    Reads ``overnight-state.json``, renders ``morning-report.md`` as HTML,
    loads per-feature phase transitions, and builds swim lane data from
    ``overnight-events.log``.

    Args:
        session_id: Directory name of the session (e.g. ``"overnight-2026-02-26-2129"``).
        lifecycle_dir: Path to the ``lifecycle/`` directory.

    Returns:
        Dict with keys ``session_id``, ``start_ts``, ``end_ts``,
        ``duration_str``, ``morning_report_html``, ``swim_data``,
        ``features_merged``, ``features_paused``, ``features_failed``,
        ``features_total``.  Returns ``None`` if the session directory does
        not exist.
    """
    session_dir = lifecycle_dir / "sessions" / session_id
    if not session_dir.exists():
        return None

    # Load events from overnight-events.log
    events = tail_jsonl(session_dir / "overnight-events.log", last_n=2000, offset=0)[0]

    # Determine end_dt: scan for last session_complete event
    end_dt: datetime | None = None
    for event in reversed(events):
        if isinstance(event, dict) and event.get("event") == "session_complete":
            ts = event.get("ts")
            if ts:
                try:
                    end_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    break
                except (ValueError, TypeError):
                    pass

    if end_dt is None:
        try:
            end_dt = datetime.fromtimestamp(session_dir.stat().st_mtime, tz=timezone.utc)
        except OSError:
            end_dt = None

    # Parse overnight-state.json
    overnight = parse_overnight_state(session_dir / "overnight-state.json")
    if overnight is None:
        overnight = {}

    start_ts: str | None = overnight.get("started_at") or None
    end_ts: str | None = overnight.get("updated_at") or None

    # Compute duration_str (same logic as _format_duration in app.py)
    duration_str = "—"
    if start_ts and end_ts:
        try:
            start_dt_dur = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
            end_dt_dur = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
            if start_dt_dur.tzinfo is None:
                start_dt_dur = start_dt_dur.replace(tzinfo=timezone.utc)
            if end_dt_dur.tzinfo is None:
                end_dt_dur = end_dt_dur.replace(tzinfo=timezone.utc)
            total_minutes = int((end_dt_dur - start_dt_dur).total_seconds() // 60)
            hours, minutes = divmod(total_minutes, 60)
            duration_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"
        except (ValueError, TypeError):
            duration_str = "—"

    # Build feature_states from per-feature phase transitions.
    # Per-feature artifacts may live under a different project's lifecycle dir
    # when the session's overnight state specifies project_root.
    project_lifecycle_dir = lifecycle_dir  # default fallback
    project_root = overnight.get("project_root")
    if project_root:
        try:
            pr_path = Path(project_root)
            if pr_path.exists():
                project_lifecycle_dir = pr_path / "lifecycle"
        except OSError:
            pass  # degrade gracefully to default

    feature_states: dict = {}
    features_dict = overnight.get("features", {})
    if isinstance(features_dict, dict):
        for slug in features_dict:
            feature_states[slug] = parse_feature_events(slug, project_lifecycle_dir)

    # Render morning-report.md as HTML
    morning_report_html: str | None = None
    report_path = session_dir / "morning-report.md"
    try:
        report_text = report_path.read_text(encoding="utf-8")
        morning_report_html = markdown.markdown(
            report_text, extensions=["fenced_code", "tables"]
        )
    except OSError:
        morning_report_html = None

    # Build swim lane data
    swim_data = build_swim_lane_data(overnight, events, feature_states, lifecycle_dir, end_dt=end_dt)

    # Compute feature status counts
    if isinstance(features_dict, dict):
        statuses = [f.get("status", "") for f in features_dict.values() if isinstance(f, dict)]
    else:
        statuses = []

    return {
        "session_id": session_id,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "duration_str": duration_str,
        "morning_report_html": morning_report_html,
        "swim_data": swim_data,
        "features_merged": statuses.count("merged"),
        "features_paused": statuses.count("paused"),
        "features_failed": statuses.count("failed"),
        "features_total": len(statuses),
    }


def parse_backlog_counts(backlog_dir: Path) -> dict[str, int]:
    """Count backlog items grouped by their ``status`` frontmatter field.

    Scans ``backlog_dir`` for files matching the pattern
    ``[0-9]*-*.md``, reads the YAML frontmatter between ``---``
    markers, and extracts the ``status`` field.  Files with missing or
    malformed frontmatter are skipped.  Items with no ``status`` field
    default to ``"open"``.

    Args:
        backlog_dir: Path to the ``backlog/`` directory.

    Returns:
        Dict mapping status string to count.  Returns ``{}`` if
        ``backlog_dir`` is absent or no matching files are found.
    """
    counts: dict[str, int] = {}
    try:
        files = sorted(backlog_dir.glob("[0-9]*-*.md"))
    except OSError:
        return counts

    for filepath in files:
        try:
            text = filepath.read_text(encoding="utf-8")
        except OSError:
            continue

        lines = text.splitlines()
        # Frontmatter must start on the first line with "---"
        if not lines or lines[0].strip() != "---":
            continue

        # Find the closing "---"
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break

        if end_idx is None:
            continue

        frontmatter_lines = lines[1:end_idx]
        status = "open"
        for fm_line in frontmatter_lines:
            match = re.match(r"^status\s*:\s*(.+)$", fm_line)
            if match:
                status = match.group(1).strip().strip("\"'")
                break

        status = normalize_status(status)
        counts[status] = counts.get(status, 0) + 1

    return counts


def parse_backlog_titles(backlog_dir: Path) -> dict[str, str]:
    """Return a mapping of lifecycle-slug → human-readable backlog title.

    Scans ``backlog_dir`` for files matching the pattern
    ``[0-9]*-*.md``, reads the YAML frontmatter between ``---``
    markers, and extracts the ``title`` field.  The lookup key is
    derived by ``slugify(title)`` from ``cortex_command.common`` (lowercase,
    underscores/slashes to spaces, strip non-alphanumeric, collapse
    whitespace/hyphens).

    Files with missing or malformed frontmatter are skipped silently.

    Args:
        backlog_dir: Path to the ``backlog/`` directory.

    Returns:
        Dict mapping slug string to title string.  Returns ``{}`` if
        ``backlog_dir`` is absent or on ``OSError``.
    """
    titles: dict[str, str] = {}
    try:
        files = sorted(backlog_dir.glob("[0-9]*-*.md"))
    except OSError:
        return titles

    for filepath in files:
        try:
            text = filepath.read_text(encoding="utf-8")
        except OSError:
            continue

        lines = text.splitlines()
        # Frontmatter must start on the first line with "---"
        if not lines or lines[0].strip() != "---":
            continue

        # Find the closing "---"
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break

        if end_idx is None:
            continue

        frontmatter_lines = lines[1:end_idx]
        title = None
        for fm_line in frontmatter_lines:
            match = re.match(r"^title\s*:\s*(.+)$", fm_line)
            if match:
                title = match.group(1).strip().strip("\"'")
                break

        if not title:
            continue

        slug = slugify(title)

        if slug:
            titles[slug] = title

    return titles


def parse_pipeline_dispatch(lifecycle_dir: Path) -> dict[str, dict]:
    """Read pipeline-events.log and return per-feature dispatch info.

    Scans ``lifecycle_dir/pipeline-events.log`` for ``dispatch_start``
    events and extracts the ``model`` and ``complexity`` fields for each
    feature.  If a feature appears multiple times (re-dispatch), only the
    last entry is kept.

    Args:
        lifecycle_dir: Path to the ``lifecycle/`` directory.

    Returns:
        Dict mapping feature name to ``{"model": str, "complexity": str}``.
        Returns ``{}`` if the file is absent, unreadable, or contains no
        ``dispatch_start`` events.
    """
    path = lifecycle_dir / "pipeline-events.log"
    events, _ = _read_all_jsonl(path)

    result: dict[str, dict] = {}
    for event in events:
        if event.get("event") != "dispatch_start":
            continue
        feature = event.get("feature")
        if not feature:
            continue
        model = event.get("model", "")
        complexity = event.get("complexity", "")
        result[feature] = {"model": model, "complexity": complexity}

    return result


def parse_metrics(lifecycle_dir: Path) -> dict | None:
    """Read and return the metrics data as a plain dict.

    Args:
        lifecycle_dir: Path to the ``lifecycle/`` directory.

    Returns:
        Parsed JSON dict from ``lifecycle_dir/metrics.json``, or None if
        the file is absent or unreadable.
    """
    path = lifecycle_dir / "metrics.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def compute_slow_flags(
    feature_states: dict,
    overnight: dict | None,
    metrics: dict | None,
    pipeline_dispatch: dict,
) -> dict[str, bool]:
    """Identify running features whose current-phase duration exceeds 3x the median.

    Compares each running feature's time in the current phase against
    historical durations from ``metrics.json``, using a tier-aware phase key.

    Phase key selection (tier-aware):
    - ``implement`` phase + ``complex`` tier -> ``"implement_to_review"``
    - ``implement`` phase + ``simple`` or ``trivial`` tier -> ``"implement_to_complete"``
    - ``review`` phase -> ``"review_to_complete"``
    - All other phases (research, specify, plan, complete) -> skip (no mapping)

    Args:
        feature_states: Per-feature parsed state from ``parse_feature_events``,
            keyed by slug.  Each entry has ``current_phase`` and
            ``phase_transitions`` keys.
        overnight: Parsed overnight-state.json dict, or None.
        metrics: Parsed metrics.json dict, or None.
        pipeline_dispatch: Dict keyed by slug, each entry has a ``complexity``
            field populated by the feature's ``dispatch_start`` event.

    Returns:
        Dict mapping slug to True for features that are running slow.  Only
        slow features are included; non-slow features are omitted.  Returns
        ``{}`` immediately when ``metrics`` or ``overnight`` is None.
    """
    if metrics is None or overnight is None:
        return {}

    result: dict[str, bool] = {}

    for slug, feat in overnight.get("features", {}).items():
        if feat.get("status") != "running":
            continue

        fs = feature_states.get(slug) or {}
        current_phase: str | None = fs.get("current_phase")

        if not current_phase:
            continue

        # Determine tier from pipeline_dispatch; fall back to "simple"
        tier: str = pipeline_dispatch.get(slug, {}).get("complexity") or "simple"

        # Select phase key based on phase and tier
        if current_phase == "implement":
            if tier == "complex":
                phase_key = "implement_to_review"
            else:
                # simple or trivial
                phase_key = "implement_to_complete"
        elif current_phase == "review":
            phase_key = "review_to_complete"
        else:
            # research, specify, plan, complete — no mapping
            continue

        # Get timestamp of the most recent phase transition
        transitions = fs.get("phase_transitions", [])
        if not transitions:
            continue

        last_ts_str: str | None = transitions[-1].get("ts")
        if not last_ts_str:
            continue

        try:
            transition_ts = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
            if transition_ts.tzinfo is None:
                transition_ts = transition_ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        current_duration_s = (datetime.now(timezone.utc) - transition_ts).total_seconds()

        # Collect historical phase durations for the same tier and phase key
        collected: list[float] = []
        for entry in metrics.get("features", []):
            if not isinstance(entry, dict):
                continue
            if entry.get("tier") != tier:
                continue
            phase_durations = entry.get("phase_durations", {})
            if not isinstance(phase_durations, dict):
                continue
            value = phase_durations.get(phase_key)
            if value is not None:
                try:
                    collected.append(float(value))
                except (TypeError, ValueError):
                    pass

        if not collected:
            # No baseline data; skip
            continue

        median_val = statistics.median(collected)
        if current_duration_s > 3 * median_val:
            result[slug] = True

    return result


def parse_feature_timestamps(
    overnight_events: list[dict],
) -> dict[str, dict]:
    """Extract per-feature start/complete timestamps from overnight session events.

    Makes a single pass through ``overnight_events`` and collects the most
    recent ``feature_start`` and ``feature_complete`` event for each slug.
    "Most recent" here means last occurrence in the list, which handles the
    rare case of duplicate events gracefully.

    Args:
        overnight_events: List of event dicts, each expected to have at least
            an ``"event"`` key and a ``"ts"`` key.  Events that are missing
            ``"feature"`` or ``"ts"`` are silently skipped.

    Returns:
        Dict mapping slug to a sub-dict with three keys:

        - ``started_at``:   ISO-format timestamp string, or ``None``
        - ``completed_at``: ISO-format timestamp string, or ``None``
        - ``duration_secs``: integer seconds between start and complete, or
          ``None`` when either timestamp is absent or un-parseable
    """
    result: dict[str, dict] = {}

    for event in overnight_events:
        event_type = event.get("event")
        if event_type not in ("feature_start", "feature_complete"):
            continue

        slug = event.get("feature")
        ts = event.get("ts")
        if not slug or not ts:
            continue

        if slug not in result:
            result[slug] = {
                "started_at": None,
                "completed_at": None,
                "duration_secs": None,
            }

        if event_type == "feature_start":
            result[slug]["started_at"] = ts
        else:
            result[slug]["completed_at"] = ts

    # Compute duration for slugs where both timestamps are present
    for slug, data in result.items():
        started_at = data["started_at"]
        completed_at = data["completed_at"]
        if started_at is None or completed_at is None:
            data["duration_secs"] = None
            continue

        try:
            start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            complete_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            data["duration_secs"] = int(
                (complete_dt - start_dt).total_seconds()
            )
        except (ValueError, TypeError):
            data["duration_secs"] = None

    return result


def parse_round_timestamps(
    overnight_events: list[dict],
) -> dict[int, dict]:
    """Extract per-round start/complete timestamps from overnight session events.

    Makes a single pass through ``overnight_events`` and collects the most
    recent ``round_start`` and ``round_complete`` event for each round number.
    "Most recent" here means last occurrence in the list, which handles the
    rare case of duplicate events gracefully.

    Args:
        overnight_events: List of event dicts, each expected to have at least
            an ``"event"`` key, a ``"round"`` key, and a ``"ts"`` key.  Events
            that are missing ``"round"`` or ``"ts"`` fields are silently
            skipped.

    Returns:
        Dict mapping round number (int) to a sub-dict with two keys:

        - ``started_at``:   ISO-format timestamp string, or ``None``
        - ``completed_at``: ISO-format timestamp string, or ``None``
    """
    result: dict[int, dict] = {}

    for event in overnight_events:
        event_type = event.get("event")
        if event_type not in ("round_start", "round_complete"):
            continue

        raw_round = event.get("round")
        ts = event.get("ts")
        if raw_round is None or not ts:
            continue

        try:
            round_number = int(raw_round)
        except (TypeError, ValueError):
            continue

        if round_number not in result:
            result[round_number] = {
                "started_at": None,
                "completed_at": None,
            }

        if event_type == "round_start":
            result[round_number]["started_at"] = ts
        else:
            result[round_number]["completed_at"] = ts

    return result
