#!/usr/bin/env python3
"""Atomic backlog item creator.

Assigns the next available NNN ID, writes YAML frontmatter + empty body,
appends a status_changed event to the sidecar .events.jsonl, and regenerates
the index.

Usage:
    python3 backlog/create_item.py --title "My feature" --status backlog --type feature

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

# Resolve project root so imports work when called from any directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from claude.common import atomic_write  # noqa: E402

BACKLOG_DIR = Path.cwd() / "backlog"

# Prefer project-local generate_index.py; fall back to the shared skill copy.
_local_py = BACKLOG_DIR / "generate_index.py"
_skill_py = Path.home() / ".claude" / "skills" / "backlog" / "generate_index.py"
GENERATE_INDEX = _local_py if _local_py.exists() else _skill_py


# ---------------------------------------------------------------------------
# ID and slug helpers
# ---------------------------------------------------------------------------

def _get_next_id() -> str:
    """Return the next available numeric ID (no zero-padding for IDs > 999)."""
    ids = [
        int(m.group(1))
        for p in BACKLOG_DIR.glob("[0-9]*-*.md")
        if (m := re.match(r"^(\d+)-", p.name))
    ]
    next_id = (max(ids) + 1) if ids else 1
    return f"{next_id:03d}" if next_id < 1000 else str(next_id)


def _slugify(title: str) -> str:
    """Convert a title to a lowercase kebab-case slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


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
    priority: str = "low",
    rework_of: str | None = None,
    parent: str | None = None,
) -> Path:
    """Create a new backlog item atomically and return its path."""
    today = date.today().isoformat()
    item_uuid = str(uuid4())
    nnn = _get_next_id()
    slug = _slugify(title)
    filename = f"{nnn}-{slug}.md"
    item_path = BACKLOG_DIR / filename

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

    if GENERATE_INDEX.exists():
        subprocess.run([sys.executable, str(GENERATE_INDEX)], check=False)

    return item_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
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

    try:
        item_path = create_item(
            title=args.title,
            status=args.status,
            item_type=args.item_type,
            priority=args.priority,
            rework_of=args.rework_of,
            parent=args.parent,
        )
        print(str(item_path))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
