"""Test #4 (R9 routing-precision non-regression, ticket
reduce-boot-context-surface-claudemd-skillmd Task 4): trigger-phrase substring
presence across the concatenated ``description:`` + ``when_to_use:`` routing
surface for the routing-pressure-cluster skills.

Where ``tests/test_skill_descriptions.py`` enforces phrase presence against
``description`` alone, this module enforces presence against the concatenated
``description:`` + ``when_to_use:`` text because Claude Code's L1 listing
concatenates the two fields — both surfaces are load-bearing for routing.

``test_routing_cluster_phrases_in_description_or_when_to_use`` is parametrized
over ``(skill, phrase)`` for the routing-pressure cluster (``dev``,
``lifecycle``, ``refine``, ``research``, ``discovery``, ``critical-review``)
and asserts each ``must_contain`` phrase appears as a case-sensitive substring
of the skill's concatenated frontmatter.

(The former path-token assertion for the lifecycle skill was retired when the
cortex-command-specific protected-path routing moved out of the shipped skill
description into this repo's CLAUDE.md — the shipped skill is repo-agnostic.)
"""

from __future__ import annotations

import pytest
import yaml

from conftest import (
    enumerate_canonical_skills,
    parse_skill_frontmatter,
    repo_root,
)


CANONICAL_FIXTURE = repo_root() / "tests" / "fixtures" / "skill_trigger_phrases.yaml"

# The routing-pressure cluster — skills that compete on overlapping user
# utterances and therefore need disambiguation-grade routing precision.
ROUTING_PRESSURE_CLUSTER = (
    "dev",
    "lifecycle",
    "refine",
    "research",
    "discovery",
    "critical-review",
)


def _load_fixture() -> dict:
    """Load the canonical trigger-phrase fixture."""
    return yaml.safe_load(CANONICAL_FIXTURE.read_text(encoding="utf-8"))


def _concatenated_routing_text() -> dict[str, str]:
    """Map each canonical skill name to its concatenated ``description`` +
    ``when_to_use`` frontmatter text. Both fields are L1 routing surface
    because Claude Code's skill listing concatenates them — phrase presence
    in either suffices to support routing."""
    texts: dict[str, str] = {}
    for skill_path in enumerate_canonical_skills():
        skill_name = skill_path.parent.name
        frontmatter = parse_skill_frontmatter(skill_path)
        description = frontmatter.get("description", "") or ""
        when_to_use = frontmatter.get("when_to_use", "") or ""
        texts[skill_name] = f"{description}\n{when_to_use}"
    return texts


def _cluster_pairs() -> list[tuple[str, str]]:
    """Build the parametrize corpus: (skill, phrase) for each phrase listed
    under each routing-pressure-cluster skill's ``must_contain`` array."""
    fixture = _load_fixture()
    pairs: list[tuple[str, str]] = []
    for skill_name in ROUTING_PRESSURE_CLUSTER:
        entry = fixture["skills"].get(skill_name)
        if entry is None:
            # Surface as a parametrize entry that will fail loudly rather
            # than silently dropping coverage.
            pairs.append((skill_name, "<skill missing from fixture>"))
            continue
        for phrase in entry.get("must_contain", []):
            pairs.append((skill_name, phrase))
    return pairs


@pytest.mark.parametrize(("skill", "phrase"), _cluster_pairs())
def test_routing_cluster_phrases_in_description_or_when_to_use(
    skill: str, phrase: str
) -> None:
    """Each routing-pressure-cluster phrase must appear as a case-sensitive
    substring of the concatenated ``description:`` + ``when_to_use:`` text
    of the corresponding canonical SKILL.md."""
    texts = _concatenated_routing_text()
    assert skill in texts, (
        f"routing-cluster skill {skill!r} not found in canonical enumerator"
    )
    text = texts[skill]
    assert phrase in text, (
        f"phrase {phrase!r} missing from {skill} SKILL.md concatenated "
        f"description+when_to_use routing surface"
    )
