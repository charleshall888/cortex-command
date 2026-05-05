"""Scanner for ``scheduled-fire-failed.json`` fail-markers (spec §R13).

When the launchd-fired launcher script (Task 3 of the launchagent-scheduler
migration) cannot spawn the cortex binary at fire time — typically due to
a TCC permission denial (EPERM) or a missing/non-executable cortex binary
(command-not-found) — it writes a JSON sentinel at::

    <session_dir>/scheduled-fire-failed.json

This module provides the consumer side of that contract: a single
function :func:`scan_session_dirs` that walks
``<state_root>/sessions/*/scheduled-fire-failed.json``, parses each
marker, and returns a list of :class:`FailedFire` records.

The morning-report integration (``report.collect_report_data``) and the
``cortex overnight status`` JSON envelope and human output both call this
scanner so fire-time failures surface across all three layered surfaces:

  1. Immediate macOS notification at fire time (Task 3, ``osascript``).
  2. ``cortex overnight status`` reports the failure any time the user
     runs status (this module + ``cli_handler.handle_status``).
  3. The next morning report includes the failure in a dedicated section
     (this module + ``report.render_scheduled_fire_failures``).

The module is intentionally stand-alone: no dependency on the scheduler
package or the runner. Corrupt marker JSON is skipped with a warning (so
one malformed file does not block surface of the rest), and a missing
state root or sessions directory returns an empty list.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


__all__ = ["FailedFire", "scan_session_dirs"]


@dataclass
class FailedFire:
    """A single parsed ``scheduled-fire-failed.json`` fail-marker.

    Attributes:
        ts: ISO-8601 timestamp (string) when the launcher recorded the
            failure. Comes from the marker's ``ts`` field.
        error_class: Failure classification. Currently ``"EPERM"`` or
            ``"command_not_found"`` per Task 3 of the migration spec.
        error_text: Human-readable error text captured by the launcher
            (e.g. the missing binary path or the permission-denied
            message).
        label: launchd label used to schedule the fire (e.g.
            ``com.charleshall.cortex-command.overnight-schedule.<sid>.<n>``).
        session_id: The cortex session id this fire was scheduled for.
        session_dir: Absolute path to the session directory containing
            this fail-marker. Useful for diagnostics — the morning
            report and status surface both echo this so the user can
            copy-paste straight to ``cat <path>/scheduled-fire-failed.json``.
    """

    ts: str
    error_class: str
    error_text: str
    label: str
    session_id: str
    session_dir: Path

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (``session_dir`` cast to str)."""
        d = asdict(self)
        d["session_dir"] = str(self.session_dir)
        return d


def _parse_marker_ts(ts_value: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string written by the launcher.

    The launcher emits timestamps in the form ``2026-05-04T22:30:11Z``
    (GMT) per its ``date -u +%Y-%m-%dT%H:%M:%SZ`` invocation. Python's
    :meth:`datetime.fromisoformat` accepts that format on 3.11+; for
    older versions we replace a trailing ``Z`` with ``+00:00`` first.
    Returns ``None`` when the string is unparseable, which causes the
    ``since`` filter in :func:`scan_session_dirs` to fall through and
    keep the marker rather than drop it silently.
    """
    if not isinstance(ts_value, str) or not ts_value:
        return None
    s = ts_value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def scan_session_dirs(
    state_root: Path,
    since: Optional[datetime] = None,
) -> list[FailedFire]:
    """Walk ``state_root/sessions/*`` for fail-marker JSON files.

    Args:
        state_root: The cortex state root containing a ``sessions/``
            subdirectory (typically ``<repo>/lifecycle``). When the
            directory does not exist, an empty list is returned.
        since: Optional cutoff. When provided, fail-markers whose
            ``ts`` is strictly before this datetime are filtered out.
            Markers whose ``ts`` does not parse as ISO-8601 are kept
            (better to over-surface than drop silently).

    Returns:
        List of :class:`FailedFire` records, sorted by timestamp string
        ascending so the oldest failure surfaces first.

    Behavior:
        - Missing ``state_root`` or missing ``sessions/`` subdir →
          returns ``[]``.
        - Corrupt JSON in any single marker → that marker is skipped
          with a warning to stderr; scanning continues.
        - A marker missing one or more required fields (``ts``,
          ``error_class``, ``error_text``, ``label``, ``session_id``)
          → that marker is skipped with a warning; the remaining
          markers are still returned.
    """
    sessions_root = state_root / "sessions"
    if not sessions_root.is_dir():
        return []

    results: list[FailedFire] = []

    for marker_path in sorted(sessions_root.glob("*/scheduled-fire-failed.json")):
        if not marker_path.is_file():
            continue

        try:
            text = marker_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"warning: cannot read fail-marker {marker_path}: {exc}",
                file=sys.stderr,
            )
            continue

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            print(
                f"warning: corrupt fail-marker {marker_path}: {exc}",
                file=sys.stderr,
            )
            continue

        if not isinstance(payload, dict):
            print(
                f"warning: fail-marker {marker_path} is not a JSON object; skipping",
                file=sys.stderr,
            )
            continue

        required = ("ts", "error_class", "error_text", "label", "session_id")
        missing = [k for k in required if k not in payload]
        if missing:
            print(
                f"warning: fail-marker {marker_path} missing keys {missing}; skipping",
                file=sys.stderr,
            )
            continue

        ts_value = str(payload["ts"])

        # Apply the `since` cutoff. A marker with an unparseable ts is
        # kept (we'd rather over-surface than drop silently).
        if since is not None:
            parsed = _parse_marker_ts(ts_value)
            if parsed is not None:
                # Compare apples-to-apples: if `since` is naive, treat
                # parsed as naive (drop tzinfo); if `since` is aware,
                # ensure parsed is aware. The launcher always writes
                # UTC, so parsed will be aware; if `since` is naive we
                # strip the tz from parsed for the comparison.
                if since.tzinfo is None and parsed.tzinfo is not None:
                    parsed_cmp = parsed.replace(tzinfo=None)
                else:
                    parsed_cmp = parsed
                if parsed_cmp < since:
                    continue

        results.append(
            FailedFire(
                ts=ts_value,
                error_class=str(payload["error_class"]),
                error_text=str(payload["error_text"]),
                label=str(payload["label"]),
                session_id=str(payload["session_id"]),
                session_dir=marker_path.parent.resolve(),
            )
        )

    results.sort(key=lambda f: f.ts)
    return results
