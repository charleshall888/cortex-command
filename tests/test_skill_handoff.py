"""Test #2 (skill-design test infrastructure, ticket #181): cross-skill
handoff field-name presence in canonical SKILL.md and references/*.md prose.

Walks the canonical-skill enumerator from ``tests/conftest.py`` and the
handoff-schema corpus at ``tests/fixtures/skill_handoff_schema.yaml``,
parametrizes over each ``(field, skill)`` pair (one per producer plus one
per consumer per field), and asserts the literal field-name token appears
at least once in ``skills/<skill>/SKILL.md`` OR in any
``skills/<skill>/references/*.md``. Substring search is plain
case-sensitive — no regex.

Scope and limitations (the four phrases below are grep-checked verbatim by
the spec's verification step; do not edit them):

Bounded scope (verbatim policy phrases — do not edit):

(a) This test does NOT catch semantic drift — it catches field-name presence/rename only. If both producer and consumer rename a field together, or if the value-shape contract drifts while names stay stable, the test passes silently.

(b) Do not expand fixture YAML to encode value-shape rules. The fixture is intentionally minimal (name + producer + consumers); encoding value-shape rules would re-introduce the 3-way drift trap (test/fixture/code) the spec excluded.

(c) Scope limited to SKILL.md-prose-mediated handoff fields with no Python-test coverage — currently the compound token discovery_source. Substring presence in SKILL.md / references prose reliably reflects the contract for these compound tokens.

(d) Python-mediated handoff fields (e.g., lifecycle_slug, complexity, criticality, areas read by cortex_command/) are out of scope for this test — coverage relies on existing Python tests. Renames of those fields break loudly via Python attribute-access errors in suites such as tests/test_select_overnight_batch.py.

A regression-fixture variant runs the same name-presence logic over a
synthetic schema/SKILL.md pair under
``tests/fixtures/skill_design/handoff_rename/`` where the fixture
consumer omits the declared field name. ``pytest.raises(AssertionError,
match=<field-name>)`` pins the failure to the missing-field-name
detection path, not an unrelated YAML-parse or path-resolution bug.

Path-traversal safety note: the canonical test reads only fixed
``skills/<name>/SKILL.md`` and ``skills/<name>/references/*.md`` glob
results — no path is constructed from fixture content. The regression
fixture enumerates its own subtree using a fixed path. Path-traversal
safety check is trivially satisfied.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import repo_root


CANONICAL_FIXTURE = repo_root() / "tests" / "fixtures" / "skill_handoff_schema.yaml"
REGRESSION_FIXTURE_YAML = (
    repo_root()
    / "tests"
    / "fixtures"
    / "skill_design"
    / "handoff_rename"
    / "skill_handoff_schema.yaml"
)
REGRESSION_FIXTURE_SKILLS_ROOT = (
    repo_root()
    / "tests"
    / "fixtures"
    / "skill_design"
    / "handoff_rename"
    / "skills"
)


def _load_fixture(path: Path) -> dict:
    """Load a handoff-schema fixture YAML or fail with the offending path."""
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AssertionError(f"failed to parse fixture {path}: {exc}") from exc


def _iter_field_skill_pairs(fixture: dict) -> list[tuple[str, str]]:
    """Yield each ``(field_name, skill_name)`` pair for a producer plus
    each of its consumers, derived from the handoff-schema fixture."""
    pairs: list[tuple[str, str]] = []
    for entry in fixture["handoff_fields"]:
        field = entry["name"]
        pairs.append((field, entry["producer"]))
        for consumer in entry["consumers"]:
            pairs.append((field, consumer))
    return pairs


def _field_present_in_skill(field: str, skills_root: Path, skill: str) -> bool:
    """Return True if the literal ``field`` token appears in
    ``<skills_root>/<skill>/SKILL.md`` OR any
    ``<skills_root>/<skill>/references/*.md``. Plain case-sensitive
    substring search."""
    skill_dir = skills_root / skill
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists() and field in skill_md.read_text(encoding="utf-8"):
        return True
    references_dir = skill_dir / "references"
    if references_dir.exists():
        for ref in references_dir.glob("*.md"):
            if field in ref.read_text(encoding="utf-8"):
                return True
    return False


def _check_pairs(
    pairs: list[tuple[str, str]], skills_root: Path
) -> list[tuple[str, str]]:
    """Return the list of ``(field, skill)`` pairs that fail the
    name-presence check."""
    missing: list[tuple[str, str]] = []
    for field, skill in pairs:
        if not _field_present_in_skill(field, skills_root, skill):
            missing.append((field, skill))
    return missing


def test_canonical_skill_handoff_fields_present() -> None:
    """Aggregate name-presence assertion across every ``(field, skill)``
    pair derived from ``skill_handoff_schema.yaml``.

    Aggregates findings into a single multi-line ``AssertionError`` per
    the spec's "no fail-fast" convention. The error message names both
    the field and the consumer-skill that's missing it.
    """
    fixture = _load_fixture(CANONICAL_FIXTURE)
    pairs = _iter_field_skill_pairs(fixture)
    skills_root = repo_root() / "skills"

    missing = _check_pairs(pairs, skills_root)
    if missing:
        lines = [
            f"  field {field!r} missing from skill {skill!r} "
            f"(SKILL.md and references/*.md)"
            for field, skill in missing
        ]
        raise AssertionError(
            f"{len(missing)} handoff field(s) missing from canonical "
            f"skill prose:\n" + "\n".join(lines)
        )


def _assert_pairs_present(pairs: list[tuple[str, str]], skills_root: Path) -> None:
    """Apply the name-presence check used by both canonical and
    regression paths. Raises a single multi-line ``AssertionError``
    naming each missing ``(field, skill)``."""
    missing = _check_pairs(pairs, skills_root)
    if missing:
        lines = [
            f"  field {field!r} missing from skill {skill!r}"
            for field, skill in missing
        ]
        raise AssertionError(
            f"{len(missing)} handoff field(s) missing:\n" + "\n".join(lines)
        )


def test_regression_fixture_detects_renamed_field() -> None:
    """Regression-fixture variant: the fixture YAML declares a field
    deliberately absent from the fixture consumer's SKILL.md. The
    ``match=`` regex pins the failure to the missing-field-name
    detection path, not an unrelated YAML-parse or path-resolution
    bug."""
    fixture = _load_fixture(REGRESSION_FIXTURE_YAML)
    pairs = _iter_field_skill_pairs(fixture)
    # Only run the consumer-side check (the producer fixture skill is
    # not authored — the consumer omission is the regression we exercise).
    consumer_pairs = [
        (field, skill)
        for field, skill in pairs
        if skill == "consumer-fixture"
    ]

    with pytest.raises(AssertionError, match=r"synthetic_renamed_field"):
        _assert_pairs_present(consumer_pairs, REGRESSION_FIXTURE_SKILLS_ROOT)
