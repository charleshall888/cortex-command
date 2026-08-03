"""Behavioral tests for :func:`cortex_command.backlog.triage.render`.

``render()`` composes the two-block triage board ``/cortex-core:dev`` Step 3
prints, and until this module it had no behavioral coverage at all. The tests
here pin the rendered lines exactly (not by substring) so the recommendation
syntax itself is part of the contract, and they enforce the boundary ticket
#343 installs: recommendation logic lives in ``_recommendation()`` inside the
verb, never inline in either block's renderer.

``epic_map`` is always built by calling the real
:func:`cortex_command.backlog.build_epic_map.build_epic_map`. Hand-writing a
child envelope would defeat the point: the real builder emits only
``id``/``spec``/``status``/``title`` (``build_epic_map.py:158-163``), so the
epic block can only learn a child's ``type`` by threading ``by_id`` correctly.
A fixture that hand-added ``type`` would let a broken ``_resolve_child()`` pass.
"""

from __future__ import annotations

import inspect
import re

import pytest

from cortex_command.backlog.build_epic_map import build_epic_map
from cortex_command.backlog.triage import _render_epic_block, render


# ---------------------------------------------------------------------------
# Minimal item-record factory
# ---------------------------------------------------------------------------

def _item(**kwargs) -> dict:
    """Return one backlog item record, defaults overridden by ``kwargs``.

    Keys mirror exactly what ``render()`` and its callees read: ``id``,
    ``title``, ``status``, ``priority``, ``type``, ``spec``, ``parent``,
    ``blocked_by``, ``tags``, ``uuid``. Local factory per the convention at
    ``tests/test_backlog_readiness.py:29`` — there is no shared conftest
    builder.
    """
    defaults: dict = {
        "id": 1,
        "title": "Default Item",
        "status": "backlog",
        "priority": "medium",
        "type": "feature",
        "spec": None,
        "parent": None,
        "blocked_by": [],
        "tags": [],
        "uuid": None,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Recommendation extraction — by regex on rendered text, keyed on item id.
# Never recompute via _is_refined/_recommendation: doing so would make the
# cross-block guard compare a function against itself.
# ---------------------------------------------------------------------------

def _epic_child_recommendation(blocks: str, item_id: int) -> str:
    """Return the recommendation marks on the epic-block child row for *item_id*."""
    matches = re.findall(
        rf"^- \*\*{item_id}\*\* .+? — \S+ (.+)$", blocks, re.MULTILINE
    )
    assert len(matches) == 1, (
        f"expected exactly one epic-child row for {item_id}, got {matches!r}"
    )
    return matches[0]


def _ready_row_recommendation(blocks: str, item_id: int) -> str:
    """Return the recommendation on the ``## Ready`` row for *item_id*."""
    matches = re.findall(
        rf"^- `[^`]*` `[^`]*` \*\*{item_id}\*\* .+? → (.+)$", blocks, re.MULTILINE
    )
    assert len(matches) == 1, (
        f"expected exactly one Ready row for {item_id}, got {matches!r}"
    )
    return matches[0]


def _guard_fixture(item_type: str) -> tuple[dict, list[dict]]:
    """Return ``(child_item, items)`` for the cross-block guard.

    The child is individually ready (``status: refined``) and carries a
    ``spec:``, and the parent epic is ready too, so the same record is
    renderable in both blocks. Restricted to the ready subset deliberately:
    the epic block renders every child regardless of status, while ``## Ready``
    holds only ``_ready_set()`` survivors.
    """
    epic = _item(
        id=7000,
        title="Guard epic",
        type="epic",
        status="refined",
        spec="cortex/lifecycle/guard-epic/spec.md",
    )
    child = _item(
        id=7001,
        title="Guarded child",
        type=item_type,
        status="refined",
        spec="cortex/lifecycle/guarded-child/spec.md",
        parent=7000,
    )
    return child, [epic, child]


# ---------------------------------------------------------------------------
# Requirement 3 — the cross-block byte-identity drift guard.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("item_type", ["bug", "chore", "idea", "feature"])
def test_recommendation_is_byte_identical_across_blocks(item_type: str) -> None:
    """The same record must route identically as an epic child and as a Ready row.

    This is the structural enforcement of ticket #343's boundary. If the two
    blocks ever grow independent routing again, exactly one of these four
    parametrized cases starts failing.
    """
    child, items = _guard_fixture(item_type)

    epic_blocks, _ = render(items, build_epic_map(items))
    flat_blocks, _ = render(items, {})

    epic_rec = _epic_child_recommendation(epic_blocks, child["id"])
    flat_rec = _ready_row_recommendation(flat_blocks, child["id"])

    assert epic_rec == flat_rec, (
        f"{item_type}: epic block rendered {epic_rec!r} but Ready rendered "
        f"{flat_rec!r} for the same record"
    )


# ---------------------------------------------------------------------------
# Requirement 2 — the recommendation is one line, and neither renderer
# computes it inline.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_type", ["bug", "chore", "idea", "feature"])
def test_recommendation_never_spans_lines(fixture_type: str) -> None:
    """No rendered recommendation may carry an embedded newline in either block."""
    child, items = _guard_fixture(fixture_type)

    epic_blocks, _ = render(items, build_epic_map(items))
    flat_blocks, _ = render(items, {})

    for rec in (
        _epic_child_recommendation(epic_blocks, child["id"]),
        _ready_row_recommendation(flat_blocks, child["id"]),
    ):
        assert "\n" not in rec
        assert rec == rec.strip()


def test_render_computes_no_recommendation_inline() -> None:
    """``render()`` delegates every route decision to ``_recommendation()``.

    The spec's literal criterion 2(c) is unsatisfiable — ``_render_epic_block``
    legitimately keeps the empty-children ``/cortex-core:discovery`` line and
    the footer's ``/cortex-core:refine`` sentence, both preserved by
    requirement 6 and the Non-Requirements. The tightened check below pins the
    actual claim: no *per-item* recommendation is computed inline.
    """
    render_src = inspect.getsource(render)
    assert "/cortex-core:" not in render_src

    epic_src = inspect.getsource(_render_epic_block)
    assert "/cortex-core:build" not in epic_src
    # Retired type-first marks — they must not come back.
    assert "[refined]" not in epic_src
    assert "[needs " not in epic_src


# ---------------------------------------------------------------------------
# Requirement 8 — exact rendered output for the structural cases.
# ---------------------------------------------------------------------------

def test_ready_epic_renders_all_children_across_types_and_readiness() -> None:
    """A ready epic lists every child, spanning both readiness states and all types."""
    items = [
        _item(id=100, title="Platform epic", type="epic", status="refined",
              priority="high", spec="cortex/lifecycle/platform/spec.md"),
        _item(id=101, title="Fix crash", type="bug", status="refined",
              parent=100, spec="cortex/lifecycle/fix-crash/spec.md"),
        _item(id=102, title="Bump deps", type="chore", status="backlog",
              parent=100),
        _item(id=103, title="Maybe caching", type="idea", status="backlog",
              parent=100),
        _item(id=104, title="New export", type="feature", status="refined",
              parent=100, spec="cortex/lifecycle/new-export/spec.md"),
    ]

    blocks, flat = render(items, build_epic_map(items))

    assert blocks == (
        "## Epics\n"
        "\n"
        "### Epic 100 — Platform epic _(epic, not directly workable)_\n"
        "\n"
        "- **101** Fix crash — refined `/cortex-core:build`\n"
        "- **102** Bump deps — backlog `/cortex-core:refine`\n"
        "- **103** Maybe caching — backlog `/cortex-core:discovery`\n"
        "- **104** New export — refined `/cortex-core:build`\n"
        "\n"
        "Run `/cortex-core:refine` on each unrefined child, one at a time "
        "(each needs interactive spec approval before the next): 102 Bump deps.\n"
    )
    # Children shown in the epic block are not repeated in ## Ready.
    assert flat == []


def test_flat_ready_rows_render_with_and_without_spec() -> None:
    """A flat ready item routes on ``spec:`` presence, in priority order."""
    items = [
        _item(id=201, title="Refined feature", status="refined",
              priority="critical", spec="cortex/lifecycle/refined/spec.md"),
        _item(id=202, title="Unrefined feature", status="backlog",
              priority="low"),
    ]

    blocks, flat = render(items, build_epic_map(items))

    assert blocks == (
        "## Ready\n"
        "\n"
        "- `critical` `feature` **201** Refined feature → `/cortex-core:build`\n"
        "- `low` `feature` **202** Unrefined feature → `/cortex-core:refine`\n"
    )
    assert [i["id"] for i in flat] == [201, 202]


def test_epic_with_no_active_children_recommends_discovery() -> None:
    """Every child held in flight leaves the epic with nothing to recommend."""
    items = [
        _item(id=300, title="Stalled epic", type="epic", status="refined",
              spec="cortex/lifecycle/stalled/spec.md"),
        _item(id=301, title="Work in flight", status="in_progress", parent=300),
    ]

    blocks, flat = render(items, build_epic_map(items))

    assert blocks == (
        "## Epics\n"
        "\n"
        "### Epic 300 — Stalled epic _(epic, not directly workable)_\n"
        "\n"
        "- **301** Work in flight — in_progress `/cortex-core:refine`\n"
        "\n"
        "No active child tickets — consider `/cortex-core:discovery` to "
        "decompose this epic.\n"
    )
    assert flat == []


def test_empty_backlog_renders_the_clear_message() -> None:
    """No ready items at all collapses to the single backlog-is-clear line."""
    blocks, flat = render([], build_epic_map([]))

    assert blocks == (
        "Backlog is clear — no ready items. Check blocked items or create "
        "new ones with `/cortex-backlog:backlog add`.\n"
    )
    assert flat == []


def test_deferred_item_appears_in_neither_block() -> None:
    """A whole-element ``deferred`` tag keeps an otherwise-ready item off the board."""
    items = [
        _item(id=401, title="Parked work", status="backlog", tags=["deferred"]),
        _item(id=402, title="Active item", status="backlog"),
    ]

    blocks, flat = render(items, build_epic_map(items))

    assert blocks == (
        "## Ready\n"
        "\n"
        "- `medium` `feature` **402** Active item → `/cortex-core:refine`\n"
    )
    assert "401" not in blocks
    assert [i["id"] for i in flat] == [402]


# ---------------------------------------------------------------------------
# Requirement 5 — an idea is a readiness statement, spec or no spec.
# ---------------------------------------------------------------------------

def test_idea_routes_to_discovery_with_and_without_spec() -> None:
    """``type: idea`` routes to discovery regardless of ``spec:``.

    ``idea`` is checked ahead of ``spec:`` because an idea has nothing to spec
    yet — a stray ``spec:`` value must not promote it to build.
    """
    items = [
        _item(id=501, title="Idea no spec", type="idea", status="backlog"),
        _item(id=502, title="Idea with spec", type="idea", status="refined",
              spec="cortex/lifecycle/idea-with-spec/spec.md"),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert blocks == (
        "## Ready\n"
        "\n"
        "- `medium` `idea` **501** Idea no spec → `/cortex-core:discovery`\n"
        "- `medium` `idea` **502** Idea with spec → `/cortex-core:discovery`\n"
    )


# ---------------------------------------------------------------------------
# Requirement 6 — the three-way epic footer.
# ---------------------------------------------------------------------------

def test_unrefined_idea_child_licenses_neither_refine_nor_overnight() -> None:
    """An unrefined ``idea`` child is neither refine work nor overnight-ready.

    It must not be listed in the refine sentence (it is unrefinable by design),
    and its presence must withhold the overnight sentence — the epic still has
    undecomposed work in it.
    """
    items = [
        _item(id=600, title="Idea-bearing epic", type="epic", status="refined",
              spec="cortex/lifecycle/idea-bearing/spec.md"),
        _item(id=601, title="Unrefined idea", type="idea", status="backlog",
              parent=600),
        _item(id=602, title="Refined feature", type="feature", status="refined",
              parent=600, spec="cortex/lifecycle/refined-feature/spec.md"),
        _item(id=603, title="Refined bug", type="bug", status="refined",
              parent=600, spec="cortex/lifecycle/refined-bug/spec.md"),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert blocks == (
        "## Epics\n"
        "\n"
        "### Epic 600 — Idea-bearing epic _(epic, not directly workable)_\n"
        "\n"
        "- **601** Unrefined idea — backlog `/cortex-core:discovery`\n"
        "- **602** Refined feature — refined `/cortex-core:build`\n"
        "- **603** Refined bug — refined `/cortex-core:build`\n"
    )
    assert "Run `/cortex-core:refine` on each unrefined child" not in blocks
    assert "/cortex-overnight:overnight" not in blocks


def test_refined_idea_child_also_withholds_the_overnight_sentence() -> None:
    """A *refined* idea withholds the overnight sentence too.

    The exclusion is keyed on the child's type, not on its refinement: an idea
    carrying a `spec:` still renders `/cortex-core:discovery` on its own row
    (requirement 5), and overnight's readiness scan will not honor a discovery
    topic. Partitioning on refinement first dropped such a child out of the idea
    bucket entirely, so an all-refined epic emitted "auto-select them" over a row
    that said discovery — the same contradiction requirement 6 removed for the
    unrefined case.
    """
    items = [
        _item(id=700, title="Refined-idea epic", type="epic", status="refined",
              spec="cortex/lifecycle/refined-idea-epic/spec.md"),
        _item(id=701, title="Refined idea", type="idea", status="refined",
              parent=700, spec="cortex/lifecycle/refined-idea/spec.md"),
        _item(id=702, title="Refined feature", type="feature", status="refined",
              parent=700, spec="cortex/lifecycle/refined-feature/spec.md"),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert blocks == (
        "## Epics\n"
        "\n"
        "### Epic 700 — Refined-idea epic _(epic, not directly workable)_\n"
        "\n"
        "- **701** Refined idea — refined `/cortex-core:discovery`\n"
        "- **702** Refined feature — refined `/cortex-core:build`\n"
    )
    assert "/cortex-overnight:overnight" not in blocks
    # The idea is not refine work either — it must not be listed for refining.
    assert "Run `/cortex-core:refine` on each unrefined child" not in blocks


def test_overnight_sentence_still_fires_with_no_idea_children() -> None:
    """The exclusion is scoped: an all-refined epic of real work still routes.

    Guards against over-correcting requirement 6 into withholding the overnight
    sentence from every epic.
    """
    items = [
        _item(id=800, title="Workable epic", type="epic", status="refined",
              spec="cortex/lifecycle/workable-epic/spec.md"),
        _item(id=801, title="Refined feature", type="feature", status="refined",
              parent=800, spec="cortex/lifecycle/rf/spec.md"),
        _item(id=802, title="Refined bug", type="bug", status="refined",
              parent=800, spec="cortex/lifecycle/rb/spec.md"),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert "Run `/cortex-overnight:overnight`" in blocks


# ---------------------------------------------------------------------------
# Requirement 9 — ticket-425 regression guard.
# ---------------------------------------------------------------------------

def test_refined_chore_routes_to_build_in_ready_block() -> None:
    """A refined ``chore`` must offer build, not the retired type-first hint.

    Regression guard for ticket 425: before the readiness-driven
    ``_recommendation()``, the type-first router sent every ``chore`` down a
    "direct implementation" path no matter how thoroughly it had been specced,
    so a refined chore's spec was silently discarded at triage.
    """
    items = [
        _item(id=425, title="Refined chore", type="chore", status="refined",
              spec="cortex/lifecycle/refined-chore/spec.md"),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert blocks == (
        "## Ready\n"
        "\n"
        "- `medium` `chore` **425** Refined chore → `/cortex-core:build`\n"
    )
    assert "direct implementation" not in blocks


# ---------------------------------------------------------------------------
# Requirement 10 — known hole, pinned rather than fixed.
# ---------------------------------------------------------------------------

def test_ready_child_of_non_ready_epic_disappears_entirely() -> None:
    """PINS A KNOWN BUG, does not assert desired behavior.

    An individually-ready child lands in ``child_ids`` (``triage.py:152-154``)
    and is therefore excluded from ``## Ready``, but its epic is not in the
    ready set, so no epic block is rendered for it (``:161-165``). The child's
    id appears nowhere in the output. Fixing this is a separate ticket; this
    test exists so the fix is a deliberate, visible change rather than a
    silent one.
    """
    items = [
        _item(id=7770, title="Epic underway", type="epic", status="in_progress",
              spec="cortex/lifecycle/epic-underway/spec.md"),
        _item(id=8881, title="Orphaned child", status="refined", parent=7770,
              spec="cortex/lifecycle/orphaned-child/spec.md"),
    ]

    blocks, flat = render(items, build_epic_map(items))

    assert "8881" not in blocks
    assert flat == []
    assert blocks == (
        "Backlog is clear — no ready items. Check blocked items or create "
        "new ones with `/cortex-backlog:backlog add`.\n"
    )
