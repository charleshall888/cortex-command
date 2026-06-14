"""L1 surface ratchet — deliberate per-skill frontmatter byte budgets.

Each skill's L1 surface (the ``description`` + ``when_to_use`` frontmatter
loaded into every session's system prompt) is bounded by a **deliberate
per-skill byte budget** declared in ``_BASELINES`` below. These are no longer
a frozen snapshot: the values are the cap policy for ``cortex/backlog/298-
l1-frontmatter-cap-policy-for-new-skills-research-description-overage.md``.

Ratchet direction: equal-or-lower passes; any skill that EXCEEDS its budget
fails. When this test fails, reduce the offending skill's frontmatter until
it is at or below its budget rather than raising the budget here.

Two structural gates accompany the per-skill comparison:
- ``test_budget_rows_complete`` asserts every canonical skill under ``skills/``
  has a budget row (a new skill with no row fails), drawn from the same
  enumeration the budgets are validated against.
- ``test_non_cluster_budgets_within_default`` asserts every non-cluster skill's
  budget is <= 400 bytes (the cap-policy default). The routing-pressure cluster
  (``ROUTING_PRESSURE_CLUSTER``, the single source of truth imported from
  ``test_skill_routing_disambiguation``) is the only exemption surface.

Provenance correction (298): ``research`` was itself post-#191 regrowth — its
L1 surface had grown +124B (378 -> 502) after the harness-token-efficiency-trim
snapshot, correcting the 298 ticket body's claim that the original 13 skills
did not regrow. Ticket 302 has since reverted that regrowth: ``research`` is now
at its post-revert cluster budget of 379 (the #191 close-state, plus 1B for the
corrected 3-10 agent count).

Spec: cortex/lifecycle/l1-frontmatter-cap-policy-for-new/spec.md R1, R5.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conftest import enumerate_canonical_skills
from test_skill_routing_disambiguation import ROUTING_PRESSURE_CLUSTER


REPO_ROOT = Path(__file__).resolve().parent.parent
UTILITY = REPO_ROOT / "bin" / "cortex-measure-l1-surface"

# Deliberate per-skill byte budgets (the 298 cap policy) — NOT a frozen
# snapshot. Do NOT raise a value without a documented justification and a
# lifecycle-id'd re-cap rationale (see cortex/requirements/project.md, the
# "SKILL.md L1 surface ratchet" constraint). When a skill exceeds its budget,
# reduce its frontmatter rather than bumping the number here.
# Cap-policy lifecycle: cortex/backlog/298-l1-frontmatter-cap-policy-for-new-
# skills-research-description-overage.md
_BASELINES: dict[str, int] = {
    "backlog": 319,
    "backlog-author": 288,
    "commit": 208,
    "critical-review": 795,
    "dev": 285,
    "diagnose": 294,
    "discovery": 932,
    "interview": 361,
    "lifecycle": 890,
    "morning-review": 320,
    "overnight": 314,
    "pr": 237,
    "refine": 644,
    "requirements": 231,
    "requirements-gather": 347,
    "requirements-write": 353,
    "research": 379,
    "total": 7197,
}


def _utility_rows() -> dict[str, int]:
    """Run the utility and parse stdout into ``{skill_name: bytes}``."""
    proc = subprocess.run(
        [str(UTILITY)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    out: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        name, count = parts
        out[name] = int(count)
    return out


# Parametrize one case per skill plus the total row.
_RATCHET_CASES = sorted(_BASELINES.keys())


@pytest.fixture(scope="module")
def utility_rows() -> dict[str, int]:
    """Run the utility once per module and share the result across all cases."""
    return _utility_rows()


def test_budget_rows_complete(utility_rows: dict[str, int]) -> None:
    """Every canonical skill must have a deliberate budget row.

    Set-equality between the budget dict and the SAME enumeration the
    per-skill budgets are validated against (the measure utility's rows), so a
    new skill with no row AND a stale row both fail at add time. A corroborating
    check ties the conftest canonical enumerator to the utility so the two
    directory walks cannot silently diverge (e.g. a dangling ``SKILL.md``
    symlink the glob yields but the utility's ``is_file()`` skips).
    """
    measured = set(utility_rows) - {"total"}
    budgeted = set(_BASELINES) - {"total"}
    assert measured == budgeted, (
        "L1 budget rows out of sync with measured skills: "
        f"skills missing a budget row: {sorted(measured - budgeted)}; "
        f"stale budget rows (no such skill): {sorted(budgeted - measured)}. "
        "Add a deliberate budget row for each new skill (cap policy 298)."
    )
    canonical = {p.parent.name for p in enumerate_canonical_skills()}
    assert canonical == measured, (
        "canonical skill enumerator disagrees with the measure utility: "
        f"glob-only (utility skipped): {sorted(canonical - measured)}; "
        f"utility-only (glob skipped): {sorted(measured - canonical)}. "
        "Check for a dangling SKILL.md symlink or a non-skill directory under skills/."
    )


def test_non_cluster_budgets_within_default() -> None:
    """Every non-cluster skill's deliberate budget is <= 400 bytes.

    This is the cap-policy default (298): a new non-cluster skill shipping
    >400B fails here at add time. The routing-pressure cluster — sourced from
    ``ROUTING_PRESSURE_CLUSTER`` (the single source of truth in
    ``test_skill_routing_disambiguation``) — is the only exemption surface; its
    skills carry irreducible disambiguation/path-routing tokens and are bounded
    by their own higher budget rows. Promoting a skill into the cluster is a
    reviewed allowlist edit, not a self-granted per-skill pass (see
    cortex/requirements/project.md, "SKILL.md L1 surface ratchet").
    """
    # Subtractive-set guard: the non-cluster set is defined by subtracting the
    # cluster from the budget keys, so every cluster name must itself be a
    # budget row — otherwise a stray/renamed cluster name would silently shrink
    # the enforced non-cluster set instead of failing loudly.
    cluster = set(ROUTING_PRESSURE_CLUSTER)
    missing = cluster - set(_BASELINES)
    assert not missing, (
        f"routing-pressure cluster names with no budget row: {sorted(missing)}. "
        "Add a budget row for each, or fix ROUTING_PRESSURE_CLUSTER."
    )
    non_cluster = set(_BASELINES) - cluster - {"total"}
    over = {name: _BASELINES[name] for name in sorted(non_cluster) if _BASELINES[name] > 400}
    assert not over, (
        f"non-cluster skills over the 400B default budget: {over}. "
        "Trim the frontmatter to <=400B, or promote the skill into the "
        "routing-pressure cluster via a reviewed allowlist edit (cap policy 298)."
    )


@pytest.mark.parametrize("name", _RATCHET_CASES)
def test_l1_surface_within_baseline(name: str, utility_rows: dict[str, int]) -> None:
    """Each skill's L1 surface must be at or below its deliberate budget.

    Failure means frontmatter has grown above the budget. Reduce the
    description/when_to_use text rather than raising the budget here. Raising a
    budget requires a documented justification and lifecycle-id'd re-cap per the
    cap policy (cortex/requirements/project.md, "SKILL.md L1 surface ratchet").
    Cap-policy backlog: cortex/backlog/298-l1-frontmatter-cap-policy-for-new-
    skills-research-description-overage.md
    """
    assert name in utility_rows, (
        f"utility output missing row for {name!r}; known rows: {sorted(utility_rows)}"
    )
    actual = utility_rows[name]
    baseline = _BASELINES[name]
    assert actual <= baseline, (
        f"L1 surface ratchet breach for {name!r}: "
        f"actual={actual} bytes > budget={baseline} bytes "
        f"(delta=+{actual - baseline}). "
        "Reduce frontmatter description/when_to_use rather than raising the budget. "
        "Cap-policy backlog: cortex/backlog/298-l1-frontmatter-cap-policy-for-new-"
        "skills-research-description-overage.md"
    )
