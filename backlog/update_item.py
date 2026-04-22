#!/usr/bin/env python3
"""Atomic in-place backlog item updater.

Replaces the file-move archival pattern from close-item.py with in-place
frontmatter updates, sidecar event logging, and dependency cascade — all
without moving any file.

Usage:
    python3 backlog/update_item.py <slug-or-uuid> key=value [key=value ...]

Examples:
    python3 backlog/update_item.py 030-cf-tunnel-fallback-polish status=complete
    python3 backlog/update_item.py 030-cf-tunnel-fallback-polish status=complete session_id=null
    python3 backlog/update_item.py 550e8400-... lifecycle_phase=implement

Exit 0 = item updated successfully.
Exit 1 = item not found or no fields provided.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Resolve project root so imports work when called from any directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from claude.common import TERMINAL_STATUSES, atomic_write  # noqa: E402


def _resolve_generate_index(backlog_dir: Path) -> Path:
    """Return the generate_index.py script path for the given backlog_dir.

    Prefers the project-local script; falls back to the globally-deployed
    ``~/.local/bin/generate-backlog-index``.
    """
    local_py = backlog_dir / "generate_index.py"
    skill_py = Path.home() / ".local" / "bin" / "generate-backlog-index"
    return local_py if local_py.exists() else skill_py


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

def _get_frontmatter_value(text: str, key: str) -> str | None:
    """Return the value for ``key:`` within the YAML frontmatter block."""
    in_fm = False
    for line in text.splitlines():
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
                continue
            else:
                break
        if in_fm:
            m = re.match(rf"^{re.escape(key)}:\s*[\"']?(.+?)[\"']?\s*$", line)
            if m:
                return m.group(1)
    return None


def _set_frontmatter_value(text: str, key: str, value: str) -> str:
    """Replace ``key: <anything>`` inside the frontmatter block.

    If the key does not exist in frontmatter, inserts it before the
    closing ``---``.
    """
    lines = text.splitlines(keepends=True)
    in_fm = False
    fm_closes = -1
    first_dash = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "---":
            if not in_fm:
                in_fm = True
                first_dash = i
                continue
            else:
                fm_closes = i
                break

    if first_dash == -1 or fm_closes == -1:
        return text  # no frontmatter

    for i in range(first_dash + 1, fm_closes):
        if re.match(rf"^{re.escape(key)}:\s", lines[i]):
            lines[i] = f"{key}: {value}\n"
            return "".join(lines)

    # Key not found — insert before closing ---
    lines.insert(fm_closes, f"{key}: {value}\n")
    return "".join(lines)


def _get_item_id(path: Path) -> str | None:
    """Parse the numeric ID from a backlog filename (e.g. '045' from '045-slug.md')."""
    m = re.match(r"^(\d+)-", path.name)
    return m.group(1) if m else None


def _parse_inline_str_list(val: str) -> list[str]:
    """Parse an inline YAML list like ``[abc, def-123, 045]`` into a list of strings.

    Handles both UUID strings and integer IDs. Returns an empty list for
    empty brackets or missing values.
    """
    val = val.strip()
    if val.startswith("["):
        val = val[1:]
    if val.endswith("]"):
        val = val[:-1]
    entries = [e.strip().strip("'\"") for e in val.split(",") if e.strip()]
    return entries


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def _find_item(slug_or_uuid: str, backlog_dir: Path) -> Path | None:
    """Find a backlog item by slug substring or UUID prefix.

    Search order:
      1. Exact filename match (``NNN-slug.md``)
      2. Exact numeric prefix match (pure-digit queries) or substring match (slug queries)
      3. UUID field match (prefix or full)
    """
    if backlog_dir is None:
        raise TypeError("backlog_dir is required")
    if not backlog_dir.is_dir():
        return None

    # Try exact filename match first
    for p in sorted(backlog_dir.glob("[0-9]*-*.md")):
        # Strip the .md extension and compare
        stem = p.stem  # e.g. "030-cf-tunnel-fallback-polish"
        if stem == slug_or_uuid:
            return p

    # For pure-numeric queries, match the exact ID prefix to avoid "100" matching
    # "1000-foo.md" when "100-foo.md" has been archived.
    if slug_or_uuid.isdigit():
        for p in sorted(backlog_dir.glob("[0-9]*-*.md")):
            if p.stem.startswith(f"{slug_or_uuid}-"):
                return p
    else:
        # Try filename substring match for slug queries
        for p in sorted(backlog_dir.glob("[0-9]*-*.md")):
            if slug_or_uuid in p.stem:
                return p

    # Try UUID match (reading frontmatter)
    for p in sorted(backlog_dir.glob("[0-9]*-*.md")):
        text = p.read_text()
        uuid_val = _get_frontmatter_value(text, "uuid")
        if uuid_val and uuid_val.startswith(slug_or_uuid):
            return p

    return None


# ---------------------------------------------------------------------------
# Event logging
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

    # Append (not atomic replace — append-only log)
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(line)


# ---------------------------------------------------------------------------
# Cascade helpers
# ---------------------------------------------------------------------------

def _remove_uuid_from_blocked_by(
    closed_uuid: str | None,
    closed_id: str | None,
    today: str,
    backlog_dir: Path,
) -> None:
    """Remove the closed item's UUID (or numeric ID) from ``blocked-by``
    arrays in all active backlog items.

    Handles both UUID strings and legacy integer IDs for backward
    compatibility during migration.
    """
    if backlog_dir is None:
        raise TypeError("backlog_dir is required")
    if not backlog_dir.is_dir():
        return
    if not closed_uuid and not closed_id:
        return

    pattern = re.compile(
        r"^(blocked-by:\s*\[)(.*?)(\])\s*$",
        re.MULTILINE,
    )

    for p in sorted(backlog_dir.glob("[0-9]*-*.md")):
        text = p.read_text()
        m = pattern.search(text)
        if not m:
            continue

        entries_raw = m.group(2)
        entries = [e.strip().strip("'\"") for e in entries_raw.split(",") if e.strip()]

        # Build the set of identifiers to remove
        remove_set: set[str] = set()
        if closed_uuid:
            remove_set.add(closed_uuid)
        if closed_id:
            # Match both zero-padded legacy form ("045") and plain integer form ("45").
            # For IDs >= 1000, zfill(3) is a no-op and both entries are the same string.
            padded = closed_id.zfill(3)
            remove_set.add(padded)
            remove_set.add(str(int(closed_id)))

        filtered = [e for e in entries if e not in remove_set]

        if len(filtered) == len(entries):
            continue  # nothing changed

        new_val = ", ".join(filtered)
        new_line = f"blocked-by: [{new_val}]"
        updated = pattern.sub(new_line, text)
        updated = _set_frontmatter_value(updated, "updated", today)
        atomic_write(p, updated)


def _check_and_close_parent(
    item_path: Path, today: str, backlog_dir: Path
) -> Path | None:
    """If the item has a ``parent`` field and all siblings are terminal,
    auto-close the parent.

    Returns the parent path if it was closed, ``None`` otherwise.
    """
    if backlog_dir is None:
        raise TypeError("backlog_dir is required")

    archive_dir = backlog_dir / "archive"

    text = item_path.read_text()
    parent_val = _get_frontmatter_value(text, "parent")
    if not parent_val:
        return None

    # parent_val might be an integer ID or a UUID
    parent_path: Path | None = None

    # Try numeric ID first
    try:
        parent_id = int(parent_val)
        parent_id_padded = str(parent_id).zfill(3)
        candidates = sorted(backlog_dir.glob(f"{parent_id_padded}-*.md"))
        if candidates:
            parent_path = candidates[0]
    except ValueError:
        # Might be a UUID — search by UUID field
        for p in sorted(backlog_dir.glob("[0-9]*-*.md")):
            t = p.read_text()
            uuid_val = _get_frontmatter_value(t, "uuid")
            if uuid_val and uuid_val == parent_val:
                parent_path = p
                break

    if parent_path is None:
        return None

    parent_text = parent_path.read_text()
    parent_status = _get_frontmatter_value(parent_text, "status") or "open"
    if parent_status in TERMINAL_STATUSES:
        return None  # already closed

    # Get the parent identifier for sibling matching
    parent_id_for_match = _get_item_id(parent_path)
    parent_uuid = _get_frontmatter_value(parent_text, "uuid")

    # Collect sibling statuses from both active and archive dirs
    sibling_statuses: list[str] = []
    for search_dir in [backlog_dir, archive_dir]:
        if not search_dir.is_dir():
            continue
        for p in sorted(search_dir.glob("[0-9]*-*.md")):
            t = p.read_text()
            p_parent = _get_frontmatter_value(t, "parent")
            if not p_parent:
                continue
            # Match by either numeric ID or UUID
            matches = False
            if parent_id_for_match:
                try:
                    if int(p_parent) == int(parent_id_for_match):
                        matches = True
                except ValueError:
                    pass
            if not matches and parent_uuid and p_parent == parent_uuid:
                matches = True
            if matches:
                status = _get_frontmatter_value(t, "status") or "open"
                sibling_statuses.append(status)

    if not sibling_statuses:
        return None
    if not all(s in TERMINAL_STATUSES for s in sibling_statuses):
        return None

    # All siblings are terminal — close the parent
    parent_text = _set_frontmatter_value(parent_text, "status", "complete")
    parent_text = _set_frontmatter_value(parent_text, "updated", today)
    atomic_write(parent_path, parent_text)
    return parent_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_item(
    item_path: Path,
    fields: dict[str, Any],
    backlog_dir: Path,
    session_id: str | None = None,
) -> None:
    """Update a backlog item's frontmatter fields atomically in place.

    Always sets ``updated`` to today. Appends ``status_changed`` or
    ``phase_changed`` events to the sidecar log. For terminal status
    transitions, cascades blocked-by removal and parent auto-close.

    Args:
        item_path: Path to the backlog item ``.md`` file.
        fields: Dict of frontmatter keys to new values.
            Use ``None`` for null/empty values.
        backlog_dir: Path to the backlog directory. Required — callers must
            route explicitly through the correct worktree's backlog.
        session_id: Session ID for event attribution. Defaults to
            ``LIFECYCLE_SESSION_ID`` env var or ``"manual"``.
    """
    if backlog_dir is None:
        raise TypeError("backlog_dir is required")

    today = date.today().isoformat()
    text = item_path.read_text()

    if session_id is None:
        session_id = os.environ.get("LIFECYCLE_SESSION_ID", "manual")

    # Read current values for change detection
    old_status = _get_frontmatter_value(text, "status")
    old_phase = _get_frontmatter_value(text, "lifecycle_phase")
    item_uuid = _get_frontmatter_value(text, "uuid")
    item_id = _get_item_id(item_path)

    # Apply field updates
    for key, value in fields.items():
        if value is None:
            text = _set_frontmatter_value(text, key, "null")
        else:
            text = _set_frontmatter_value(text, key, str(value))

    # Always update the `updated` field
    text = _set_frontmatter_value(text, "updated", today)

    # Write atomically
    atomic_write(item_path, text)

    # Determine new values for event logging
    new_status = fields.get("status")
    new_phase = fields.get("lifecycle_phase")

    # Append events
    if new_status is not None and str(new_status) != old_status:
        _append_event(
            item_path,
            "status_changed",
            item_uuid,
            session_id,
            details={"from": old_status, "to": str(new_status)},
        )

    if new_phase is not None and str(new_phase) != old_phase:
        _append_event(
            item_path,
            "phase_changed",
            item_uuid,
            session_id,
            details={"from": old_phase, "to": str(new_phase)},
        )

    # Cascade for terminal status changes
    if new_status is not None and str(new_status) in TERMINAL_STATUSES:
        _remove_uuid_from_blocked_by(item_uuid, item_id, today, backlog_dir)
        parent_closed = _check_and_close_parent(item_path, today, backlog_dir)
        if parent_closed:
            print(f"Parent epic also closed: {parent_closed}")

    # Regenerate index (non-fatal)
    generate_index = _resolve_generate_index(backlog_dir)
    if generate_index.exists():
        result = subprocess.run(
            [sys.executable, str(generate_index)],
            capture_output=True,
        )
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr.decode(errors="replace"), file=sys.stderr, end="")
            print(
                f"WARNING: Index regeneration failed (exit {result.returncode})",
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: python3 backlog/update_item.py <slug-or-uuid> key=value [key=value ...]",
            file=sys.stderr,
        )
        sys.exit(1)

    # CLI-layer cwd resolution — internal callers must pass backlog_dir
    # explicitly (see spec R3 / update_item signature).
    BACKLOG_DIR = Path.cwd() / "backlog"

    slug_or_uuid = sys.argv[1]
    field_args = sys.argv[2:]

    # Parse key=value pairs
    fields: dict[str, Any] = {}
    for arg in field_args:
        if "=" not in arg:
            print(f"Invalid argument (expected key=value): {arg}", file=sys.stderr)
            sys.exit(1)
        key, value = arg.split("=", 1)
        # Handle null/None values
        if value.lower() in ("null", "none", ""):
            fields[key] = None
        else:
            fields[key] = value

    # Find the item
    item_path = _find_item(slug_or_uuid, BACKLOG_DIR)
    if item_path is None:
        print(f"Item not found: {slug_or_uuid}", file=sys.stderr)
        sys.exit(1)

    update_item(item_path, fields, BACKLOG_DIR)
    print(f"Updated: {item_path}")


if __name__ == "__main__":
    main()
