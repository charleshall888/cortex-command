#!/usr/bin/env python3
"""Atomic backlog item creator.

Assigns the next available NNN ID, writes YAML frontmatter + empty body,
appends a status_changed event to the sidecar .events.jsonl, and regenerates
the index.

Usage:
    cortex-create-backlog-item --title "My feature" --status backlog --type feature

Exit 0 = item created successfully.
Exit 1 = error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cortex_command.backlog import _telemetry
from cortex_command.common import _resolve_user_project_root, atomic_write, slugify


# ---------------------------------------------------------------------------
# ID and slug helpers
# ---------------------------------------------------------------------------

def _get_next_id(backlog_dir: Path) -> str:
    """Return the next available numeric ID (no zero-padding for IDs > 999)."""
    ids = [
        int(m.group(1))
        for p in backlog_dir.glob("[0-9]*-*.md")
        if (m := re.match(r"^(\d+)-", p.name))
    ]
    next_id = (max(ids) + 1) if ids else 1
    return f"{next_id:03d}" if next_id < 1000 else str(next_id)


_slugify = slugify  # Use canonical slugify from cortex_command.common


# ---------------------------------------------------------------------------
# Event logging (verbatim from update_item.py)
# ---------------------------------------------------------------------------

def _append_event(
    item_path: Path,
    event_type: str,
    item_uuid: str | None,
    session_id: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append an event to the sidecar ``{stem}.events.jsonl`` file."""
    events_path = item_path.parent / f"{item_path.stem}.events.jsonl"
    event = {
        "v": 1,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event_type,
        "item_uuid": item_uuid,
        "session_id": session_id,
    }
    if details:
        event["details"] = details

    line = json.dumps(event, separators=(",", ":")) + "\n"

    with open(events_path, "a", encoding="utf-8") as f:
        f.write(line)


# ---------------------------------------------------------------------------
# Main creation logic
# ---------------------------------------------------------------------------

def create_item(
    title: str,
    status: str,
    item_type: str,
    backlog_dir: Path,
    priority: str = "low",
    rework_of: str | None = None,
    parent: str | None = None,
) -> Path:
    """Create a new backlog item atomically and return its path."""
    if backlog_dir is None:
        raise TypeError("backlog_dir is required")

    today = date.today().isoformat()
    item_uuid = str(uuid4())
    nnn = _get_next_id(backlog_dir)
    slug = _slugify(title)
    filename = f"{nnn}-{slug}.md"
    item_path = backlog_dir / filename

    session_id = os.environ.get("LIFECYCLE_SESSION_ID", "manual")

    # Build frontmatter in spec-specified field order
    lines = [
        "---\n",
        f'schema_version: "1"\n',
        f"uuid: {item_uuid}\n",
        f'title: "{title}"\n',
        f"status: {status}\n",
        f"priority: {priority}\n",
        f"type: {item_type}\n",
        f"created: {today}\n",
        f"updated: {today}\n",
    ]
    if rework_of is not None:
        lines.append(f"rework_of: {rework_of}\n")
    if parent is not None:
        lines.append(f'parent: "{parent}"\n')
    lines.append("---\n")

    atomic_write(item_path, "".join(lines))

    _append_event(
        item_path,
        "status_changed",
        item_uuid,
        session_id,
        details={"from": None, "to": status},
    )

    subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.generate_index"],
        check=False,
    )

    return item_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    _telemetry.log_invocation("cortex-create-backlog-item")
    parser = argparse.ArgumentParser(
        description="Create a new backlog item with the next available ID."
    )
    parser.add_argument("--title", required=True, help="Item title")
    parser.add_argument("--status", required=True, help="Initial status (e.g. backlog)")
    parser.add_argument("--type", required=True, dest="item_type",
                        help="Item type (e.g. feature, bug, chore)")
    parser.add_argument("--priority", default="low", help="Priority (default: low)")
    parser.add_argument("--rework-of", dest="rework_of", default=None,
                        help="ID of the original item this reworks")
    parser.add_argument("--parent", default=None, help="Parent epic ID")
    args = parser.parse_args()

    # CLI-layer resolver routing — internal callers must pass backlog_dir
    # explicitly (see spec R3 / create_item signature). Routes through
    # _resolve_user_project_root() so the CLI works from any subdirectory.
    BACKLOG_DIR = _resolve_user_project_root() / "cortex" / "backlog"

    try:
        item_path = create_item(
            title=args.title,
            status=args.status,
            item_type=args.item_type,
            backlog_dir=BACKLOG_DIR,
            priority=args.priority,
            rework_of=args.rework_of,
            parent=args.parent,
        )
        print(str(item_path))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
