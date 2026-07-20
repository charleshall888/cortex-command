"""Wiring + content guard for the competing-plans lazy-reference extraction (#341).

Pins the *static* wiring of the §1b "Competing Plans (Critical Only)" extraction
so it cannot silently regress after the one-shot grep acceptances vanish. Follows
the ``tests/test_post_refine_commit_wired.py`` precedent (file+mirror existence,
consumer-references-target, SKILL.md mention, content token), and additionally
guards the load-bearing §1a Read directive as a *distinct* line: a revert of §1a
back to "proceed to §1b" — which would drop the only routing wire that makes the
critical arm fetch ``competing-plans.md`` — fails CI here even though the §1b stub
pointer still names the target.

Deliberately OUT OF SCOPE (so this gate is honest rather than self-sealing): the
*runtime* cold-read under-trigger — whether the model actually obeys the §1a
directive at plan time — is untestable in a static check and is not asserted.
"""

from __future__ import annotations

import pathlib


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def _plan_lines() -> list[str]:
    plan = _repo_root() / "skills" / "lifecycle" / "references" / "plan.md"
    return plan.read_text(encoding="utf-8").splitlines()


def test_competing_plans_reference_and_mirror_exist() -> None:
    root = _repo_root()
    canonical = root / "skills" / "lifecycle" / "references" / "competing-plans.md"
    assert canonical.exists(), f"competing-plans.md missing at {canonical}"
    mirror = (
        root
        / "plugins"
        / "cortex-core"
        / "skills"
        / "lifecycle"
        / "references"
        / "competing-plans.md"
    )
    assert mirror.exists(), f"plugin-tree mirror missing at {mirror}"


def test_plan_md_carries_the_1a_read_directive() -> None:
    """plan.md's §1a critical branch must carry the load-bearing Read directive.

    Assert a *single* line contains all of: the criticality-``critical``
    condition, a read/follow verb, and the ``competing-plans`` target. The §1b
    stub pointer names the target but has no read verb and no ``critical``
    condition, so it cannot satisfy this — a revert of §1a to "proceed to §1b"
    (dropping the only routing wire) fails here even though the stub survives.
    """
    lines = _plan_lines()
    directive_lines = [
        i
        for i, line in enumerate(lines)
        if all(tok in line.lower() for tok in ("critical", "read", "competing-plans"))
    ]
    assert directive_lines, (
        "plan.md §1a critical branch must carry a single line naming the "
        "competing-plans target with a read/follow directive (all of 'critical' "
        "+ 'read' + 'competing-plans' on one line) — the load-bearing routing "
        "wire, not satisfiable by the §1b stub pointer alone"
    )


def test_plan_md_1b_stub_names_target() -> None:
    """The kept ### 1b. heading must be followed by a pointer to the target."""
    lines = _plan_lines()
    heading_idx = [
        i
        for i, line in enumerate(lines)
        if line.strip() == "### 1b. Competing Plans (Critical Only)"
    ]
    assert heading_idx, "plan.md must keep the ### 1b. heading as the stub anchor"
    h = heading_idx[0]
    window = lines[h : h + 6]
    assert any("competing-plans" in line for line in window), (
        "the ### 1b. stub must name the competing-plans target within a few "
        "lines of the heading"
    )


def test_competing_plans_contains_key_content_token() -> None:
    """The synthesizer-dispatch step is the reference's load-bearing core.

    (The former token was the ``plan_comparison`` event schema; #398 deleted
    that event — zero production readers — so the pin moved to the synthesizer
    fragment path, which the extraction flow cannot function without.)
    """
    canonical = (
        _repo_root() / "skills" / "lifecycle" / "references" / "competing-plans.md"
    )
    text = canonical.read_text(encoding="utf-8")
    assert "plan-synthesizer.md" in text, (
        "competing-plans.md must name the canonical plan-synthesizer prompt "
        "fragment its synthesizer dispatch loads"
    )
    assert "plan_comparison" not in text, (
        "the plan_comparison event was deleted in #398 (zero production "
        "readers); its emission must not reappear in competing-plans.md"
    )
