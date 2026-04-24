"""Byte-offset + RFC3339 cursor log reader for `cortex overnight logs`.

Backend for R4/R11: reads per-session `events.log`, `agent-activity.jsonl`,
and `escalations.jsonl` with support for two cursor forms:

- Byte-offset cursors (``@<int>``): exact, idempotent across retries. Used by
  programmatic consumers (ticket 116's MCP tools). Seeks directly to the
  offset and reads up to ``limit`` lines. Past-EOF returns empty with a
  ``# cursor-beyond-eof`` note on stderr.
- RFC3339 timestamp cursors (``<iso8601>``): filters each line's ``ts`` field
  where ``ts >= since_dt``. Convenient but not idempotent across lines with
  identical sub-second timestamps.

When no cursor is supplied, reads the last ``tail`` lines (default 20). In
all paths ``limit`` caps total returned lines. The returned
``next_byte_offset`` is suitable for chaining via ``--since @<next>`` calls
and is emitted by the CLI handler as a ``next_cursor: @<int>`` trailer on
stderr.

Pattern reference: supervisord XML-RPC ``log.tail(offset, length) -> (string,
new_offset, overflow)``.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Maps --files stream names to per-session log filenames.
LOG_FILES: dict[str, str] = {
    "events": "overnight-events.log",
    "agent-activity": "agent-activity.jsonl",
    "escalations": "escalations.jsonl",
}


def _parse_cursor(since: str) -> tuple[str, object]:
    """Classify a cursor string.

    Returns ``("offset", int)`` for ``@<int>`` cursors, ``("timestamp",
    datetime)`` for RFC3339 cursors. Raises ``ValueError("invalid cursor")``
    on anything else.
    """
    if since.startswith("@"):
        try:
            offset = int(since[1:])
        except ValueError as exc:
            raise ValueError("invalid cursor") from exc
        if offset < 0:
            raise ValueError("invalid cursor")
        return ("offset", offset)

    try:
        # datetime.fromisoformat accepts RFC3339 in Python 3.11+, including
        # the trailing 'Z' suffix.
        dt = datetime.fromisoformat(since)
    except ValueError as exc:
        raise ValueError("invalid cursor") from exc
    return ("timestamp", dt)


def _extract_ts(line: str) -> datetime | None:
    """Parse the ``ts`` field out of a JSONL line, or return None.

    Uses a cheap string scan first to avoid the cost of a full JSON parse on
    lines that don't even carry a ``ts`` field. Malformed lines return None
    (caller skips them silently per spec).
    """
    import json

    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    ts = obj.get("ts")
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def read_log(
    log_path: Path,
    since: str | None,
    tail: int | None,
    limit: int,
) -> tuple[list[str], int]:
    """Read lines from ``log_path`` per cursor + tail + limit.

    Args:
        log_path: Path to the log file (events.log or a .jsonl file).
        since: Optional cursor. ``@<int>`` for byte-offset, RFC3339 for
            timestamp filtering. ``None`` disables cursor filtering.
        tail: When ``since`` is ``None``, read the last ``tail`` lines
            (default 20 via caller). Applied after ``since`` filtering when
            both are present.
        limit: Hard cap on total returned lines in every path.

    Returns:
        ``(lines, next_byte_offset)``. ``next_byte_offset`` is the file
        position immediately after the last line returned (or the file size
        when past EOF / no lines read), suitable for chained
        ``--since @<next>`` queries.

    Raises:
        ValueError("invalid cursor"): when ``since`` is neither ``@<int>``
            nor parseable as RFC3339.
    """
    if not log_path.exists():
        return ([], 0)

    file_size = log_path.stat().st_size

    if since is not None:
        kind, value = _parse_cursor(since)
    else:
        kind, value = (None, None)

    if kind == "offset":
        offset = int(value)  # type: ignore[arg-type]
        if offset >= file_size:
            # Past EOF: caller emits `# cursor-beyond-eof` trailer on stderr
            # per R4 / spec edge case.
            sys.stderr.write("# cursor-beyond-eof\n")
            return ([], file_size)

        lines: list[str] = []
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            for _ in range(limit):
                line = f.readline()
                if not line:
                    break
                lines.append(line.rstrip("\n"))
            next_offset = f.tell()

        # `tail` is applied after `since` filtering when both are present.
        if tail is not None and tail >= 0:
            lines = lines[-tail:]
        return (lines, next_offset)

    if kind == "timestamp":
        since_dt: datetime = value  # type: ignore[assignment]
        filtered: list[str] = []
        next_offset = 0
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            while True:
                line = f.readline()
                if not line:
                    break
                ts = _extract_ts(line)
                if ts is None:
                    # Malformed lines skipped silently per spec.
                    continue
                if ts >= since_dt:
                    filtered.append(line.rstrip("\n"))
                    next_offset = f.tell()
                    if len(filtered) >= limit:
                        break

        if tail is not None and tail >= 0:
            filtered = filtered[-tail:]
        return (filtered, next_offset)

    # No cursor: read last `tail` lines (default 20 per caller/spec).
    effective_tail = tail if tail is not None else 20
    # `limit` still caps the returned count in this path.
    count = min(effective_tail, limit) if effective_tail >= 0 else limit

    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
        next_offset = f.tell()

    if count <= 0:
        return ([], next_offset)
    last = all_lines[-count:]
    return ([ln.rstrip("\n") for ln in last], next_offset)
