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
KEPT_PAUSES_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "kept-pauses.md"
LINE_TOLERANCE = 35

# Inventory bullet line: `- <file>:<line> — <rationale>` or with hyphen-minus
# (em-dash and minus dash both seen in practice). Capture file and line only.
_INVENTORY_BULLET = re.compile(
    r"^-\s+`?([^`\s:]+(?:/[^`\s:]+)*\.md)`?:(\d+)\b",
    re.MULTILINE,
)

# Step-heading pattern used to validate phase-exit pause entries.
# Matches lines like "### Step 6", "### Step 6 — Title", or "## Step 6".
_STEP_HEADING = re.compile(r"^#{1,4}\s+Step\s+(\d+)\b", re.MULTILINE)

_PHASE_EXIT_PAUSE_TAG = "phase-exit pause"
_CONDITIONAL_PAUSE_TAG = "conditional pause"
_CONDITIONAL_PAUSE_MARKER = re.compile(r"\bread_branch_mode\b|\blifecycle_config\b|\bcortex-lifecycle-branch-mode\b|\bcortex-lifecycle-branch-decision\b")


def _parse_inventory() -> list[tuple[Path, int, str, str]]:
    """Return a list of (resolved_path, line_number, raw_matched, rationale) entries.

    Reads the kept-pauses inventory file and parses each bullet line. Paths
    in the inventory are repo-root-relative. ``rationale`` is the text on the
    bullet line after the file:line anchor (may be empty).
    """
    if not KEPT_PAUSES_MD.is_file():
        pytest.fail(
            "Kept-pauses inventory not found at "
            f"{KEPT_PAUSES_MD.relative_to(REPO_ROOT)}"
        )
    section_body = KEPT_PAUSES_MD.read_text(encoding="utf-8")
    section_lines = section_body.splitlines()
    entries: list[tuple[Path, int, str, str]] = []
    for match in _INVENTORY_BULLET.finditer(section_body):
        rel_path = match.group(1)
        line_num = int(match.group(2))
        full_path = (REPO_ROOT / rel_path).resolve()
        # Recover the full bullet line to extract the rationale text.
        # match.start() is the offset into section_body; count newlines before
        # it to get the line index.
        line_start = section_body.rfind("\n", 0, match.start()) + 1
        line_end_nl = section_body.find("\n", match.end())
        full_line = section_body[line_start: line_end_nl if line_end_nl != -1 else None]
        # Rationale: everything after the first em-dash or " — " separator.
        rationale_match = re.search(r"[—\-]{1,2}\s*(.*)", full_line[match.end() - line_start:])
        rationale = rationale_match.group(1).strip() if rationale_match else ""
        entries.append((full_path, line_num, match.group(0), rationale))
    return entries


def _step_heading_exists(path: Path, step_num: int) -> bool:
    """Return True if ``path`` contains a step heading for ``step_num``."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    for m in _STEP_HEADING.finditer(text):
        if int(m.group(1)) == step_num:
            return True
    return False


def _askuserquestion_sites() -> dict[Path, list[int]]:
    """Return {file_path: [line_numbers]} for every AskUserQuestion mention.

    Scans skills/lifecycle/ and skills/refine/ markdown files.
    """
    sites: dict[Path, list[int]] = {}
    for skill_dir in ("skills/lifecycle", "skills/refine"):
        skill_path = REPO_ROOT / skill_dir
        for md_path in skill_path.rglob("*.md"):
            # Skip the SKILL.md Phase Transition rule and the relocated
            # kept-pauses inventory — both mention AskUserQuestion in prose
            # but are not call sites.
            if md_path in (SKILL_MD, KEPT_PAUSES_MD):
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
    """Each inventory entry points to a file:line near an AskUserQuestion ref.

    Phase-exit pause entries (rationale contains 'phase-exit pause') are
    validated differently: instead of checking for an AskUserQuestion call
    site, we verify that the referenced file contains a step heading whose
    number matches the step referenced at the anchor line (within ±LINE_TOLERANCE
    lines of the heading). The line tolerance still applies — the anchor must
    fall within ±LINE_TOLERANCE lines of the matching step heading.
    """
    entries = _parse_inventory()
    assert entries, "Inventory parsed empty — section header may have drifted"
    sites = _askuserquestion_sites()

    violations: list[str] = []
    for path, line_num, raw, rationale in entries:
        # Phase-exit pause entries: validate via step-heading lookup.
        if _PHASE_EXIT_PAUSE_TAG in rationale:
            try:
                file_text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                violations.append(
                    f"Inventory entry {raw!r} (phase-exit pause) names "
                    f"{path.relative_to(REPO_ROOT)} but the file cannot be read"
                )
                continue
            heading_lines = [
                file_text.count("\n", 0, m.start()) + 1
                for m in _STEP_HEADING.finditer(file_text)
            ]
            if not heading_lines:
                violations.append(
                    f"Inventory entry {raw!r} (phase-exit pause) names "
                    f"{path.relative_to(REPO_ROOT)} but no step headings "
                    f"('### Step N') were found in that file"
                )
            elif not _within_tolerance(line_num, heading_lines):
                violations.append(
                    f"Inventory entry {raw!r} (phase-exit pause) points to "
                    f"line {line_num} but the nearest step heading in "
                    f"{path.relative_to(REPO_ROOT)} is at line(s) "
                    f"{heading_lines} (±{LINE_TOLERANCE}-line tolerance exceeded)"
                )
            continue

        # Standard AskUserQuestion entries.
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

        # Conditional pause entries: additionally require a structural marker
        # (read_branch_mode or lifecycle_config) within ±LINE_TOLERANCE lines
        # of the anchor. This enforces that the documented suppression
        # behavior is actually wired in skill prose.
        if _CONDITIONAL_PAUSE_TAG in rationale.lower():
            try:
                file_lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                violations.append(
                    f"Inventory entry {raw!r} (conditional pause) names "
                    f"{path.relative_to(REPO_ROOT)} but the file cannot be read"
                )
                continue
            window_start = max(1, line_num - LINE_TOLERANCE)
            window_end = min(len(file_lines), line_num + LINE_TOLERANCE)
            window_text = "\n".join(file_lines[window_start - 1: window_end])
            if not _CONDITIONAL_PAUSE_MARKER.search(window_text):
                violations.append(
                    f"conditional pause at {path.relative_to(REPO_ROOT)}:"
                    f"{line_num} lacks structural marker (read_branch_mode "
                    f"or lifecycle_config) within ±{LINE_TOLERANCE} lines"
                )
    assert not violations, "\n".join(violations)


def test_every_askuserquestion_site_has_inventory_entry() -> None:
    """Each AskUserQuestion reference has a matching inventory entry."""
    entries = _parse_inventory()
    sites = _askuserquestion_sites()
    # Group inventory entries by file for quick lookup.
    by_file: dict[Path, list[int]] = {}
    for path, line_num, _raw, _rationale in entries:
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
