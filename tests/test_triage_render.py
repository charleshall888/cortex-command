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
from cortex_command.backlog.triage import _EPIC_LEGEND, _render_epic_block, render


#: The once-per-board preamble above the epic sections. Imported rather than
#: restated: its wording is not the contract — the rows and footers below it
#: are — and pinning the prose in nine places would make every reword a
#: nine-file edit.
_EPICS = f"## Epics\n\n{_EPIC_LEGEND}\n\n"


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
    renderable in both blocks — the only way to compare the two routings on
    one record, since neither block will render a closed, held, or parked one.
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

def test_ready_epic_lists_workable_children_across_types_and_readiness() -> None:
    """A ready epic lists its workable children, spanning readiness and all types."""
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
        _EPICS
        + "### Epic 100 — Platform epic\n"
        "\n"
        "4 workable\n"
        "\n"
        "- **101** Fix crash — refined `/cortex-core:build`\n"
        "- **102** Bump deps — backlog `/cortex-core:refine`\n"
        "- **103** Maybe caching — backlog `/cortex-core:discovery`\n"
        "- **104** New export — refined `/cortex-core:build`\n"
        "\n"
        "Build in parallel: 101 · 104\n"
        "Refine: 102\n"
    )
    # Children shown in the epic block are not repeated in ## Ready.
    assert flat == []


# ---------------------------------------------------------------------------
# Ticket #456 — closed children are counted, never listed and never routed.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("closed_status", ["complete", "done", "abandoned",
                                           "superseded", "wont-do"])
def test_closed_child_is_counted_but_never_listed_or_routed(closed_status) -> None:
    """No terminal status may reach a row, a route mark, or a footer.

    Parametrized across the vocabulary because the corpus genuinely carries
    several spellings of "finished" — ``345`` is ``done`` while ``348`` is
    ``complete`` — and a set that covers only one of them half-works, which is
    exactly how the held-status set failed before this ticket.
    """
    items = [
        _item(id=900, title="Epic", type="epic", status="refined",
              spec="cortex/lifecycle/e/spec.md"),
        _item(id=901, title="Shipped work", status=closed_status, parent=900,
              spec="cortex/lifecycle/shipped/spec.md"),
        _item(id=902, title="Live work", status="backlog", parent=900),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert "901" not in blocks
    assert "Shipped work" not in blocks
    assert "1 workable · 1 closed" in blocks
    assert "- **902** Live work — backlog `/cortex-core:refine`" in blocks
    assert "Refine: 902" in blocks


def test_closed_child_with_a_spec_is_not_offered_for_build() -> None:
    """The pre-fix failure mode: ``spec:`` archaeology routing finished work.

    A ticket closed *with* a lifecycle spec read ``complete /cortex-core:build``
    and a ticket closed without it read ``complete /cortex-core:refine`` — the
    verb was decided by whether the finished work happened to leave an artifact
    behind, never by whether it was finished.
    """
    items = [
        _item(id=910, title="Epic", type="epic", status="refined",
              spec="cortex/lifecycle/e/spec.md"),
        _item(id=911, title="Closed with spec", status="complete", parent=910,
              spec="cortex/lifecycle/withspec/spec.md"),
        _item(id=912, title="Closed without spec", status="done", parent=910),
        _item(id=913, title="Live", status="backlog", parent=910),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert "/cortex-core:build" not in blocks
    assert "911" not in blocks and "912" not in blocks


def test_epic_with_every_child_closed_does_not_offer_decomposition() -> None:
    """A fully-shipped epic reads as finished, not as never-decomposed.

    The discovery line is reserved for an epic that genuinely has no children;
    firing it here told the operator to decompose an epic that had already been
    decomposed and delivered.
    """
    items = [
        _item(id=920, title="Delivered epic", type="epic", status="backlog"),
        _item(id=921, title="A", status="complete", parent=920),
        _item(id=922, title="B", status="done", parent=920),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert blocks == (
        _EPICS
        + "### Epic 920 — Delivered epic\n"
        "\n"
        "2 closed\n"
        "\n"
        "Nothing left to pick up — this epic looks finished.\n"
    )


def test_childless_epic_still_offers_decomposition() -> None:
    """The discovery line survives where it is actually true."""
    items = [_item(id=930, title="Undecomposed", type="epic", status="backlog")]

    blocks, _ = render(items, build_epic_map(items))

    assert "No child tickets — consider `/cortex-core:discovery`" in blocks


def test_deferred_child_is_listed_but_never_routed() -> None:
    """Parked is a decision to revisit, not work to pick up.

    It stays visible — an operator scanning the epic should see it — but it
    carries no route verb and appears in no footer. The tag-parked variant
    needs the explicit mark; the status-parked one already says ``deferred``.
    """
    items = [
        _item(id=940, title="Epic", type="epic", status="refined",
              spec="cortex/lifecycle/e/spec.md"),
        _item(id=941, title="Parked by status", status="deferred", parent=940),
        _item(id=942, title="Parked by tag", status="backlog", parent=940,
              tags=["deferred"]),
        _item(id=943, title="Live", status="backlog", parent=940),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert "1 workable · 2 parked" in blocks
    assert "- **941** Parked by status — deferred\n" in blocks
    assert "- **942** Parked by tag — backlog [parked]\n" in blocks
    assert "Refine: 943" in blocks  # not "943 · 941", and not "every workable"


# ---------------------------------------------------------------------------
# Dependency waves — the parallel/sequential signal.
# ---------------------------------------------------------------------------

def _chain_fixture() -> list[dict]:
    """A four-child epic: a two-step chain plus two independent children."""
    spec = "cortex/lifecycle/x/spec.md"
    return [
        _item(id=200, title="Chained epic", type="epic", status="refined",
              spec=spec),
        _item(id=201, title="Foundation", status="refined", parent=200, spec=spec),
        _item(id=202, title="On top", status="refined", parent=200, spec=spec,
              blocked_by=[201]),
        _item(id=203, title="Independent", status="refined", parent=200, spec=spec),
        _item(id=204, title="Unrefined behind the chain", status="backlog",
              parent=200, blocked_by=[202]),
    ]


def test_dependency_chain_renders_as_waves() -> None:
    """The ``Order:`` line sequences the dependency-connected subgraph only.

    Independent children are wave-0 singletons carrying no ordering
    information, so listing them would make the line a second copy of the row
    list rather than a dependency chain.
    """
    items = _chain_fixture()

    blocks, _ = render(items, build_epic_map(items))

    assert "Order: 201 → 202 → 204\n" in blocks
    assert "203" not in blocks.split("Order:")[1].split("\n")[0]


def test_build_offers_only_the_unblocked_wave_and_marks_the_rest() -> None:
    """Only wave 0 is startable; a later wave says what it waits on."""
    items = _chain_fixture()

    blocks, _ = render(items, build_epic_map(items))

    assert "Build in parallel: 201 · 203\n" in blocks
    assert "- **202** On top — refined `/cortex-core:build` [blocked by 201]\n" in blocks


def test_refine_ignores_the_execution_order() -> None:
    """A blocked child is still refinable — ordering constrains building only.

    Writing a spec for a ticket whose blocker has not shipped costs nothing and
    unblocks the moment the blocker lands, so refine targets are drawn from
    every wave. The old renderer excluded blocked children from the footer
    entirely, which serialized refinement behind execution for no reason.
    """
    items = _chain_fixture()

    blocks, _ = render(items, build_epic_map(items))

    assert "Refine: 204\n" in blocks


def test_a_blocker_that_shipped_no_longer_blocks() -> None:
    """``blocked_by`` pointing at closed work is satisfied, not pending.

    The old rule — any ``blocked_by`` entry means blocked — held children
    behind work that had already landed, permanently.
    """
    items = [
        _item(id=210, title="Epic", type="epic", status="refined",
              spec="cortex/lifecycle/e/spec.md"),
        _item(id=211, title="Shipped blocker", status="complete", parent=210),
        _item(id=212, title="Freed", status="refined", parent=210,
              spec="cortex/lifecycle/freed/spec.md", blocked_by=[211]),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert "[blocked" not in blocks
    assert "Build: 212" in blocks


def test_unresolvable_blocker_is_reported_and_withheld_from_build() -> None:
    """A cross-repo reference cannot be resolved here, so it is shown verbatim.

    Nothing is startable, so neither the build line nor the overnight offer may
    fire: overnight runs the same readiness scan and would select nothing, and
    an epic that is fully refined but wholly blocked otherwise satisfies the
    offer's "no refine work left, no ideas" condition.
    """
    items = [
        _item(id=220, title="Epic", type="epic", status="refined",
              spec="cortex/lifecycle/e/spec.md"),
        _item(id=221, title="Waiting on someone else", status="refined",
              parent=220, spec="cortex/lifecycle/w/spec.md",
              blocked_by=["acme/repo#12"]),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert "[blocked by acme/repo#12]" in blocks
    assert "Build" not in blocks
    assert "/cortex-overnight:overnight" not in blocks


@pytest.mark.parametrize(
    "cycle,expected",
    [
        pytest.param(
            {231: [232], 232: [231]},
            "Circular `blocked_by` among 231 · 232 — none can start until that "
            "is edited.",
            id="mutual",
        ),
        pytest.param(
            {231: [231], 232: []},
            "231 lists itself in `blocked_by` — it cannot start until that is "
            "edited.",
            id="self-referential",
        ),
    ],
)
def test_a_dependency_cycle_is_named_and_never_called_startable(
    cycle, expected
) -> None:
    """A cycle must not be laundered into a wave that claims parallel-safety.

    Kahn layering stalls with nothing schedulable. Appending the remainder as a
    final wave would have rendered two mutually-blocking children as ``231 ·
    232`` — the separator that means "start these together" — and reading
    ``startable`` off that wave would have offered both for build.
    """
    items = [
        _item(id=230, title="Epic", type="epic", status="refined",
              spec="cortex/lifecycle/e/spec.md"),
        _item(id=231, title="A", status="refined", parent=230,
              spec="cortex/lifecycle/a/spec.md", blocked_by=cycle[231]),
        _item(id=232, title="B", status="refined", parent=230,
              spec="cortex/lifecycle/b/spec.md", blocked_by=cycle[232]),
    ]

    blocks, _ = render(items, build_epic_map(items))

    assert expected in blocks
    assert "Build in parallel" not in blocks
    assert "Build: 231" not in blocks


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
        "No ordering — any of these can be picked up in parallel.\n"
        "\n"
        "- `critical` `feature` **201** Refined feature → `/cortex-core:build`\n"
        "- `low` `feature` **202** Unrefined feature → `/cortex-core:refine`\n"
    )
    assert [i["id"] for i in flat] == [201, 202]


def test_in_flight_child_is_listed_without_a_route_verb() -> None:
    """Every child held in flight leaves the epic with nothing to recommend.

    The row survives — in-flight work is resumable, which is a real action —
    but it carries no verb: routing ``in_progress`` work to ``refine`` told the
    operator to re-spec something already being implemented.
    """
    items = [
        _item(id=300, title="Stalled epic", type="epic", status="refined",
              spec="cortex/lifecycle/stalled/spec.md"),
        _item(id=301, title="Work in flight", status="in_progress", parent=300),
    ]

    blocks, flat = render(items, build_epic_map(items))

    assert blocks == (
        _EPICS
        + "### Epic 300 — Stalled epic\n"
        "\n"
        "1 in flight\n"
        "\n"
        "- **301** Work in flight — in_progress\n"
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
        "No ordering — any of these can be picked up in parallel.\n"
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
        _EPICS
        + "### Epic 600 — Idea-bearing epic\n"
        "\n"
        "3 workable\n"
        "\n"
        "- **601** Unrefined idea — backlog `/cortex-core:discovery`\n"
        "- **602** Refined feature — refined `/cortex-core:build`\n"
        "- **603** Refined bug — refined `/cortex-core:build`\n"
        "\n"
        "Build in parallel: 602 · 603\n"
    )
    assert "\nRefine" not in blocks  # footer lines only; the legend names it too
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
        _EPICS
        + "### Epic 700 — Refined-idea epic\n"
        "\n"
        "2 workable\n"
        "\n"
        "- **701** Refined idea — refined `/cortex-core:discovery`\n"
        "- **702** Refined feature — refined `/cortex-core:build`\n"
        "\n"
        "Build: 702\n"
    )
    assert "/cortex-overnight:overnight" not in blocks
    # The idea is not refine work either — it must not be listed for refining.
    assert "\nRefine" not in blocks


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

    # Folded onto the build line: both name the same set, and handing the epic
    # to overnight is an alternative to building those ids by hand.
    assert (
        "Build in parallel: 801 · 802 — or `/cortex-overnight:overnight` "
        "to auto-select them\n"
    ) in blocks


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
# Requirement 10 — the hole above, now closed (#438).
# ---------------------------------------------------------------------------

def test_ready_child_of_non_ready_epic_is_still_listed() -> None:
    """A ready child whose epic is not rendered must appear in ``## Ready``.

    This previously pinned a known bug: the child landed in ``child_ids`` and
    was suppressed from Block 2, but its epic was not in the ready set, so no
    epic block was rendered either — the id appeared nowhere in the output.
    ``child_ids`` is now derived only from the epics actually rendered, so
    suppression can never outlive the block that justifies it.

    The fix became load-bearing when the epic map widened to the full corpus:
    every *closed* epic is now in the map, and a closed epic is never in the
    ready set, so the old derivation would have hidden every ready child of
    every closed epic — the late-arriving child #438 exists to surface.
    """
    items = [
        _item(id=7770, title="Epic underway", type="epic", status="in_progress",
              spec="cortex/lifecycle/epic-underway/spec.md"),
        _item(id=8881, title="Orphaned child", status="refined", parent=7770,
              spec="cortex/lifecycle/orphaned-child/spec.md"),
    ]

    blocks, flat = render(items, build_epic_map(items))

    assert [i["id"] for i in flat] == [8881]
    assert "8881" in blocks
    assert "## Ready" in blocks


def test_ready_child_of_rendered_epic_is_not_duplicated() -> None:
    """The suppression still works where it is justified.

    When the epic *is* rendered in Block 1, its children are listed there, so
    they must not repeat in Block 2.
    """
    items = [
        _item(id=7771, title="Epic ready", type="epic", status="refined",
              spec="cortex/lifecycle/epic-ready/spec.md"),
        _item(id=8882, title="Listed child", status="refined", parent=7771,
              spec="cortex/lifecycle/listed-child/spec.md"),
    ]

    blocks, flat = render(items, build_epic_map(items))

    assert [i["id"] for i in flat] == []
    assert "## Ready" not in blocks
