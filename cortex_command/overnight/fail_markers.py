"""Scanners for the launcher's fire-time marker files (spec §R6/§R7/§R13).

The launchd-fired launcher script writes one of two kinds of marker at
fire time, depending on the outcome of the spawn handshake:

  * A **failure** marker at ``<session_dir>/scheduled-fire-failed.json``
    when the fire genuinely died — either the cortex binary could not be
    executed (TCC EPERM / command-not-found) or the runner child died
    before claiming ``runner.pid`` (``error_class: spawn_died``).
  * A distinct **advisory** marker at
    ``<session_dir>/scheduled-fire-advisory.json`` (carrying
    ``kind: advisory`` / ``severity: advisory``,
    ``error_class: spawn_unconfirmed``) when the fire is live-but-slow:
    the runner is alive but had not yet claimed ``runner.pid`` when the
    handshake budget elapsed. This is NOT a failure.

This module provides the consumer side of both contracts:

  * :func:`scan_session_dirs` walks
    ``<state_root>/sessions/*/scheduled-fire-failed.json`` and returns a
    list of :class:`FailedFire` records (``kind == "failure"``).
  * :func:`scan_advisory_dirs` walks
    ``<state_root>/sessions/*/scheduled-fire-advisory.json`` and returns
    a list of :class:`FireAdvisory` records, classifying each — at read
    time — as a fresh advisory or an **escalated** advisory (a stale
    advisory whose runner appears wedged; see below).

**Stale-advisory escalation (spec §R7).** An advisory marker is only ever
written by the launcher; the read-only status/morning-report surfaces
never write markers. So a runner that wedged *before* its round loop —
spawned, claimed nothing, and then died or hung without ever clearing the
advisory — would otherwise render as a perpetual advisory forever. To
close that orphan gap, :func:`scan_advisory_dirs` re-classifies an
advisory as a FAILURE at read time when ALL of:

  1. its age exceeds :data:`STALE_ADVISORY_THRESHOLD_SECONDS` (set
     comfortably above the fire-path handshake budget so a normally-slow
     start is never escalated), AND
  2. there is no live ``runner.pid`` in the session dir
     (:func:`ipc.verify_runner_pid` returns ``False`` or the file is
     absent), AND
  3. the session is not executing/complete (its on-disk ``phase`` is
     neither ``"executing"`` nor ``"complete"``) — a session that
     reached its round loop demonstrates the slow start resolved, so the
     advisory was benign and must NOT escalate.

The escalation is inferred purely at read time from the marker age, the
``runner.pid`` liveness probe, and the session state file; nothing is
written back.

The module is intentionally stand-alone with respect to the scheduler
package and the runner. Corrupt marker JSON is skipped with a warning (so
one malformed file does not block surface of the rest), and a missing
state root or sessions directory returns an empty list.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cortex_command.overnight import ipc


__all__ = [
    "FailedFire",
    "FireAdvisory",
    "scan_session_dirs",
    "scan_advisory_dirs",
    "STALE_ADVISORY_THRESHOLD_SECONDS",
]


# Stale-advisory escalation threshold (spec §R7). An advisory older than
# this — with no live runner.pid and a session that never reached its
# round loop — escalates to a failure at read time. Set comfortably above
# the fire-path handshake budget (``_FIRE_HANDSHAKE_TIMEOUT_SECONDS`` =
# 20s in cli_handler) so a normally-slow post-sleep cold start is never
# mistaken for a wedged runner: 5 minutes is ~15x the handshake budget,
# far longer than any healthy runner takes to claim runner.pid, yet soon
# enough to surface a genuinely wedged runner the same night.
STALE_ADVISORY_THRESHOLD_SECONDS: float = 300.0


@dataclass
class FailedFire:
    """A single parsed ``scheduled-fire-failed.json`` fail-marker.

    Attributes:
        ts: ISO-8601 timestamp (string) when the launcher recorded the
            failure. Comes from the marker's ``ts`` field.
        error_class: Failure classification. ``"EPERM"`` or
            ``"command_not_found"`` for a bash-side exec failure, or
            ``"spawn_died"`` when the runner child died before claiming
            ``runner.pid``.
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
        kind: The ``kind`` dimension distinguishing a real failure from an
            escalated advisory. ``"failure"`` for a marker scanned from
            ``scheduled-fire-failed.json``; ``"advisory_escalated"`` for a
            stale advisory re-classified as a failure at read time
            (:func:`scan_advisory_dirs`).
    """

    ts: str
    error_class: str
    error_text: str
    label: str
    session_id: str
    session_dir: Path
    kind: str = "failure"

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (``session_dir`` cast to str)."""
        d = asdict(self)
        d["session_dir"] = str(self.session_dir)
        return d


@dataclass
class FireAdvisory:
    """A single parsed ``scheduled-fire-advisory.json`` advisory marker.

    A live-but-unconfirmed fire: the runner is alive but had not yet
    claimed ``runner.pid`` when the handshake budget elapsed. This is NOT
    a failure — unless it has gone stale (see :func:`scan_advisory_dirs`),
    in which case it is surfaced as a :class:`FailedFire` instead.

    Attributes:
        ts: ISO-8601 timestamp (string) when the launcher recorded the
            advisory.
        error_class: Advisory classification — ``"spawn_unconfirmed"``.
        error_text: Human-readable advisory text captured by the launcher.
        label: launchd label used to schedule the fire.
        session_id: The cortex session id this fire was scheduled for.
        session_dir: Absolute path to the session directory containing
            this advisory marker.
        kind: The marker's own ``kind`` field — ``"advisory"``.
        severity: The marker's own ``severity`` field — ``"advisory"``.
    """

    ts: str
    error_class: str
    error_text: str
    label: str
    session_id: str
    session_dir: Path
    kind: str = "advisory"
    severity: str = "advisory"

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


def _passes_since_cutoff(ts_value: str, since: Optional[datetime]) -> bool:
    """Return ``True`` if ``ts_value`` is at/after ``since``.

    A marker whose ``ts`` is unparseable is kept (we'd rather over-surface
    than drop silently), as is any marker when ``since`` is ``None``.
    """
    if since is None:
        return True
    parsed = _parse_marker_ts(ts_value)
    if parsed is None:
        return True
    # Compare apples-to-apples: if `since` is naive, treat parsed as
    # naive (drop tzinfo); the launcher always writes UTC so parsed is
    # aware. If `since` is aware, leave parsed as-is.
    if since.tzinfo is None and parsed.tzinfo is not None:
        parsed_cmp = parsed.replace(tzinfo=None)
    else:
        parsed_cmp = parsed
    return parsed_cmp >= since


def _read_marker_payload(marker_path: Path, descriptor: str) -> Optional[dict]:
    """Read + parse a marker JSON file, returning ``None`` on any error.

    ``descriptor`` is used only in warning messages (e.g. ``"fail-marker"``
    or ``"advisory marker"``). Unreadable, corrupt, or non-object markers
    are skipped with a warning to stderr.
    """
    if not marker_path.is_file():
        return None
    try:
        text = marker_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"warning: cannot read {descriptor} {marker_path}: {exc}",
            file=sys.stderr,
        )
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        print(
            f"warning: corrupt {descriptor} {marker_path}: {exc}",
            file=sys.stderr,
        )
        return None
    if not isinstance(payload, dict):
        print(
            f"warning: {descriptor} {marker_path} is not a JSON object; skipping",
            file=sys.stderr,
        )
        return None
    return payload


def _session_phase(session_dir: Path) -> Optional[str]:
    """Return the on-disk ``phase`` for a session, or ``None`` if absent.

    Reads ``<session_dir>/overnight-state.json`` and returns its ``phase``
    field. Returns ``None`` when the state file is missing, unreadable, or
    carries no string ``phase`` — so an escalation predicate that wants
    "not executing/complete" treats an unreadable session as not-running.
    """
    state_path = session_dir / "overnight-state.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    phase = payload.get("phase")
    return phase if isinstance(phase, str) else None


def _advisory_is_stale(advisory: "FireAdvisory", now: datetime) -> bool:
    """Return ``True`` if a fresh advisory should escalate to a failure.

    Escalates (spec §R7) iff ALL of:
      1. the advisory's age exceeds
         :data:`STALE_ADVISORY_THRESHOLD_SECONDS`, AND
      2. there is no live ``runner.pid`` in the session dir
         (:func:`ipc.verify_runner_pid` is ``False`` or the file is
         absent), AND
      3. the session is not executing/complete (its on-disk ``phase`` is
         neither ``"executing"`` nor ``"complete"``).

    An advisory whose ``ts`` is unparseable cannot be aged, so it is
    treated as NOT stale (it keeps rendering as a fresh advisory rather
    than being escalated on a guess).
    """
    parsed = _parse_marker_ts(advisory.ts)
    if parsed is None:
        return False
    # Age the marker against an aware ``now`` (launcher writes UTC).
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_seconds = (now - parsed).total_seconds()
    if age_seconds <= STALE_ADVISORY_THRESHOLD_SECONDS:
        return False

    pid_data = ipc.read_runner_pid(advisory.session_dir)
    if pid_data is not None and ipc.verify_runner_pid(pid_data):
        return False

    phase = _session_phase(advisory.session_dir)
    if phase in ("executing", "complete"):
        return False

    return True


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
        payload = _read_marker_payload(marker_path, "fail-marker")
        if payload is None:
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
        if not _passes_since_cutoff(ts_value, since):
            continue

        results.append(
            FailedFire(
                ts=ts_value,
                error_class=str(payload["error_class"]),
                error_text=str(payload["error_text"]),
                label=str(payload["label"]),
                session_id=str(payload["session_id"]),
                session_dir=marker_path.parent.resolve(),
                kind="failure",
            )
        )

    results.sort(key=lambda f: f.ts)
    return results


def scan_advisory_dirs(
    state_root: Path,
    since: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> tuple[list[FireAdvisory], list[FailedFire]]:
    """Walk ``state_root/sessions/*`` for advisory-marker JSON files.

    Reads each ``scheduled-fire-advisory.json`` marker and classifies it,
    at read time, into one of two buckets (spec §R6/§R7):

      * a **fresh advisory** (:class:`FireAdvisory`) — a live-but-slow
        fire that is NOT a failure; or
      * an **escalated** advisory (:class:`FailedFire` with
        ``kind == "advisory_escalated"``) — a stale advisory whose runner
        appears wedged before its round loop (age > threshold AND no live
        ``runner.pid`` AND session not executing/complete).

    The escalation is inferred purely at read time (marker age +
    ``runner.pid`` liveness + session ``phase``); nothing is written back,
    consistent with the read-only status/morning-report surfaces.

    Args:
        state_root: The cortex state root containing a ``sessions/``
            subdirectory. When the directory does not exist, ``([], [])``
            is returned.
        since: Optional cutoff applied to the marker ``ts`` (same
            semantics as :func:`scan_session_dirs`).
        now: Reference "current time" for the staleness calculation.
            Defaults to ``datetime.now(timezone.utc)``. Exposed for
            deterministic testing.

    Returns:
        A ``(advisories, escalated)`` tuple. ``advisories`` is the list of
        fresh (non-failure) :class:`FireAdvisory` records; ``escalated``
        is the list of :class:`FailedFire` records produced from stale
        advisories. Both are sorted by timestamp string ascending.

    Behavior mirrors :func:`scan_session_dirs`: missing root → ``([], [])``;
    corrupt/non-object markers skipped with a warning; a marker missing
    one or more required fields (``ts``, ``error_class``, ``error_text``,
    ``label``, ``session_id``) is skipped with a warning.
    """
    sessions_root = state_root / "sessions"
    if not sessions_root.is_dir():
        return ([], [])

    if now is None:
        now = datetime.now(timezone.utc)

    advisories: list[FireAdvisory] = []
    escalated: list[FailedFire] = []

    for marker_path in sorted(
        sessions_root.glob("*/scheduled-fire-advisory.json")
    ):
        payload = _read_marker_payload(marker_path, "advisory marker")
        if payload is None:
            continue

        required = ("ts", "error_class", "error_text", "label", "session_id")
        missing = [k for k in required if k not in payload]
        if missing:
            print(
                f"warning: advisory marker {marker_path} missing keys "
                f"{missing}; skipping",
                file=sys.stderr,
            )
            continue

        ts_value = str(payload["ts"])
        if not _passes_since_cutoff(ts_value, since):
            continue

        advisory = FireAdvisory(
            ts=ts_value,
            error_class=str(payload["error_class"]),
            error_text=str(payload["error_text"]),
            label=str(payload["label"]),
            session_id=str(payload["session_id"]),
            session_dir=marker_path.parent.resolve(),
            kind=str(payload.get("kind", "advisory")),
            severity=str(payload.get("severity", "advisory")),
        )

        if _advisory_is_stale(advisory, now):
            escalated.append(
                FailedFire(
                    ts=advisory.ts,
                    error_class=advisory.error_class,
                    error_text=(
                        f"stale advisory escalated to failure: {advisory.error_text} "
                        f"(no live runner.pid and session not executing/complete "
                        f"after > {STALE_ADVISORY_THRESHOLD_SECONDS:.0f}s — runner "
                        f"appears wedged before its round loop)"
                    ),
                    label=advisory.label,
                    session_id=advisory.session_id,
                    session_dir=advisory.session_dir,
                    kind="advisory_escalated",
                )
            )
        else:
            advisories.append(advisory)

    advisories.sort(key=lambda a: a.ts)
    escalated.sort(key=lambda f: f.ts)
    return (advisories, escalated)
