"""Opaque base64-JSON cursor codec for log pagination (R10, R11).

The MCP `overnight_logs` tool returns a `next_cursor` string that clients pass
back unmodified on the next read. The encoded form carries enough state for
the server to detect log-file truncation across calls — when the file shrinks
between an emit and a re-read, the embedded `file_size_at_emit` exceeds the
current size, and `read_log` signals `cursor_invalid: True` with
`next_cursor: None` so the client re-baselines without a cursor.

Cursors are opaque to consumers per the MCP spec; the encoded structure is
documented here and in research.md but **never** in `docs/mcp-server.md`
(R23). Documentation that leaks the structure invites coupling and defeats
the invariant.

Encoding:
    base64.urlsafe_b64encode(json.dumps({"offset": ..., "file_size_at_emit": ...}).encode())
"""

from __future__ import annotations

import base64
import json


def encode(offset: int, file_size_at_emit: int) -> str:
    """Encode a (offset, file_size_at_emit) pair into an opaque cursor token.

    Args:
        offset: Byte offset into the log file at which the next read should
            resume.
        file_size_at_emit: Size of the log file at the time this cursor was
            emitted, used by ``read_log`` on the next call to detect
            truncation.

    Returns:
        Base64 URL-safe encoded JSON string. Treat as opaque on the client
        side — re-encoding parameters that arrive elsewhere is a contract
        violation.
    """
    payload = json.dumps(
        {"offset": int(offset), "file_size_at_emit": int(file_size_at_emit)}
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode(cursor: str) -> dict:
    """Decode an opaque cursor token back into ``{offset, file_size_at_emit}``.

    Args:
        cursor: Cursor previously produced by :func:`encode`.

    Returns:
        Dict with integer ``offset`` and ``file_size_at_emit`` keys.

    Raises:
        ValueError: When ``cursor`` is malformed (bad base64, bad JSON,
            missing keys, or non-integer values).
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ValueError("invalid cursor") from exc

    try:
        obj = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid cursor") from exc

    if not isinstance(obj, dict):
        raise ValueError("invalid cursor")

    offset = obj.get("offset")
    file_size_at_emit = obj.get("file_size_at_emit")
    if not isinstance(offset, int) or not isinstance(file_size_at_emit, int):
        raise ValueError("invalid cursor")
    if offset < 0 or file_size_at_emit < 0:
        raise ValueError("invalid cursor")

    return {"offset": offset, "file_size_at_emit": file_size_at_emit}
