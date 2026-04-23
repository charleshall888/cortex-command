#!/usr/bin/env python3
"""Generate backlog/index.json and backlog/index.md from active item frontmatter.

Produces:
  - backlog/index.json  — all BacklogItem fields for active items (O(1) index)
  - backlog/index.md    — summary table sorted by priority then ID

Usage:
    python3 backlog/generate_index.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Resolve project root so imports work when called from any directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cortex_command.common import TERMINAL_STATUSES, atomic_write, detect_lifecycle_phase, normalize_status, slugify  # noqa: E402

BACKLOG_DIR = Path.cwd() / "backlog"
LIFECYCLE_DIR = Path.cwd() / "lifecycle"

# Priority sort order (lower rank = higher priority)
_PRIORITY_RANK: dict[str, int] = {"critical": 1, "high": 2, "medium": 3, "low": 4}

# Frontmatter extraction: matches block between first pair of --- delimiters
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract key-value pairs from YAML frontmatter (between --- delimiters)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    pairs: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        colon_idx = line.find(":")
        if colon_idx < 0:
            continue
        pairs[line[:colon_idx].strip()] = line[colon_idx + 1:].strip()
    return pairs


def _parse_inline_str_list(raw: str) -> list[str]:
    """Parse an inline YAML list like ``[tag1, tag2]`` into a list of strings."""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    return [raw] if raw else []


def _opt(fm: dict[str, str], key: str) -> str | None:
    """Return frontmatter value for key, or None if absent/empty/null."""
    v = fm.get(key, "").strip().strip("\"'")
    return v if v and v.lower() != "null" else None


def collect_items() -> tuple[list[dict], set[int], set[int]]:
    """Scan BACKLOG_DIR and return (active_items, active_ids, archive_ids).

    active_items is sorted by priority rank then ID ascending.
    """
    if not BACKLOG_DIR.is_dir():
        return [], set(), set()

    # Build archive ID set for stale-reference detection in warnings.
    archive_ids: set[int] = set()
    archive_dir = BACKLOG_DIR / "archive"
    if archive_dir.is_dir():
        for path in archive_dir.glob("[0-9]*-*.md"):
            m = re.match(r"^(\d+)-", path.name)
            if m:
                archive_ids.add(int(m.group(1)))

    items: list[dict] = []
    active_ids: set[int] = set()

    for path in sorted(BACKLOG_DIR.glob("[0-9]*-*.md")):
        if "archive" in path.parts:
            continue
        if path.name == "index.md":
            continue
        m = re.match(r"^(\d+)-", path.name)
        if not m:
            continue
        item_id = int(m.group(1))

        fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
        if not fm:
            continue

        status = normalize_status(fm.get("status", "open"))
        if status in TERMINAL_STATUSES:
            continue

        active_ids.add(item_id)

        title = fm.get("title", "").strip().strip("\"'")

        lc_slug = fm.get("lifecycle_slug", "").strip().strip("\"'") or slugify(title)
        lc_dir = LIFECYCLE_DIR / lc_slug if lc_slug else None
        if lc_dir and lc_dir.is_dir():
            lifecycle_phase: str | None = detect_lifecycle_phase(lc_dir)
        else:
            lifecycle_phase = _opt(fm, "lifecycle_phase")

        items.append({
            "id": item_id,
            "title": title,
            "status": status,
            "priority": fm.get("priority", "medium").strip(),
            "type": fm.get("type", "feature").strip(),
            "tags": _parse_inline_str_list(fm.get("tags", "[]")),
            "areas": _parse_inline_str_list(fm.get("areas", "[]")),
            "created": fm.get("created", "").strip(),
            "updated": fm.get("updated", "").strip(),
            "blocks": _parse_inline_str_list(fm.get("blocks", "[]")),
            "blocked_by": _parse_inline_str_list(fm.get("blocked-by", "[]")),
            "parent": _opt(fm, "parent"),
            "research": _opt(fm, "research"),
            "spec": _opt(fm, "spec"),
            "discovery_source": _opt(fm, "discovery_source"),
            "plan": _opt(fm, "plan"),
            "uuid": _opt(fm, "uuid"),
            "lifecycle_slug": _opt(fm, "lifecycle_slug"),
            "session_id": _opt(fm, "session_id"),
            "lifecycle_phase": lifecycle_phase,
            "schema_version": _opt(fm, "schema_version"),
            "repo": _opt(fm, "repo"),
        })

    items.sort(key=lambda x: (_PRIORITY_RANK.get(x["priority"], 9), x["id"]))
    return items, active_ids, archive_ids


def generate_json(items: list[dict]) -> str:
    """Serialize active items to JSON (BacklogItem-compatible field names)."""
    return json.dumps(items, indent=2, ensure_ascii=False) + "\n"


def generate_md(items: list[dict], active_ids: set[int], archive_ids: set[int]) -> str:
    """Produce index.md summary table with Ready, In-Progress, and Warnings sections."""
    lines: list[str] = ["# Backlog Index", ""]
    lines.append("| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |")
    lines.append("|-----|-------|--------|----------|------|------------|--------|------|")

    for item in items:
        blocked_display = ", ".join(item["blocked_by"]) if item["blocked_by"] else "\u2014"
        parent_display = item["parent"] if item["parent"] else "\u2014"
        spec_display = "\u2713" if item["spec"] else "\u2014"
        lines.append(
            f"| {item['id']} | {item['title']} | {item['status']} | "
            f"{item['priority']} | {item['type']} | {blocked_display} | "
            f"{parent_display} | {spec_display} |"
        )

    # --- Refined section ---
    lines += ["", "## Refined", ""]
    for item in items:
        if item["status"] != "refined":
            continue
        if not item["blocked_by"]:
            lines.append(f"- **{item['id']}** {item['title']}")
        else:
            all_resolved = all(
                int(b) not in active_ids
                for b in item["blocked_by"]
                if b.isdigit()
            )
            if all_resolved:
                lines.append(f"- **{item['id']}** {item['title']}")

    # --- Backlog section ---
    lines += ["", "## Backlog", ""]
    for item in items:
        if item["status"] not in ("backlog", "open", "blocked"):
            continue
        if not item["blocked_by"]:
            lines.append(f"- **{item['id']}** {item['title']}")
        else:
            all_resolved = all(
                int(b) not in active_ids
                for b in item["blocked_by"]
                if b.isdigit()
            )
            if all_resolved:
                lines.append(f"- **{item['id']}** {item['title']}")

    # --- In-Progress section ---
    lines += ["", "## In-Progress", ""]
    for item in items:
        if item["status"] in ("in_progress", "implementing", "review", "in-progress"):
            lines.append(f"- **{item['id']}** {item['title']} ({item['status']})")

    # --- Warnings section ---
    warnings: list[str] = []
    for item in items:
        if not item["blocked_by"]:
            continue
        item_id_num = item["id"]
        for b in item["blocked_by"]:
            if not b.isdigit():
                continue
            b_num = int(b)
            if b_num == item_id_num:
                warnings.append(
                    f"- **{item['id']}**: self-referential blocked-by (references own ID)"
                )
            elif b_num in archive_ids and b_num not in active_ids:
                warnings.append(
                    f"- **{item['id']}**: blocked-by {b} references archived item"
                )

    if warnings:
        lines += ["", "## Warnings", ""]
        lines.extend(warnings)

    return "\n".join(lines) + "\n"


def main() -> None:
    items, active_ids, archive_ids = collect_items()
    atomic_write(BACKLOG_DIR / "index.json", generate_json(items))
    atomic_write(BACKLOG_DIR / "index.md", generate_md(items, active_ids, archive_ids))
    print(f"Generated index.json ({len(items)} items) and index.md")


if __name__ == "__main__":
    main()
