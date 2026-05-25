"""Resolve a fuzzy backlog-item reference to its canonical metadata.

Accepts a numeric ID, kebab-slug, or title-phrase and resolves it against
``cortex/backlog/[0-9]*-*.md`` files. Prints a closed-set JSON object on
stdout (exit 0) or a diagnostic on stderr (exit 2/3/64/70). See ``--help``
for the full exit-code surface, resolution order, and backlog-directory
override.

Atomic-read-snapshot semantics: reads see either pre- or post-snapshot of any
concurrently written file (``atomic_write`` uses tempfile + ``os.replace``);
no defensive locking needed.

Exit codes:
  0   Unambiguous match — JSON on stdout.
  2   Ambiguous match — candidate list on stderr.
  3   No match — stderr message.
  64  Usage error — empty/whitespace input or input that normalises to empty
      after slugify (e.g. '!!!').
  70  Software/IO error — malformed frontmatter, missing or empty backlog
      directory, file-permission failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional, Tuple

import yaml

from cortex_command.common import slugify


# ---------------------------------------------------------------------------
# Public library surface — pure resolution result + error type
# ---------------------------------------------------------------------------


class ResolutionError(Exception):
    """Raised by ``resolve()`` for IO or parse failures.

    The CLI shim in ``main()`` catches this and maps it to exit-70. Library
    callers are free to catch or propagate as they see fit.
    """


@dataclass(frozen=True)
class ResolutionResult:
    """Tagged result returned by ``resolve()``.

    Attributes:
        status:
            ``"ok"``        — unambiguous match; ``item`` is the resolved path.
            ``"ambiguous"`` — multiple matches; ``candidates`` holds all of them.
            ``"not_found"`` — no match in any resolution step.
        item: Resolved ``Path`` when ``status == "ok"``; ``None`` otherwise.
        candidates: Full candidate list when ``status == "ambiguous"``; empty
            otherwise.
    """

    status: Literal["ok", "ambiguous", "not_found"]
    item: Optional[Path] = None
    candidates: List[Path] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

def _parse_frontmatter(path: Path) -> dict:
    """Return ``title`` and ``lifecycle_slug`` from a YAML frontmatter block.

    Reads only the frontmatter (between the two ``---`` fences); does NOT load
    body content.  Raises ``yaml.YAMLError`` on malformed frontmatter and
    ``OSError`` on file-access failures.
    """
    with open(path, "r", encoding="utf-8") as fh:
        first_line = fh.readline()
        if first_line.rstrip("\r\n") != "---":
            return {}
        lines = []
        for line in fh:
            if line.rstrip("\r\n") == "---":
                break
            lines.append(line)
    return yaml.safe_load("".join(lines)) or {}


# ---------------------------------------------------------------------------
# Title helper
# ---------------------------------------------------------------------------

def _item_title(path: Path, fm: dict) -> str:
    """Return the display title for an item, falling back to filename-derived."""
    title = fm.get("title", "")
    if title and isinstance(title, str):
        return title
    # Synthesise from filename: strip NNN- prefix and .md suffix
    stem = path.stem
    stem = re.sub(r"^\d+-", "", stem)
    return stem


# ---------------------------------------------------------------------------
# lifecycle_slug resolution
# Mirrors cortex_command.overnight.backlog.BacklogItem.resolve_slug L100-115
# Priority: lifecycle_slug frontmatter → spec/research dirname → slugify(title)
# ---------------------------------------------------------------------------

_LIFECYCLE_SLUG_WORD_CAP = 6


def _cap_slug_words(slug: str, max_words: int = _LIFECYCLE_SLUG_WORD_CAP) -> str:
    """Truncate a hyphenated slug to its first ``max_words`` words.

    Used only when a lifecycle slug is derived from a backlog title via
    ``slugify(title)`` — explicit frontmatter ``lifecycle_slug`` values and
    spec/research dirname extractions are returned verbatim so existing
    on-disk directory references stay valid.
    """
    parts = slug.split("-")
    if len(parts) <= max_words:
        return slug
    return "-".join(parts[:max_words])


def _resolve_lifecycle_slug(fm: dict, title: str) -> str:
    """Derive lifecycle_slug using the same fallback chain as BacklogItem.resolve_slug."""
    if fm.get("lifecycle_slug"):
        return fm["lifecycle_slug"]
    for key in ("spec", "research"):
        artifact_path = fm.get(key)
        if artifact_path:
            parent = Path(artifact_path).parent.name
            if parent and parent != ".":
                return parent
    return _cap_slug_words(slugify(title))


# ---------------------------------------------------------------------------
# Resolution functions
# ---------------------------------------------------------------------------

def _resolve_numeric(input_str: str, items: List[Path]) -> List[Path]:
    """Match items by leading-digit ID, ignoring zero-padding on either side.

    Only called when ``input_str`` is ``re.fullmatch(r'\\d+', input_str)``.
    Filenames 1-99 are zero-padded (``091-...``) but 100+ are not, so
    string-prefix matching against the raw input would miss padded files
    queried by their unpadded ID.
    """
    target = int(input_str)
    matches: List[Path] = []
    for p in items:
        m = re.match(r"^(\d+)-", p.name)
        if m and int(m.group(1)) == target:
            matches.append(p)
    return matches


def _resolve_kebab(input_str: str, items: List[Path]) -> List[Path]:
    """Match items by filename stem after stripping ``^\\d+-`` prefix."""
    return [
        p for p in items
        if re.sub(r"^\d+-", "", p.stem) == input_str
    ]


def _resolve_title_phrase(
    input_str: str,
    items_with_fm: List[Tuple[Path, dict]],
) -> List[Path]:
    """Match items whose slugified title contains slugified input, deduplicated by filename.

    Returns items where ``slugify(input_str) ⊆ slugify(title)``.
    Empty ``slug_input`` is handled upstream as exit-64 before reaching here.
    """
    slug_input = slugify(input_str)

    seen: set = set()
    results: List[Path] = []

    for path, fm in items_with_fm:
        title = _item_title(path, fm)

        # Slugified substring match
        slug_title = slugify(title)
        if bool(slug_input) and slug_input in slug_title:
            if path.name not in seen:
                seen.add(path.name)
                results.append(path)

    return results


# ---------------------------------------------------------------------------
# JSON output builder
# ---------------------------------------------------------------------------

def _build_json(path: Path, fm: dict) -> dict:
    """Build the closed-set JSON output object."""
    title = _item_title(path, fm)
    lifecycle_slug = _resolve_lifecycle_slug(fm, title)
    return {
        "filename": path.name,
        "backlog_filename_slug": path.stem,
        "title": title,
        "lifecycle_slug": lifecycle_slug,
    }


# ---------------------------------------------------------------------------
# Candidate list formatter
# ---------------------------------------------------------------------------

def _format_candidates(
    matches: List[Path],
    items_with_fm: List[Tuple[Path, dict]],
) -> str:
    """Format up to 5 candidates as a stderr-ready string."""
    fm_map = {path.name: fm for path, fm in items_with_fm}
    count = len(matches)
    lines = [f"ambiguous: {count} matches"]
    for path in matches[:5]:
        fm = fm_map.get(path.name, {})
        title = _item_title(path, fm)
        lines.append(f"{path.name}\t{title}")
    if count > 5:
        lines.append(f"... ({count - 5} more)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Backlog directory resolution
# ---------------------------------------------------------------------------

def _backlog_dir() -> Path:
    """Return the backlog directory, honouring CORTEX_BACKLOG_DIR override.

    Walks up from ``Path.cwd()`` (not ``__file__``) because the script binary
    lives in a plugin-cache path unrelated to the user's checkout once
    installed via ``/plugin install``. User intent: operate on the
    cortex-command checkout the user is currently in.
    """
    env_override = os.environ.get("CORTEX_BACKLOG_DIR")
    if env_override:
        return Path(env_override)
    here = Path.cwd().resolve()
    while True:
        candidate = here / "cortex" / "backlog"
        if candidate.is_dir():
            return candidate
        legacy = here / "backlog"
        if legacy.is_dir():
            return legacy
        if here == here.parent:
            break
        here = here.parent
    # No backlog/ found anywhere up the tree. Return a cwd-relative path so
    # the existing exit-70 branch in main() emits an intelligible diagnostic
    # ("backlog directory not found at <user-cwd>/cortex/backlog") rather
    # than a plugin-cache path the user has never heard of.
    return Path.cwd() / "cortex" / "backlog"


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-resolve-backlog-item",
        description=(
            "Resolve a fuzzy backlog-item reference (numeric ID, kebab-slug, "
            "or title phrase) to its canonical metadata. Prints a JSON object "
            "on stdout (exit 0) or a diagnostic on stderr (exit 2/3/64/70)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0   Unambiguous match — JSON on stdout.\n"
            "  2   Ambiguous match — candidate list on stderr.\n"
            "  3   No match — stderr message.\n"
            "  64  Usage error — empty/whitespace input or input that\n"
            "      normalises to empty after slugify (e.g. '!!!').\n"
            "  70  Software/IO error — malformed frontmatter, missing or\n"
            "      empty backlog directory, file-permission failure.\n\n"
            "Resolution order: numeric → kebab-slug → title-phrase.\n\n"
            "Numeric: matches filenames whose NNN- prefix equals the input.\n"
            "Leading zeros are matched literally (009 → 009-*.md, not 9-*.md).\n\n"
            "Title-phrase predicate: slugify(input) ⊆ slugify(title),\n"
            "deduplicated by filename.\n\n"
            "Override the backlog directory with CORTEX_BACKLOG_DIR (for tests).\n"
        ),
    )
    parser.add_argument(
        "input",
        help="Fuzzy backlog reference: numeric ID, kebab-slug, or title phrase.",
    )
    return parser


# ---------------------------------------------------------------------------
# Pure library function — 3-step resolution returning a tagged result.
# Mirrors the 3-step order (numeric → kebab → title-phrase) verbatim from
# the prior main() flow. IO/parse failures raise ResolutionError; usage-error
# preconditions (empty input, slugifies-to-empty) are handled at the CLI
# boundary, NOT inside the library — callers pass a non-empty input_str and
# the library returns status="not_found" rather than encoding exit codes.
# ---------------------------------------------------------------------------


def resolve(input_str: str, backlog_dir: Path) -> ResolutionResult:
    """Resolve a fuzzy backlog reference to a ``ResolutionResult``.

    Applies the existing 3-step order verbatim:
      1) Numeric ID  (input fullmatches ``\\d+``)
      2) Kebab-stem  (filename stem after stripping ``^\\d+-``)
      3) Title-phrase (slugify(input) ⊆ slugify(title))

    Raises:
        ResolutionError: backlog directory missing/empty, malformed frontmatter,
            or any IO failure during the resolution sweep.

    Returns:
        ``ResolutionResult`` whose ``status`` is one of ``"ok"``,
        ``"ambiguous"``, or ``"not_found"``. Usage errors (empty input,
        slugifies-to-empty) are the caller's responsibility — the library
        treats such inputs as ``"not_found"`` when they reach this far.
    """
    try:
        if not backlog_dir.is_dir():
            raise ResolutionError(
                f"backlog directory not found at {backlog_dir}"
            )

        items = sorted(backlog_dir.glob("[0-9]*-*.md"))
        if not items:
            raise ResolutionError(
                "backlog directory contains no NNN-*.md items"
            )

        is_numeric = bool(re.fullmatch(r"\d+", input_str))

        # Step 1: Numeric dispatch
        if is_numeric:
            matches = _resolve_numeric(input_str, items)
            if len(matches) == 1:
                return ResolutionResult(status="ok", item=matches[0])
            if len(matches) > 1:
                return ResolutionResult(
                    status="ambiguous", candidates=list(matches)
                )
            # n=0: fall through to kebab

        # Step 2: Kebab dispatch (skip if pure numeric — already tried above)
        if not is_numeric:
            kebab_matches = _resolve_kebab(input_str, items)
            if len(kebab_matches) == 1:
                return ResolutionResult(status="ok", item=kebab_matches[0])
            if len(kebab_matches) > 1:
                return ResolutionResult(
                    status="ambiguous", candidates=list(kebab_matches)
                )
            # n=0: fall through to title-phrase

        # Step 3: Title-phrase — load frontmatter for all items
        items_with_fm: List[Tuple[Path, dict]] = []
        for p in items:
            try:
                items_with_fm.append((p, _parse_frontmatter(p)))
            except Exception as exc:
                raise ResolutionError(
                    f"{p.name}: failed to parse frontmatter"
                ) from exc

        title_matches = _resolve_title_phrase(input_str, items_with_fm)

        if len(title_matches) == 1:
            return ResolutionResult(status="ok", item=title_matches[0])
        if len(title_matches) > 1:
            return ResolutionResult(
                status="ambiguous", candidates=list(title_matches)
            )

        return ResolutionResult(status="not_found")

    except ResolutionError:
        raise
    except Exception as exc:
        raise ResolutionError(str(exc)) from exc


# ---------------------------------------------------------------------------
# CLI shim — translates ResolutionResult / ResolutionError to exit codes.
# Owns usage-error preconditions (empty input → 64; slugifies-to-empty → 64)
# and stdout/stderr formatting; the library function knows nothing of these.
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:  # noqa: UP007 (Python 3.9 compat)
    parser = _build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    input_str: str = args.input

    # Exit 64: empty or whitespace-only input
    if not input_str or not input_str.strip():
        parser.print_usage(sys.stderr)
        print(
            "cortex-resolve-backlog-item: error: input must not be empty",
            file=sys.stderr,
        )
        return 64

    try:
        backlog_dir = _backlog_dir()
        result = resolve(input_str, backlog_dir)
    except ResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return 70
    except Exception as exc:
        print(
            f"cortex-resolve-backlog-item: internal error: {exc}",
            file=sys.stderr,
        )
        return 70

    if result.status == "ok":
        path = result.item
        assert path is not None  # status="ok" guarantees item is set
        try:
            fm = _parse_frontmatter(path)
        except Exception as exc:
            print(
                f"cortex-resolve-backlog-item: internal error: {exc}",
                file=sys.stderr,
            )
            return 70
        print(
            json.dumps(
                _build_json(path, fm),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0

    if result.status == "ambiguous":
        items_with_fm: List[Tuple[Path, dict]] = []
        for p in result.candidates:
            try:
                items_with_fm.append((p, _parse_frontmatter(p)))
            except Exception:
                items_with_fm.append((p, {}))
        print(
            _format_candidates(result.candidates, items_with_fm),
            file=sys.stderr,
        )
        return 2

    # result.status == "not_found"
    # Exit 64: input slugifies to empty (e.g. "!!!" → ""). Checked after the
    # resolve() sweep so a kebab/numeric match on a literal-special-char stem
    # wins over the usage-error guard, mirroring the pre-extraction main()
    # sequencing where this check sat between kebab and title-phrase.
    if not re.fullmatch(r"\d+", input_str) and not slugify(input_str):
        print(
            f"input '{input_str}' resolves to empty after normalization; "
            "provide more characters",
            file=sys.stderr,
        )
        return 64

    print(f"no match for '{input_str}'", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
