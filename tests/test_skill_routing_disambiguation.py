"""Test #4 (R9 routing-precision non-regression, ticket
reduce-boot-context-surface-claudemd-skillmd Task 4): trigger-phrase substring
presence across the concatenated ``description:`` + ``when_to_use:`` routing
surface for the routing-pressure-cluster skills, plus path-token routing
assertions for the lifecycle skill.

Where ``tests/test_skill_descriptions.py`` enforces phrase presence against
``description`` alone, this module enforces presence against the concatenated
``description:`` + ``when_to_use:`` text because Claude Code's L1 listing
concatenates the two fields — both surfaces are load-bearing for routing.

Two test functions:

1. ``test_routing_cluster_phrases_in_description_or_when_to_use``
   — parametrized over ``(skill, phrase)`` for the routing-pressure cluster
   (``dev``, ``lifecycle``, ``refine``, ``research``, ``discovery``,
   ``critical-review``). Asserts each ``must_contain`` phrase appears as a
   case-sensitive substring of the skill's concatenated frontmatter.

2. ``test_lifecycle_skill_frontmatter_contains_path_tokens``
   — asserts each token in the lifecycle entry's ``must_contain_paths`` key
   appears as a case-sensitive substring of the concatenated frontmatter of
   ``skills/lifecycle/SKILL.md``. The ``must_contain_paths`` block is fixture
   data only; the assertion is separate from ``must_contain`` because path
   tokens are non-phrase routing data.
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


def test_lifecycle_skill_frontmatter_contains_path_tokens() -> None:
    """The lifecycle skill's concatenated ``description`` + ``when_to_use``
    frontmatter must contain every path token listed under the fixture's
    lifecycle ``must_contain_paths`` key. Path tokens are non-phrase routing
    data (canonical-source paths that mandate lifecycle entry) and are
    enforced separately from the phrase-token regression gate."""
    fixture = _load_fixture()
    lifecycle_entry = fixture["skills"]["lifecycle"]
    assert "must_contain_paths" in lifecycle_entry, (
        "lifecycle fixture entry missing must_contain_paths key — "
        "path-routing assertions cannot run"
    )
    path_tokens = lifecycle_entry["must_contain_paths"]

    text = _concatenated_routing_text()["lifecycle"]

    missing = [token for token in path_tokens if token not in text]
    if missing:
        lines = [f"  lifecycle: missing path token {token!r}" for token in missing]
        raise AssertionError(
            f"{len(missing)} path token(s) missing from lifecycle SKILL.md "
            f"concatenated description+when_to_use routing surface:\n"
            + "\n".join(lines)
        )
