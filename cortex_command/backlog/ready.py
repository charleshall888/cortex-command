"""Emit priority-grouped ready backlog items as JSON.

Reads ``cortex/backlog/index.json`` (the O(1) index produced by
``cortex_command.backlog.generate_index``), applies the shared
``cortex_command.backlog.readiness.is_item_ready`` predicate via
``partition_ready``, and emits the result on stdout as a single JSON
document. The wire format is consumed by ``/backlog pick`` and
``/backlog ready``.

Schema (``--include-blocked`` adds a sibling ``ineligible`` array)::

    {
      "schema_version": 1,
      "groups": [
        {"priority": "critical",   "items": [...]},
        {"priority": "high",       "items": [...]},
        {"priority": "medium",     "items": [...]},
        {"priority": "low",        "items": [...]},
        {"priority": "contingent", "items": [...]}
      ]
    }

Item shape::

    {"id": int, "title": str, "status": str, "type": str,
     "blocked_by": list[str], "parent": str | null}

With ``--include-blocked`` each ineligible item additionally carries
``"reason": str`` and ``"rejection": "status" | "blocker"``.

Stale-index warnings (``cortex/backlog/[0-9]*-*.md`` newer than
``cortex/backlog/index.json``) are written to stderr but do not affect
exit status. A missing ``index.json`` is treated as a cache miss and
regenerated in-memory from the backlog ``.md`` files. On malformed input
the script emits ``{"error": "...", "schema_version": 1}`` to stdout and
exits 1.

Usage::

    python3 -m cortex_command.backlog.ready [--include-blocked]
    cortex-backlog-ready [--include-blocked]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
import types
from pathlib import Path
from typing import Any

from cortex_command.backlog import _telemetry, partition_ready
from cortex_command.common import TERMINAL_STATUSES  # noqa: F401

BACKLOG_DIR = Path.cwd() / "cortex" / "backlog"

# Canonical priority ordering. Unknown priorities sort alphabetically
# *after* "contingent" and are only emitted when non-empty.
_PRIORITY_ORDER: tuple[str, ...] = ("critical", "high", "medium", "low", "contingent")

# Status values that count as "eligible for the ready set". Mirrors
# ELIGIBLE_STATUSES in cortex_command/overnight/backlog.py:39.
_ELIGIBLE_STATUSES: tuple[str, ...] = (
    "backlog",
    "ready",
    "in_progress",
    "implementing",
    "refined",
)

_STALE_WARNING_CAP = 5

# Minimal frontmatter probes for the full-corpus scan. We only need id
# (from filename), status, and uuid — anything richer comes from
# index.json. Mirrors the regex-light parsing pattern used in
# cortex/backlog/generate_index.py without re-importing its private
# helpers (keeps ready.py independent of generate_index.py).
_FILENAME_ID_RE = re.compile(r"^(\d+)-")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(\n|$)", re.DOTALL)
_STATUS_LINE_RE = re.compile(r"^status:\s*(.+?)\s*$", re.MULTILINE)
_UUID_LINE_RE = re.compile(r"^uuid:\s*(.+?)\s*$", re.MULTILINE)


def _emit_error(reason: str) -> int:
    """Write JSON error to stdout, traceback to stderr, return exit code 1."""
    json.dump({"error": reason, "schema_version": 1}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 1


def _check_stale_index(backlog_dir: Path) -> None:
    """Warn on stderr when any tracked .md is newer than index.json.

    Caps output at ``_STALE_WARNING_CAP`` lines, then emits
    ``... and N more`` if more files are stale. Exit code is unaffected.
    """
    index_path = backlog_dir / "index.json"
    try:
        index_mtime = index_path.stat().st_mtime
    except FileNotFoundError:
        # Caller will surface this via the JSON error contract.
        return

    md_files = sorted(backlog_dir.glob("[0-9]*-*.md"))
    stale: list[str] = []
    for md in md_files:
        try:
            if md.stat().st_mtime > index_mtime:
                stale.append(md.name)
        except FileNotFoundError:
            continue

    if not stale:
        return

    for name in stale[:_STALE_WARNING_CAP]:
        sys.stderr.write(
            f"WARNING: backlog/index.json is older than {name} — "
            f"run `cortex-generate-backlog-index` to refresh.\n"
        )
    if len(stale) > _STALE_WARNING_CAP:
        sys.stderr.write(f"... and {len(stale) - _STALE_WARNING_CAP} more\n")


def _item_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Project a raw index.json record into the wire-format item shape."""
    return {
        "id": raw.get("id"),
        "title": raw.get("title", ""),
        "status": raw.get("status", ""),
        "type": raw.get("type", ""),
        "blocked_by": list(raw.get("blocked_by") or []),
        "parent": raw.get("parent"),
    }


def _sort_key_ready(raw: dict[str, Any]) -> tuple[int, Any]:
    """Within-group ordering for the ready set: refined first, then ID asc."""
    status = raw.get("status", "")
    item_id = raw.get("id")
    return (0 if status == "refined" else 1, item_id)


def _sort_key_ineligible(raw: dict[str, Any]) -> Any:
    """Within-group ordering for ineligible items: ID ascending."""
    return raw.get("id")


def _safe_sort(records: list[dict[str, Any]], key) -> list[dict[str, Any]]:
    """Sort tolerantly. If heterogeneous IDs raise TypeError, fall back to str.

    Spec edge case: an item with a non-int ``id`` should not crash the
    script. We log to stderr and re-sort by string comparison.
    """
    try:
        return sorted(records, key=key)
    except TypeError:
        sys.stderr.write(
            "WARNING: heterogeneous id types in backlog/index.json; "
            "sorting by string comparison.\n"
        )
        if key is _sort_key_ready:
            return sorted(
                records,
                key=lambda r: (
                    0 if r.get("status") == "refined" else 1,
                    str(r.get("id")),
                ),
            )
        return sorted(records, key=lambda r: str(r.get("id")))


def _group_by_priority(
    records: list[dict[str, Any]],
    *,
    transform,
    sort_key,
    canonical_only: bool,
) -> list[dict[str, Any]]:
    """Bucket *records* into priority groups in canonical order.

    ``canonical_only=True`` restricts output groups to the five canonical
    priorities; unknown-priority items are dropped (used for the
    ``ineligible`` projection where uniformity matters per spec R7).
    Otherwise unknown priorities are appended in alphabetical order
    after ``contingent`` and only emitted when non-empty (spec R6 +
    edge-case lines 117-118).
    """
    buckets: dict[str, list[dict[str, Any]]] = {p: [] for p in _PRIORITY_ORDER}
    extras: dict[str, list[dict[str, Any]]] = {}

    for raw in records:
        priority = raw.get("priority") or "medium"
        if priority in buckets:
            buckets[priority].append(raw)
        elif canonical_only:
            # Map unknown priorities to "medium" for uniform-schema output
            # (ineligible groups). The literal-priority projection is only
            # used for the ready groups.
            buckets["medium"].append(raw)
        else:
            extras.setdefault(priority, []).append(raw)

    groups: list[dict[str, Any]] = []
    for priority in _PRIORITY_ORDER:
        sorted_records = _safe_sort(buckets[priority], sort_key)
        groups.append(
            {
                "priority": priority,
                "items": [transform(r) for r in sorted_records],
            }
        )

    if not canonical_only:
        for priority in sorted(extras):
            sorted_records = _safe_sort(extras[priority], sort_key)
            groups.append(
                {
                    "priority": priority,
                    "items": [transform(r) for r in sorted_records],
                }
            )

    return groups


def _build_namespace(raw: dict[str, Any]) -> types.SimpleNamespace:
    """Wrap a raw index.json record for attribute access by the helper."""
    return types.SimpleNamespace(**raw)


def _load_full_corpus(backlog_dir: Path) -> list[types.SimpleNamespace]:
    """Scan source .md files for minimal {id, status, uuid} records.

    Covers ``cortex/backlog/[0-9]*-*.md`` (active + terminal-status) and
    ``cortex/backlog/archive/[0-9]*-*.md`` (archived) so blockers pointing to
    terminal items resolve as resolved inside ``partition_ready``
    instead of being misclassified as ``blocker not found`` or
    ``external blocker``. ``index.json`` filters terminal items out, so
    the helper's status-lookup map needs this richer corpus to match
    ``cortex_command/backlog/generate_index.py``'s built-in behavior.

    Returned records expose ``id`` (int), ``status`` (str), and ``uuid``
    (str | None) as attributes — the minimum the helper needs.
    Anything richer comes from ``index.json`` via ``_build_namespace``.
    """
    records: list[types.SimpleNamespace] = []
    if not backlog_dir.is_dir():
        return records

    paths: list[Path] = list(sorted(backlog_dir.glob("[0-9]*-*.md")))
    archive_dir = backlog_dir / "archive"
    if archive_dir.is_dir():
        paths.extend(sorted(archive_dir.glob("[0-9]*-*.md")))

    for path in paths:
        match = _FILENAME_ID_RE.match(path.name)
        if not match:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm = _FRONTMATTER_RE.match(text)
        if not fm:
            continue
        block = fm.group(1)
        status_match = _STATUS_LINE_RE.search(block)
        uuid_match = _UUID_LINE_RE.search(block)
        status = ""
        if status_match:
            status = status_match.group(1).strip().strip("\"'")
        uuid_val: str | None = None
        if uuid_match:
            uuid_val = uuid_match.group(1).strip().strip("\"'") or None
        records.append(
            types.SimpleNamespace(
                id=int(match.group(1)),
                status=status,
                uuid=uuid_val,
            )
        )
    return records


def _ineligible_transform(raw: dict[str, Any], reason: str, rejection: str) -> dict[str, Any]:
    payload = _item_payload(raw)
    payload["reason"] = reason
    payload["rejection"] = rejection
    return payload


def _build_result(
    records: list[dict[str, Any]],
    all_items_ns: list[types.SimpleNamespace],
    *,
    include_blocked: bool,
    required_tags: list[str],
) -> dict[str, Any]:
    """Run partition_ready over *records* and build the wire-format dict.

    *records* is the active set from ``index.json`` (used as the
    classification input); *all_items_ns* is the full-corpus minimal
    record list (active + terminal + archived) used by the helper to
    resolve blocker references against terminal items as resolved.

    *required_tags* is an AND-semantics, case-sensitive list of tags.
    When non-empty, only records whose ``tags`` field (a list) contains
    ALL of the required tags are passed to ``partition_ready``.
    *all_items_ns* is intentionally left unfiltered so cross-corpus
    blocker-status lookups remain correct for tagged items blocked by
    untagged items.
    """
    if required_tags:
        required_set = set(required_tags)
        records = [r for r in records if required_set <= set(r.get("tags") or [])]

    namespaces = [_build_namespace(r) for r in records]
    # Map id(namespace) → original dict so the output projection uses the
    # raw JSON record (per task context: "Preserve the original dict
    # alongside the namespace").
    raw_by_ns_id: dict[int, dict[str, Any]] = {
        id(ns): r for ns, r in zip(namespaces, records)
    }

    partition = partition_ready(
        namespaces,
        all_items_ns,
        eligible_statuses=_ELIGIBLE_STATUSES,
        treat_external_blockers_as="blocking",
    )

    ready_raw = [raw_by_ns_id[id(ns)] for ns in partition.ready]
    groups = _group_by_priority(
        ready_raw,
        transform=_item_payload,
        sort_key=_sort_key_ready,
        canonical_only=False,
    )

    result: dict[str, Any] = {
        "schema_version": 1,
        "groups": groups,
    }

    if include_blocked:
        ineligible_records: list[tuple[dict[str, Any], str, str]] = []
        for ns, reason, rejection in partition.ineligible:
            raw = raw_by_ns_id[id(ns)]
            ineligible_records.append((raw, reason, rejection))

        # Wrap into priority-grouped projection. We carry reason/rejection
        # alongside each raw via a per-item lookup.
        meta_by_id: dict[int, tuple[str, str]] = {
            id(raw): (reason, rejection) for raw, reason, rejection in ineligible_records
        }
        only_raws = [raw for raw, _r, _j in ineligible_records]

        def _xform(raw: dict[str, Any]) -> dict[str, Any]:
            reason, rejection = meta_by_id[id(raw)]
            return _ineligible_transform(raw, reason, rejection)

        result["ineligible"] = _group_by_priority(
            only_raws,
            transform=_xform,
            sort_key=_sort_key_ineligible,
            canonical_only=True,
        )

    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cortex-backlog-ready",
        description=(
            "Emit priority-grouped ready backlog items as JSON. Reads "
            "cortex/backlog/index.json and applies the shared readiness "
            "predicate. JSON goes to stdout; warnings to stderr."
        ),
    )
    parser.add_argument(
        "--include-blocked",
        action="store_true",
        help=(
            "Also emit filtered-out items under an `ineligible` array, "
            "annotated with reason and rejection cause."
        ),
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=None,
        dest="tag",
        metavar="TAG",
        help=(
            "Filter to items carrying this tag. Repeatable; all specified "
            "tags must be present (AND semantics). Matching is case-sensitive. "
            "Example: --tag phase2-trigger --tag my-label"
        ),
    )
    args = parser.parse_args(argv)
    if args.tag is None:
        args.tag = []
    return args


def main(argv: list[str] | None = None) -> int:
    _telemetry.log_invocation("cortex-backlog-ready")

    args = _parse_args(argv)

    try:
        if not BACKLOG_DIR.is_dir():
            return _emit_error("backlog/ not found in cwd")

        # Stale-index warnings. Best-effort; failures here must not
        # block the JSON output.
        try:
            _check_stale_index(BACKLOG_DIR)
        except Exception:
            traceback.print_exc(file=sys.stderr)

        index_path = BACKLOG_DIR / "index.json"
        try:
            with index_path.open("r", encoding="utf-8") as fh:
                records = json.load(fh)
        except FileNotFoundError:
            # A missing index is a cache miss, not an error: regenerate the
            # records in-memory from the backlog ``.md`` files (no disk
            # write) and continue. The index is a regenerated local cache,
            # not a source of truth. This runs inside the outer ``try`` so
            # any I/O error during regeneration falls through to the
            # canonical ``_emit_error`` path below.
            from cortex_command.backlog.generate_index import (
                collect_items,
                generate_json,
            )

            items, _active_ids, _archive_ids, _all_items = collect_items(
                BACKLOG_DIR, BACKLOG_DIR.parent / "lifecycle"
            )
            records = json.loads(generate_json(items))
        except json.JSONDecodeError as exc:
            return _emit_error(f"backlog/index.json is malformed: {exc.msg}")

        if not isinstance(records, list):
            return _emit_error("backlog/index.json must be a JSON array")

        all_items_ns = _load_full_corpus(BACKLOG_DIR)
        result = _build_result(
            records,
            all_items_ns,
            include_blocked=args.include_blocked,
            required_tags=args.tag,
        )
    except Exception as exc:  # pragma: no cover - last-resort error path
        traceback.print_exc(file=sys.stderr)
        return _emit_error(f"unexpected error: {exc}")

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
