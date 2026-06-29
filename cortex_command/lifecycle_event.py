"""CLI helper for appending events to a feature's events.log.

Exposes a single ``log`` subcommand:

    cortex-lifecycle-event log --event <name> --feature <slug> \
        [--set k=v ...] [--set-json k=v ...]

Path resolution uses ``_resolve_user_project_root_from_cwd()`` (ignores
``CORTEX_REPO_ROOT``), so the log target follows the physical CWD — the
intended behaviour when the orchestrator session has cd'd into a worktree.

Write discipline: append-only under an exclusive sibling-lockfile
``fcntl.flock`` with ``O_APPEND`` — the events.log is append-only JSONL and
each call writes exactly one row, so no read-modify-write is performed (see
``cortex/requirements/pipeline.md`` L143/146/151 for the atomicity,
audit-trail, and locking constraints this satisfies).

JSONL row schema::

    {
        "ts": "<ISO 8601 UTC, second-precision Z>",
        "event": "<event-name>",
        "feature": "<feature-slug>",
        <ordered extra fields from --set / --set-json>
    }

The three base keys are emitted first, then any extra fields in argv order.
``--set k=v`` records the literal string ``v``; ``--set-json k=v`` parses ``v``
with ``json.loads`` (int/bool/null/array/object). Duplicate keys are
last-wins. Serialization uses ``json.dumps`` spaced defaults.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root_from_cwd,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC time as ``%Y-%m-%dT%H:%M:%SZ``."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _events_log_path(feature_slug: str) -> Path:
    """Resolve the events.log path using the CWD-based root resolver.

    Raises ``CortexProjectRootError`` when the root cannot be resolved.
    """
    root = _resolve_user_project_root_from_cwd()
    return root / "cortex" / "lifecycle" / feature_slug / "events.log"


def _append_event_atomic(log_path: Path, row: str) -> None:
    """Append *row* to *log_path* under an exclusive sibling-lockfile flock.

    Protocol:
        1. Create the parent directory if absent.
        2. Open (or create) a sibling lock file ``{log_path}.lock`` and
           acquire an exclusive advisory ``fcntl.flock`` on it.
        3. Open *log_path* with ``O_WRONLY | O_CREAT | O_APPEND`` and write the
           single *row*; ``O_APPEND`` positions every write at end-of-file.
        4. Release the flock (close the lock fd).

    The events.log is append-only, so there is no read-modify-write step. The
    flock serialises this verb's own concurrent invocations; ``O_APPEND`` keeps
    a write atomic against an unlocked bare appender for the common bounded row.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = log_path.parent / f"{log_path.name}.lock"

    lock_fd = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC,
        0o600,
    )
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            target_fd = os.open(
                log_path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_CLOEXEC,
                0o644,
            )
            try:
                os.write(target_fd, row.encode("utf-8"))
            finally:
                os.close(target_fd)
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            os.close(lock_fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def log_event(
    event: str,
    feature: str,
    fields: Optional[list[tuple[str, str, object]]] = None,
) -> None:
    """Append one event row to ``cortex/lifecycle/{feature}/events.log``.

    Path is resolved from the physical CWD (ignores ``CORTEX_REPO_ROOT``).

    Args:
        event: Event name string (e.g. ``"interactive_worktree_entered"``).
        feature: Feature slug (e.g. ``"my-feature"``).
        fields: Optional ordered ``(kind, key, value)`` triples appended after
            the ``ts``/``event``/``feature`` base keys. ``value`` is already
            typed by the caller; ``kind`` is retained only for symmetry with
            the flag surface. Keys are emitted in order; duplicate keys are
            last-wins.

    Raises:
        CortexProjectRootError: When the project root cannot be resolved
            from the current working directory.
    """
    log_path = _events_log_path(feature)
    row_dict: dict = {
        "ts": _now_iso(),
        "event": event,
        "feature": feature,
    }
    for _kind, key, value in fields or []:
        row_dict[key] = value
    row = json.dumps(row_dict) + "\n"
    _append_event_atomic(log_path, row)


# ---------------------------------------------------------------------------
# Console-script entry point
# ---------------------------------------------------------------------------


class _SetFieldAction(argparse.Action):
    """Collect repeated ``--set`` / ``--set-json`` tokens into one ordered list.

    Both flags write ``(kind, key, value)`` triples to a single shared ``dest``
    so interleaved argv order is preserved. ``kind`` is ``"str"`` for ``--set``
    (literal string value) or ``"json"`` for ``--set-json`` (``json.loads``-
    parsed). Each token splits on the **first** ``=`` only; a ``=``-less token
    or a malformed ``--set-json`` value is an argparse usage error (exit != 0),
    raised at parse time before any row is written.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        kind = "json" if option_string == "--set-json" else "str"
        if "=" not in values:
            parser.error(
                f"argument {option_string}: expected KEY=VALUE, got {values!r}"
            )
        key, value_str = values.split("=", 1)
        if not key:
            parser.error(
                f"argument {option_string}: empty key in {values!r}"
            )
        if kind == "json":
            try:
                value: object = json.loads(value_str)
            except json.JSONDecodeError as exc:
                parser.error(
                    f"argument {option_string}: invalid JSON value for "
                    f"key {key!r}: {exc}"
                )
        else:
            value = value_str
        items = getattr(namespace, self.dest, None)
        if items is None:
            items = []
            setattr(namespace, self.dest, items)
        items.append((kind, key, value))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-event",
        description="Append events to a feature's events.log.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    log_p = sub.add_parser("log", help="Append one event row to events.log")
    log_p.add_argument(
        "--event",
        required=True,
        metavar="NAME",
        help="Event name (e.g. interactive_worktree_entered)",
    )
    log_p.add_argument(
        "--feature",
        required=True,
        metavar="SLUG",
        help="Feature slug (e.g. my-feature)",
    )
    log_p.add_argument(
        "--set",
        dest="set_fields",
        action=_SetFieldAction,
        default=None,
        metavar="KEY=VALUE",
        help="Add a literal string field (repeatable; argv order preserved)",
    )
    log_p.add_argument(
        "--set-json",
        dest="set_fields",
        action=_SetFieldAction,
        default=None,
        metavar="KEY=VALUE",
        help="Add a JSON-typed field parsed via json.loads (repeatable)",
    )
    return parser


def _run(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "log":
        try:
            log_event(
                event=args.event,
                feature=args.feature,
                fields=args.set_fields,
            )
        except CortexProjectRootError as exc:
            sys.stderr.write(f"cortex-lifecycle-event: {exc}\n")
            return 1
        return 0

    # Unreachable (argparse requires subcommand), but satisfies type checker.
    return 1


def main(argv: Optional[list[str]] = None) -> None:
    sys.exit(_run(argv))


if __name__ == "__main__":
    main()
