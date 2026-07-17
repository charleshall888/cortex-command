"""Byte-faithful ``index.md`` creation verb for the lifecycle Step 2 bootstrap.

``cortex-lifecycle-create-index --feature {slug} --backlog-file {basename|""}``
owns the 7-field lifecycle ``index.md`` creation template that
``discovery-bootstrap.md`` previously narrated as hand-executed prose. It writes
``{root}/cortex/lifecycle/{feature}/index.md`` (skip-if-exists, with the one
repair carve-out below) and emits a single compact-JSON signal on stdout::

    {"signal": "created"|"repaired"|"skipped", "path": "cortex/lifecycle/{slug}/index.md"}

Two shapes:

* **Shape A** (``--backlog-file`` is a non-empty resolver basename, e.g.
  ``326-foo.md``) — the backlog-linked form. The file is located via the
  canonical backlog dir (``{root}/cortex/backlog/<basename>``; the Step-1
  resolver emits only a basename, never a ``cortex/backlog/…`` path), its
  frontmatter re-parsed for ``uuid``/``tags``/``title``. ``parent_backlog_id``
  derives from the basename's ``^(\\d+)-`` prefix and the wikilink stem from the
  basename ``.stem``. A non-empty ``--backlog-file`` whose resolved path does
  not exist is a contract violation (``return 1``), **never** a silent
  fall-back to Shape B.
* **Shape B** (``--backlog-file ""``) — the ad-hoc form: bare unquoted ``null``
  for ``parent_backlog_uuid``/``parent_backlog_id``, ``tags: []``, and no
  heading/body.

**Repair carve-out (#400):** a non-empty ``--backlog-file`` against an EXISTING
index that is still an unlinked Shape B — its ``parent_backlog_uuid``,
``parent_backlog_id``, and ``tags`` lines all byte-match the Shape-B defaults —
rewrites exactly those three lines (plus ``updated:``) from the backlog item and
reports ``repaired``. Without this, an index created before the backlog match was
known (e.g. a resume that passed ``""``) kept ``tags: []`` forever, silently
narrowing every ``cortex-load-requirements`` load to ``project.md``. Anything
that does NOT byte-match all three defaults — a hand-edited or already-linked
index — is left untouched (``skipped``); ``artifacts``/``created``/body are
never rewritten either way.

The template is rendered as a manual f-string (atomic temp + ``os.replace``,
pinned trailing newline): PyYAML cannot reproduce the ordered-block +
inline-unquoted-array + unquoted-date + bare-``null`` shape that the downstream
stdlib readers (``load_requirements_cli._extract_tags``,
``wontfix_cli._frontmatter_value``) parse. The write root resolves via
``_resolve_user_project_root`` (honoring ``CORTEX_REPO_ROOT``) so the file lands
in the same tree as the ``cortex-update-item`` write-back under overnight
(#319 precedent).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cortex_command.backlog import _telemetry
from cortex_command.backlog.frontmatter_quote import quote_scalar
from cortex_command.backlog.resolve_item import _item_title, _parse_frontmatter
from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root,
)

_ID_PREFIX = re.compile(r"^(\d+)-")


# ---------------------------------------------------------------------------
# Date seam (date-only; monkeypatched in the test)
# ---------------------------------------------------------------------------


def _today() -> str:
    """Return today's UTC date as ``YYYY-MM-DD`` (date-only).

    Mirrors ``lifecycle_event._now_iso``'s UTC source but with the date-only
    format (not the ``…T..:..:..Z`` form). Defined locally — not imported — so
    the test can monkeypatch it deterministically.
    """
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _render_tags(tags: list) -> str:
    """Render *tags* as an unquoted inline flow sequence (``[a, b]`` / ``[]``).

    Plain-kebab tags render bare and round-trip through
    ``load_requirements_cli._extract_tags``; a tag containing ``:`` or ``[`` is
    quoted. A comma-bearing tag is NOT supported (``_extract_tags`` splits on
    comma before unquoting) — out of scope, not a target.
    """
    if not tags:
        return "[]"
    parts = []
    for tag in tags:
        text = str(tag)
        if ":" in text or "[" in text:
            parts.append(f'"{text}"')
        else:
            parts.append(text)
    return "[" + ", ".join(parts) + "]"


def _render(
    *,
    feature: str,
    uuid: Optional[str],
    backlog_id: Optional[int],
    tags: list,
    created: str,
    updated: str,
    stem: Optional[str],
    title: Optional[str],
    shape_a: bool,
) -> str:
    """Render the byte-faithful index.md content for Shape A or Shape B."""
    uuid_val = uuid if uuid else "null"
    id_val = str(backlog_id) if backlog_id is not None else "null"
    frontmatter = (
        "---\n"
        # ``feature`` is a string-intended slug — route through the key-scoped
        # quoter so a numeric-keyed dir (e.g. 378) emits as "378", not int 378.
        # ``parent_backlog_id`` is an intended int and stays bare.
        f"feature: {quote_scalar('feature', feature)}\n"
        f"parent_backlog_uuid: {uuid_val}\n"
        f"parent_backlog_id: {id_val}\n"
        "artifacts: []\n"
        f"tags: {_render_tags(tags)}\n"
        f"created: {created}\n"
        f"updated: {updated}\n"
        "---\n"
    )
    if not shape_a:
        return frontmatter
    body = f"# [[{stem}|{title}]]\n" "\n" f"Feature lifecycle for [[{stem}]].\n"
    return frontmatter + body


def _atomic_write(target: Path, content: str) -> None:
    """Write *content* to *target* atomically (temp file + ``os.replace``)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".index-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def _repair_unlinked_index(
    target: Path, backlog_file: str, root: Path, rel: str
) -> dict:
    """Repair an EXISTING index that is still an unlinked Shape B.

    Fires only when the ``parent_backlog_uuid``/``parent_backlog_id``/``tags``
    lines ALL byte-match the Shape-B defaults — a hand-edited or already-linked
    index never matches and is skipped, so the repair cannot clobber one. Only
    those three lines (plus ``updated:``) are rewritten; ``artifacts``,
    ``created``, and any body are preserved byte-for-byte.
    """
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return {"signal": "skipped", "path": rel}

    # Bound the check AND the rewrite to the frontmatter block: a body that
    # happens to contain a default-looking line must neither arm the repair
    # nor be touched by it. A file without a well-formed leading frontmatter
    # block is a hand-edit — skip.
    if not text.startswith("---\n"):
        return {"signal": "skipped", "path": rel}
    closing = text.find("\n---\n", 4)
    if closing == -1:
        return {"signal": "skipped", "path": rel}
    split = closing + len("\n---\n")
    frontmatter, body = text[:split], text[split:]

    defaults = (
        "parent_backlog_uuid: null\n",
        "parent_backlog_id: null\n",
        "tags: []\n",
    )
    if not all(line in frontmatter for line in defaults):
        return {"signal": "skipped", "path": rel}

    backlog_path = root / "cortex" / "backlog" / Path(backlog_file).name
    fm = _parse_frontmatter(backlog_path)  # raises OSError if absent (exit 1)
    uuid = fm.get("uuid")
    tags = fm.get("tags") or []
    match = _ID_PREFIX.match(Path(backlog_file).name)
    backlog_id = int(match.group(1)) if match else None

    uuid_val = uuid if uuid else "null"
    id_val = str(backlog_id) if backlog_id is not None else "null"
    frontmatter = frontmatter.replace(defaults[0], f"parent_backlog_uuid: {uuid_val}\n", 1)
    frontmatter = frontmatter.replace(defaults[1], f"parent_backlog_id: {id_val}\n", 1)
    frontmatter = frontmatter.replace(defaults[2], f"tags: {_render_tags(tags)}\n", 1)
    frontmatter = re.sub(
        r"^updated: .*$", f"updated: {_today()}", frontmatter, count=1, flags=re.MULTILINE
    )
    _atomic_write(target, frontmatter + body)
    return {"signal": "repaired", "path": rel}


def create_index(feature: str, backlog_file: str, root: Path) -> dict:
    """Create ``{root}/cortex/lifecycle/{feature}/index.md`` (skip-if-exists,
    except the unlinked-Shape-B repair carve-out — see the module docstring).

    Returns a ``{"signal", "path"}`` dict. Raises ``OSError`` when *backlog_file*
    is non-empty but its resolved path under ``cortex/backlog/`` is absent — a
    contract violation the caller maps to exit 1 (NOT a silent Shape-B write).
    """
    rel = f"cortex/lifecycle/{feature}/index.md"
    target = root / "cortex" / "lifecycle" / feature / "index.md"
    if target.exists():
        if backlog_file:
            return _repair_unlinked_index(target, backlog_file, root, rel)
        return {"signal": "skipped", "path": rel}

    today = _today()
    if backlog_file:
        # The Step-1 resolver emits a bare basename; normalize via the canonical
        # backlog dir. A naive ``root / backlog_file`` open would miss the file.
        backlog_path = root / "cortex" / "backlog" / Path(backlog_file).name
        fm = _parse_frontmatter(backlog_path)  # raises OSError if absent
        uuid = fm.get("uuid")
        tags = fm.get("tags") or []
        title = _item_title(backlog_path, fm)
        stem = Path(backlog_file).stem
        match = _ID_PREFIX.match(Path(backlog_file).name)
        backlog_id = int(match.group(1)) if match else None
        content = _render(
            feature=feature,
            uuid=uuid,
            backlog_id=backlog_id,
            tags=tags,
            created=today,
            updated=today,
            stem=stem,
            title=title,
            shape_a=True,
        )
    else:
        content = _render(
            feature=feature,
            uuid=None,
            backlog_id=None,
            tags=[],
            created=today,
            updated=today,
            stem=None,
            title=None,
            shape_a=False,
        )
    _atomic_write(target, content)
    return {"signal": "created", "path": rel}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-create-index",
        description=(
            "Create the lifecycle index.md from its byte-faithful 7-field "
            "creation template (skip-if-exists; a non-empty --backlog-file "
            "repairs an existing unlinked Shape-B index in place) and emit a "
            "{signal, path} JSON verdict on stdout."
        ),
    )
    parser.add_argument(
        "--feature",
        required=True,
        metavar="SLUG",
        help="Feature slug (e.g. my-feature).",
    )
    parser.add_argument(
        "--backlog-file",
        required=True,
        metavar="BASENAME",
        help=(
            "The Step-1 resolver's filename basename (e.g. 326-foo.md), located "
            'via cortex/backlog/; or "" for the ad-hoc (no-backlog) shape.'
        ),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-create-index")
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        root = _resolve_user_project_root()
    except CortexProjectRootError as exc:
        sys.stderr.write(f"cortex-lifecycle-create-index: {exc}\n")
        return 1
    try:
        result = create_index(args.feature, args.backlog_file, root)
    except OSError as exc:
        sys.stderr.write(
            "cortex-lifecycle-create-index: --backlog-file "
            f"{args.backlog_file!r} not found under cortex/backlog/ ({exc}). "
            "A non-empty --backlog-file must resolve to an existing ticket.\n"
        )
        return 1
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
