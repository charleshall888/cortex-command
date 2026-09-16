"""Marker-set parity checks for kept pauses.

The kept-pause taxonomy has a single durable source of truth,
``skills/build/references/kept-pauses-data.toml`` — one ``[[pause]]`` row per
``<!-- pause: <slug> <kind> -->`` marker across ``skills/lifecycle`` and
``skills/refine``. This test replaces the retired line-anchored
inventory-bullet scheme (``LINE_TOLERANCE`` / rough ``file:line`` anchors).

One invariant:

(a) **Set-equality** — the set of marker slugs parsed from prose equals the set
    of ``id`` values in the data file. An orphan marker (no data row) and a data
    row with no marker both fail. Each marker's kind must also match its data row.


The per-kind semantic proximity sub-checks that used to ride along here were
removed on 2026-08-28: they asserted that an interaction token sat within
``±8`` lines of each marker, which is the prose-layout pin ``docs/policies.md``
§ "No tests on skill prose" forbids. Set-equality is structural
and stays. The freshness check against a committed ``kept-pauses.md`` went
with that file on 2026-09-16 — nothing loaded it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KEPT_PAUSES_DATA = (
    REPO_ROOT / "skills" / "build" / "references" / "kept-pauses-data.toml"
)
SKILL_DIRS = ("skills/build", "skills/refine")

# `<!-- pause: <slug> <kind> -->` marker. Strict slug (kebab) + kind classes so
# the literal `<!-- pause: <slug> <kind> -->` placeholder text inside
# kept-pauses-data.toml prose never matches.
_MARKER_RE = re.compile(r"<!--\s*pause:\s+([a-z][a-z0-9-]*)\s+([a-z][a-z-]*[a-z])\s+-->")

_KINDS = {"question", "phase-exit-wait", "config-conditional", "relayed-consent"}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _iter_markers() -> list[tuple[str, str, Path, int]]:
    """Return (slug, kind, path, line_num) for every prose pause marker.

    Scans ``*.md`` under skills/build and skills/refine.
    """
    out: list[tuple[str, str, Path, int]] = []
    for skill_dir in SKILL_DIRS:
        for md_path in sorted((REPO_ROOT / skill_dir).rglob("*.md")):
            text = md_path.read_text(encoding="utf-8")
            for idx, line in enumerate(text.splitlines(), start=1):
                m = _MARKER_RE.search(line)
                if m:
                    out.append((m.group(1), m.group(2), md_path, idx))
    return out


def _load_data() -> list[dict]:
    """Parse the pause taxonomy TOML into a list of ``[[pause]]`` tables."""
    with KEPT_PAUSES_DATA.open("rb") as fh:
        return tomllib.load(fh).get("pause", [])


# ---------------------------------------------------------------------------
# Pure check helpers (shared by the live checks and the negative controls)
# ---------------------------------------------------------------------------


def _parity_diff(marker_ids: set[str], data_ids: set[str]) -> tuple[set[str], set[str]]:
    """Return (orphan markers, missing markers) between the two id sets."""
    return marker_ids - data_ids, data_ids - marker_ids








# ---------------------------------------------------------------------------
# (a) Set-equality + kind consistency
# ---------------------------------------------------------------------------


def test_marker_set_equals_data_set() -> None:
    """Exact set-equality between prose marker slugs and data-file ids."""
    marker_ids = {slug for slug, _kind, _path, _line in _iter_markers()}
    data_ids = {row["id"] for row in _load_data()}
    assert marker_ids, "No pause markers parsed — the marker regex may have drifted"
    orphan, missing = _parity_diff(marker_ids, data_ids)
    assert not orphan and not missing, (
        f"orphan markers (no data row): {sorted(orphan)}; "
        f"data rows without a marker: {sorted(missing)}"
    )


def test_marker_kinds_valid_and_match_data() -> None:
    """Every marker kind is a known kind, is unique, and matches its data row."""
    data_by_id = {row["id"]: row for row in _load_data()}
    problems: list[str] = []
    seen: dict[str, str] = {}
    for slug, kind, path, line in _iter_markers():
        rel = f"{path.relative_to(REPO_ROOT)}:{line}"
        if kind not in _KINDS:
            problems.append(f"{rel} marker {slug!r} has unknown kind {kind!r}")
        if slug in seen:
            problems.append(f"duplicate marker slug {slug!r} at {rel} and {seen[slug]}")
        seen[slug] = rel
        row = data_by_id.get(slug)
        if row is not None and row.get("kind") != kind:
            problems.append(
                f"{rel} marker {slug!r} kind {kind!r} != data-file kind "
                f"{row.get('kind')!r}"
            )
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# Negative controls — assert each check actually fails on bad input.
# These use synthetic in-memory corpora / id sets; they never touch the tree.
# ---------------------------------------------------------------------------


def test_negative_marker_without_data_row() -> None:
    """A marker slug with no data row is reported as an orphan."""
    orphan, missing = _parity_diff({"real-pause", "ghost-marker"}, {"real-pause"})
    assert orphan == {"ghost-marker"} and not missing


def test_negative_data_row_without_marker() -> None:
    """A data row with no marker is reported as missing."""
    orphan, missing = _parity_diff({"real-pause"}, {"real-pause", "ghost-row"})
    assert missing == {"ghost-row"} and not orphan

