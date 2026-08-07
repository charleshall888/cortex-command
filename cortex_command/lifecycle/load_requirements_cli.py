"""cortex-load-requirements — emit the area-relevant requirements file list.

Deterministic selection verb that replaced a hand-executed prose algorithm
in the lifecycle skill (that reference is retired). Reads project.md's
``## Conditional Loading`` area-to-doc map + ``## Global Context`` section and
a feature's ``index.md`` ``areas:``, then prints the resolved repo-relative
path list (paths only, never file contents) to stdout and a coverage report to
stderr. The verb selects the minimal area-relevant requirements set, avoiding
both under-loading (missed constraints) and over-loading (token bloat); the
model still reads the listed file bodies into its own context.

Selection:

  1. ``cortex/requirements/project.md`` first (always; ``(skipped: file
     absent)`` suffix if absent on disk — the verb never directs reading a
     non-existent file).
  2. every ``## Global Context`` path, in file order, resolved literally
     against repo root (absent → ``(skipped: file absent)``).
  3. area docs whose ``## Conditional Loading`` row declares a key equal to one
     of the feature's areas, in section order.

Dedup is by resolved path: each path is emitted once. A Global Context entry
that also matches as an area doc keeps its Global Context position (placement
wins); a Global Context entry equal to ``project.md`` collapses into the
unconditional first line; an intra-Global-Context duplicate is emitted at its
first occurrence.

Matching semantics: **exact key lookup**, not substring. Each row's left half
is a list of area keys separated by ``,`` or ``/``; a key matches an area only
when both kebab-normalize (ASCII-lowercase, spaces and underscores to hyphens)
to the same string. ``pipe`` therefore does NOT select ``pipeline.md``, and
``overnight-runner`` and ``overnight runner`` are the same key. ``index.md``
``tags:`` no longer participates in selection.

Corrections to the retired prose's defects (documented, not silent drift):
  (i)  empty/whitespace areas are stripped before matching;
  (ii) Global Context is loaded in the no-match fallback too — reconciling the
       prose's step-1 ("always loaded regardless of matches") vs step-5
       ("load project.md only") self-contradiction in favor of step 1.

Coverage: every run emits exactly one ``COVERAGE:<state>`` line on stderr —
``loaded`` (an area selected a doc present on disk), ``doc-missing`` (an area
selected a doc absent from disk), ``unmapped`` (areas declared, none in the
map), or ``no-area`` (nothing declared). A human-readable detail line precedes
the marker in every state but ``loaded``. Stdout is unchanged by the marker.

The verb writes nothing to ``events.log`` and registers no event.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root,
)

PROJECT_MD_RELPATH = "cortex/requirements/project.md"
SKIPPED_SUFFIX = " (skipped: file absent)"
ARROW = "→"  # → separator in Conditional Loading bullets
KEY_SEPARATORS = ",/"  # both accepted between area keys on a map row

# Machine-parseable coverage states, one emitted per run on stderr.
COVERAGE_MARKER_PREFIX = "COVERAGE:"
COVERAGE_LOADED = "loaded"
COVERAGE_DOC_MISSING = "doc-missing"
COVERAGE_UNMAPPED = "unmapped"
COVERAGE_NO_AREA = "no-area"

FALLBACK_NOTE_TEMPLATE = (
    "no areas declared for this feature; loaded project.md + Global Context "
    "only"
)
# Distinct note for the case where there were no areas to match *because the
# index does not exist yet*. Collapsing this into the template above made a
# bare project.md result indistinguishable from "this feature genuinely has no
# area docs" — at the one phase (a fresh refine, before the index is written)
# where the index cannot exist. Coverage there is UNVERIFIED, not empty, and
# the rating built on it feeds the critical-review gate.
NO_INDEX_NOTE_TEMPLATE = (
    "no lifecycle index at {path}, so no areas were available; loaded "
    "project.md + Global Context only — area coverage is UNVERIFIED, not empty"
)
DOC_MISSING_NOTE_TEMPLATE = (
    "area doc absent from disk: {details} — the map row resolves but the file "
    "is not there"
)
# Deliberately ONE terse line naming the areas together: `unmapped` is the
# most common non-`loaded` state and is an expected outcome, not a defect. A
# per-area report here would train operators to ignore the whole signal.
UNMAPPED_NOTE_TEMPLATE = (
    "no area doc is mapped for {areas} — expected for areas that have none"
)


def _frontmatter_lines(text: str) -> Optional[List[str]]:
    """Return the lines inside the leading ``---`` fence, or ``None``."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    block: List[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return block
        block.append(line)
    return None  # unterminated frontmatter


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _extract_list_field(block: List[str], field: str) -> List[str]:
    """Extract a scalar-list frontmatter field (stdlib-only).

    Handles the inline flow form (``f: [a, b, c]`` / ``f: []``) and the
    block-sequence form (``f:`` then indented ``- a`` lines). Avoids a YAML
    dependency so the read-only verb stays stdlib-only and runs under the
    dual-channel wrapper's system-``python3`` branch.
    """
    prefix = field + ":"
    for i, line in enumerate(block):
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        value = stripped[len(prefix):].strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [_unquote(p.strip()) for p in inner.split(",")]
        if value:
            return [_unquote(value)]  # inline scalar (unusual) — single entry
        # Block-sequence form: collect subsequent ``- item`` lines.
        items: List[str] = []
        for sub in block[i + 1:]:
            s = sub.strip()
            if s.startswith("- "):
                items.append(_unquote(s[2:].strip()))
            elif s == "":
                continue
            else:
                break
        return items
    return []


def _extract_tags(block: List[str]) -> List[str]:
    """Extract the ``tags:`` list from frontmatter lines.

    Inert for selection since the switch to ``areas:``; kept because the index
    still carries ``tags:`` and other readers round-trip it through here.
    """
    return _extract_list_field(block, "tags")


def _extract_areas(block: List[str]) -> List[str]:
    """Extract the ``areas:`` list from frontmatter lines — the selection key."""
    return _extract_list_field(block, "areas")


def _index_path(project_root: Path, feature_slug: str) -> Path:
    return project_root / "cortex" / "lifecycle" / feature_slug / "index.md"


def _read_field(
    project_root: Path, feature_slug: Optional[str], field: str
) -> List[str]:
    """Return a feature index's list field, empty/whitespace entries stripped.

    Omitted ``feature_slug`` or an absent/field-less ``index.md`` ⇒ ``[]`` (the
    fallback path). Never raises.
    """
    if not feature_slug:
        return []
    index_path = _index_path(project_root, feature_slug)
    try:
        text = index_path.read_text(encoding="utf-8")
    except OSError:
        return []
    block = _frontmatter_lines(text)
    if block is None:
        return []
    # Correction (i): strip empty/whitespace entries before matching.
    return [v.strip() for v in _extract_list_field(block, field) if v.strip()]


def _read_tags(project_root: Path, feature_slug: Optional[str]) -> List[str]:
    """Return the feature's ``tags:`` list — inert for selection, see above."""
    return _read_field(project_root, feature_slug, "tags")


def _read_areas(project_root: Path, feature_slug: Optional[str]) -> List[str]:
    """Return the feature's ``areas:`` list — what selection matches on."""
    return _read_field(project_root, feature_slug, "areas")


def _normalize_key(value: str) -> str:
    """Kebab-normalize an area key or declared area for exact comparison."""
    return value.strip().lower().replace(" ", "-").replace("_", "-")


def _split_keys(key_text: str) -> List[str]:
    """Split a map row's left half into normalized, non-empty area keys."""
    for sep in KEY_SEPARATORS[1:]:
        key_text = key_text.replace(sep, KEY_SEPARATORS[0])
    keys = (_normalize_key(k) for k in key_text.split(KEY_SEPARATORS[0]))
    return [k for k in keys if k]


def _section_lines(text: str, heading: str) -> List[str]:
    """Return the raw lines under an H2 ``heading``, up to the next H2/H1/EOF."""
    out: List[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == heading:
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## ") or stripped.startswith("# "):
                break
            out.append(line)
    return out


def _parse_conditional_loading(project_md: str) -> List[Tuple[str, str]]:
    """Return ``(key_text, path)`` pairs in file order.

    Splits each bullet on the FIRST U+2192; a bullet with no separator
    (comment, sub-bullet, blank) is skipped — never an ``IndexError``. The path
    is the FIRST whitespace-delimited token to the right of the separator, so a
    trailing editorial parenthetical can never become part of the path (#454).
    Prose that must sit in this section therefore has to avoid the separator.
    """
    pairs: List[Tuple[str, str]] = []
    for line in _section_lines(project_md, "## Conditional Loading"):
        if ARROW not in line:
            continue
        key_part, _, path_part = line.partition(ARROW)
        key_text = key_part.lstrip().lstrip("-").strip()
        path_tokens = path_part.split()
        if key_text and path_tokens:
            pairs.append((key_text, path_tokens[0]))
    return pairs


def _parse_global_context(project_md: str) -> List[str]:
    """Return ``## Global Context`` bullet paths in file order."""
    paths: List[str] = []
    for line in _section_lines(project_md, "## Global Context"):
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        path = stripped.lstrip("-").strip()
        if path:
            paths.append(path)
    return paths


def resolve(
    project_root: Path, feature_slug: Optional[str] = None
) -> Tuple[List[str], Optional[str], str]:
    """Resolve the requirements selection for ``feature_slug`` under ``project_root``.

    Returns ``(lines, note, coverage)``. ``lines`` is the newline-ready
    repo-relative path list (project.md first, Global Context in file order,
    then matched area docs; absent paths carry the skip-suffix; deduped by
    resolved path with Global Context placement winning). ``coverage`` is one
    of the four ``COVERAGE_*`` states and ``note`` its human-readable detail,
    ``None`` in the ``loaded`` state where the path list says it all.
    """
    areas = _read_areas(project_root, feature_slug)
    try:
        project_md_text = (project_root / PROJECT_MD_RELPATH).read_text(
            encoding="utf-8"
        )
    except OSError:
        project_md_text = ""

    global_context = _parse_global_context(project_md_text)
    conditional = _parse_conditional_loading(project_md_text)

    declared: List[str] = []  # normalized, order-preserving, deduped
    for area in areas:
        key = _normalize_key(area)
        if key and key not in declared:
            declared.append(key)

    matched: List[str] = []
    hits: List[Tuple[str, str]] = []  # (declared area, path) in row order
    for key_text, path in conditional:
        keys = set(_split_keys(key_text))
        hit = next((a for a in declared if a in keys), None)
        if hit is not None:
            matched.append(path)
            hits.append((hit, path))

    lines: List[str] = []
    seen: Set[str] = set()

    def emit(relpath: str) -> None:
        if relpath in seen:
            return
        seen.add(relpath)
        if (project_root / relpath).exists():
            lines.append(relpath)
        else:
            lines.append(relpath + SKIPPED_SUFFIX)

    emit(PROJECT_MD_RELPATH)  # unconditional first-line slot
    for path in global_context:  # file order; project.md collapses into line 1
        emit(path)
    for path in matched:  # section order; GC placement wins on a dup
        emit(path)

    # Coverage precedence: a doc that actually loaded outranks every partial
    # failure, so a feature with one good area doc and one unmapped area is
    # `loaded` — the drift check has something to run against.
    present = [(area, path) for area, path in hits if (project_root / path).exists()]
    note: Optional[str] = None
    if present:
        coverage = COVERAGE_LOADED
    elif hits:
        coverage = COVERAGE_DOC_MISSING
        note = DOC_MISSING_NOTE_TEMPLATE.format(
            details="; ".join(f"{area} → {path}" for area, path in hits)
        )
    elif declared:
        coverage = COVERAGE_UNMAPPED
        note = UNMAPPED_NOTE_TEMPLATE.format(areas=", ".join(declared))
    else:
        coverage = COVERAGE_NO_AREA
        # An absent index is a different failure from an index that declares no
        # areas: the first means coverage was never determined, the second that
        # it was determined to be empty. Only the first is a defect the caller
        # can repair.
        index_absent = bool(feature_slug) and not _index_path(
            project_root, feature_slug
        ).is_file()
        if index_absent:
            note = NO_INDEX_NOTE_TEMPLATE.format(
                path=f"cortex/lifecycle/{feature_slug}/index.md"
            )
        else:
            note = FALLBACK_NOTE_TEMPLATE

    return lines, note, coverage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-load-requirements",
        description=(
            "Emit the area-relevant requirements file list (paths only) for a "
            "repo. Reads project.md's Conditional Loading area-to-doc map + "
            "Global Context and the feature index.md areas; prints "
            "repo-relative paths to stdout (project.md first, absent files "
            "suffixed ' (skipped: file absent)') and a coverage report plus "
            "one COVERAGE:<state> marker line to stderr. Read-only; matches "
            "areas by exact kebab-normalized key lookup, never substring; "
            "emits no event."
        ),
    )
    parser.add_argument(
        "--feature",
        default=None,
        help=(
            "Lifecycle feature slug; reads cortex/lifecycle/<slug>/index.md "
            "areas. An absent/area-less index or omitted --feature falls back "
            "to project.md + Global Context only (stdout byte-identical to "
            "omitting --feature). Never errors on a missing index."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        project_root = _resolve_user_project_root()
    except CortexProjectRootError:
        project_root = Path.cwd()
    lines, note, coverage = resolve(project_root, args.feature)
    if lines:
        sys.stdout.write("\n".join(lines) + "\n")
    if note is not None:
        sys.stderr.write(note + "\n")
    sys.stderr.write(COVERAGE_MARKER_PREFIX + coverage + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
