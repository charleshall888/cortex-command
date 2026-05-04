"""On-disk sidecar index of active scheduled launches.

The sidecar at ``~/.cache/cortex-command/scheduled-launches.json`` is a
JSON array of records, one per pending schedule. Schema (per record):

    {
      "label":             str,
      "session_id":        str,
      "plist_path":        str,
      "launcher_path":     str,
      "scheduled_for_iso": str,
      "created_at_iso":    str,
    }

Writes are atomic (tempfile in the same directory + ``durable_fsync``
+ ``os.replace``) so a crashed process can never leave a half-written
file. Reads tolerate corruption: a JSONDecodeError logs a single
warning and returns an empty list; the next ``add_entry`` /
``remove_entry`` write overwrites the corrupt file. This matches the
spec's "sidecar index file corrupted or missing — schedule subcommand
recreates it on next write; cancel-list returns empty (warn but don't
crash)" edge case.

The sidecar is consumed by:
  - ``MacOSLaunchAgentBackend.schedule()`` — calls ``add_entry`` after
    bootstrap+verify succeeds.
  - ``MacOSLaunchAgentBackend._gc_pass()`` — calls ``read_sidecar`` to
    determine which plists in ``$TMPDIR/cortex-overnight-launch/`` are
    still tracked.
  - ``cortex overnight cancel`` — calls ``find_by_session_id`` to
    locate the schedule for a session and ``remove_entry`` after
    ``launchctl bootout``.
  - ``cortex overnight start`` — calls ``read_sidecar`` to detect
    pending schedules and exit non-zero unless ``--force``.

Concurrency: standalone calls to ``add_entry`` / ``remove_entry`` are
NOT serialized internally. The schedule path acquires the
:func:`schedule_lock` (in :mod:`lock`) BEFORE calling ``add_entry``
so two concurrent schedules cannot race on the same record. Cancel
also runs under the schedule lock per the task contract; cross-path
read-only callers (``read_sidecar`` from status / list) do not need
the lock because ``os.replace`` is atomic — readers see either the
old file or the new file, never a partial write.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from cortex_command.common import durable_fsync
from cortex_command.overnight.scheduler.protocol import ScheduledHandle


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Cache directory and sidecar filename. Mirrors the layout used by
# :mod:`lock` so the sidecar and its lockfile sit side by side.
_CACHE_DIR_RELATIVE = Path(".cache") / "cortex-command"
_SIDECAR_FILENAME = "scheduled-launches.json"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    """Resolve ``~/.cache/cortex-command/`` (no creation)."""
    return Path.home() / _CACHE_DIR_RELATIVE


def sidecar_path() -> Path:
    """Absolute path to the sidecar index JSON file.

    Exposed publicly so callers (tests, debug utilities) can locate
    the file without re-deriving the layout.
    """
    return _cache_dir() / _SIDECAR_FILENAME


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _record_from_handle(handle: ScheduledHandle) -> dict:
    """Convert a :class:`ScheduledHandle` to the on-disk dict form."""
    return {
        "label": handle.label,
        "session_id": handle.session_id,
        "plist_path": str(handle.plist_path),
        "launcher_path": str(handle.launcher_path),
        "scheduled_for_iso": handle.scheduled_for_iso,
        "created_at_iso": handle.created_at_iso,
    }


def _handle_from_record(record: dict) -> ScheduledHandle:
    """Convert an on-disk dict back into a :class:`ScheduledHandle`.

    Tolerant of missing optional fields: any missing required field
    raises ``KeyError``, which the caller (``read_sidecar``) catches
    and treats as corruption.
    """
    return ScheduledHandle(
        label=record["label"],
        session_id=record["session_id"],
        plist_path=Path(record["plist_path"]),
        launcher_path=Path(record["launcher_path"]),
        scheduled_for_iso=record["scheduled_for_iso"],
        created_at_iso=record["created_at_iso"],
    )


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_records(records: list[dict]) -> None:
    """Write ``records`` to the sidecar file atomically.

    Creates the parent directory on first use (``mkdir -p`` semantics
    per R8). Uses tempfile-in-same-dir + ``durable_fsync`` +
    ``os.replace`` — the canonical pattern from
    :func:`cortex_command.common.durable_fsync` callers (see
    ``ipc._atomic_write_json``).
    """
    path = sidecar_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = json.dumps(records, indent=2, sort_keys=True).encode("utf-8")

    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}-",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    closed = False
    try:
        tmp.write(data)
        tmp.flush()
        durable_fsync(tmp.fileno())
        tmp.close()
        closed = True
        os.replace(tmp_path, path)
    except BaseException:
        if not closed:
            try:
                tmp.close()
            except OSError:
                pass
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_sidecar() -> list[ScheduledHandle]:
    """Return all entries in the sidecar index.

    Behavior on missing file: returns ``[]`` (no warning — first-use is
    the normal case).

    Behavior on JSON-decode failure: logs a single WARNING and returns
    ``[]``. The next ``add_entry`` / ``remove_entry`` write overwrites
    the corrupt file, so a corrupt sidecar self-heals on the next
    schedule operation.

    Behavior on a record that fails ``_handle_from_record`` (missing
    required fields): logs a WARNING, skips that record, and returns
    the rest. This degrades gracefully rather than corrupting the
    cancel path on a single malformed record.
    """
    path = sidecar_path()
    if not path.exists():
        return []

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("sidecar read failed (%s); treating as empty", exc)
        return []

    if not raw.strip():
        return []

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "sidecar JSON decode failed (%s); treating as empty",
            exc,
        )
        return []

    if not isinstance(decoded, list):
        logger.warning(
            "sidecar root is not a list (got %s); treating as empty",
            type(decoded).__name__,
        )
        return []

    handles: list[ScheduledHandle] = []
    for record in decoded:
        if not isinstance(record, dict):
            logger.warning(
                "sidecar record is not a dict (got %s); skipping",
                type(record).__name__,
            )
            continue
        try:
            handles.append(_handle_from_record(record))
        except KeyError as exc:
            logger.warning(
                "sidecar record missing required field %s; skipping",
                exc,
            )
            continue
    return handles


def add_entry(handle: ScheduledHandle) -> None:
    """Append ``handle`` to the sidecar.

    Reads the current sidecar (treating corruption as empty), appends
    the new record, and writes atomically. If a record with the same
    ``label`` already exists, it is replaced rather than duplicated —
    label uniqueness is the load-bearing contract for cancel and GC.
    """
    existing = read_sidecar()
    records = [
        _record_from_handle(h) for h in existing if h.label != handle.label
    ]
    records.append(_record_from_handle(handle))
    _atomic_write_records(records)


def remove_entry(label: str) -> bool:
    """Remove the record with ``label`` from the sidecar.

    Returns:
        ``True`` if a record was removed; ``False`` if no record
        matched (idempotent — calling ``remove_entry`` for a label
        already absent is not an error).
    """
    existing = read_sidecar()
    kept = [h for h in existing if h.label != label]
    if len(kept) == len(existing):
        return False
    _atomic_write_records([_record_from_handle(h) for h in kept])
    return True


def find_by_session_id(session_id: str) -> ScheduledHandle | None:
    """Return the entry whose ``session_id`` matches, or ``None``.

    If multiple records share a session_id (should not occur under
    normal operation, but the sidecar tolerates it for forward
    compatibility), the most recently added one wins — i.e. the last
    matching record in the list, since ``add_entry`` appends.
    """
    matches = [h for h in read_sidecar() if h.session_id == session_id]
    if not matches:
        return None
    return matches[-1]


__all__ = [
    "add_entry",
    "find_by_session_id",
    "read_sidecar",
    "remove_entry",
    "sidecar_path",
]
