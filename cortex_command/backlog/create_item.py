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
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from cortex_command.backlog import _telemetry
from cortex_command.common import (
    TERMINAL_STATUSES,
    _resolve_user_project_root,
    atomic_write,
    normalize_status,
    slugify,
)


def _id_list(refs: list[str] | None) -> str:
    """Render dependency refs as the inline ``[a, b]`` form the parser needs.

    Ids are normalised to bare integers. The corpus carries every spelling —
    ``["013"]``, ``[016]``, a bare ``170``, ``null`` — because these have only
    ever been hand-edited; emitting one shape is how that stops spreading.
    A ref that is not a number is passed through rather than dropped, so a
    typo stays visible in the file instead of vanishing on write.
    """
    if not refs:
        return "[]"
    out: list[str] = []
    for ref in refs:
        token = str(ref).strip().strip("\"'")
        if not token:
            continue
        out.append(str(int(token)) if token.isdigit() else token)
    return "[" + ", ".join(out) + "]"


def _warn_if_parent_closed(parent: str | None, backlog_dir: Path) -> None:
    """Say so when a new item is filed under an already-closed epic.

    A closed epic absorbs later children silently: nothing reopens it, and its
    ``updated:`` does not move, so the growth leaves no trace. The item is
    still created — filing follow-up work under a delivered epic is legitimate
    — but it stops being invisible.

    Best-effort by construction: a parent that cannot be resolved is not worth
    failing a creation over.
    """
    if not parent:
        return
    try:
        parent_id = int(str(parent).strip().strip("\"'"))
    except (TypeError, ValueError):
        return  # UUID-shaped or malformed — resolution is not worth the cost here
    for path in sorted(backlog_dir.glob(f"{parent_id:03d}-*.md")):
        m = re.search(r"^status:\s*(.+)$", path.read_text(encoding="utf-8"), re.M)
        if not m:
            return
        raw = m.group(1).strip().strip("\"'")
        if raw in TERMINAL_STATUSES or normalize_status(raw) in TERMINAL_STATUSES:
            print(
                f"Warning: parent epic {path.name} is already {raw!r}. "
                f"The epic stays closed and its `updated:` does not move, so "
                f"this child is invisible in the epic's own record.",
                file=sys.stderr,
            )
        return


# ---------------------------------------------------------------------------
# ID and slug helpers
# ---------------------------------------------------------------------------

# Filenames the pre-containment dashboard seeder (cortex_command/dashboard/seed.py)
# wrote into project repos. They are transient fixture data, never real backlog
# items, so a repo that ran the old seeder and never cleaned up must not have its
# ID sequence jumped past them.
_SEED_FIXTURE_RE = re.compile(r"^\d+-seed-.+\.md$")


# Branch tips consulted before an ID is minted. Bounded so a repo with hundreds
# of stale branches cannot turn filing a ticket into a multi-second operation;
# the deadline is the same bound expressed in time.
_REF_SCAN_LIMIT = 100
_REF_SCAN_DEADLINE_S = 5.0


def _ids_taken_on_other_branches(backlog_dir: Path) -> set[int]:
    """Return backlog IDs held under *backlog_dir* on any local or remote branch.

    The working directory alone cannot see a sibling branch, another worktree or
    an unmerged commit, so two sessions filing in parallel both read the same
    maximum and both take ``max + 1``. Neither commit conflicts, because the two
    files have *different names* — ``558-foo.md`` and ``558-bar.md`` merge
    cleanly and silently. Measured in one consumer on 2026-08-19: 8 backlog IDs
    held by two or three tickets each, one of them a four-way collision, and 3
    now permanent because every holder is cited from shipped source.

    Reads branch **tips**, not history. History was tried first and is wrong: a
    single smoke-test artifact committed and later deleted (``995-release-gate-
    empirical-…``) sat in ``--all --diff-filter=A`` output forever and pushed the
    next ID from 498 to 996. Tips also give the right semantics for the consumer's
    ratified renumbering rule — once a collision is resolved by renaming, the
    vacated number is genuinely free, because nothing cites it any more.

    Tags are excluded: 151 of this repo's 166 refs are release tags, they carry
    no ticket a live branch does not, and scanning them is pure cost.

    **This narrows the window; it does not close it.** A branch on another machine
    that has never been pushed is invisible to any local scan, as is a ticket that
    a sibling worktree has written but not yet committed. Failure is silent by
    design: git absent, no commits, a timeout or any non-zero exit yields an empty
    set and the caller falls back to the working-directory scan — exactly today's
    behaviour. Filing a ticket must not start failing because git is slow.

    ADR numbers have the same defect and are deliberately not covered: they have
    no allocator at all — the number is chosen by whoever writes the file — and
    #464 ruled the ADR side report-only after measuring that arming the existing
    ``adr_citation_audit.detect_duplicates`` produced 631 findings and 0 actions.
    """
    def _git(args: list[str], timeout: float) -> str | None:
        # Deliberately broad: this is a best-effort narrowing of a race, and
        # nothing it can hit is worth failing a ticket filing over. Callers in
        # the suite also stub ``subprocess.run`` wholesale, so the result may not
        # be a CompletedProcess at all.
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(backlog_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return result.stdout if result.returncode == 0 else None
        except Exception:  # noqa: BLE001 — never block filing
            return None

    refs_out = _git(
        ["for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"],
        timeout=_REF_SCAN_DEADLINE_S,
    )
    if refs_out is None:
        return set()

    deadline = time.monotonic() + _REF_SCAN_DEADLINE_S
    ids: set[int] = set()
    for ref in refs_out.split()[:_REF_SCAN_LIMIT]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break  # partial is still strictly better than the local scan alone
        listing = _git(["ls-tree", "-r", "--name-only", ref, "--", "."], remaining)
        if listing is None:
            continue
        for line in listing.splitlines():
            name = line.rsplit("/", 1)[-1]
            if not name.endswith(".md") or _SEED_FIXTURE_RE.match(name):
                continue
            if m := re.match(r"^(\d+)-", name):
                ids.add(int(m.group(1)))
    return ids


def _get_next_id(backlog_dir: Path) -> str:
    """Return the next available numeric ID (no zero-padding for IDs > 999).

    Scans ``backlog_dir`` and its ``archive/`` subdirectory, so an archived ID is
    never reallocated to a new item, and skips stale dashboard-seed fixtures.
    Unions that with the IDs held on every local and remote branch tip
    (:func:`_ids_taken_on_other_branches`), so a parallel branch or worktree the
    working directory cannot see does not get handed the same number.
    """
    paths = [
        *backlog_dir.glob("[0-9]*-*.md"),
        *(backlog_dir / "archive").glob("[0-9]*-*.md"),
    ]
    ids = {
        int(m.group(1))
        for p in paths
        if not _SEED_FIXTURE_RE.match(p.name)
        if (m := re.match(r"^(\d+)-", p.name))
    }
    ids |= _ids_taken_on_other_branches(backlog_dir)
    next_id = (max(ids) + 1) if ids else 1
    return f"{next_id:03d}" if next_id < 1000 else str(next_id)


_slugify = slugify  # Use canonical slugify from cortex_command.common


def _yaml_safe_title_value(title: str) -> str:
    """Serialize ``title`` as a single-line YAML scalar for a ``title:`` field.

    A title carrying a ``: `` or an embedded ``"`` makes a naively-quoted
    ``title: "{title}"`` line invalid YAML, which aborts the eager whole-backlog
    scan in ``resolve_item.resolve`` and blocks all backlog tooling until the
    bad file is removed. Sanitize-then-serialize (ordering is load-bearing):
    first collapse any CR/LF/control characters to a single space so no
    block-folding can occur, then emit one physical line via ``yaml.safe_dump``
    and return just the scalar value (split on the first ``": "``). The result
    round-trips exactly through the strict ``resolve_item._parse_frontmatter``
    (``yaml.safe_load``) and never raises. Implemented inline here rather than
    shared with the overnight report writer — see spec Non-Requirements.
    """
    sanitized = re.sub(r"[\r\n\x00-\x1f\x7f]+", " ", title)
    dumped = yaml.safe_dump(
        {"title": sanitized},
        default_flow_style=False,
        width=float("inf"),
        allow_unicode=True,
    ).rstrip("\n")
    assert "\n" not in dumped, "title must serialize to a single physical line"
    return dumped.split(": ", 1)[1]


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
    tags: list[str] | None = None,
    areas: list[str] | None = None,
    blocked_by: list[str] | None = None,
    blocks: list[str] | None = None,
    body: str | None = None,
) -> Path:
    """Create a new backlog item atomically and return its path.

    ``blocked_by`` and ``blocks`` are written on every item, empty list and
    all — unlike ``tags``/``areas``, which are omitted when unset. That
    asymmetry is deliberate and it is the point of the pair existing here.

    ``references/schema.md`` has always specified that "optional arrays default
    to ``[]``", and this verb has never emitted either field. Measured on the
    wild-light corpus: of 453 items carrying a ``uuid`` (so, tool-created), 316
    had no ``blocked-by`` key at all and only 16 (3.5%) declared a real
    dependency, against 20.8% of the 48 hand-authored items — a six-fold gap
    on the same backlog. An absent key is not a neutral default: there is
    nothing on the page to fill in, so ordering that exists in the author's
    head goes unrecorded and the dashboard's epic map has nothing to draw.
    """
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
        f"title: {_yaml_safe_title_value(title)}\n",
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
    if tags is not None:
        lines.append(f"tags: {tags}\n")
    if areas is not None:
        lines.append(f"areas: {areas}\n")
    # Always written, in the hyphenated spelling ``collect_items`` reads. The
    # underscored ``blocked_by`` parses to [] in silence, which is the failure
    # this pair is here to stop being invisible.
    lines.append(f"blocked-by: {_id_list(blocked_by)}\n")
    lines.append(f"blocks: {_id_list(blocks)}\n")
    lines.append("---\n")
    if body is not None:
        lines.append(body)

    # Emit exactly one trailing newline. A caller-supplied --body almost never
    # ends in one (shell strings and $(cat file) both drop it), and a body that
    # ends in several is just as bad: the standard pre-commit-hooks
    # `end-of-file-fixer` modifies the file in either direction, which aborts
    # the caller's commit. Normalizing the assembled document rather than the
    # body alone also covers `--body ""`, where appending to the body would
    # leave a blank line after the frontmatter and abort for the same reason.
    atomic_write(item_path, "".join(lines).rstrip("\n") + "\n")

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
    parser.add_argument(
        "--blocked-by", dest="blocked_by", nargs="*", default=None,
        help="Item IDs that must land before this one (space-separated)",
    )
    parser.add_argument(
        "--blocks", nargs="*", default=None,
        help="Item IDs this one must land before (space-separated)",
    )
    parser.add_argument("--tags", nargs="*", default=None, help="Tags (space-separated)")
    parser.add_argument("--areas", nargs="*", default=None, help="Areas (space-separated)")
    parser.add_argument("--body", default=None, help="Markdown body content to append after frontmatter")
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
            tags=args.tags,
            areas=args.areas,
            blocked_by=args.blocked_by,
            blocks=args.blocks,
            body=args.body,
        )
        print(str(item_path))
        _warn_if_parent_closed(args.parent, BACKLOG_DIR)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
