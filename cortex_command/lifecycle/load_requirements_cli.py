"""cortex-load-requirements — emit the tag-relevant requirements file list.

Deterministic selection verb that replaces the hand-executed prose algorithm
in ``skills/lifecycle/references/load-requirements.md``. Reads project.md's
``## Conditional Loading`` + ``## Global Context`` sections and a feature's
``index.md`` ``tags:``, then prints the resolved repo-relative path list
(paths only, never file contents) to stdout and a no-match fallback note to
stderr. The verb selects the minimal tag-relevant requirements set, avoiding
both under-loading (missed constraints) and over-loading (token bloat); the
model still reads the listed file bodies into its own context.

Selection (the prose's *intended* set, with two documented corrections):

  1. ``cortex/requirements/project.md`` first (always; ``(skipped: file
     absent)`` suffix if absent on disk — the verb never directs reading a
     non-existent file).
  2. every ``## Global Context`` path, in file order, resolved literally
     against repo root (absent → ``(skipped: file absent)``).
  3. area docs whose ``## Conditional Loading`` trigger — the text *left* of
     the U+2192 separator — ASCII-casefold-substring-matches any tag, in
     section order.

Dedup is by resolved path: each path is emitted once. A Global Context entry
that also matches as an area doc keeps its Global Context position (placement
wins); a Global Context entry equal to ``project.md`` collapses into the
unconditional first line; an intra-Global-Context duplicate is emitted at its
first occurrence.

Matching semantics: pure ASCII-casefold substring (``tag.lower() in
trigger.lower()``) — a short tag that is a substring of a longer trigger token
DOES match (e.g. ``pipe`` matches ``pipeline``); this is intentional substring,
NOT word-boundary. "Whole-tag" means the tag string is used whole as the search
needle (``harness-adaptation`` is not split into ``harness`` + ``adaptation``).

Corrections to prose defects (documented, not silent drift):
  (i)  empty/whitespace tags are stripped before matching — the prose's bare
       substring rule treats ``""`` as a substring of every trigger, which
       would load all area docs;
  (ii) Global Context is loaded in the no-match fallback too — reconciling the
       prose's step-1 ("always loaded regardless of tag matches") vs step-5
       ("load project.md only") self-contradiction in favor of step 1.

The verb writes nothing to ``events.log`` and registers no event.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

import yaml

from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root,
)

PROJECT_MD_RELPATH = "cortex/requirements/project.md"
SKIPPED_SUFFIX = " (skipped: file absent)"
ARROW = "→"  # → separator in Conditional Loading bullets
FALLBACK_NOTE_TEMPLATE = (
    "no area docs matched for tags: {tags}; loaded project.md only"
)


def _parse_frontmatter(path: Path) -> dict:
    """Return the YAML frontmatter dict, or ``{}`` on absence/parse failure."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            if fh.readline().rstrip("\r\n") != "---":
                return {}
            lines: List[str] = []
            for line in fh:
                if line.rstrip("\r\n") == "---":
                    break
                lines.append(line)
    except OSError:
        return {}
    try:
        data = yaml.safe_load("".join(lines))
    except yaml.YAMLError:
        return {}
    return data or {}


def _read_tags(project_root: Path, feature_slug: Optional[str]) -> List[str]:
    """Return the feature's ``tags:`` list, empty/whitespace entries stripped.

    Omitted ``feature_slug`` or an absent/tag-less ``index.md`` ⇒ ``[]`` (the
    fallback path). Never raises.
    """
    if not feature_slug:
        return []
    index_path = (
        project_root / "cortex" / "lifecycle" / feature_slug / "index.md"
    )
    if not index_path.is_file():
        return []
    raw = _parse_frontmatter(index_path).get("tags")
    if not isinstance(raw, list):
        return []
    # Correction (i): strip empty/whitespace tags before matching.
    return [t.strip() for t in raw if isinstance(t, str) and t.strip()]


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
    """Return ``(trigger, path)`` pairs in file order.

    Splits each bullet on the FIRST U+2192; a bullet with no separator
    (comment, sub-bullet, blank) is skipped — never an ``IndexError``.
    """
    pairs: List[Tuple[str, str]] = []
    for line in _section_lines(project_md, "## Conditional Loading"):
        if ARROW not in line:
            continue
        trigger_part, _, path_part = line.partition(ARROW)
        trigger = trigger_part.lstrip().lstrip("-").strip()
        path = path_part.strip()
        if trigger and path:
            pairs.append((trigger, path))
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
) -> Tuple[List[str], Optional[str]]:
    """Resolve the requirements selection for ``feature_slug`` under ``project_root``.

    Returns ``(lines, fallback_note)`` where ``lines`` is the newline-ready
    repo-relative path list (project.md first, Global Context in file order,
    then matched area docs; absent paths carry the skip-suffix; deduped by
    resolved path with Global Context placement winning) and ``fallback_note``
    is the stderr note string when no area docs matched, else ``None``.
    """
    tags = _read_tags(project_root, feature_slug)
    try:
        project_md_text = (project_root / PROJECT_MD_RELPATH).read_text(
            encoding="utf-8"
        )
    except OSError:
        project_md_text = ""

    global_context = _parse_global_context(project_md_text)
    conditional = _parse_conditional_loading(project_md_text)

    matched: List[str] = []
    for trigger, path in conditional:
        trigger_lower = trigger.lower()
        for tag in tags:
            if tag.lower() in trigger_lower:
                matched.append(path)
                break

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

    fallback_note: Optional[str] = None
    if not matched:
        fallback_note = FALLBACK_NOTE_TEMPLATE.format(
            tags="[" + ", ".join(tags) + "]"
        )

    return lines, fallback_note


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-load-requirements",
        description=(
            "Emit the tag-relevant requirements file list (paths only) for a "
            "repo. Reads project.md's Conditional Loading + Global Context and "
            "the feature index.md tags; prints repo-relative paths to stdout "
            "(project.md first, absent files suffixed ' (skipped: file "
            "absent)') and a no-match fallback note to stderr. Read-only; "
            "matches tags case-insensitively as whole-tag substrings against "
            "each Conditional Loading trigger; emits no event."
        ),
    )
    parser.add_argument(
        "--feature",
        default=None,
        help=(
            "Lifecycle feature slug; reads cortex/lifecycle/<slug>/index.md "
            "tags. An absent/tag-less index or omitted --feature falls back to "
            "project.md + Global Context only (byte-identical to omitting "
            "--feature). Never errors on a missing index."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        project_root = _resolve_user_project_root()
    except CortexProjectRootError:
        project_root = Path.cwd()
    lines, fallback_note = resolve(project_root, args.feature)
    if lines:
        sys.stdout.write("\n".join(lines) + "\n")
    if fallback_note is not None:
        sys.stderr.write(fallback_note + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
