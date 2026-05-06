"""Test #1 (skill-design test infrastructure, ticket #181): trigger-phrase
substring presence in canonical SKILL.md descriptions.

Walks the canonical-skill enumerator from ``tests/conftest.py`` and the
trigger-phrase corpus at ``tests/fixtures/skill_trigger_phrases.yaml``,
parametrizes over each ``(skill, phrase)`` pair, and asserts each phrase
appears as a case-sensitive substring in the corresponding canonical
``skills/<skill>/SKILL.md`` ``description`` frontmatter field.

The aggregate test runs the substring check across every ``(skill, phrase)``
pair and emits a single multi-line ``AssertionError`` naming each missing
``(skill, phrase)`` (per ``tests/test_lifecycle_references_resolve.py`` and
``tests/test_check_parity.py`` precedent — no fail-fast).

A regression-fixture variant runs the same assertion logic over a synthetic
SKILL.md at ``tests/fixtures/skill_design/skills/regression-fixture/SKILL.md``
paired with ``tests/fixtures/skill_design/regression_skill_trigger_phrases.yaml``.
The fixture YAML declares a phrase deliberately absent from the fixture
SKILL.md description so ``pytest.raises(AssertionError, match=...)`` proves
the failure-detection path runs (the ``match=`` regex is non-negotiable —
without it the assertion would catch any AssertionError tautologically).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import (
    enumerate_canonical_skills,
    parse_skill_frontmatter,
    repo_root,
)


CANONICAL_FIXTURE = repo_root() / "tests" / "fixtures" / "skill_trigger_phrases.yaml"
REGRESSION_SKILL = (
    repo_root()
    / "tests"
    / "fixtures"
    / "skill_design"
    / "skills"
    / "regression-fixture"
    / "SKILL.md"
)
REGRESSION_FIXTURE_YAML = (
    repo_root()
    / "tests"
    / "fixtures"
    / "skill_design"
    / "regression_skill_trigger_phrases.yaml"
)


def _load_fixture(path: Path) -> dict:
    """Load a trigger-phrase fixture YAML or fail with the offending path."""
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AssertionError(f"failed to parse fixture {path}: {exc}") from exc


def _canonical_descriptions() -> dict[str, str]:
    """Map each canonical skill name to its parsed description string."""
    descriptions: dict[str, str] = {}
    for skill_path in enumerate_canonical_skills():
        skill_name = skill_path.parent.name
        frontmatter = parse_skill_frontmatter(skill_path)
        descriptions[skill_name] = frontmatter.get("description", "") or ""
    return descriptions


def test_canonical_skill_descriptions_contain_trigger_phrases() -> None:
    """Aggregate substring assertion across every ``(skill, phrase)`` pair.

    Aggregates findings into a single multi-line ``AssertionError`` per the
    spec's "no fail-fast" convention. The error message names each missing
    ``(skill, phrase)`` so the operator can identify the regressed skill
    and which phrase was dropped.
    """
    fixture = _load_fixture(CANONICAL_FIXTURE)
    descriptions = _canonical_descriptions()

    missing: list[tuple[str, str]] = []
    for skill_name, data in fixture["skills"].items():
        if skill_name not in descriptions:
            missing.append((skill_name, "<skill not found in canonical enumerator>"))
            continue
        desc = descriptions[skill_name]
        for phrase in data["must_contain"]:
            if phrase not in desc:
                missing.append((skill_name, phrase))

    if missing:
        lines = [f"  {skill}: missing phrase {phrase!r}" for skill, phrase in missing]
        raise AssertionError(
            f"{len(missing)} trigger-phrase(s) missing from canonical "
            f"SKILL.md description(s):\n" + "\n".join(lines)
        )


def _assert_phrases_in_description(
    skill_name: str, description: str, phrases: list[str]
) -> None:
    """Apply the substring check used by both the canonical and regression
    paths. Raises a single multi-line ``AssertionError`` naming each
    ``(skill, phrase)`` miss."""
    missing = [p for p in phrases if p not in description]
    if missing:
        lines = [f"  {skill_name}: missing phrase {p!r}" for p in missing]
        raise AssertionError(
            f"{len(missing)} trigger-phrase(s) missing from "
            f"{skill_name} SKILL.md description:\n" + "\n".join(lines)
        )


def test_regression_fixture_detects_missing_phrase() -> None:
    """Regression-fixture variant: the fixture YAML declares a phrase
    deliberately absent from the fixture SKILL.md description. The
    ``match=`` regex pins the failure to the missing-phrase detection
    path, not an unrelated AssertionError elsewhere."""
    fixture = _load_fixture(REGRESSION_FIXTURE_YAML)
    text = REGRESSION_SKILL.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise AssertionError(
            f"regression fixture {REGRESSION_SKILL} missing frontmatter"
        )
    frontmatter = yaml.safe_load(parts[1])
    description = frontmatter.get("description", "") or ""

    skill_name = "regression-fixture"
    phrases = fixture["skills"][skill_name]["must_contain"]

    with pytest.raises(AssertionError, match=r"fixture missing phrase"):
        _assert_phrases_in_description(skill_name, description, phrases)
