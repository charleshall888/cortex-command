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
from types import SimpleNamespace

# Resolve project root so imports work when called from any directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cortex_command.backlog import is_item_ready  # noqa: E402
from cortex_command.common import TERMINAL_STATUSES, atomic_write, detect_lifecycle_phase, normalize_status, slugify  # noqa: E402

BACKLOG_DIR = Path.cwd() / "backlog"
LIFECYCLE_DIR = Path.cwd() / "lifecycle"

# Priority sort order (lower rank = higher priority)
_PRIORITY_RANK: dict[str, int] = {"critical": 1, "high": 2, "medium": 3, "low": 4}

# Frontmatter extraction: matches block between first pair of --- delimiters
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)

# UUID v4-style pattern, mirrored from cortex_command.backlog.readiness so
# external-blocker classification in generate_md matches the helper's
# disambiguation between "external ref" and "blocker not found: <uuid>".
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


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


def collect_items() -> tuple[list[dict], set[int], set[int], list[dict]]:
    """Scan BACKLOG_DIR and return (active_items, active_ids, archive_ids, all_items).

    active_items is sorted by priority rank then ID ascending. all_items is
    a parallel list of minimal records (id, status, uuid) covering ALL
    backlog markdown files — active, terminal-status, and archived — used
    by the shared readiness helper to resolve blocker references.
    """
    if not BACKLOG_DIR.is_dir():
        return [], set(), set(), []

    # Build archive ID set + minimal records for stale-reference detection
    # and helper blocker-resolution. Archived items participate in the
    # full-corpus all_items map so that a blocker pointing to an archived
    # (terminal) ID resolves as resolved rather than "not found".
    archive_ids: set[int] = set()
    all_items: list[dict] = []
    archive_dir = BACKLOG_DIR / "archive"
    if archive_dir.is_dir():
        for path in sorted(archive_dir.glob("[0-9]*-*.md")):
            m = re.match(r"^(\d+)-", path.name)
            if not m:
                continue
            arc_id = int(m.group(1))
            archive_ids.add(arc_id)
            fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
            arc_status = normalize_status(fm.get("status", "complete")) if fm else "complete"
            arc_uuid = _opt(fm, "uuid") if fm else None
            all_items.append({"id": arc_id, "status": arc_status, "uuid": arc_uuid})

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
        # Track every non-archived item (active + terminal) in the full corpus
        # so the helper resolves blocker references against terminal items
        # the same way the legacy `int(b) not in active_ids` short-circuit
        # silently treated them as resolved.
        all_items.append({
            "id": item_id,
            "status": status,
            "uuid": _opt(fm, "uuid"),
        })

        if status in TERMINAL_STATUSES:
            continue

        active_ids.add(item_id)

        title = fm.get("title", "").strip().strip("\"'")

        lc_slug = fm.get("lifecycle_slug", "").strip().strip("\"'") or slugify(title)
        lc_dir = LIFECYCLE_DIR / lc_slug if lc_slug else None
        # `lifecycle_phase` value set: {"research", "specify", "plan",
        # "implement", "implement-rework", "review", "complete", "escalated"}.
        # `"implement-rework"` was added when phase detection was unified
        # around `claude/common.py`. See skills/backlog/references/schema.md
        # for the full backlog schema.
        if lc_dir and lc_dir.is_dir():
            lifecycle_phase: str | None = detect_lifecycle_phase(lc_dir)["phase"]
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
    return items, active_ids, archive_ids, all_items


def generate_json(items: list[dict]) -> str:
    """Serialize active items to JSON (BacklogItem-compatible field names)."""
    return json.dumps(items, indent=2, ensure_ascii=False) + "\n"


def generate_md(
    items: list[dict],
    active_ids: set[int],
    archive_ids: set[int],
    all_items: list[dict],
) -> str:
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

    # Wrap each full-corpus record as a SimpleNamespace so the shared helper
    # can resolve blocker references via attribute access. SimpleNamespace
    # avoids importing cortex_command.overnight.backlog (and its eager
    # __init__ fan-out) on every pre-commit run.
    all_items_ns = [SimpleNamespace(**rec) for rec in all_items]

    # --- Refined section ---
    lines += ["", "## Refined", ""]
    for item in items:
        if item["status"] != "refined":
            continue
        ready, _ = is_item_ready(
            SimpleNamespace(**item),
            all_items_ns,
            eligible_statuses={"refined"},
            treat_external_blockers_as="blocking",
        )
        if ready:
            lines.append(f"- **{item['id']}** {item['title']}")

    # --- Backlog section ---
    lines += ["", "## Backlog", ""]
    for item in items:
        if item["status"] not in ("backlog", "open", "blocked"):
            continue
        ready, _ = is_item_ready(
            SimpleNamespace(**item),
            all_items_ns,
            eligible_statuses={"backlog", "open", "blocked"},
            treat_external_blockers_as="blocking",
        )
        if ready:
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
                # External (non-digit, non-UUID) reference. Surface it here
                # since the Refined/Backlog passes now exclude such items.
                # UUID-shaped references map to "blocker not found" semantics
                # in the helper but are not surfaced as external-blocker
                # warnings (no fixture today; keep this conservative).
                if not _UUID_RE.match(b):
                    warnings.append(
                        f"- **{item['id']}**: external blocker ({b})"
                    )
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
    items, active_ids, archive_ids, all_items = collect_items()
    atomic_write(BACKLOG_DIR / "index.json", generate_json(items))
    atomic_write(
        BACKLOG_DIR / "index.md",
        generate_md(items, active_ids, archive_ids, all_items),
    )
    print(f"Generated index.json ({len(items)} items) and index.md")


if __name__ == "__main__":
    main()
