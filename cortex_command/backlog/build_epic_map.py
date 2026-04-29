#!/usr/bin/env python3
"""Build a deterministic epic→children JSON map from ``backlog/index.json``.

Auto-detects ``type: epic`` items in the active backlog index and emits a
sorted JSON envelope keying each epic to the list of its child items
(matched by the parent-field normalization rules from ``skills/dev/SKILL.md``
Step 3b). Output is stable across runs: epics ordered by integer-id
ascending, children ordered by id ascending, per-child fields ordered
lexicographically.

Usage:
    cortex-build-epic-map [INDEX_PATH]

INDEX_PATH defaults to ``backlog/index.json`` resolved relative to the
current working directory.

Exit codes:
    0 — success; JSON envelope written to stdout.
    1 — index file missing or malformed JSON.
    2 — unsupported ``schema_version`` encountered (only ``"1"`` is supported).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cortex_command.backlog import _telemetry


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class SchemaVersionError(Exception):
    """Raised when an item carries a ``schema_version`` other than ``"1"``.

    The offending value's :func:`repr` is stored on :attr:`value` so callers
    can format a precise diagnostic message.
    """

    def __init__(self, value: Any) -> None:
        self.value = repr(value)
        super().__init__(f"unsupported schema_version {self.value} — expected \"1\"")


# ---------------------------------------------------------------------------
# Parent-field normalization
# ---------------------------------------------------------------------------

def normalize_parent(value: Any) -> int | None:
    """Normalize a backlog item's ``parent`` field to an integer epic id or ``None``.

    Implements the four-step rule from ``skills/dev/SKILL.md`` Step 3b:

    1. ``None``/missing  → ``None``
    2. Strip surrounding ``"`` or ``'`` characters from string values.
    3. If the stripped value contains ``-`` (UUID heuristic) → ``None``.
    4. Else attempt ``int()``; on ``ValueError`` → ``None``.

    Returns the parsed integer epic id (e.g. ``100``), or ``None`` if the
    value is missing, malformed, UUID-shaped, or non-integer.
    """
    if value is None:
        return None

    # Strip surrounding quotes (single or double) for string inputs.
    if isinstance(value, str):
        stripped = value
        if len(stripped) >= 2 and stripped[0] in ("\"", "'") and stripped[-1] == stripped[0]:
            stripped = stripped[1:-1]
        if "-" in stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None

    # Bare-integer inputs pass through directly.
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Epic-map construction
# ---------------------------------------------------------------------------

def build_epic_map(items: list[dict], strict_schema: bool = True) -> dict:
    """Build the epic→children envelope from a list of backlog item dicts.

    Auto-detects items with ``type: epic`` and groups every other item whose
    normalized ``parent`` matches an epic id. The returned envelope has the
    form::

        {
            "schema_version": "1",
            "epics": {
                "<epic_id>": {
                    "children": [
                        {"id": ..., "spec": ..., "status": ..., "title": ...},
                        ...
                    ]
                },
                ...
            }
        }

    Children are sorted by ``id`` ascending; epics are inserted in
    integer-id ascending order. Per-child keys are inserted in
    lexicographic order (``id``, ``spec``, ``status``, ``title``) so a
    ``keys | sort | join(",")`` assertion succeeds without re-sorting.

    When ``strict_schema=True`` (the default), each item's
    ``schema_version`` must be the string ``"1"`` (or absent/None, which is
    treated as ``"1"``). Any other value — including the integer ``1``,
    ``"2"``, lists, or dicts — raises :class:`SchemaVersionError`.

    The ``spec`` field is copied verbatim from the source item; both
    explicit ``None`` and a missing ``spec`` key serialize to JSON ``null``.
    """
    if strict_schema:
        for item in items:
            sv = item.get("schema_version") if isinstance(item, dict) else None
            if sv is None:
                # Missing or null → treated as "1".
                continue
            if sv != "1":
                raise SchemaVersionError(sv)

    # Discover epic ids.
    epic_ids: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "epic":
            try:
                epic_ids.add(int(item["id"]))
            except (KeyError, TypeError, ValueError):
                continue

    # Group children by their normalized parent, restricted to detected epics.
    children_by_epic: dict[int, list[dict]] = {eid: [] for eid in epic_ids}
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "epic":
            continue
        parent_id = normalize_parent(item.get("parent"))
        if parent_id is None or parent_id not in epic_ids:
            continue
        # Per-child dict — keys inserted in lexicographic order so that
        # `sorted(child.keys())` equals the insertion order.
        child = {
            "id": item.get("id"),
            "spec": item.get("spec"),
            "status": item.get("status"),
            "title": item.get("title"),
        }
        children_by_epic[parent_id].append(child)

    # Build epics map in integer-ascending order.
    epics_map: dict[str, dict] = {}
    for epic_id in sorted(epic_ids):
        children = sorted(children_by_epic[epic_id], key=lambda c: c["id"])
        epics_map[str(epic_id)] = {"children": children}

    # Outer envelope — keys inserted in the exact required order.
    return {"schema_version": "1", "epics": epics_map}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-build-epic-map",
        description=(
            "Build a deterministic epic→children JSON map from backlog/index.json. "
            "Auto-detects type:epic items and groups each non-epic item under its "
            "normalized parent epic. Reads index.json, writes JSON envelope to stdout."
        ),
    )
    parser.add_argument(
        "index_path",
        nargs="?",
        default="backlog/index.json",
        help="Path to backlog index.json (default: backlog/index.json, resolved relative to CWD).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See module docstring for exit-code semantics."""
    _telemetry.log_invocation("cortex-build-epic-map")
    parser = _build_argparser()
    args = parser.parse_args(argv)

    index_path = Path(args.index_path)
    try:
        text = index_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(
            f"cortex-build-epic-map: index file not found: {index_path}",
            file=sys.stderr,
        )
        return 1

    try:
        items = json.loads(text)
    except json.JSONDecodeError as exc:
        print(
            f"cortex-build-epic-map: failed to parse JSON from {index_path}: {exc}",
            file=sys.stderr,
        )
        return 1

    if not isinstance(items, list):
        print(
            f"cortex-build-epic-map: expected top-level JSON array in {index_path}, "
            f"got {type(items).__name__}",
            file=sys.stderr,
        )
        return 1

    try:
        envelope = build_epic_map(items, strict_schema=True)
    except SchemaVersionError as exc:
        print(
            f"cortex-build-epic-map: unsupported schema_version {exc.value} — expected \"1\"",
            file=sys.stderr,
        )
        return 2

    print(json.dumps(envelope, indent=2, sort_keys=False, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
