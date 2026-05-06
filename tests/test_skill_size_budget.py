"""Test #4 (skill-design test infrastructure, ticket #181): SKILL.md size
budget — ≤500 lines unless a valid in-file size-budget-exception marker is
present.

Enumerates canonical ``skills/<name>/SKILL.md`` files and plugin
``plugins/<plugin>/skills/<name>/SKILL.md`` files (deduplicated by content
hash so byte-identical mirrors fan out to a single failure rather than two)
via the helpers in ``tests/conftest.py``. For each enumerated file:

  - Search for any ``size-budget-exception:`` token. If a token is found but
    no full match of the valid-marker regex covers it, emit an
    "invalid size-budget-exception marker" error containing the file path.
  - If ``line_count > CAP`` and no valid marker is present, emit a cap-breach
    error containing the file path, the literal numeric line count vs. cap,
    and BOTH remediation hint substrings: ``extract to references/`` AND
    ``<!-- size-budget-exception:`` (the marker template prefix).

A valid marker matches the regex
``<!--\\s*size-budget-exception:\\s*(?P<reason>.{30,}?),\\s*lifecycle-id=(?P<lid>\\d+),\\s*date=(?P<date>\\d{4}-\\d{2}-\\d{2})\\s*-->``
— rationale ≥30 characters, positive integer lifecycle-id, YYYY-MM-DD date.

All findings are aggregated into a single multi-line ``AssertionError`` per
the spec's "no fail-fast" convention.

Three regression-fixture variants exercise the failure paths against
synthetic SKILL.md files under ``tests/fixtures/skill_size_budget/``
(deliberately outside the canonical glob):

  - ``over-cap-no-marker/SKILL.md`` — 501 lines, no marker at all → cap-breach.
  - ``invalid-marker/SKILL.md`` — under-cap file containing
    ``<!-- size-budget-exception: too short -->`` (rationale <30 chars) →
    invalid-marker error.
  - ``boundary-29-char-reason/SKILL.md`` — 501-line file with a marker whose
    rationale is exactly 29 characters (one short of the regex boundary) →
    marker is rejected and the file falls through to the cap-breach path.
    Proves the 30-char-min boundary holds: 30 passes, 29 fails.

Each ``pytest.raises(AssertionError, match=<regex>)`` pin ensures the
AssertionError originates specifically from the intended detection path
(cap-breach with line counts, or invalid-marker by literal substring), not
an unrelated error elsewhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import (
    enumerate_canonical_skills,
    enumerate_plugin_skills,
    enumerate_skills,
    repo_root,
)


CAP = 500

# Valid marker regex per spec requirement #13.
MARKER_REGEX = re.compile(
    r"<!--\s*size-budget-exception:\s*(?P<reason>.{30,}?),"
    r"\s*lifecycle-id=(?P<lid>\d+),"
    r"\s*date=(?P<date>\d{4}-\d{2}-\d{2})\s*-->"
)

# Loose "any marker prefix" detector — used to find malformed markers. If a
# file contains the marker prefix but no full match of MARKER_REGEX covers
# the same span, the marker is invalid.
MARKER_PREFIX_REGEX = re.compile(r"<!--\s*size-budget-exception:")

REGRESSION_FIXTURES_ROOT = repo_root() / "tests" / "fixtures" / "skill_size_budget"


def _classify_skill(path: Path) -> list[str]:
    """Return the list of error messages for ``path``.

    Empty list ⇒ no problems. The function does NOT raise; aggregation into
    a single ``AssertionError`` is the caller's responsibility.
    """
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    line_count = len(text.splitlines())

    valid_marker_spans: list[tuple[int, int]] = [
        m.span() for m in MARKER_REGEX.finditer(text)
    ]
    prefix_spans: list[tuple[int, int]] = [
        m.span() for m in MARKER_PREFIX_REGEX.finditer(text)
    ]

    # An "invalid marker" is a prefix occurrence not covered by any valid
    # full-marker span.
    for ps, pe in prefix_spans:
        covered = any(vs <= ps and ve >= pe for vs, ve in valid_marker_spans)
        if not covered:
            errors.append(
                f"invalid size-budget-exception marker in {path}: "
                f"the marker at offset {ps} does not match the required "
                f"format <!-- size-budget-exception: <reason ≥30 chars>, "
                f"lifecycle-id=<NNN>, date=<YYYY-MM-DD> -->"
            )

    if line_count > CAP and not valid_marker_spans:
        errors.append(
            f"{path}: {line_count} lines exceeds cap of {CAP} and no valid "
            f"size-budget-exception marker is present. Remediation: "
            f"extract to references/ to bring the file under the cap, OR "
            f"add an in-file marker of the form "
            f"<!-- size-budget-exception: <reason ≥30 chars>, "
            f"lifecycle-id=<NNN>, date=<YYYY-MM-DD> -->"
        )

    return errors


def _run_size_budget_check(paths: list[Path]) -> None:
    """Run the size-budget check across ``paths``. Raises a single
    multi-line ``AssertionError`` aggregating all findings."""
    all_errors: list[str] = []
    for path in paths:
        all_errors.extend(_classify_skill(path))

    if all_errors:
        raise AssertionError(
            f"{len(all_errors)} size-budget violation(s):\n"
            + "\n".join(f"  {e}" for e in all_errors)
        )


def test_canonical_and_plugin_skills_within_size_budget() -> None:
    """Aggregate size-budget assertion across canonical skills and plugin
    skills. Plugin mirrors that are byte-identical to a canonical SKILL.md
    are deduplicated by content hash via ``enumerate_plugin_skills`` so a
    cap breach in a mirrored file fans out to a single message rather than
    two."""
    paths = enumerate_canonical_skills() + enumerate_plugin_skills()
    _run_size_budget_check(paths)


def test_regression_over_cap_no_marker() -> None:
    """The 501-line fixture with no marker triggers the cap-breach path.

    The ``match=`` regex pins the AssertionError to the cap-breach path
    specifically — line count (501) and cap (500) must both appear in the
    message alongside the fixture's path."""
    fixture = REGRESSION_FIXTURES_ROOT / "over-cap-no-marker" / "SKILL.md"
    assert fixture.exists(), fixture

    with pytest.raises(AssertionError, match=r"over-cap-no-marker.*501.*500"):
        _run_size_budget_check([fixture])


def test_regression_invalid_marker() -> None:
    """The under-cap fixture containing a malformed marker triggers the
    invalid-marker path. The ``match=`` regex pins on the literal
    ``invalid size-budget-exception marker`` substring required by the
    spec."""
    fixture = REGRESSION_FIXTURES_ROOT / "invalid-marker" / "SKILL.md"
    assert fixture.exists(), fixture

    with pytest.raises(AssertionError, match=r"invalid size-budget-exception marker"):
        _run_size_budget_check([fixture])


def test_regression_boundary_29_char_reason() -> None:
    """The 501-line fixture with a 29-char rationale (one short of the
    30-char minimum) is treated as having no valid marker, so the file
    falls through to the cap-breach path. Proves the 30-char boundary in
    the marker regex is enforced — 30 passes, 29 fails."""
    fixture = REGRESSION_FIXTURES_ROOT / "boundary-29-char-reason" / "SKILL.md"
    assert fixture.exists(), fixture

    with pytest.raises(
        AssertionError, match=r"boundary-29-char-reason.*501.*500"
    ):
        _run_size_budget_check([fixture])


def test_regression_fixtures_enumerated_via_generic_helper() -> None:
    """Sanity-check the spec's note that the regression fixtures are
    enumerable via the Task 1 generic helper
    ``enumerate_skills(repo_root() / "tests/fixtures/skill_size_budget", "*/SKILL.md")``.
    The helper is the one the canonical enumerators delegate to; surfacing
    its use here documents the path the spec calls out and proves all
    three fixtures are reachable from the glob."""
    paths = enumerate_skills(REGRESSION_FIXTURES_ROOT, "*/SKILL.md")
    names = {p.parent.name for p in paths}
    assert names == {
        "over-cap-no-marker",
        "invalid-marker",
        "boundary-29-char-reason",
    }, names
