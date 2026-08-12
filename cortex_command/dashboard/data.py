"""Data parsers for the dashboard.

Pure functions that read project state files and return parsed data
structures. All file I/O is wrapped in try/except so parsers never raise
on missing or malformed files.

Functions:
    parse_overnight_state  -- reads cortex/lifecycle/overnight-state.json
    parse_pipeline_state   -- reads cortex/lifecycle/pipeline-state.json
    tail_jsonl             -- byte-offset-aware JSONL tail utility
    parse_feature_events   -- reads cortex/lifecycle/{feature}/events.log
    parse_agent_activity   -- reads cortex/lifecycle/{feature}/agent-activity.jsonl
    get_last_activity_ts   -- most recent event timestamp for a feature
    parse_fleet_cards      -- builds agent fleet cards for running features
    build_swim_lane_data   -- builds swim lane timeline data for a session
    parse_last_session     -- summary of the most recently completed session
    parse_session_list     -- summary rows for all completed sessions
    parse_session_detail   -- all data for a single session detail page
    parse_backlog_titles   -- one corpus pass yielding both slug→title and id→title
    _read_all_jsonl        -- reads all JSONL events from byte 0 (initial-read primitive)
    parse_feature_cost_delta -- incremental cost delta and new byte offset for a feature
    parse_metrics          -- reads cortex/lifecycle/metrics.json
    compute_slow_flags     -- identifies running features slower than 3x median for their phase
    parse_feature_timestamps -- extracts start/complete timestamps and duration per feature slug
    parse_round_timestamps   -- extracts start/complete timestamps per round number from overnight events
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple

import markdown

from cortex_command.backlog.build_epic_map import build_epic_map
from cortex_command.backlog.generate_index import _parse_frontmatter, _parse_inline_str_list
from cortex_command.common import normalize_status, resolve_lifecycle_phase, slugify


def read_text_lossy(path: Path) -> str | None:
    """Read *path* as text, substituting U+FFFD for undecodable bytes.

    Every text read in this module used ``read_text(encoding="utf-8")`` under
    an ``except OSError``, and ``UnicodeDecodeError`` is a ``ValueError`` — so
    a single file that is not valid UTF-8 anywhere under ``cortex/backlog/``
    or ``cortex/lifecycle/`` escaped every guard. Measured consequences, on a
    root with one such file: ``_poll_slow`` raised on its first sweep and kept
    raising, leaving the whole backlog navigator reading "awaiting first poll"
    for the life of the process, and ``/tickets/{id}`` returned 500.

    Lossy rather than skipping, because this is a monitoring surface and the
    two outcomes are not symmetric: a record dropped from the board is a
    record an operator cannot see is missing, while a replacement character in
    one title is visibly wrong in exactly the place that is wrong. A file that
    is genuinely binary still fails frontmatter parsing downstream and is
    skipped there, which is where "this is not a ticket" belongs.

    Returns None only when the file cannot be read at all.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def parse_overnight_state(path: Path) -> dict | None:
    """Read and return the overnight session state as a plain dict.

    Args:
        path: Path to overnight-state.json (typically
            ``cortex/lifecycle/overnight-state.json``).

    Returns:
        Parsed JSON dict, or None if the file is absent or unreadable.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def parse_pipeline_state(path: Path) -> dict | None:
    """Read and return the pipeline state as a plain dict.

    The file is deleted on pipeline completion, so a missing file is the
    normal "no active pipeline" signal — return None cleanly.

    Args:
        path: Path to pipeline-state.json (typically
            ``cortex/lifecycle/pipeline-state.json``).

    Returns:
        Parsed JSON dict, or None if the file is absent or unreadable.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
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

    Reads ``cortex/lifecycle/{feature_slug}/events.log`` via
    ``cortex_command.pipeline.metrics.parse_events()``.

    Args:
        feature_slug: Feature directory name under ``cortex/lifecycle/``.
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.

    Returns:
        Dict with keys:

        - ``current_phase`` (str | None): the ``phase`` field from the
          events-first ``resolve_lifecycle_phase`` resolver (events
          authoritative where machine rows exist, artifact derivation the
          legacy fallback — ADR-0025), or None when the feature events.log
          read fails.
        - ``phase_transitions`` (list[dict]): each entry has ``from``,
          ``to``, and ``ts`` keys.
        - ``rework_cycles`` (int): count of ``to in {"implement",
          "implement-rework"}`` transitions that follow a
          ``to == "review"`` transition.
        - ``checked`` (int): count of completed plan tasks from the
          shared resolver (0 when plan.md is absent).
        - ``total`` (int): count of total plan tasks from the shared
          resolver (0 when plan.md is absent).

        On events.log read failure, returns ``current_phase=None``,
        ``phase_transitions=[]``, ``rework_cycles=0`` with ``checked``
        and ``total`` still pulled from the shared resolver.
    """
    feature_dir = lifecycle_dir / feature_slug
    detector = resolve_lifecycle_phase(feature_dir)
    checked = detector["checked"]
    total = detector["total"]

    default: dict = {
        "current_phase": None,
        "phase_transitions": [],
        "rework_cycles": 0,
        "checked": checked,
        "total": total,
    }
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

    current_phase: str | None = detector["phase"]

    # Count rework cycles: number of "implement" or "implement-rework"
    # transitions that follow a "review" transition immediately before them.
    rework_cycles = 0
    for i in range(1, len(transitions)):
        prev_to = transitions[i - 1].get("to")
        curr_to = transitions[i].get("to")
        if prev_to == "review" and curr_to in ("implement", "implement-rework"):
            rework_cycles += 1

    return {
        "current_phase": current_phase,
        "phase_transitions": phase_transitions,
        "rework_cycles": rework_cycles,
        "checked": checked,
        "total": total,
    }


def parse_agent_activity(
    feature_slug: str, lifecycle_dir: Path, last_n: int = 50
) -> list[dict]:
    """Return the last ``last_n`` events from a feature's agent-activity.jsonl.

    Reads lines from the end of the file without tracking a byte offset
    (non-incremental simple tail).  Malformed JSON lines are silently skipped.

    Args:
        feature_slug: Feature directory name under ``cortex/lifecycle/``.
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.
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
        feature_slug: Feature directory name under ``cortex/lifecycle/``.
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.

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
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.
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


# Nominal geometry for the swim-lane de-overlap sweep. The track is a flex
# child whose real pixel width is a browser-side fact the server cannot know,
# so label widths are estimated against a representative rendered width and the
# result is expressed in percent. Over-estimating the track only under-spreads
# (labels sit closer than ideal); under-estimating it over-spreads (labels drift
# further from their true time). Both degrade gracefully — unlike no sweep at
# all, which renders "specify→implement" straight through "complete".
_LANE_TRACK_NOMINAL_PX = 900.0
_LANE_CHAR_PX = 6.2          # JetBrains Mono at 9.5px, uppercased
_LANE_LABEL_PADDING_PX = 14.0  # .lane-event horizontal padding + border
_LANE_LABEL_GAP_PX = 4.0     # breathing room between adjacent labels


def _lane_label_width_pct(label: str) -> float:
    """Estimate a lane label's rendered width as a percentage of the track."""
    px = len(label) * _LANE_CHAR_PX + _LANE_LABEL_PADDING_PX
    return (px / _LANE_TRACK_NOMINAL_PX) * 100.0


def _spread_lane_events(events: list[dict]) -> list[dict]:
    """Nudge lane events apart so their labels do not render on top of one another.

    Events are absolutely positioned at ``left: x_pct%`` inside a shared track,
    and two events close in time — a ``complete`` immediately followed by a
    ``specify→implement`` transition, which is the common case at a phase
    boundary — overlapped into an unreadable composite. DESIGN.md's
    "Operational usefulness" criterion names a legible swim-lane with no
    overlapping labels explicitly.

    Positions are advisory rather than exact: a lane is a qualitative "what
    happened, roughly when" reading, not a measuring instrument, and the
    tooltip carries each event's true timestamp. So the sweep preserves order
    and relative spacing while guaranteeing separation.

    Two passes. Forward, each event is pushed right far enough to clear its
    predecessor. That can push the last events past the track's right edge, so
    the backward pass pulls any overflow back left, which can in turn re-collide
    at the left — bounded by the track holding more label-widths than a lane
    has events in every realistic session. Events keep their original list
    order for the caller; only ``x_pct`` moves.
    """
    if len(events) < 2:
        return events

    ordered = sorted(events, key=lambda e: e["elapsed_secs"])
    widths = [_lane_label_width_pct(e["label"]) for e in ordered]

    # Forward: never start before the previous label ends.
    cursor = 0.0
    for i, event in enumerate(ordered):
        x = max(event["x_pct"], cursor)
        event["x_pct"] = x
        cursor = x + widths[i] + (_LANE_LABEL_GAP_PX / _LANE_TRACK_NOMINAL_PX) * 100.0

    # Backward: nothing may extend past the right edge.
    limit = 100.0
    for i in range(len(ordered) - 1, -1, -1):
        x = min(ordered[i]["x_pct"], limit - widths[i])
        ordered[i]["x_pct"] = max(0.0, x)
        limit = ordered[i]["x_pct"] - (_LANE_LABEL_GAP_PX / _LANE_TRACK_NOMINAL_PX) * 100.0

    return events


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
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory (currently unused;
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
        "review→implement-rework": "→rework",
        "implement-rework→review": "→rev",
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
            "events": _spread_lane_events(lane_events),
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


def _session_state_files(sessions_dir: Path) -> list[Path]:
    """Return one ``overnight-state.json`` per real session directory.

    ``sessions/`` holds pointer symlinks alongside the session directories
    themselves — ``latest-overnight`` is created by the runner on every start
    and by the dashboard seeder — and a plain ``*/overnight-state.json`` glob
    matches through them. The pointer and its target are the same session, so
    the newest run was listed twice on ``/sessions``, once under its real id
    and once more under the identical id resolved through the link.

    Skipping symlinked directories is the same rule ``cli_handler`` and
    ``guardian`` already apply when they enumerate sessions; only this module
    was missing it. Returns [] rather than raising when ``sessions/`` is
    absent, which is the normal state of a repo that has never run overnight.
    """
    try:
        candidates = list(sessions_dir.glob("*/overnight-state.json"))
    except OSError:
        return []
    return [path for path in candidates if not path.parent.is_symlink()]


def parse_last_session(lifecycle_dir: Path) -> dict | None:
    """Return a summary dict for the most recently completed overnight session.

    Reads one ``overnight-state.json`` per real session directory (pointer
    symlinks are skipped — see ``_session_state_files``), parses each file,
    and returns a summary for the session with the latest ``updated_at``
    timestamp.

    Args:
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.

    Returns:
        Dict with keys:
        - ``session_id`` (str)
        - ``features_merged`` (int)
        - ``features_failed`` (int)
        - ``features_total`` (int)
        - ``ended_hours_ago`` (float)
        - ``ended_at`` (str) -- ISO-8601 value of ``updated_at``

        Returns None if ``lifecycle_dir/sessions/`` is absent, empty, or all
        files are unreadable.
    """
    candidates = _session_state_files(lifecycle_dir / "sessions")
    if not candidates:
        return None

    best: dict | None = None
    best_updated: datetime | None = None

    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
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
        # The raw end timestamp, so views can render elapsed time at whatever
        # resolution reads well. ``ended_hours_ago`` alone bottoms out at
        # "0.0h ago" for anything under three minutes, which is exactly when
        # an operator is most likely to be looking.
        "ended_at": best.get("updated_at", ""),
    }


def _format_session_span(start_ts: str | None, end_ts: str | None) -> str:
    """Return ``'Xh Ym'`` / ``'Nm'`` between two ISO-8601 stamps, or ``'—'``.

    Session-scale, deliberately: a run measured in hours reads as ``'6h 51m'``
    here and as ``'411m 3s'`` under ``_format_duration_secs``, which is the
    minute-scale formatter the feature cards use. Both session surfaces —
    the history list and the per-session detail page — call this one function
    so a session cannot report two different lengths of itself.

    Accepts a trailing ``Z`` (``fromisoformat`` did not until 3.11) and
    assumes UTC for a naive stamp, matching every other timestamp reader here.
    """
    if not start_ts or not end_ts:
        return "—"
    try:
        start_dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        total_minutes = int((end_dt - start_dt).total_seconds() // 60)
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}h {minutes}m" if hours else f"{minutes}m"
    except (ValueError, TypeError):
        return "—"


def parse_session_list(lifecycle_dir: Path) -> list[dict]:
    """Return a summary row for every completed overnight session found on disk.

    Reads one ``overnight-state.json`` per real session directory (pointer
    symlinks are skipped — see ``_session_state_files``), extracts a
    summary dict from each readable file, and returns all rows sorted
    most-recent-first by ``end_ts`` (sessions with no parseable ``end_ts``
    are appended at the end in arbitrary order).

    Args:
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.

    Returns:
        List of dicts, each with keys:

        - ``session_id`` (str)
        - ``start_ts`` (str | None) -- ISO-8601 value of ``started_at``
        - ``end_ts`` (str | None) -- ISO-8601 value of ``updated_at``
        - ``duration_secs`` (int | None) -- whole seconds between start and end
        - ``duration_str`` (str) -- that span as ``'Xh Ym'`` / ``'Nm'``, or
          ``'—'``. Rendered rather than derived in the template because the
          history list read a ``duration_str`` these rows never carried, and
          a Jinja undefined took the ``default('—')`` arm on every row of
          every session — a column that could not display a value.
        - ``features_merged`` (int)
        - ``features_paused`` (int)
        - ``features_failed`` (int)
        - ``features_total`` (int)

        Returns ``[]`` if the sessions directory is absent, empty, or all
        files are unreadable.
    """
    candidates = _session_state_files(lifecycle_dir / "sessions")

    rows: list[dict] = []

    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
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
            "duration_str": _format_session_span(start_ts, end_ts),
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
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.

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

    duration_str = _format_session_span(start_ts, end_ts)

    # Build feature_states from per-feature phase transitions.
    # Per-feature artifacts may live under a different project's lifecycle dir
    # when the session's overnight state specifies project_root.
    project_lifecycle_dir = lifecycle_dir  # default fallback
    project_root = overnight.get("project_root")
    if project_root:
        try:
            pr_path = Path(project_root)
            if pr_path.exists():
                project_lifecycle_dir = pr_path / "cortex" / "lifecycle"
        except OSError:
            pass  # degrade gracefully to default

    feature_states: dict = {}
    features_dict = overnight.get("features", {})
    if isinstance(features_dict, dict):
        for slug in features_dict:
            feature_states[slug] = parse_feature_events(slug, project_lifecycle_dir)

    # Render morning-report.md as HTML, through the same allowlist every other
    # markdown surface here goes through. Python-Markdown passes raw HTML in
    # the source straight to the output, and this value reaches the template
    # under `| safe` — so an unsanitized report was the one `| safe` site on
    # the dashboard that a `<script>` could reach. The report is agent-written
    # and quotes material the agent read (PR bodies, issue text, code), which
    # is untrusted-input-shaped, and `DASHBOARD_HOST` makes a non-loopback bind
    # a documented option. The asymmetry with `load_ticket_body` was the defect
    # whether or not it was reachable: same renderer, same `| safe`, one
    # sanitized and one not.
    morning_report_html: str | None = None
    report_text = read_text_lossy(session_dir / "morning-report.md")
    if report_text is not None:
        morning_report_html = _sanitize_ticket_html(
            markdown.markdown(report_text, extensions=["fenced_code", "tables"])
        )

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


class BacklogTitles(NamedTuple):
    """Both title lookups produced by one pass over ``cortex/backlog/``.

    Attributes:
        by_slug: ``slugify(title)`` → title. The feature-slug lookup the
            feature-card and escalation panels have always consumed.
        by_id: stringified, unpadded item id → title. Added for the ticket
            feed's blocked-why join (#411 R13), which must resolve blocker
            ids to titles across *terminal* items — something neither
            ``collect_items``' ``all_items`` (id/status/uuid only) nor the
            slug map (keyed for feature matching, not by id) can serve.
            Keys mirror ``generate_index.collect_items``' unpadded form.

    Both maps are built in the single existing glob because the slow poll
    already reads this corpus twice per 30s cycle; a third title pass would
    be a fourth full scan.  ``archive/`` is out of scope by construction —
    the glob is non-recursive — so an archived blocker resolves with a
    ``None`` title rather than appearing under a wrong one.
    """

    by_slug: dict[str, str]
    by_id: dict[str, str]


def parse_backlog_titles(backlog_dir: Path) -> BacklogTitles:
    """Return slug→title and id→title maps from one pass over ``backlog_dir``.

    Scans ``backlog_dir`` for files matching the pattern
    ``[0-9]*-*.md``, reads the YAML frontmatter between ``---``
    markers, and extracts the ``title`` field.  The slug key is
    derived by ``slugify(title)`` from ``cortex_command.common`` (lowercase,
    underscores/slashes to spaces, strip non-alphanumeric, collapse
    whitespace/hyphens); the id key is the leading digits of the filename,
    unpadded and stringified.

    Files with missing or malformed frontmatter are skipped silently.

    Args:
        backlog_dir: Path to the ``cortex/backlog/`` directory.

    Returns:
        :class:`BacklogTitles`.  Both maps are ``{}`` if ``backlog_dir`` is
        absent or on ``OSError``.
    """
    titles: dict[str, str] = {}
    titles_by_id: dict[str, str] = {}
    try:
        files = sorted(backlog_dir.glob("[0-9]*-*.md"))
    except OSError:
        return BacklogTitles(titles, titles_by_id)

    for filepath in files:
        text = read_text_lossy(filepath)
        if text is None:
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

        id_match = re.match(r"^(\d+)-", filepath.name)
        if id_match:
            titles_by_id[str(int(id_match.group(1)))] = title

    return BacklogTitles(titles, titles_by_id)


#: Tags Python-Markdown emits for the extensions this dashboard enables, plus
#: the inline formatting a ticket body legitimately uses. Anything outside this
#: set is dropped from the rendered output — except an attribute-free
#: unrecognized start tag (e.g. a bare `<slug>` placeholder), which is
#: literalized as escaped text instead of vanishing; see
#: _TicketBodySanitizer.handle_starttag.
_TICKET_ALLOWED_TAGS = frozenset(
    """a blockquote br code del em h1 h2 h3 h4 h5 h6 hr li ol p pre strong
       sub sup table tbody td th thead tr ul""".split()
)

#: Tags whose *contents* are dropped along with the tag. For everything else,
#: unwrapping keeps the text; for these it would leak script source as prose.
_TICKET_VOID_CONTENT_TAGS = frozenset({"script", "style", "iframe", "object", "embed"})

#: Attributes worth preserving, per tag. `class` survives only on code/pre
#: because that is where the fenced-code extension puts `language-*`.
_TICKET_ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "code": {"class"},
    "pre": {"class"},
    "td": {"align"},
    "th": {"align"},
}

_TICKET_SAFE_URL_RE = re.compile(r"^(?:https?:|mailto:|#|/|\.{0,2}/)", re.I)


class _TicketBodySanitizer(HTMLParser):
    """Rebuild rendered markdown keeping only an allowlist of tags.

    Ticket bodies routinely quote material this repo did not author — pasted
    error output, a GitHub issue, a tool transcript — and Python-Markdown has
    no safe mode, so raw HTML in a body reaches the page verbatim. An injected
    ``<script>`` would run with the dashboard's origin; there is no auth to
    defeat, but it could read what the dashboard renders and reach other
    services on loopback.

    Sanitizing the *output* rather than escaping the *input* is deliberate.
    Escaping the source first double-escapes every fenced code block, because
    Markdown escapes ``&`` again inside code — ``-> str`` rendered as
    ``-&gt; str`` on screen. Rendering first and filtering after leaves code
    blocks correct and still drops raw HTML.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self._suppress_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _TICKET_VOID_CONTENT_TAGS:
            self._suppress_depth += 1
            return
        if tag not in _TICKET_ALLOWED_TAGS:
            if not self._suppress_depth and not attrs:
                self.out.append(escape(self.get_starttag_text()))
            return
        if self._suppress_depth:
            return
        allowed = _TICKET_ALLOWED_ATTRS.get(tag, set())
        rendered = ""
        for name, value in attrs:
            if name not in allowed or value is None:
                continue
            if name == "href" and not _TICKET_SAFE_URL_RE.match(value.strip()):
                continue
            rendered += f' {name}="{escape(value, quote=True)}"'
        self.out.append(f"<{tag}{rendered}>")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if not self._suppress_depth and tag in _TICKET_ALLOWED_TAGS:
            self.out.append(f"<{tag} />")

    def handle_endtag(self, tag: str) -> None:
        if tag in _TICKET_VOID_CONTENT_TAGS:
            self._suppress_depth = max(0, self._suppress_depth - 1)
            return
        if tag not in _TICKET_ALLOWED_TAGS:
            if not self._suppress_depth:
                self.out.append(escape(f"</{tag}>"))
            return
        if self._suppress_depth:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._suppress_depth:
            self.out.append(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if not self._suppress_depth:
            self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._suppress_depth:
            self.out.append(f"&#{name};")


def _sanitize_ticket_html(html: str) -> str:
    """Return *html* with every non-allowlisted tag removed."""
    parser = _TicketBodySanitizer()
    parser.feed(html)
    parser.close()
    return "".join(parser.out)


#: Ceiling on a rendered ticket body, in characters of source markdown. The
#: largest body in this repo's own corpus is ~21 KB and the mean is ~3.6 KB, so
#: 64 KB is well clear of real content while bounding what one request can pull
#: into the page if a body is ever pathological (a pasted log, a base64 blob).
#: Truncation is reported to the reader rather than silently swallowing text.
TICKET_BODY_MAX_CHARS = 64_000


def _resolve_ticket_path(item_id: str, backlog_dir: Path) -> Path | None:
    """Resolve a ticket id to its markdown file under ``backlog_dir``, or None.

    Shared file-resolution step behind every per-ticket loader in this
    module: id validation, padding-agnostic matching, the ``archive/``
    fallback, and the containment re-check, extracted from ``load_ticket_body``
    so ``load_ticket_page`` and ``load_ticket_artifact`` reuse one resolver
    instead of a second implementation.

    Args:
        item_id: The ticket's numeric id, as a string, straight off the URL.
        backlog_dir: Path to the ``cortex/backlog/`` directory.

    Returns:
        The resolved, existing :class:`Path`, or ``None`` when *item_id* is
        not a bare integer, no file matches it, or the resolved file does not
        sit under *backlog_dir*.
    """
    # The id arrives from the URL path, so it is validated as a bare integer
    # before it reaches any filesystem call. This rejects "..", absolute paths,
    # and glob metacharacters by construction rather than by escaping them.
    if not re.fullmatch(r"\d{1,9}", item_id or ""):
        return None

    wanted = int(item_id)

    # Filenames are zero-padded (``007-…``, ``042-…``) while every id the board
    # carries is unpadded — ``parse_backlog_titles`` keys them by
    # ``str(int(...))``. Globbing the id literally therefore missed every
    # padded file, so the match is made on the parsed leading integer and is
    # padding-agnostic in both directions.
    def _match(directory: Path) -> list[Path]:
        try:
            files = sorted(directory.glob("[0-9]*-*.md"))
        except OSError:
            return []
        found = []
        for candidate in files:
            head = re.match(r"^(\d+)-", candidate.name)
            if head and int(head.group(1)) == wanted:
                found.append(candidate)
        return found

    candidates = _match(backlog_dir) or _match(backlog_dir / "archive")
    if not candidates:
        return None

    path = candidates[0]
    # Belt and braces on top of the id validation: confirm the resolved file
    # really sits under the backlog directory before reading it.
    try:
        resolved = path.resolve()
        root = backlog_dir.resolve()
        if not resolved.is_relative_to(root):
            return None
        return resolved
    except (OSError, ValueError):
        return None


#: A ticket reference at the start of a block — ``#331`` — behind any mix of
#: indentation, blockquote markers and a list bullet. Python-Markdown does not
#: require a space after ``#`` for an ATX heading (CommonMark does), so every
#: such line renders as an ``<h1>``.
#:
#: The list-marker arm is not an edge case: ``1. #129 (…)`` opens a new block
#: inside the ``<li>``, so an implementation-order list — a common shape in
#: this corpus — renders every one of its steps as the largest type on the
#: page. Measured on wild-light: 156 lines across 109 of 512 tickets (21%),
#: of which 28 sit behind a list marker.
#:
#: Cross-referencing other tickets by id at the start of a sentence is ordinary
#: here, so this is not something the corpus can be spelled around.
_LINE_START_TICKET_REF = re.compile(
    r"(?m)^([ \t]*(?:>[ \t]*)*(?:(?:[-*+]|\d+[.)])[ \t]+)?)#(?=\d)"
)


def _escape_ticket_refs(body: str) -> str:
    """Backslash-escape a line-leading ``#`` that introduces a ticket id.

    Only ``#`` immediately followed by a digit is touched, so real headings are
    untouched: ``# Why`` has a space, ``## Role`` has a second ``#``, and
    neither matches. A mid-line ``#331`` was never a heading and is left alone.

    Escaping the source rather than post-processing the HTML keeps the fix on
    the same side of the render as the existing angle-bracket escaping, so the
    sanitizer downstream still sees exactly what Python-Markdown emitted.
    """
    return _LINE_START_TICKET_REF.sub(r"\1\\#", body)


def load_ticket_body(item_id: str, backlog_dir: Path) -> dict | None:
    """Return ``{id, title, html, truncated}`` for one backlog ticket, or None.

    Reads the markdown body of ``cortex/backlog/<item_id>-*.md`` — falling back
    to ``archive/`` so a blocker pointing at a closed ticket is still readable —
    strips the YAML frontmatter, and renders what remains to HTML.

    This is a per-request read rather than part of the 30s snapshot on purpose.
    Bodies are large relative to everything else the poller carries: this repo's
    corpus is ~1.5 MB across 416 files, so folding them into the polled fragment
    would morph hundreds of KB into the DOM twice a minute to display prose the
    operator has usually not asked for. Only an opened row pays.

    Args:
        item_id: The ticket's numeric id, as a string, straight off the URL.
        backlog_dir: Path to the ``cortex/backlog/`` directory.

    Returns:
        A dict with the rendered body, or ``None`` when *item_id* is not a bare
        integer, no file matches it, or the file cannot be read.
    """
    resolved = _resolve_ticket_path(item_id, backlog_dir)
    if resolved is None:
        return None

    normalized = str(int(item_id))

    text = read_text_lossy(resolved)
    if text is None:
        return None

    title = None
    body = text
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                for fm_line in lines[1:i]:
                    match = re.match(r"^title\s*:\s*(.+)$", fm_line)
                    if match:
                        title = match.group(1).strip().strip("\"'")
                        break
                body = "\n".join(lines[i + 1 :])
                break

    body = body.strip()
    truncated = len(body) > TICKET_BODY_MAX_CHARS
    if truncated:
        body = body[:TICKET_BODY_MAX_CHARS]

    # Same two extensions the morning-report render enables, and the pair the
    # seeded fixture corpus is written to exercise. Rendered first, then
    # filtered to an allowlist — see _TicketBodySanitizer for why that order.
    html = _sanitize_ticket_html(
        markdown.markdown(
            _escape_ticket_refs(body), extensions=["fenced_code", "tables"]
        )
    )

    return {"id": normalized, "title": title, "html": html, "truncated": truncated}


#: Ceiling on a rendered artifact, in characters of source markdown. Measured
#: over the real ``cortex/lifecycle/`` corpus (n=694 artifacts): median
#: 19,166, p99 51,068, max 63,707. ``TICKET_BODY_MAX_CHARS`` (64,000, above)
#: is the wrong cap to reuse here — the corpus max already sits at 99.5% of
#: it, leaving essentially no headroom before a legitimate large spec or plan
#: trips truncation. Truncation is reported to the reader, not silent.
ARTIFACT_MAX_CHARS = 128_000

#: The four artifact kinds a lifecycle feature directory may hold, in the
#: order the page renders them.
_ARTIFACT_KINDS = ("research", "spec", "plan", "review")


def _opt_field(fm: dict[str, str], key: str) -> str | None:
    """Return a stripped, unquoted frontmatter value, or None if absent/null.

    Mirrors ``generate_index._opt``'s semantics without importing a second
    module-private symbol from that module — only ``_parse_frontmatter`` and
    ``_parse_inline_str_list`` are imported here.
    """
    v = fm.get(key, "").strip().strip("\"'")
    return v if v and v.lower() != "null" else None


def resolve_artifact_dir(fm: dict, lifecycle_dir: Path) -> Path | None:
    """Resolve a ticket's lifecycle artifact directory via a two-key join.

    Tries the ``spec:`` frontmatter value's parent directory first — resolved
    under the repo root (``lifecycle_dir``'s grandparent, since
    ``lifecycle_dir`` is ``<root>/cortex/lifecycle``) — then falls back to a
    ``lifecycle_slug`` probe of ``lifecycle_dir/<slug>`` and
    ``lifecycle_dir/archive/<slug>``. A ``spec:`` value pointing at a
    directory that no longer exists (5 tickets in the corpus) falls through
    to the probe rather than short-circuiting to None.

    Each candidate must be a real directory *and* pass a ``resolve()`` +
    containment check under ``lifecycle_dir`` before it is returned, so a
    ``spec:`` value cannot be used as a traversal vector.

    Args:
        fm: Frontmatter dict with optional ``spec`` and ``lifecycle_slug``
            keys (as produced by ``generate_index._parse_frontmatter``).
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.

    Returns:
        The resolved artifact directory, or ``None`` when neither key
        resolves (150 of 448 tickets in the corpus at spec time).
    """
    try:
        lifecycle_root = lifecycle_dir.resolve()
    except OSError:
        return None
    repo_root = lifecycle_dir.parent.parent

    def _valid(candidate: Path) -> Path | None:
        try:
            if not candidate.is_dir():
                return None
            resolved = candidate.resolve()
            if not resolved.is_relative_to(lifecycle_root):
                return None
            return resolved
        except (OSError, ValueError):
            return None

    spec = _opt_field(fm, "spec")
    if spec:
        found = _valid((repo_root / Path(spec)).parent)
        if found is not None:
            return found

    slug = _opt_field(fm, "lifecycle_slug")
    if slug:
        for probe in (lifecycle_dir / slug, lifecycle_dir / "archive" / slug):
            found = _valid(probe)
            if found is not None:
                return found

    return None


def _epic_children_corpus(backlog_dir: Path) -> list[dict]:
    """Build the light corpus ``build_epic_map`` needs for one page's children.

    Scans ``backlog_dir`` for files matching ``[0-9]*-*.md`` (non-recursive,
    so ``archive/`` is out of scope by construction, matching
    ``BacklogTitles``) and parses each into
    ``{id, title, status, type, parent, spec}`` — enough for
    ``build_epic_map``'s grouping and nothing else. Deliberately skips
    ``collect_items``' per-item live phase detection, which this page has no
    use for and which is the expensive part of a full-corpus scan.
    """
    corpus: list[dict] = []
    try:
        files = sorted(backlog_dir.glob("[0-9]*-*.md"))
    except OSError:
        return corpus

    for filepath in files:
        text = read_text_lossy(filepath)
        if text is None:
            continue
        fm = _parse_frontmatter(text)
        if not fm:
            continue
        id_match = re.match(r"^(\d+)-", filepath.name)
        if not id_match:
            continue
        corpus.append({
            "id": int(id_match.group(1)),
            "title": _opt_field(fm, "title"),
            "status": _opt_field(fm, "status"),
            "type": _opt_field(fm, "type"),
            "parent": _opt_field(fm, "parent"),
            "spec": _opt_field(fm, "spec"),
        })
    return corpus


def _resolve_epic_children(item_id: str, backlog_dir: Path) -> list[dict]:
    """Return ``{id, spec, status, title}`` children of the epic *item_id*.

    Builds the light corpus and passes it to ``build_epic_map`` — the same
    canonical grouping and ``normalize_parent`` handling the triage board
    uses (``ticket_feed.py``'s ``_epic_map_for_board``) — with
    ``strict_schema=False`` for the same reason: this corpus is not one this
    process controls, and a schema-version bump elsewhere must not turn into
    a 500 here. Children are already sorted by id ascending.
    """
    corpus = _epic_children_corpus(backlog_dir)
    envelope = build_epic_map(corpus, strict_schema=False)
    epic_key = str(int(item_id))
    return envelope["epics"].get(epic_key, {}).get("children", [])


def load_ticket_page(item_id: str, backlog_dir: Path, lifecycle_dir: Path) -> dict | None:
    """Return the full read side of a ticket's ``/tickets/{id}`` page, or None.

    Composes ``load_ticket_body`` (for the body — no second frontmatter-strip
    or render, requirement 8) with a raw frontmatter read for the badge-strip
    fields, the two-key artifact join, and epic-child resolution.

    Args:
        item_id: The ticket's numeric id, as a string, straight off the URL.
        backlog_dir: Path to the ``cortex/backlog/`` directory.
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.

    Returns:
        ``None`` when *item_id* is not a bare integer or no ticket resolves
        under *backlog_dir* — the route turns this into a 404. Otherwise a
        dict with:

        - ``id``, ``title`` -- from ``load_ticket_body``.
        - ``status``, ``priority``, ``type``, ``parent``, ``areas`` -- the
          frontmatter fields the badge strip needs. ``parent`` is ``None``
          when absent; ``areas`` is a list, empty when absent.
        - ``body`` (dict): ``load_ticket_body``'s return value verbatim.
        - ``artifacts`` (list[str]): artifact kinds present in the resolved
          artifact directory, in ``("research", "spec", "plan", "review")``
          order; absent kinds are omitted, never rendered as empty shells.
        - ``children`` (list[dict] | None): epic children when
          ``type == "epic"``, else ``None`` — a non-epic page pays nothing
          for the corpus scan.
    """
    resolved = _resolve_ticket_path(item_id, backlog_dir)
    if resolved is None:
        return None

    text = read_text_lossy(resolved)
    if text is None:
        return None

    body = load_ticket_body(item_id, backlog_dir)
    if body is None:
        return None

    # _parse_frontmatter / _parse_inline_str_list are generate_index's
    # module-private but canonical parser this package already reads backlog
    # frontmatter with (see generate_index.collect_items) — reused here
    # rather than a third hand-rolled scanner in this module.
    fm = _parse_frontmatter(text)

    ticket_type = _opt_field(fm, "type") or "feature"

    artifact_dir = resolve_artifact_dir(fm, lifecycle_dir)
    artifacts = [
        kind for kind in _ARTIFACT_KINDS
        if artifact_dir is not None and (artifact_dir / f"{kind}.md").is_file()
    ]

    # Ask for children regardless of type, because heading a group is not a
    # property of `type`. A ticket typed `chore` that eight others name as
    # their parent has eight children, and gating the lookup on `type: epic`
    # is what kept #357's from ever reaching this page.
    #
    # `None` still means "no children section at all", and an empty list still
    # means "a container with nothing active left in it" — so a typed epic
    # keeps its empty state, and an ordinary ticket nobody names stays silent.
    children: list[dict] | None = _resolve_epic_children(item_id, backlog_dir)
    if not children and ticket_type != "epic":
        children = None

    return {
        "id": body["id"],
        "title": body["title"],
        "status": _opt_field(fm, "status") or "open",
        "priority": _opt_field(fm, "priority") or "medium",
        "type": ticket_type,
        "parent": _opt_field(fm, "parent"),
        "areas": _parse_inline_str_list(fm.get("areas", "[]")),
        "body": body,
        "artifacts": artifacts,
        "children": children,
    }


def load_ticket_artifact(
    item_id: str, kind: str, backlog_dir: Path, lifecycle_dir: Path
) -> dict | None:
    """Return ``{"kind", "html", "truncated"}`` for one lifecycle artifact, or None.

    Fetched when an artifact panel is expanded, one request per panel —
    nothing here is cached, and the artifact directory is re-resolved through
    ``resolve_artifact_dir`` on every call (``spec.md`` non-requirement: the
    page is computed per request throughout).

    Args:
        item_id: The ticket's numeric id, as a string, straight off the URL.
        kind: One of ``"research"``, ``"spec"``, ``"plan"``, ``"review"``.
        backlog_dir: Path to the ``cortex/backlog/`` directory.
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.

    Returns:
        ``None`` when *kind* is not one of the four kinds, *item_id* does not
        resolve to a ticket, the ticket has no resolvable artifact directory,
        or that directory has no file for *kind*. Otherwise the rendered
        artifact.
    """
    # Validated against the closed set before any filesystem call — the same
    # posture as the id check in _resolve_ticket_path.
    if kind not in _ARTIFACT_KINDS:
        return None

    resolved = _resolve_ticket_path(item_id, backlog_dir)
    if resolved is None:
        return None

    text = read_text_lossy(resolved)
    if text is None:
        return None

    fm = _parse_frontmatter(text)
    artifact_dir = resolve_artifact_dir(fm, lifecycle_dir)
    if artifact_dir is None:
        return None

    artifact_path = artifact_dir / f"{kind}.md"
    raw = read_text_lossy(artifact_path)
    if raw is None:
        return None

    raw = raw.strip()
    truncated = len(raw) > ARTIFACT_MAX_CHARS
    if truncated:
        raw = raw[:ARTIFACT_MAX_CHARS]

    # Same render + sanitize path Task 1 repaired — see load_ticket_body.
    html = _sanitize_ticket_html(
        markdown.markdown(raw, extensions=["fenced_code", "tables"])
    )

    return {"kind": kind, "html": html, "truncated": truncated}


def parse_pipeline_dispatch(lifecycle_dir: Path) -> dict[str, dict]:
    """Read pipeline-events.log and return per-feature dispatch info.

    Scans ``lifecycle_dir/pipeline-events.log`` for ``dispatch_start`` events
    and extracts the ``complexity`` field for each feature.  The model is not
    known at dispatch_start (cortex does not choose one), so it is picked up
    from the later ``dispatch_model_observed`` / ``dispatch_complete`` events —
    with a ``dispatch_start`` fallback for historical logs.  If a feature
    appears multiple times (re-dispatch), only the last entry is kept.

    Args:
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.

    Returns:
        Dict mapping feature name to ``{"model": str, "complexity": str}``.
        Returns ``{}`` if the file is absent, unreadable, or contains no
        ``dispatch_start`` events.
    """
    path = lifecycle_dir / "pipeline-events.log"
    events, _ = _read_all_jsonl(path)

    result: dict[str, dict] = {}
    for event in events:
        kind = event.get("event")
        feature = event.get("feature")
        if not feature:
            continue
        if kind == "dispatch_start":
            result[feature] = {
                # Historical logs carried the model here; current ones do not.
                "model": event.get("model") or "",
                "complexity": event.get("complexity", ""),
            }
        elif kind in ("dispatch_model_observed", "dispatch_complete"):
            model = event.get("model")
            if model and feature in result:
                result[feature]["model"] = model

    return result


def parse_metrics(lifecycle_dir: Path) -> dict | None:
    """Read and return the metrics data as a plain dict.

    Args:
        lifecycle_dir: Path to the ``cortex/lifecycle/`` directory.

    Returns:
        Parsed JSON dict from ``lifecycle_dir/metrics.json``, or None if
        the file is absent or unreadable.
    """
    path = lifecycle_dir / "metrics.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
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

        # Select phase key based on phase and tier. Strip -paused suffix
        # first so a paused feature still hits the slow-flag classifier
        # for its underlying phase (paused implement remains tracked).
        base_phase = current_phase.removesuffix("-paused") if isinstance(current_phase, str) else current_phase
        if base_phase in ("implement", "implement-rework"):
            if tier == "complex":
                phase_key = "implement_to_review"
            else:
                # simple or trivial
                phase_key = "implement_to_complete"
        elif base_phase == "review":
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


def parse_escalations(
    feature_slug: str, lifecycle_dir: Path, last_n: int = 5
) -> list[dict]:
    """Return up to ``last_n`` most recent escalation entries for a feature.

    Reads ``lifecycle_dir/{feature_slug}/escalations.jsonl``. Each line is a
    JSON object representing an open question that blocks the feature. Useful
    fields: ``question`` (text), ``context`` (text), ``ts`` (ISO-8601).

    Returns ``[]`` when the file is absent.
    """
    path = lifecycle_dir / feature_slug / "escalations.jsonl"
    events, _ = _read_all_jsonl(path)
    return events[-last_n:]


def _exit_report_sort_key(stem: str) -> tuple[int, str]:
    """Order exit-report filename stems by ``(numeric-prefix, suffix)`` so a
    sub-task stem (``3a``) sorts after its parent (``3``) and before the next
    integer (``4``) — #297. Non-conforming stems bucket to the sort floor
    (``1 << 30``) with the stem as tiebreak, preserving the prior non-digit
    fallback. Composite-tuple idiom, mirroring ``FeatureTask.sort_key``."""
    m = re.fullmatch(r"(\d+)([a-z]*)", stem)
    if m is None:
        return (1 << 30, stem)
    return (int(m.group(1)), m.group(2))


def parse_exit_reports(feature_slug: str, lifecycle_dir: Path) -> list[dict]:
    """Return all exit-report dicts for a feature, sorted by filename number.

    Reads ``lifecycle_dir/{feature_slug}/exit-reports/*.json``. Each file
    typically has ``action`` (complete/question/failed/paused), ``reason``,
    optionally ``question`` or ``error``.

    Returns ``[]`` when the directory is absent.
    """
    reports_dir = lifecycle_dir / feature_slug / "exit-reports"
    if not reports_dir.is_dir():
        return []
    out: list[dict] = []
    try:
        for path in sorted(
            reports_dir.glob("*.json"),
            key=lambda p: _exit_report_sort_key(p.stem),
        ):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                data = {**data, "_task_number": path.stem}
                out.append(data)
    except OSError:
        return []
    return out


def parse_feature_pr_artifact(lifecycle_dir: Path, feature_slug: str) -> dict | None:
    """Return parsed ``pr.json`` dict for a feature, or None when absent or invalid.

    Reads ``lifecycle_dir/{feature_slug}/pr.json``. The canonical schema
    (per ``skills/build/references/complete.md``) contains ``number``,
    ``url``, ``head_branch``, ``opened_at``, and ``repo``. Only ``number``
    and ``url`` are required for template rendering; additional fields are
    tolerated without raising.

    Returns ``None`` on ``FileNotFoundError``, ``json.JSONDecodeError``, or
    when either required key is absent.
    """
    path = lifecycle_dir / feature_slug / "pr.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if "number" not in data or "url" not in data:
        return None
    return data


def parse_learnings_progress(
    feature_slug: str, lifecycle_dir: Path, max_attempts: int = 3
) -> dict | None:
    """Parse ``learnings/progress.txt`` into a structured summary.

    The file uses the format::

        ============================================================
        Attempt N | <iso ts>
        ============================================================
        Task: ...
        Error: ...
        Output: ...

    Returns ``{"attempts": int, "recent": [{"n": int, "ts": str,
    "task": str, "error": str}, ...]}`` or None when absent.
    """
    path = lifecycle_dir / feature_slug / "learnings" / "progress.txt"
    text = read_text_lossy(path)
    if text is None:
        return None
    if not text.strip():
        return None

    blocks: list[dict] = []
    current: dict | None = None
    pending_header = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("===="):
            pending_header = True
            continue
        if pending_header and line.lower().startswith("attempt"):
            pending_header = False
            head_parts = line.split("|", 1)
            n_str = head_parts[0].strip().split()[-1] if head_parts else ""
            try:
                n = int(n_str)
            except (ValueError, IndexError):
                n = len(blocks) + 1
            ts = head_parts[1].strip() if len(head_parts) > 1 else ""
            current = {"n": n, "ts": ts, "task": "", "error": ""}
            blocks.append(current)
            continue
        pending_header = False
        if current is None:
            continue
        if line.lower().startswith("task:"):
            current["task"] = line.split(":", 1)[1].strip()
        elif line.lower().startswith("error:"):
            current["error"] = line.split(":", 1)[1].strip()

    if not blocks:
        return None
    return {
        "attempts": len(blocks),
        "recent": blocks[-max_attempts:],
    }


def parse_clarify_critic(feature_slug: str, lifecycle_dir: Path) -> dict | None:
    """Return the most recent ``clarify_critic`` event for a feature, or None.

    Scans ``lifecycle_dir/{feature_slug}/events.log``.
    """
    path = lifecycle_dir / feature_slug / "events.log"
    events, _ = _read_all_jsonl(path)
    latest: dict | None = None
    for ev in events:
        if ev.get("event") == "clarify_critic":
            latest = ev
    return latest


def parse_complexity_overrides(
    feature_slug: str, lifecycle_dir: Path
) -> list[dict]:
    """Return all ``complexity_override`` events for a feature in order."""
    path = lifecycle_dir / feature_slug / "events.log"
    events, _ = _read_all_jsonl(path)
    return [e for e in events if e.get("event") == "complexity_override"]


def parse_dispatch_details(lifecycle_dir: Path) -> dict[str, dict]:
    """Return per-feature dispatch details including budget and turn caps.

    Extends ``parse_pipeline_dispatch`` by also surfacing ``max_turns``,
    ``max_budget_usd``, and ``criticality`` from ``pipeline-events.log``.
    Last-write-wins on re-dispatch.
    """
    path = lifecycle_dir / "pipeline-events.log"
    events, _ = _read_all_jsonl(path)
    out: dict[str, dict] = {}
    for ev in events:
        kind = ev.get("event")
        feature = ev.get("feature")
        if not feature:
            continue
        if kind == "dispatch_start":
            out[feature] = {
                # See parse_pipeline_dispatch: the model arrives later.
                "model": ev.get("model") or "",
                "complexity": ev.get("complexity", ""),
                "criticality": ev.get("criticality", ""),
                "max_turns": ev.get("max_turns"),
                "max_budget_usd": ev.get("max_budget_usd"),
                "ts": ev.get("ts", ""),
            }
        elif kind in ("dispatch_model_observed", "dispatch_complete"):
            model = ev.get("model")
            if model and feature in out:
                out[feature]["model"] = model
    return out


def parse_tool_usage(
    feature_slug: str, lifecycle_dir: Path, last_n: int = 6
) -> dict:
    """Summarize per-feature agent tool usage.

    Returns a dict with:
      - ``counts``: dict[str, int] tool name -> total call count
      - ``recent``: list of {"tool": str, "ts": str, "success": bool|None}
        for the last ``last_n`` ``tool_call`` events
      - ``last_tool_ts``: ISO-8601 of the most recent tool_call, or None
      - ``total_calls``: int
    """
    path = lifecycle_dir / feature_slug / "agent-activity.jsonl"
    events, _ = _read_all_jsonl(path)
    counts: dict[str, int] = {}
    recent: list[dict] = []
    last_ts: str | None = None
    total = 0
    # Build a map of tool_result success keyed by (tool, idx) for matching;
    # simpler: walk and pair sequentially.
    for ev in events:
        ev_type = ev.get("event")
        if ev_type == "tool_call":
            tool = ev.get("tool") or "unknown"
            counts[tool] = counts.get(tool, 0) + 1
            total += 1
            ts = ev.get("ts")
            if ts:
                last_ts = ts
            recent.append({"tool": tool, "ts": ts or "", "success": None})
    # Match successes from tool_result events to the most recent call
    last_results_by_tool: dict[str, bool] = {}
    for ev in events:
        if ev.get("event") == "tool_result":
            tool = ev.get("tool") or "unknown"
            last_results_by_tool[tool] = bool(ev.get("success"))
    for entry in recent:
        s = last_results_by_tool.get(entry["tool"])
        entry["success"] = s
    return {
        "counts": counts,
        "recent": recent[-last_n:],
        "last_tool_ts": last_ts,
        "total_calls": total,
    }


def parse_recent_session_events(
    overnight_events: list[dict], last_n: int = 12
) -> list[dict]:
    """Return the last ``last_n`` overnight events with friendly labels.

    Each entry: ``{"event": str, "ts": str, "round": int|None,
    "feature": str|None, "detail": str}`` where ``detail`` is a short
    human-readable summary derived from event-specific fields.
    """
    def _detail(ev: dict) -> str:
        e = ev.get("event") or ""
        if e == "batch_assigned":
            feats = ev.get("features") or []
            n = len(feats)
            preview = ", ".join(feats[:3])
            if n > 3:
                preview += f" +{n - 3} more"
            return f"batch · {preview}" if preview else "batch · —"
        if e == "feature_checkpoint":
            note = ev.get("note") or ""
            return f"checkpoint · {note}" if note else "checkpoint"
        if e == "feature_retry":
            return f"retry attempt {ev.get('attempt', '?')}"
        if e == "feature_failed":
            return f"error · {ev.get('error', 'unknown')}"
        if e == "feature_paused":
            return ev.get("reason") or "paused"
        if e == "feature_complete":
            return f"status · {ev.get('status', '—')}"
        if e == "merge_started":
            return "merge started"
        if e == "branch_created":
            return ev.get("branch") or "branch created"
        if e == "branch_synced":
            return ev.get("branch") or "branch synced"
        if e == "plan_loaded":
            return f"plan · {ev.get('plan_ref', 'main')}"
        if e == "heartbeat":
            return f"phase · {ev.get('phase', '—')}"
        if e == "round_start":
            return "round started"
        if e == "round_complete":
            merged = ev.get("features_merged") or []
            paused = ev.get("features_paused") or []
            parts = []
            if merged:
                parts.append(f"{len(merged)} merged")
            if paused:
                parts.append(f"{len(paused)} paused")
            return " · ".join(parts) if parts else "round complete"
        if e == "session_start":
            return "session start"
        return ""

    # Sort by timestamp before slicing rather than trusting file order. The
    # panel is labelled "newest first", and append order does not guarantee
    # that: the runner interleaves writers (per-round heartbeats alongside
    # per-feature checkpoints), so a purely positional tail rendered a
    # 5m/1h/8m/45m jumble under a heading promising descending time. ISO-8601
    # UTC strings sort lexicographically in timestamp order, so no parse is
    # needed. Events missing a ``ts`` sort last (newest-first) rather than
    # crashing the comparison, and Python's stable sort keeps same-timestamp
    # events in the order the runner emitted them.
    ordered = sorted(
        overnight_events,
        key=lambda ev: (ev.get("ts") or ""),
        reverse=True,
    )
    return [
        {
            "event": (ev.get("event") or "").lower(),
            "ts": ev.get("ts") or "",
            "round": ev.get("round"),
            "feature": ev.get("feature"),
            "detail": _detail(ev),
        }
        for ev in ordered[:last_n]
    ]


def parse_checkpoints_per_feature(
    overnight_events: list[dict],
) -> dict[str, list[dict]]:
    """Group ``feature_checkpoint`` events by feature slug, oldest first."""
    out: dict[str, list[dict]] = {}
    for ev in overnight_events:
        if ev.get("event") != "feature_checkpoint":
            continue
        slug = ev.get("feature")
        if not slug:
            continue
        out.setdefault(slug, []).append({
            "ts": ev.get("ts") or "",
            "note": ev.get("note") or "",
        })
    return out


def parse_retries_per_feature(
    overnight_events: list[dict],
) -> dict[str, int]:
    """Count ``feature_retry`` events per feature."""
    out: dict[str, int] = {}
    for ev in overnight_events:
        if ev.get("event") != "feature_retry":
            continue
        slug = ev.get("feature")
        if not slug:
            continue
        out[slug] = max(out.get(slug, 0), int(ev.get("attempt") or 0))
    return out


def parse_batches_per_round(
    overnight_events: list[dict],
) -> dict[int, list[str]]:
    """Return the most recent ``BATCH_ASSIGNED`` features list per round."""
    out: dict[int, list[str]] = {}
    for ev in overnight_events:
        if ev.get("event") != "batch_assigned":
            continue
        rn = ev.get("round")
        try:
            rn_int = int(rn)
        except (TypeError, ValueError):
            continue
        feats = ev.get("features") or []
        if isinstance(feats, list):
            out[rn_int] = list(feats)
    return out


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
