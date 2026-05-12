"""Parity test for the Kept user pauses inventory in skills/lifecycle/SKILL.md.

The lifecycle skill's "Kept user pauses" subsection (under "Phase Transition")
enumerates every user-facing AskUserQuestion call site that intentionally
remains after the auto-progression rewrite. This test enforces parity in both
directions:

1. Every inventory entry points to a real AskUserQuestion reference in the
   named file, within a ±20-line tolerance window of the rough-line anchor.
2. Every AskUserQuestion reference under skills/lifecycle/ and skills/refine/
   has a matching inventory entry (within the same tolerance).

Either direction failing is a parity violation — the inventory has drifted
from the source of truth, or new pauses were added without inventory
updates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL_MD = REPO_ROOT / "skills" / "lifecycle" / "SKILL.md"
LINE_TOLERANCE = 35

# Inventory bullet line: `- <file>:<line> — <rationale>` or with hyphen-minus
# (em-dash and minus dash both seen in practice). Capture file and line only.
_INVENTORY_BULLET = re.compile(
    r"^-\s+`?([^`\s:]+(?:/[^`\s:]+)*\.md)`?:(\d+)\b",
    re.MULTILINE,
)


def _parse_inventory() -> list[tuple[Path, int, str]]:
    """Return a list of (resolved_path, line_number, raw_line) inventory entries.

    Reads the "Kept user pauses" subsection from SKILL.md and parses each
    bullet line. Paths in the inventory are repo-root-relative.
    """
    content = SKILL_MD.read_text(encoding="utf-8")
    # Anchor on the subsection heading; slice until the next H2 or H3.
    section_match = re.search(
        r"###\s+Kept user pauses\s*\n(.*?)(?=^#{1,3}\s|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if not section_match:
        pytest.fail(
            "Could not locate '### Kept user pauses' section in "
            f"{SKILL_MD.relative_to(REPO_ROOT)}"
        )
    section_body = section_match.group(1)
    entries: list[tuple[Path, int, str]] = []
    for match in _INVENTORY_BULLET.finditer(section_body):
        rel_path = match.group(1)
        line_num = int(match.group(2))
        full_path = (REPO_ROOT / rel_path).resolve()
        entries.append((full_path, line_num, match.group(0)))
    return entries


def _askuserquestion_sites() -> dict[Path, list[int]]:
    """Return {file_path: [line_numbers]} for every AskUserQuestion mention.

    Scans skills/lifecycle/ and skills/refine/ markdown files.
    """
    sites: dict[Path, list[int]] = {}
    for skill_dir in ("skills/lifecycle", "skills/refine"):
        skill_path = REPO_ROOT / skill_dir
        for md_path in skill_path.rglob("*.md"):
            # Skip the SKILL.md inventory itself — the inventory text mentions
            # AskUserQuestion in prose but isn't a call site.
            if md_path == SKILL_MD:
                continue
            try:
                lines = md_path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(lines, start=1):
                if "AskUserQuestion" in line:
                    sites.setdefault(md_path.resolve(), []).append(idx)
    return sites


def _within_tolerance(anchor: int, candidates: list[int]) -> bool:
    return any(abs(anchor - c) <= LINE_TOLERANCE for c in candidates)


def test_inventory_entries_resolve_to_real_askuserquestion_sites() -> None:
    """Each inventory entry points to a file:line near an AskUserQuestion ref."""
    entries = _parse_inventory()
    assert entries, "Inventory parsed empty — section header may have drifted"
    sites = _askuserquestion_sites()

    violations: list[str] = []
    for path, line_num, raw in entries:
        # Inventory may reference SKILL.md itself (e.g., SKILL.md:60 ambiguous
        # backlog match); allow that file too.
        if path == SKILL_MD.resolve():
            # SKILL.md AskUserQuestion sites: scan SKILL.md directly.
            skill_lines = SKILL_MD.read_text(encoding="utf-8").splitlines()
            candidates = [
                i for i, line in enumerate(skill_lines, start=1)
                if "AskUserQuestion" in line
            ]
        else:
            candidates = sites.get(path, [])
        if not candidates:
            violations.append(
                f"Inventory entry {raw!r} names {path.relative_to(REPO_ROOT)} "
                f"but no AskUserQuestion reference exists in that file"
            )
        elif not _within_tolerance(line_num, candidates):
            violations.append(
                f"Inventory entry {raw!r} points to line {line_num} but the "
                f"nearest AskUserQuestion reference in "
                f"{path.relative_to(REPO_ROOT)} is at line(s) {candidates} "
                f"(±{LINE_TOLERANCE}-line tolerance exceeded)"
            )
    assert not violations, "\n".join(violations)


def test_every_askuserquestion_site_has_inventory_entry() -> None:
    """Each AskUserQuestion reference has a matching inventory entry."""
    entries = _parse_inventory()
    sites = _askuserquestion_sites()
    # Group inventory entries by file for quick lookup.
    by_file: dict[Path, list[int]] = {}
    for path, line_num, _raw in entries:
        by_file.setdefault(path, []).append(line_num)
    # Also accept SKILL.md itself — but exclude AskUserQuestion mentions
    # inside the "Kept user pauses" subsection (those are inventory prose,
    # not call sites).
    skill_text = SKILL_MD.read_text(encoding="utf-8")
    skill_lines = skill_text.splitlines()
    # Exclude the entire Phase Transition section (which contains prose
    # mentions of AskUserQuestion in the per-phase completion rule and the
    # Kept user pauses inventory). The actual SKILL.md call site is the
    # ambiguous-backlog-match prompt at line 60.
    section_match = re.search(
        r"^##\s+Phase Transition\s*$",
        skill_text,
        re.MULTILINE,
    )
    excluded_range: tuple[int, int] | None = None
    if section_match:
        start_offset = section_match.start()
        start_line = skill_text.count("\n", 0, start_offset) + 1
        # End of section = next h1 or h2 header (skip h3 children) or EOF
        rest = skill_text[section_match.end():]
        end_match = re.search(r"^#{1,2}\s", rest, re.MULTILINE)
        if end_match:
            end_offset = section_match.end() + end_match.start()
            end_line = skill_text.count("\n", 0, end_offset) + 1
        else:
            end_line = len(skill_lines)
        excluded_range = (start_line, end_line)

    def _in_excluded_range(line_no: int) -> bool:
        return (
            excluded_range is not None
            and excluded_range[0] <= line_no <= excluded_range[1]
        )

    skill_sites = [
        i for i, line in enumerate(skill_lines, start=1)
        if "AskUserQuestion" in line and not _in_excluded_range(i)
    ]
    if skill_sites:
        sites[SKILL_MD.resolve()] = skill_sites

    violations: list[str] = []
    for path, site_lines in sites.items():
        inventory_anchors = by_file.get(path, [])
        for site_line in site_lines:
            if not _within_tolerance(site_line, inventory_anchors):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{site_line} has an "
                    f"AskUserQuestion reference but no inventory entry within "
                    f"±{LINE_TOLERANCE} lines (inventory anchors for this "
                    f"file: {inventory_anchors or 'none'})"
                )
    assert not violations, "\n".join(violations)
