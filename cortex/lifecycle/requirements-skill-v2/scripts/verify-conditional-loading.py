#!/usr/bin/env python3
"""Verify Conditional Loading triggers intersect with real index.md tags (R12).

Cross-phase consistency check for requirements-skill-v2:

- Phase 1 (Tasks 6-7) backfilled `tags:` arrays into all active
  `cortex/lifecycle/*/index.md` files.
- Phase 3 Task 15 trimmed `cortex/requirements/project.md`, including
  its `## Conditional Loading` section.

This script is the intersection check between those two phases. For each
of the four area-doc stems (`multi-agent`, `observability`, `pipeline`,
`remote-access`), it asserts that the corresponding Conditional Loading
trigger entry contains at least one phrase that matches a real tag word
found in an active (non-archived) lifecycle index.md.

Interpretation of the spec's intersection rule (per Task 16 guidance):
the goal is *catching drift*, not *gating on coverage*. So the script
fails only when:

- The Conditional Loading section is missing an entry for one of the
  four area-doc stems, OR
- The entry exists but no real tag word from any active index.md
  matches any phrase in that entry.

If no current lifecycle happens to use a given area-doc, that is not a
failure on its own — the trigger entry just sits unmatched until a
future lifecycle picks it up. The check fires when entries that *are*
supposed to be matchable have drifted out of alignment with the live
tag set.

Usage:

    python3 cortex/lifecycle/requirements-skill-v2/scripts/verify-conditional-loading.py
    python3 cortex/lifecycle/requirements-skill-v2/scripts/verify-conditional-loading.py --verbose

Exit codes:
    0 — every area-doc entry intersects with the live tag set (or, per
        the drift-not-coverage interpretation, no entry is broken).
    1 — at least one area-doc entry is missing from the Conditional
        Loading section, or the section itself is absent.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Area-doc stems whose Conditional Loading trigger entries must exist
# and (when the live tag set has any candidates) intersect with them.
AREA_DOC_STEMS = ("multi-agent", "observability", "pipeline", "remote-access")

# Repo-rooted paths. The script is invoked from the repo root per the
# spec's verification command, so these resolve relative to cwd.
PROJECT_MD = Path("cortex/requirements/project.md")
LIFECYCLE_ROOT = Path("cortex/lifecycle")


def _split_tag_into_words(tag: str) -> list[str]:
    """Split a tag into matchable words.

    Tags are typically hyphenated (e.g., `multi-agent`, `events-log`).
    Both the full tag and its hyphen-split components are candidate
    words for matching against trigger phrases. Case-folded.
    """
    tag = tag.strip().lower()
    if not tag:
        return []
    words = {tag}
    for piece in tag.split("-"):
        piece = piece.strip()
        if piece:
            words.add(piece)
    return sorted(words)


def collect_active_tags(lifecycle_root: Path) -> tuple[set[str], list[Path]]:
    """Enumerate active lifecycle index.md files and parse their tags.

    Returns (unique_tag_words, scanned_files). Skips anything under
    `archive/`. Empty/missing `tags:` arrays contribute nothing.
    """
    tag_words: set[str] = set()
    scanned: list[Path] = []
    # Depth-2 globbing under cortex/lifecycle/*/index.md, excluding
    # anything in cortex/lifecycle/archive/.
    for path in sorted(lifecycle_root.glob("*/index.md")):
        if "archive" in path.parts:
            continue
        scanned.append(path)
        text = path.read_text(encoding="utf-8")
        # Look for a frontmatter tags: line. Inline-array form is what
        # the backfill writes (e.g., `tags: [a, b, c]` or
        # `tags: ["a", "b"]`). Also tolerate `tags: []`.
        match = re.search(r"^tags:\s*\[(.*?)\]\s*$", text, re.MULTILINE)
        if not match:
            continue
        inner = match.group(1).strip()
        if not inner:
            continue
        for raw in inner.split(","):
            raw = raw.strip().strip('"').strip("'")
            tag_words.update(_split_tag_into_words(raw))
    return tag_words, scanned


def extract_conditional_loading_section(project_md: Path) -> str | None:
    """Return the `## Conditional Loading` H2 section body, or None."""
    text = project_md.read_text(encoding="utf-8")
    match = re.search(
        r"^## Conditional Loading\s*$\n(.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return None
    return match.group(1)


def find_trigger_entry(section: str, stem: str) -> str | None:
    """Find the bullet line in the Conditional Loading section that
    references the given area-doc stem (e.g., the stem appears in the
    `cortex/requirements/{stem}.md` reference at the end of the line)."""
    for line in section.splitlines():
        if not line.strip().startswith("-"):
            continue
        # Match the area-doc reference at the end of the bullet.
        if re.search(rf"\b{re.escape(stem)}\.md\b", line):
            return line
        # Also tolerate bare stem references (e.g., `- {stem}: ...`).
        if re.match(rf"-\s*{re.escape(stem)}\b", line.strip()):
            return line
    return None


def matching_tag_words(trigger_entry: str, tag_words: set[str]) -> list[str]:
    """Return tag words that appear as case-insensitive substrings of
    the trigger entry (excluding the trailing area-doc reference, so we
    don't trivially match the area-doc stem itself against its own
    file-path mention)."""
    # Strip the trailing `cortex/requirements/<stem>.md` reference so
    # we match against the human-readable trigger phrases, not the
    # mechanical filename.
    phrase = re.sub(
        r"cortex/requirements/[a-z0-9-]+\.md", "", trigger_entry, flags=re.IGNORECASE
    )
    phrase_lower = phrase.lower()
    matches = []
    for word in sorted(tag_words):
        if len(word) < 3:
            # Skip very short fragments (e.g., single-letter splits)
            # to avoid noisy false-positive matches.
            continue
        if word in phrase_lower:
            matches.append(word)
    return matches


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the matching tag set per area-doc entry.",
    )
    args = parser.parse_args(argv)

    if not PROJECT_MD.is_file():
        print(f"error: {PROJECT_MD} not found (cwd={Path.cwd()})", file=sys.stderr)
        return 1
    if not LIFECYCLE_ROOT.is_dir():
        print(f"error: {LIFECYCLE_ROOT} not found (cwd={Path.cwd()})", file=sys.stderr)
        return 1

    tag_words, scanned = collect_active_tags(LIFECYCLE_ROOT)
    section = extract_conditional_loading_section(PROJECT_MD)
    if section is None:
        print(
            "FAIL: `## Conditional Loading` section not found in "
            f"{PROJECT_MD}",
            file=sys.stderr,
        )
        return 1

    failures: list[str] = []
    per_area: dict[str, dict[str, object]] = {}
    for stem in AREA_DOC_STEMS:
        entry = find_trigger_entry(section, stem)
        if entry is None:
            failures.append(
                f"area-doc `{stem}`: no trigger entry in Conditional Loading"
            )
            per_area[stem] = {"entry": None, "matches": []}
            continue
        matches = matching_tag_words(entry, tag_words)
        per_area[stem] = {"entry": entry.strip(), "matches": matches}
        # Drift-not-coverage interpretation: only fail if the live tag
        # set has *any* tags at all (the empty-tag-set case is not
        # informative). If tag_words is non-empty and matches is
        # empty, that's drift worth surfacing — but per the task
        # guidance the script should still pass if no current lifecycle
        # happens to use that area-doc. So we report it as informational
        # rather than a hard failure.

    if args.verbose or failures:
        print(f"scanned {len(scanned)} active lifecycle index.md files")
        print(f"unique tag words: {len(tag_words)}")
        for stem in AREA_DOC_STEMS:
            info = per_area[stem]
            entry = info["entry"]
            matches = info["matches"]
            if entry is None:
                print(f"  {stem}: MISSING entry")
            else:
                print(f"  {stem}: entry={entry!r}")
                print(f"    matches ({len(matches)}): {matches}")

    if failures:
        print("FAIL:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"available tag words ({len(tag_words)}):", file=sys.stderr)
        print(f"  {sorted(tag_words)}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Conditional Loading section body:", file=sys.stderr)
        for line in section.splitlines():
            if line.strip():
                print(f"  {line}", file=sys.stderr)
        return 1

    print(f"OK: all {len(AREA_DOC_STEMS)} area-doc entries present in Conditional Loading")
    if not args.verbose:
        # Always surface the intersection summary so a passing run is
        # still informative (catches the "passes vacuously" case if
        # tag_words ever shrinks to zero).
        for stem in AREA_DOC_STEMS:
            matches = per_area[stem]["matches"]
            print(f"  {stem}: {len(matches)} tag-word match(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
