"""CLI helper for appending events to a feature's events.log.

Exposes a single ``log`` subcommand:

    cortex-lifecycle-event log --event <name> --feature <slug> [--worktree-path <path>]

Path resolution uses ``_resolve_user_project_root_from_cwd()`` (ignores
``CORTEX_REPO_ROOT``), so the log target follows the physical CWD — the
intended behaviour when the orchestrator session has cd'd into a worktree.

Write discipline: atomic append via sibling-lockfile ``fcntl.flock`` +
tempfile + ``os.replace`` (per ``cortex/requirements/pipeline.md:126``).
The events.log file is append-only JSONL; each call writes exactly one row.

JSONL row schema::

    {
        "schema_version": 1,
        "ts": "<ISO 8601 UTC>",
        "event": "<event-name>",
        "feature": "<feature-slug>",
        "worktree_path": "<path or null>"
    }
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root_from_cwd,
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


def _events_log_path(feature_slug: str) -> Path:
    """Resolve the events.log path using the CWD-based root resolver.

    Raises ``CortexProjectRootError`` when the root cannot be resolved.
    """
    root = _resolve_user_project_root_from_cwd()
    return root / "cortex" / "lifecycle" / feature_slug / "events.log"


def _append_event_atomic(log_path: Path, row: str) -> None:
    """Append *row* to *log_path* atomically under an exclusive flock.

    Serialization protocol:
        1. Create the parent directory if absent.
        2. Open (or create) a sibling lock file ``{log_path}.lock`` and
           acquire an exclusive advisory ``fcntl.flock`` on it.
        3. Read the current content of *log_path* (empty string if absent).
        4. Write ``existing_content + row`` to a sibling temp file.
        5. ``os.replace`` the temp file over *log_path* (atomic inode swap).
        6. Release the flock (close the lock fd).

    Steps 3-5 run while the flock is held so no concurrent writer can
    interleave a partial append between the read and the replace.

    This mirrors the ``fcntl.flock`` + tempfile + ``os.replace`` pattern used
    in ``cortex_command/init/settings_merge.py`` and
    ``cortex_command/hooks/_session_state.py``.
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
            # Read existing content (tolerate absent file)
            try:
                existing = log_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                existing = ""

            new_content = existing + row

            # Write atomically via temp + os.replace
            fd, tmp_path = tempfile.mkstemp(
                dir=log_path.parent,
                prefix=f".{log_path.name}-",
                suffix=".tmp",
            )
            closed = False
            try:
                os.write(fd, new_content.encode("utf-8"))
                os.close(fd)
                closed = True
                os.replace(tmp_path, log_path)
            except BaseException:
                if not closed:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
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
    worktree_path: Optional[str] = None,
) -> None:
    """Append one event row to ``cortex/lifecycle/{feature}/events.log``.

    Path is resolved from the physical CWD (ignores ``CORTEX_REPO_ROOT``).

    Args:
        event: Event name string (e.g. ``"interactive_worktree_entered"``).
        feature: Feature slug (e.g. ``"my-feature"``).
        worktree_path: Optional worktree path to record; ``None`` serialises
            as JSON ``null``.

    Raises:
        CortexProjectRootError: When the project root cannot be resolved
            from the current working directory.
    """
    log_path = _events_log_path(feature)
    row_dict: dict = {
        "schema_version": _SCHEMA_VERSION,
        "ts": _now_iso(),
        "event": event,
        "feature": feature,
        "worktree_path": worktree_path,
    }
    row = json.dumps(row_dict, separators=(",", ":")) + "\n"
    _append_event_atomic(log_path, row)


# ---------------------------------------------------------------------------
# Console-script entry point
# ---------------------------------------------------------------------------


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
        "--worktree-path",
        default=None,
        metavar="PATH",
        help="Optional worktree path to record in the event row",
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
                worktree_path=args.worktree_path,
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
