#!/usr/bin/env python3
"""P7 grep-regression guard for lifecycle #85.

For every candidates.md P7 row that classifies as (a) conditional-requirement,
carries an M1 or M4 label, and records a non-null commit SHA, assert that
`\\bconsider\\b` does not appear at the remediated file:line post-commit.

If no qualifying rows exist, the test module skips with a descriptive reason.
Per spec R12: only P7 carries a regression guard; P1/P3/P5 do not.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
CANDIDATES_MD = REPO_ROOT / (
    "cortex/lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/"
    "candidates.md"
)

P7_SECTION_HEADER = re.compile(r"^## Pattern P7 ")
NEXT_SECTION_HEADER = re.compile(r"^## ")
ROW_RE = re.compile(r"^\|\s*(?P<file_line>\S+:\d+[^|]*)\s*\|")
CONSIDER_RE = re.compile(r"\bconsider\b", re.IGNORECASE)


def _parse_p7_rows() -> list[tuple[str, int]]:
    """Return list of (file, line) for P7 rows with classification (a),
    M-label in {M1, M4}, and a non-null commit SHA.
    """
    if not CANDIDATES_MD.exists():
        return []

    lines = CANDIDATES_MD.read_text().splitlines()
    in_section = False
    rows: list[tuple[str, int]] = []

    for raw in lines:
        if P7_SECTION_HEADER.match(raw):
            in_section = True
            continue
        if in_section and NEXT_SECTION_HEADER.match(raw):
            break
        if not in_section:
            continue
        if not raw.startswith("|") or raw.startswith("|-"):
            continue

        cols = [c.strip() for c in raw.strip("|").split("|")]
        if len(cols) < 6:
            continue
        file_line, _excerpt, classification, m_label, sha, _notes = cols[:6]
        if "(a)" not in classification:
            continue
        if m_label not in {"M1", "M4"}:
            continue
        if not sha or sha.lower() in {"null", "none", ""}:
            continue

        # Parse "path/to/file.md:123" possibly with range suffix like ":49-51"
        m = re.match(r"(?P<path>[^:]+):(?P<line>\d+)", file_line)
        if not m:
            continue
        path_str = m.group("path").strip()
        line_num = int(m.group("line"))
        rows.append((path_str, line_num))

    return rows


_ROWS = _parse_p7_rows()


if not _ROWS:
    @pytest.mark.skip(reason="candidates.md has no qualifying P7 rows (a + M1/M4 + non-null SHA); P7 regression coverage is vacuous this run")
    def test_p7_regression_vacuous():
        pass
else:
    @pytest.mark.parametrize("path_str,line_num", _ROWS)
    def test_consider_not_present_at_remediated_site(path_str: str, line_num: int) -> None:
        path = REPO_ROOT / path_str
        assert path.exists(), f"remediated file missing: {path}"

        file_lines = path.read_text().splitlines()
        assert 1 <= line_num <= len(file_lines), (
            f"{path_str}:{line_num} out of range (file has {len(file_lines)} lines)"
        )

        line = file_lines[line_num - 1]
        assert not CONSIDER_RE.search(line), (
            f"P7 regression: 'consider' reappeared at {path_str}:{line_num} -> {line!r}"
        )
