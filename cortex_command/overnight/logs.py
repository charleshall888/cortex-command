"""Byte-offset + RFC3339 cursor log reader for `cortex overnight logs`.

Backend for R4/R10/R11: reads per-session `events.log`,
`agent-activity.jsonl`, and `escalations.jsonl` with support for three
cursor forms:

- Byte-offset cursors (``@<int>``): exact, idempotent across retries. Used by
  the existing ``cortex overnight logs`` CLI. Seeks directly to the offset
  and reads up to ``limit`` lines. Past-EOF returns empty with a
  ``# cursor-beyond-eof`` note on stderr.
- Opaque base64-JSON cursors (R10): produced by :mod:`.cursor`. Carry
  ``{offset, file_size_at_emit}`` so :func:`read_log_structured` can detect
  log-file truncation across reads. Used by the MCP ``overnight_logs`` tool.
- RFC3339 timestamp cursors (``<iso8601>``): filters each line's ``ts`` field
  where ``ts >= since_dt``. Convenient but not idempotent across lines with
  identical sub-second timestamps.

When no cursor is supplied, reads the last ``tail`` lines (default 20). In
all paths ``limit`` caps total returned lines. The returned
``next_byte_offset`` (legacy 2-tuple form) is suitable for chaining via
``--since @<next>`` calls and is emitted by the CLI handler as a
``next_cursor: @<int>`` trailer on stderr.

Pattern reference: supervisord XML-RPC ``log.tail(offset, length) -> (string,
new_offset, overflow)``.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from cortex_command.overnight import cursor as cursor_codec

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


# ---------------------------------------------------------------------------
# Structured / opaque-cursor read path (R10, R11) — used by MCP overnight_logs
# ---------------------------------------------------------------------------

# Sentinel emitted in place of a single oversized log line. The "X" placeholder
# is filled with the line's true byte length so the client can confirm the
# truncation boundary independently.
_OVERSIZED_LINE_SENTINEL = "...(line truncated, original {n} bytes)"

# When a single log line exceeds the byte budget, we still emit a representative
# slice so the consumer can see the head of the line. This cap keeps the
# truncated payload compact (~10 KB) regardless of how monstrous the source
# line was.
_OVERSIZED_LINE_HEAD_CAP = 10_000


def read_log_structured(
    log_path: Path,
    cursor: str | None,
    tail: int | None,
    limit: int,
    max_bytes: int | None = None,
) -> dict:
    """Read lines with opaque-cursor + max-bytes semantics (R10, R11).

    This is the structured-return companion to :func:`read_log`. It accepts
    either the legacy ``@<int>`` byte-offset cursor or an opaque base64-JSON
    cursor produced by :mod:`.cursor`. It always returns a dict with
    truncation/oversized-line signals so the MCP ``overnight_logs`` tool can
    surface them to clients.

    Args:
        log_path: Path to the log file.
        cursor: Optional cursor. ``None`` means "tail mode" — read the last
            ``tail`` lines. ``@<int>`` is the byte-offset cursor. Otherwise
            interpreted as an opaque base64-JSON cursor.
        tail: When ``cursor`` is ``None``, read the last ``tail`` lines
            (default 20 via caller). Applied after cursor filtering when
            both are present.
        limit: Hard cap on total returned lines.
        max_bytes: Optional read-budget cap. When a single log line's
            ``start_offset + length`` would exceed this budget, the line is
            replaced with a truncated head + sentinel; ``oversized_line`` is
            set ``True`` and ``original_line_bytes`` records the source
            length. ``None`` disables the cap.

    Returns:
        A dict with the following keys:

        - ``lines``: list of strings (with trailing newlines stripped).
        - ``next_cursor``: opaque cursor string for resumption, or ``None``
          when ``cursor_invalid`` is ``True`` (the client must re-baseline).
        - ``eof``: ``True`` when the read reached end-of-file.
        - ``cursor_invalid``: ``True`` when the supplied opaque cursor's
          ``file_size_at_emit > current_size`` (file was truncated between
          emit and re-read). On ``True``, ``lines`` is empty and
          ``next_cursor`` is ``None``.
        - ``oversized_line``: ``True`` when a single log line exceeded
          ``max_bytes``. Only present (as ``True``) in that case.
        - ``original_line_bytes``: Source byte length of the oversized line.
          Only present when ``oversized_line`` is ``True``.
        - ``current_size``: File size at read time. Always present so
          callers (e.g. the MCP layer) can surface it on shrink.

    Raises:
        ValueError("invalid cursor"): when ``cursor`` cannot be parsed as
            ``@<int>`` or as an opaque base64-JSON token.
    """
    if not log_path.exists():
        return {
            "lines": [],
            "next_cursor": None,
            "eof": True,
            "cursor_invalid": False,
            "current_size": 0,
        }

    current_size = log_path.stat().st_size

    # Resolve cursor → starting offset, with truncation detection on the
    # opaque form.
    start_offset: int | None
    if cursor is None:
        start_offset = None
    elif cursor.startswith("@"):
        # Legacy byte-offset cursor (CLI compatibility).
        try:
            start_offset = int(cursor[1:])
        except ValueError as exc:
            raise ValueError("invalid cursor") from exc
        if start_offset < 0:
            raise ValueError("invalid cursor")
    else:
        decoded = cursor_codec.decode(cursor)
        if decoded["file_size_at_emit"] > current_size:
            # File was truncated between emit and re-read. Signal the client
            # to drop the cursor and re-baseline; per R11, next_cursor is
            # None and lines is empty.
            return {
                "lines": [],
                "next_cursor": None,
                "eof": False,
                "cursor_invalid": True,
                "current_size": current_size,
            }
        start_offset = decoded["offset"]

    # Tail-mode (no cursor): read from start, return the last `tail` lines.
    if start_offset is None:
        effective_tail = tail if tail is not None else 20
        count = min(effective_tail, limit) if effective_tail >= 0 else limit

        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            end_offset = f.tell()

        if count <= 0:
            return {
                "lines": [],
                "next_cursor": cursor_codec.encode(end_offset, end_offset),
                "eof": True,
                "cursor_invalid": False,
                "current_size": current_size,
            }
        last = all_lines[-count:]
        stripped = [ln.rstrip("\n") for ln in last]
        return {
            "lines": stripped,
            "next_cursor": cursor_codec.encode(end_offset, end_offset),
            "eof": True,
            "cursor_invalid": False,
            "current_size": current_size,
        }

    # Past-EOF: emit a cursor pinned to current_size so the client can
    # resume once the writer adds more bytes.
    if start_offset >= current_size:
        return {
            "lines": [],
            "next_cursor": cursor_codec.encode(current_size, current_size),
            "eof": True,
            "cursor_invalid": False,
            "current_size": current_size,
        }

    lines: list[str] = []
    bytes_consumed_before_line = 0
    oversized_line = False
    original_line_bytes = 0
    next_offset = start_offset

    with log_path.open("rb") as fb:
        fb.seek(start_offset)
        for _ in range(limit):
            line_start = fb.tell()
            raw = fb.readline()
            if not raw:
                break
            line_len = len(raw)

            # Oversized-line check: a single line whose length alone busts
            # the budget cannot be meaningfully streamed inline. Emit a
            # truncated head + sentinel and advance the cursor past its
            # terminating newline so the client paginates past it.
            if max_bytes is not None and line_len > max_bytes:
                # Decode just the head we keep so we don't flood the wire
                # with a multi-MB single line.
                head = raw[:_OVERSIZED_LINE_HEAD_CAP].decode(
                    "utf-8", errors="replace"
                )
                # Strip a trailing newline from the head (decoded slice may
                # include one if the cap exceeds the line's natural length,
                # though the oversized-line guard rules that out — defensive).
                if head.endswith("\n"):
                    head = head[:-1]
                truncated = head + _OVERSIZED_LINE_SENTINEL.format(n=line_len)
                lines.append(truncated)
                oversized_line = True
                original_line_bytes = line_len
                next_offset = line_start + line_len
                break

            # Aggregate-budget check: stop before adding a line that would
            # push us past max_bytes. The standard pagination cursor lets
            # the client resume from line_start on the next call.
            if (
                max_bytes is not None
                and bytes_consumed_before_line + line_len > max_bytes
            ):
                next_offset = line_start
                break

            lines.append(raw.rstrip(b"\n").decode("utf-8", errors="replace"))
            bytes_consumed_before_line += line_len
            next_offset = fb.tell()

    # `tail` filters the cursor-mode result when both are present.
    if tail is not None and tail >= 0:
        lines = lines[-tail:]

    eof = next_offset >= current_size
    result: dict = {
        "lines": lines,
        "next_cursor": cursor_codec.encode(next_offset, current_size),
        "eof": eof,
        "cursor_invalid": False,
        "current_size": current_size,
    }
    if oversized_line:
        result["oversized_line"] = True
        result["original_line_bytes"] = original_line_bytes
    return result
