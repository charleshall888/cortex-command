"""cortex-backfill-item-uuid — mint the missing ``uuid:`` on a backlog item.

``create_item`` mints ``uuid: str(uuid4())`` for every item it creates, and the
stable-citation rule depends on it: an id collision is resolved by citing the
slug or the uuid, never the bare ``#N``. An item that predates the field, or
that was hand-authored, has neither — and until #499 no verb could give it one.
The workaround was to hand-write ``str(uuid4())`` into the frontmatter, which is
right on format and bypasses whatever else the tool does.

Two modes, because the two shapes of the problem are different sizes: one named
item, or a sweep over every item in the backlog directory (whole eras of a
corpus predate the field — wild-light's ``008``-``070`` carry none at all).

An existing ``uuid:`` is never overwritten. Re-minting one silently breaks every
citation that already points at it, which is the exact failure the field exists
to prevent, so the verb reports ``skipped`` and moves on.

Placement is canonical, matching ``create_item``: immediately after
``schema_version:`` when that key is present, else as the first line inside the
frontmatter block. An item with no parseable frontmatter block is reported, not
rewritten (#501 — there is nowhere to put the key and saying otherwise is the
defect).

Output is one ``{state, ...}`` JSON envelope on stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from uuid import uuid4

from cortex_command.backlog import _telemetry
from cortex_command.backlog.resolve_item import _format_candidates, resolve
from cortex_command.common import CortexProjectRootError, _resolve_user_project_root

_UUID_RE = re.compile(r"^uuid:\s*\S")
_SCHEMA_RE = re.compile(r"^schema_version:\s*\S")
_DELIM = "---"


def _frontmatter_bounds(text: str) -> tuple[int, int] | None:
    """Return ``(open_idx, close_idx)`` of the frontmatter delimiters, or None."""
    lines = text.splitlines(keepends=True)
    first = -1
    for i, line in enumerate(lines):
        if line.strip() == _DELIM:
            if first == -1:
                first = i
                continue
            return (first, i)
    return None


def backfill(item_path: Path, *, mint=lambda: str(uuid4())) -> dict:
    """Insert a ``uuid:`` into *item_path* unless it already has one.

    Returns a per-item record: ``state`` is ``minted``, ``skipped`` (a uuid is
    already there) or ``no-frontmatter``.
    """
    text = item_path.read_text(encoding="utf-8")
    bounds = _frontmatter_bounds(text)
    rel = item_path.name
    if bounds is None:
        return {"item": rel, "state": "no-frontmatter", "uuid": None}

    open_idx, close_idx = bounds
    lines = text.splitlines(keepends=True)
    schema_idx = -1
    for i in range(open_idx + 1, close_idx):
        if _UUID_RE.match(lines[i]):
            return {
                "item": rel,
                "state": "skipped",
                "uuid": lines[i].split(":", 1)[1].strip(),
            }
        if schema_idx == -1 and _SCHEMA_RE.match(lines[i]):
            schema_idx = i

    minted = mint()
    insert_at = schema_idx + 1 if schema_idx != -1 else open_idx + 1
    lines.insert(insert_at, f"uuid: {minted}\n")
    item_path.write_text("".join(lines), encoding="utf-8")
    return {"item": rel, "state": "minted", "uuid": minted}


def _backlog_items(backlog_dir: Path) -> list[Path]:
    """Every item file, excluding the generated index and event sidecars."""
    return sorted(
        p
        for p in backlog_dir.glob("*.md")
        if p.name != "index.md" and not p.name.endswith(".events.md")
    )


def main() -> int:
    _telemetry.log_invocation("cortex-backfill-item-uuid")
    parser = argparse.ArgumentParser(
        prog="cortex-backfill-item-uuid",
        allow_abbrev=False,
        description=(
            "Mint a missing uuid: on a backlog item. With no slug, sweeps every "
            "item in the backlog directory. Never overwrites an existing uuid."
        ),
    )
    parser.add_argument(
        "slug",
        nargs="?",
        default=None,
        help="Slug, numeric ID, or UUID prefix. Omit to sweep the whole directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be minted without writing anything.",
    )
    args = parser.parse_args()

    try:
        backlog_dir = _resolve_user_project_root() / "cortex" / "backlog"
    except CortexProjectRootError as exc:
        print(json.dumps({"state": "error", "message": str(exc)}))
        return 1

    if args.slug is None:
        targets = _backlog_items(backlog_dir)
    else:
        result = resolve(args.slug, backlog_dir)
        if result.status == "ambiguous":
            print(_format_candidates(result.candidates), file=sys.stderr)
            return 2
        if result.status != "ok" or result.item is None:
            print(json.dumps({"state": "not-found", "slug": args.slug}))
            return 1
        targets = [result.item]

    mint = (lambda: "<dry-run>") if args.dry_run else (lambda: str(uuid4()))
    records = []
    for path in targets:
        if args.dry_run:
            text = path.read_text(encoding="utf-8")
            bounds = _frontmatter_bounds(text)
            if bounds is None:
                records.append({"item": path.name, "state": "no-frontmatter", "uuid": None})
                continue
            body = text.splitlines()[bounds[0] + 1 : bounds[1]]
            existing = next((ln for ln in body if _UUID_RE.match(ln)), None)
            records.append(
                {
                    "item": path.name,
                    "state": "skipped" if existing else "would-mint",
                    "uuid": existing.split(":", 1)[1].strip() if existing else None,
                }
            )
        else:
            records.append(backfill(path, mint=mint))

    counts: dict[str, int] = {}
    for rec in records:
        counts[rec["state"]] = counts.get(rec["state"], 0) + 1
    # Only the rows that moved or need attention: a sweep over a healthy corpus
    # is hundreds of `skipped` rows and printing them buries the two that matter.
    notable = [r for r in records if r["state"] != "skipped"]
    print(
        json.dumps(
            {
                "state": "ok",
                "scanned": len(records),
                "counts": counts,
                "items": notable,
                "dry_run": args.dry_run,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
