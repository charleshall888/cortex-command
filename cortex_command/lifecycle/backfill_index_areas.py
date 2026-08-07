"""One-shot idempotent backfill of ``areas:`` onto existing linked lifecycle indexes.

``cortex-lifecycle-backfill-index-areas`` sweeps every existing
``{root}/cortex/lifecycle/*/index.md`` and populates ``areas:`` from its
parent backlog item, so requirements-loader coverage (#472) does not wait on
each of the ~190 pre-existing lifecycles being re-entered through
``cortex-lifecycle-create-index``. It shares the exact ``upsert_areas``
frontmatter-editing seam that verb's own linked-index refresh path
(``_refresh_linked_areas``) uses, so the bytes this sweep writes are what
re-running ``create_index --backlog-file`` against the same index would have
produced.

Three outcomes leave an index untouched:

* **Unlinked** (``parent_backlog_id: null``, the ad-hoc Shape-B form) — no
  parent to read from, so no ``areas:`` field is added at all.
* **Item absent** — the index's ``parent_backlog_id`` does not resolve to
  exactly one file under ``cortex/backlog/`` (zero-padding-aware, matching
  ``resolve_item._resolve_numeric``). A stale link (the parent item was
  renamed, archived, or its id was reused) degrades to this case rather than
  attaching the wrong item's areas.
* **No areas declared** — the resolved parent item has no ``areas:`` (or an
  empty one). Writing ``areas: []`` here would read as "deliberately no
  areas" rather than "not yet backfilled"; leaving the field off preserves
  that distinction for a future re-entry.

Every other linked index gets its ``areas:`` (re-)rendered from the parent's
current value, with ``created``, ``artifacts``, and body bytes preserved and
the edit bounded to the leading frontmatter block (via ``upsert_areas`` /
``_split_frontmatter``). A write only happens when the rendered value differs
from what is already on disk — the second run over an already-backfilled tree
is a byte-level no-op, which is what makes re-entry safe.

The write root resolves via ``_resolve_user_project_root`` (honoring
``CORTEX_REPO_ROOT``), matching every sibling lifecycle verb. This is an
operator-run, no-argument sweep — no skill invokes it, so it needs no
``bin/`` dual-channel wrapper.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cortex_command.backlog import _telemetry
from cortex_command.backlog.resolve_item import _parse_frontmatter, _resolve_numeric
from cortex_command.common import CortexProjectRootError, _resolve_user_project_root
from cortex_command.lifecycle.create_index import (
    _atomic_write,
    _split_frontmatter,
    upsert_areas,
)

_NUMERIC = re.compile(r"^\d+$")


# ---------------------------------------------------------------------------
# Date seam (date-only; monkeypatched in the test) — a local copy, not an
# import, so this verb's test can pin it independently of create_index's own.
# ---------------------------------------------------------------------------


def _today() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Parent-item resolution
# ---------------------------------------------------------------------------


def _resolve_parent_areas(backlog_id, backlog_dir: Path) -> Optional[list]:
    """Return the parent item's ``areas:`` list, or ``None`` if unresolvable.

    ``backlog_id`` is whatever ``parent_backlog_id`` parsed to (an ``int`` for
    the ordinary unpadded case ``create_index`` writes; occasionally a ``str``
    for a hand-authored zero-padded value PyYAML did not fold to an int).
    Resolution goes through ``resolve_item._resolve_numeric``, which compares
    filename-leading digits as integers — so a zero-padded backlog filename
    (ids 1-99) still matches an unpadded ``parent_backlog_id`` correctly.
    Zero or more-than-one matches (an absent, renamed, or id-reused parent)
    both return ``None`` — a safe skip, never a guess at the wrong item.
    """
    if backlog_id is None:
        return None
    id_str = str(backlog_id)
    if not _NUMERIC.match(id_str):
        return None
    items = sorted(backlog_dir.glob("[0-9]*-*.md"))
    matches = _resolve_numeric(id_str, items)
    if len(matches) != 1:
        return None
    fm = _parse_frontmatter(matches[0])
    return fm.get("areas")


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def backfill_index_areas(root: Path) -> dict:
    """Sweep every ``cortex/lifecycle/*/index.md`` under *root*, backfilling
    ``areas:`` from each linked index's parent backlog item.

    Returns a compact count summary: ``total`` indexes visited, ``updated``
    (a new or changed ``areas:`` was written), ``unchanged`` (already
    up to date — the idempotent second-run case), ``unlinked`` (Shape-B, no
    parent), and ``skipped`` (the parent item could not be resolved, or
    declares no ``areas:``).
    """
    backlog_dir = root / "cortex" / "backlog"
    lifecycle_dir = root / "cortex" / "lifecycle"

    total = 0
    updated = 0
    unchanged = 0
    unlinked = 0
    skipped = 0

    for index_path in sorted(lifecycle_dir.glob("*/index.md")):
        total += 1
        fm = _parse_frontmatter(index_path)
        backlog_id = fm.get("parent_backlog_id")
        if backlog_id is None:
            unlinked += 1
            continue

        areas = _resolve_parent_areas(backlog_id, backlog_dir)
        if not areas:
            skipped += 1
            continue

        text = index_path.read_text(encoding="utf-8")
        rendered = upsert_areas(text, areas)
        if rendered is None or rendered == text:
            unchanged += 1
            continue

        frontmatter, body = _split_frontmatter(rendered)
        frontmatter = re.sub(
            r"^updated: .*$", f"updated: {_today()}", frontmatter, count=1, flags=re.MULTILINE
        )
        _atomic_write(index_path, frontmatter + body)
        updated += 1

    return {
        "signal": "backfilled",
        "total": total,
        "updated": updated,
        "unchanged": unchanged,
        "unlinked": unlinked,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="cortex-lifecycle-backfill-index-areas",
        description=(
            "One-shot idempotent sweep that populates areas: on every existing "
            "linked cortex/lifecycle/*/index.md from its parent backlog item's "
            "current areas:, and emits a {signal, ...} count summary on stdout."
        ),
    )


def main(argv: Optional[list[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-backfill-index-areas")
    _build_parser().parse_args(argv)
    try:
        root = _resolve_user_project_root()
    except CortexProjectRootError as exc:
        sys.stderr.write(f"cortex-lifecycle-backfill-index-areas: {exc}\n")
        return 1
    result = backfill_index_areas(root)
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
