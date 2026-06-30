"""Regression guard for the research fan-out tier x criticality matrix.

The research fan-out agent count is defined as a 2D matrix in the shared
reference ``skills/research/references/fanout.md``. The count is prose-applied
by the model, not computed by code, so this test asserts the *invariants* of
the published grid by parsing the markdown table out of that file. It does not
treat the numbers as the source of truth in code -- it parses the grid first,
then asserts structural and ordering invariants on the parsed values (per
spec R2 of scale-research-fanout-by-complexity).

If the table is deleted or restructured (wrong shape, missing rows/columns,
non-numeric cells), parsing fails with a clear assertion message so this test
also guards against the matrix being removed.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FANOUT_MD = REPO_ROOT / "skills" / "research" / "references" / "fanout.md"

# Column order for the criticality axis, low -> critical.
CRITICALITY_COLUMNS = ["low", "medium", "high", "critical"]
# Row order for the tier axis, simple -> complex.
TIER_ROWS = ["simple", "complex"]


def _split_markdown_row(line):
    """Split a markdown table row into trimmed cell strings.

    Tolerates leading/trailing pipes and surrounding whitespace.
    """
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _normalize(cell):
    """Lowercase a cell and strip markdown emphasis/backticks for matching."""
    return re.sub(r"[*_`]", "", cell).strip().lower()


def _is_separator_row(cells):
    """A markdown header/body separator row, e.g. ``|---|:--:|``."""
    return all(re.fullmatch(r":?-{1,}:?", c.strip()) for c in cells if c.strip())


def parse_fanout_grid(text):
    """Parse the 8-cell tier x criticality grid out of fanout.md text.

    Returns ``{"simple": [int, int, int, int], "complex": [...]}`` keyed by tier
    with values ordered low, medium, high, critical.

    Raises AssertionError with a clear message if the table cannot be located
    or does not have exactly 2 tier rows x 4 numeric criticality columns.
    """
    lines = text.splitlines()

    # Locate the header row: a table row whose cells contain all four
    # criticality column names (in order), tolerating a leading label cell.
    header_idx = None
    col_index = None  # maps criticality name -> position within the data row
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = _split_markdown_row(line)
        normalized = [_normalize(c) for c in cells]
        positions = {}
        for crit in CRITICALITY_COLUMNS:
            for pos, cell in enumerate(normalized):
                # exact token match so "high" doesn't collide elsewhere
                if cell == crit:
                    positions[crit] = pos
                    break
        if len(positions) == len(CRITICALITY_COLUMNS):
            header_idx = i
            col_index = positions
            break

    assert header_idx is not None, (
        "Could not find the fan-out matrix header row in "
        f"{FANOUT_MD}: expected a markdown table row containing all of "
        f"{CRITICALITY_COLUMNS}. The matrix may have been deleted or "
        "restructured."
    )

    # Collect the table's data rows (skip the header separator), keyed by the
    # tier label found in any cell of the row.
    grid = {}
    for line in lines[header_idx + 1:]:
        if "|" not in line:
            # Blank/non-table line after the data rows ends the table.
            if line.strip() == "":
                continue
            break
        cells = _split_markdown_row(line)
        if _is_separator_row(cells):
            continue
        normalized = [_normalize(c) for c in cells]
        tier = next((t for t in TIER_ROWS if t in normalized), None)
        if tier is None:
            # Not one of our tier rows; the data block has ended.
            break
        values = []
        for crit in CRITICALITY_COLUMNS:
            pos = col_index[crit]
            assert pos < len(cells), (
                f"Row for tier '{tier}' in {FANOUT_MD} is missing the "
                f"'{crit}' column (expected cell index {pos}, row has "
                f"{len(cells)} cells)."
            )
            raw = normalized[pos]
            assert re.fullmatch(r"\d+", raw), (
                f"Cell for tier '{tier}', criticality '{crit}' in {FANOUT_MD} "
                f"is not a positive integer: {cells[pos]!r}."
            )
            values.append(int(raw))
        grid[tier] = values

    assert set(grid) == set(TIER_ROWS), (
        f"Expected exactly the tier rows {sorted(TIER_ROWS)} in the fan-out "
        f"matrix in {FANOUT_MD}, found {sorted(grid)}. The matrix may have "
        "been deleted or restructured."
    )
    for tier, values in grid.items():
        assert len(values) == len(CRITICALITY_COLUMNS), (
            f"Tier row '{tier}' in {FANOUT_MD} has {len(values)} criticality "
            f"columns, expected {len(CRITICALITY_COLUMNS)}."
        )
    return grid


@pytest.fixture(scope="module")
def grid():
    assert FANOUT_MD.is_file(), (
        f"Fan-out reference not found at {FANOUT_MD}. The shared reference that "
        "defines the research fan-out tier x criticality matrix is missing."
    )
    text = FANOUT_MD.read_text(encoding="utf-8")
    return parse_fanout_grid(text)


def test_grid_shape(grid):
    """The parsed grid is exactly 2 tier rows x 4 criticality columns."""
    assert sorted(grid) == sorted(TIER_ROWS)
    for tier in TIER_ROWS:
        assert len(grid[tier]) == len(CRITICALITY_COLUMNS), (
            f"Tier '{tier}' must have {len(CRITICALITY_COLUMNS)} columns."
        )


def test_monotonic_across_criticality(grid):
    """Within each tier row, counts are non-decreasing low -> critical."""
    for tier in TIER_ROWS:
        row = grid[tier]
        for j in range(1, len(row)):
            left, right = row[j - 1], row[j]
            assert right >= left, (
                f"Fan-out matrix not monotonic across criticality in tier "
                f"'{tier}': {CRITICALITY_COLUMNS[j]} ({right}) < "
                f"{CRITICALITY_COLUMNS[j - 1]} ({left}). Row: {row}."
            )


def test_monotonic_across_tiers(grid):
    """For each criticality column, complex >= simple."""
    simple_row = grid["simple"]
    complex_row = grid["complex"]
    for j, crit in enumerate(CRITICALITY_COLUMNS):
        assert complex_row[j] >= simple_row[j], (
            f"Fan-out matrix not monotonic across tiers for criticality "
            f"'{crit}': complex ({complex_row[j]}) < simple ({simple_row[j]})."
        )


def test_floor_is_three(grid):
    """The lowest-effort corner (simple + low) is the floor value 3."""
    floor = grid["simple"][CRITICALITY_COLUMNS.index("low")]
    assert floor == 3, (
        f"Fan-out matrix floor (simple + low) must be 3, found {floor}."
    )


def test_corner_is_ten(grid):
    """The highest-effort corner (complex + critical) is 10."""
    corner = grid["complex"][CRITICALITY_COLUMNS.index("critical")]
    assert corner == 10, (
        f"Fan-out matrix corner (complex + critical) must be 10, found "
        f"{corner}."
    )


def test_cap_is_corner(grid):
    """No cell exceeds the corner value (10)."""
    corner = grid["complex"][CRITICALITY_COLUMNS.index("critical")]
    for tier in TIER_ROWS:
        for j, value in enumerate(grid[tier]):
            assert value <= corner, (
                f"Fan-out matrix cell (tier '{tier}', criticality "
                f"'{CRITICALITY_COLUMNS[j]}') = {value} exceeds the cap/corner "
                f"value {corner}."
            )
