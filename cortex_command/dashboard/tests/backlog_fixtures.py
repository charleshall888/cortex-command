"""Reusable synthetic-corpus factory for backlog-feed tests.

Board tests must render against the *real* feed rather than a hand-written
snapshot dict, so a future change to ``build_backlog_snapshot``'s shape
fails them instead of silently rendering blanks. That means every fixture
starts as markdown on disk and is read back through the shipped pipeline —
``collect_items`` → ``partition_ready`` / ``build_epic_map`` → the snapshot.
This module is the shared writer for that corpus; it is the first shared
factory in this suite, which has no ``conftest.py``.

The module holds no state and creates nothing at import time. Callers own
their own :class:`tempfile.TemporaryDirectory` and pass its path as *root*.

Frontmatter facts this writer encodes, all owned by ``collect_items``
(``cortex_command/backlog/generate_index.py``) — a fixture that gets any of
them wrong yields an empty snapshot rather than an error, so they are
encoded here once instead of at each call site:

* An item's **id comes from its filename**, matched as ``^(\\d+)-`` against a
  ``[0-9]*-*.md`` glob. A frontmatter ``id:`` key is ignored, so ``id`` is a
  writer argument here and never reaches the file.
* The blocker frontmatter key is ``blocked-by`` (hyphen); the parsed record
  field is ``blocked_by`` (underscore). Callers write the record spelling
  and this module renames it.
* ``tags``, ``areas``, ``blocks``, and ``blocked-by`` parse as *inline*
  bracket lists only, and the frontmatter parser is line-based — so every
  value must render on one line.
* Defaults are the parser's, not this module's: absent ``status`` reads
  ``open`` (through ``normalize_status``, which rewrites ``blocked`` →
  ``backlog``), absent ``priority`` reads ``medium``, absent ``type`` reads
  ``feature``. Omitting a key here means "exercise that default".
* An item is an epic at ``type: epic``; children attach by ``parent``.
* ``lifecycle_phase`` is honored from frontmatter **only when** no matching
  lifecycle directory exists on disk, so :func:`write_corpus` creates an
  empty lifecycle tree and phases stay fixture-controlled.
* Terminal-status items never reach ``item_order`` but do participate in
  blocker resolution, so a "blocked only by a complete item" fixture writes
  that complete item as an ordinary sibling.

Usage::

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_corpus(root, [
            {"id": 410, "title": "Epic", "type": "epic", "status": "backlog"},
            {"id": 411, "title": "Child", "status": "backlog", "parent": "410"},
            {"id": 156, "title": "Shelved", "status": "deferred"},
            {"id": 412, "title": "Waiting", "status": "backlog",
             "blocked_by": ["411"]},
        ])
        snapshot = build_snapshot(root)
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from cortex_command.dashboard.data import parse_backlog_titles
from cortex_command.dashboard.ticket_feed import build_backlog_snapshot

# A frozen timestamp: the snapshot builder never stamps its own clock, so a
# fixture that supplies a constant keeps rendered output byte-comparable
# across runs.
POLLED_TS = "2026-07-27T00:00:00+00:00"

# Written in this order for readability. Any key a caller supplies that is
# not listed here is appended afterwards in sorted order rather than
# dropped — the status/type/priority vocabularies are open in practice and
# the frontmatter schema is not this module's to police.
_FIELD_ORDER = (
    "title",
    "status",
    "priority",
    "type",
    "tags",
    "areas",
    "created",
    "updated",
    "blocks",
    "blocked_by",
    "parent",
    "research",
    "spec",
    "discovery_source",
    "plan",
    "uuid",
    "lifecycle_slug",
    "session_id",
    "lifecycle_phase",
    "schema_version",
    "repo",
)

# Parsed as inline bracket lists by ``_parse_inline_str_list``.
_LIST_FIELDS = frozenset({"tags", "areas", "blocks", "blocked_by"})

# Record field name → frontmatter key, where the two disagree.
_KEY_ALIASES = {"blocked_by": "blocked-by"}

# Consumed by the writer itself; never emitted as frontmatter.
_WRITER_KEYS = frozenset({"id", "slug", "body", "archived"})


def _slugify(value: str) -> str:
    """Return a filename-safe slug, or ``item`` when nothing survives."""
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-") or "item"


def _render_value(field: str, value: object) -> str:
    """Render one frontmatter value on a single line.

    Raises:
        ValueError: if the rendered value spans lines, which the line-based
            frontmatter parser would silently truncate.
    """
    if field in _LIST_FIELDS or isinstance(value, (list, tuple)):
        rendered = "[" + ", ".join(str(element) for element in value) + "]"
    elif isinstance(value, bool):
        rendered = "true" if value else "false"
    else:
        rendered = str(value)

    if "\n" in rendered or "\r" in rendered:
        raise ValueError(
            f"frontmatter value for {field!r} spans lines; the parser is "
            f"line-based and would truncate it: {rendered!r}"
        )
    return rendered


def _render_frontmatter(spec: Mapping[str, object]) -> str:
    """Render an item spec's non-writer keys as YAML frontmatter lines."""
    supplied = [key for key in spec if key not in _WRITER_KEYS]
    ordered = [key for key in _FIELD_ORDER if key in supplied]
    ordered += sorted(key for key in supplied if key not in _FIELD_ORDER)

    lines = []
    for field in ordered:
        value = spec[field]
        if value is None:
            # An absent key and an explicit ``null`` are the same fact to
            # ``_opt``; omitting keeps the fixture file honest. A caller
            # testing the literal token passes the string ``"null"``.
            continue
        lines.append(f"{_KEY_ALIASES.get(field, field)}: {_render_value(field, value)}")
    return "".join(f"{line}\n" for line in lines)


def write_item(backlog_dir: Path, spec: Mapping[str, object]) -> Path:
    """Write one fixture item into *backlog_dir* and return its path.

    Args:
        backlog_dir: Directory to write into — ``cortex/backlog/`` or its
            ``archive/`` subdirectory.
        spec: Item fields. ``id`` is required and sets both the filename
            and the parsed record's id. ``slug`` overrides the
            title-derived filename slug and ``body`` the markdown body;
            neither is emitted as frontmatter. Every other key becomes one
            frontmatter line, with ``blocked_by`` written as ``blocked-by``
            and list fields rendered inline. A ``None`` value omits its key.

    Raises:
        KeyError: if *spec* has no ``id``.
        ValueError: if ``id`` is not a non-negative integer, or a value
            would span lines.
    """
    if "id" not in spec:
        raise KeyError("fixture item spec requires an 'id' — the parser reads "
                       "it from the filename, not from frontmatter")
    try:
        item_id = int(spec["id"])  # type: ignore[call-overload]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"fixture item id must be an integer: {spec['id']!r}") from exc
    if item_id < 0:
        raise ValueError(f"fixture item id must be non-negative: {item_id}")

    slug = spec.get("slug") or _slugify(str(spec.get("title") or "item"))
    body = spec.get("body", "Fixture body.")

    backlog_dir.mkdir(parents=True, exist_ok=True)
    path = backlog_dir / f"{item_id:03d}-{slug}.md"
    path.write_text(
        f"---\n{_render_frontmatter(spec)}---\n\n{body}\n", encoding="utf-8"
    )
    return path


def write_corpus(root: Path, items: Iterable[Mapping[str, object]]) -> Path:
    """Write a synthetic ``cortex/backlog/`` corpus under *root*.

    Creates ``<root>/cortex/backlog/`` and an empty
    ``<root>/cortex/lifecycle/``. Both are created even for an empty *items*
    — an absent corpus and an itemless one are different facts to the feed,
    and the empty lifecycle tree is what keeps ``lifecycle_phase`` sourced
    from fixture frontmatter rather than from phase detection on disk.

    Args:
        root: A caller-owned temporary directory. This module never creates
            or cleans up one of its own.
        items: Item specs as documented on :func:`write_item`. A spec with
            ``archived: True`` is written to ``cortex/backlog/archive/``
            instead, where it contributes to blocker resolution and the
            archive counts but never to ``item_order``.

    Returns:
        The ``cortex/backlog/`` path, for tests that assert against files.
    """
    backlog_dir = root / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)
    (root / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)

    for spec in items:
        target = backlog_dir / "archive" if spec.get("archived") else backlog_dir
        write_item(target, spec)

    return backlog_dir


def build_snapshot(
    root: Path,
    titles_by_id: Mapping[str, str] | None = None,
    polled_ts: str = POLLED_TS,
) -> dict:
    """Return the shipped feed snapshot over the corpus written under *root*.

    Delegates verbatim to ``ticket_feed.build_backlog_snapshot``, so what a
    test renders is what the poller commits. Nothing about the snapshot's
    shape is asserted or reshaped here.

    Args:
        root: The directory passed to :func:`write_corpus`.
        titles_by_id: Stringified id → title. Defaults to the same
            ``parse_backlog_titles`` scan the slow poll runs, so blocker
            titles resolve exactly as they do in production — including the
            scan's non-recursive behavior, which leaves an archived
            blocker's title ``None``. Pass a dict to override.
        polled_ts: The poll timestamp, frozen by default.

    Returns:
        The schema-complete snapshot dict.
    """
    backlog_dir = root / "cortex" / "backlog"
    lifecycle_dir = root / "cortex" / "lifecycle"
    if titles_by_id is None:
        titles_by_id = parse_backlog_titles(backlog_dir).by_id
    return build_backlog_snapshot(
        backlog_dir, lifecycle_dir, dict(titles_by_id), polled_ts
    )
