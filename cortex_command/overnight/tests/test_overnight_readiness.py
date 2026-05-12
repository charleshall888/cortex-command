#!/usr/bin/env python3
"""Tests for cortex_command.overnight.backlog.filter_ready().

Constructs BacklogItem instances directly and verifies filter_ready() places
each item in the expected bucket with the correct reason substring.
"""

import tempfile
import pytest
from pathlib import Path

from cortex_command.overnight.backlog import (
    BacklogItem,
    filter_ready,
    group_into_batches,
    score_items,
)


# ---------------------------------------------------------------------------
# Test: eligible item passes all checks
# ---------------------------------------------------------------------------

def test_eligible() -> None:
    """An item with all required fields and files present is eligible."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Slug of "Eligible Feature" → "eligible-feature"
        slug = "eligible-feature"
        research_path = root / "cortex" / "lifecycle" / slug / "research.md"
        spec_path = root / "cortex" / "lifecycle" / slug / "spec.md"
        research_path.parent.mkdir(parents=True, exist_ok=True)
        research_path.write_text("# Research\n")
        spec_path.write_text("# Spec\n")

        item = BacklogItem(
            id=1,
            title="Eligible Feature",
            status="backlog",
            priority="high",
            type="feature",
            tags=["testing"],
            lifecycle_slug=slug,
        )

        result = filter_ready([item], project_root=root)

        if len(result.eligible) != 1:
            pytest.fail(f"expected 1 eligible item, got {len(result.eligible)}; ineligible: {result.ineligible}")
            return
        if result.eligible[0].id != 1:
            pytest.fail(f"wrong item in eligible list: id={result.eligible[0].id}")
            return
        if result.ineligible:
            pytest.fail(f"expected empty ineligible, got {result.ineligible}")
            return


# ---------------------------------------------------------------------------
# Test: rejected — terminal status
# ---------------------------------------------------------------------------

def test_rejected_done_status() -> None:
    """An item with status 'done' is rejected at step 1 with reason containing 'status:'."""
    item = BacklogItem(
        id=2,
        title="Done Feature",
        status="done",
        priority="medium",
        type="feature",
        research="lifecycle/done-feature/research.md",
        spec="lifecycle/done-feature/spec.md",
    )

    result = filter_ready([item])

    if result.eligible:
        pytest.fail(f"expected no eligible items, got {result.eligible}")
        return
    if not result.ineligible:
        pytest.fail("expected 1 ineligible item, got none")
        return
    _, reason = result.ineligible[0]
    if "status:" not in reason:
        pytest.fail(f"expected reason to contain 'status:', got: {reason!r}")
        return


# ---------------------------------------------------------------------------
# Test: rejected — blocked by non-terminal item
# ---------------------------------------------------------------------------

def test_rejected_blocked() -> None:
    """An item blocked by a non-terminal item is rejected at step 2 with reason containing 'blocked by'."""
    # Blocker item (id=99, status=backlog — non-terminal)
    blocker = BacklogItem(
        id=99,
        title="Blocker Feature",
        status="backlog",
        priority="medium",
        type="feature",
    )
    item = BacklogItem(
        id=3,
        title="Blocked Feature",
        status="backlog",
        priority="medium",
        type="feature",
        blocked_by=["99"],
    )

    result = filter_ready([item], all_items=[item, blocker])

    if result.eligible:
        pytest.fail(f"expected no eligible items, got {result.eligible}")
        return
    if not result.ineligible:
        pytest.fail("expected 1 ineligible item, got none")
        return
    _, reason = result.ineligible[0]
    if "blocked by" not in reason:
        pytest.fail(f"expected reason to contain 'blocked by', got: {reason!r}")
        return


# ---------------------------------------------------------------------------
# Test: rejected — missing research field
# ---------------------------------------------------------------------------

def test_rejected_no_research() -> None:
    """An item with no research artifact on disk is rejected at step 3 with 'research file not found'."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # No files created — lifecycle dir is empty
        item = BacklogItem(
            id=4,
            title="No Research Feature",
            status="backlog",
            priority="medium",
            type="feature",
        )

        result = filter_ready([item], project_root=root)

        if result.eligible:
            pytest.fail(f"expected no eligible items, got {result.eligible}")
            return
        if not result.ineligible:
            pytest.fail("expected 1 ineligible item, got none")
            return
        _, reason = result.ineligible[0]
        if "research file not found" not in reason:
            pytest.fail(f"expected reason to contain 'research file not found', got: {reason!r}")
            return


# ---------------------------------------------------------------------------
# Test: rejected — missing spec field
# ---------------------------------------------------------------------------

def test_rejected_no_spec() -> None:
    """An item with research on disk but no spec artifact is rejected at step 4 with 'spec file not found'."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        slug = "no-spec-feature"
        research_path = root / "cortex" / "lifecycle" / slug / "research.md"
        research_path.parent.mkdir(parents=True, exist_ok=True)
        research_path.write_text("# Research\n")
        # spec file deliberately omitted

        item = BacklogItem(
            id=5,
            title="No Spec Feature",
            status="backlog",
            priority="medium",
            type="feature",
            lifecycle_slug=slug,
        )

        result = filter_ready([item], project_root=root)

        if result.eligible:
            pytest.fail(f"expected no eligible items, got {result.eligible}")
            return
        if not result.ineligible:
            pytest.fail("expected 1 ineligible item, got none")
            return
        _, reason = result.ineligible[0]
        if "spec file not found" not in reason:
            pytest.fail(f"expected reason to contain 'spec file not found', got: {reason!r}")
            return


# ---------------------------------------------------------------------------
# Test: rejected — research file not found on disk
# ---------------------------------------------------------------------------

def test_rejected_research_missing() -> None:
    """An item whose research file does not exist is rejected at step 5 with 'research file not found'."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # research file does NOT exist — spec file also absent, but research is checked first
        item = BacklogItem(
            id=6,
            title="Research Missing Feature",
            status="backlog",
            priority="medium",
            type="feature",
            research="lifecycle/research-missing-feature/research.md",
            spec="lifecycle/research-missing-feature/spec.md",
        )

        result = filter_ready([item], project_root=root)

        if result.eligible:
            pytest.fail(f"expected no eligible items, got {result.eligible}")
            return
        if not result.ineligible:
            pytest.fail("expected 1 ineligible item, got none")
            return
        _, reason = result.ineligible[0]
        if "research file not found" not in reason:
            pytest.fail(f"expected reason to contain 'research file not found', got: {reason!r}")
            return


# ---------------------------------------------------------------------------
# Test: rejected — spec file not found on disk
# ---------------------------------------------------------------------------

def test_rejected_spec_missing() -> None:
    """An item whose spec file does not exist (but research does) is rejected at step 5 with 'spec file not found'."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Create the research file but NOT the spec file
        slug = "spec-missing-feature"
        research_path = root / "cortex" / "lifecycle" / slug / "research.md"
        research_path.parent.mkdir(parents=True, exist_ok=True)
        research_path.write_text("# Research\n")
        # spec file deliberately omitted

        item = BacklogItem(
            id=7,
            title="Spec Missing Feature",
            status="backlog",
            priority="medium",
            type="feature",
            research=f"cortex/lifecycle/{slug}/research.md",
            spec=f"cortex/lifecycle/{slug}/spec.md",
        )

        result = filter_ready([item], project_root=root)

        if result.eligible:
            pytest.fail(f"expected no eligible items, got {result.eligible}")
            return
        if not result.ineligible:
            pytest.fail("expected 1 ineligible item, got none")
            return
        _, reason = result.ineligible[0]
        if "spec file not found" not in reason:
            pytest.fail(f"expected reason to contain 'spec file not found', got: {reason!r}")
            return


# ---------------------------------------------------------------------------
# Test: rejected — lifecycle/slug/spec.md missing
# ---------------------------------------------------------------------------

def test_rejected_no_lifecycle_spec() -> None:
    """An item with research present but lifecycle/slug/spec.md absent is rejected at step 4 with 'spec file not found'."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        slug = "no-lifecycle-spec-feature"
        research_path = root / "cortex" / "lifecycle" / slug / "research.md"
        research_path.parent.mkdir(parents=True, exist_ok=True)
        research_path.write_text("# Research\n")
        # lifecycle/{slug}/spec.md deliberately absent

        item = BacklogItem(
            id=8,
            title="No Lifecycle Spec Feature",
            status="backlog",
            priority="medium",
            type="feature",
            lifecycle_slug=slug,
        )

        result = filter_ready([item], project_root=root)

        if result.eligible:
            pytest.fail(f"expected no eligible items, got {result.eligible}")
            return
        if not result.ineligible:
            pytest.fail("expected 1 ineligible item, got none")
            return
        _, reason = result.ineligible[0]
        if "spec file not found" not in reason:
            pytest.fail(f"expected reason to contain 'spec file not found', got: {reason!r}")
            return


# ---------------------------------------------------------------------------
# Test: lifecycle_slug explicit override
# ---------------------------------------------------------------------------

def test_lifecycle_slug_explicit() -> None:
    """Explicit lifecycle_slug overrides slugify(title) for artifact path lookup."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # "Alpha Feature" slugifies to "alpha-feature"; use a different explicit slug
        # to prove that the explicit value is used, not the title-derived one.
        explicit_slug = "custom-slug"
        research_path = root / "cortex" / "lifecycle" / explicit_slug / "research.md"
        spec_path = root / "cortex" / "lifecycle" / explicit_slug / "spec.md"
        research_path.parent.mkdir(parents=True, exist_ok=True)
        research_path.write_text("# Research\n")
        spec_path.write_text("# Spec\n")

        item = BacklogItem(
            id=9,
            title="Alpha Feature",
            status="backlog",
            priority="medium",
            type="feature",
            lifecycle_slug=explicit_slug,
        )

        result = filter_ready([item], project_root=root)

        if len(result.eligible) != 1:
            pytest.fail(f"expected 1 eligible, got {len(result.eligible)}; ineligible: {result.ineligible}")
            return
        if result.eligible[0].id != 9:
            pytest.fail(f"wrong item in eligible list: id={result.eligible[0].id}")
            return


# ---------------------------------------------------------------------------
# Test: lifecycle_slug=None falls back to slugify(title)
# ---------------------------------------------------------------------------

def test_lifecycle_slug_none_fallback() -> None:
    """When lifecycle_slug is None, slugify(title) derives the artifact path."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # slugify("Fallback Feature") → "fallback-feature"
        derived_slug = "fallback-feature"
        research_path = root / "cortex" / "lifecycle" / derived_slug / "research.md"
        spec_path = root / "cortex" / "lifecycle" / derived_slug / "spec.md"
        research_path.parent.mkdir(parents=True, exist_ok=True)
        research_path.write_text("# Research\n")
        spec_path.write_text("# Spec\n")

        item = BacklogItem(
            id=10,
            title="Fallback Feature",
            status="backlog",
            priority="medium",
            type="feature",
            # lifecycle_slug deliberately absent — tests the None fallback path
        )

        result = filter_ready([item], project_root=root)

        if len(result.eligible) != 1:
            pytest.fail(f"expected 1 eligible, got {len(result.eligible)}; ineligible: {result.ineligible}")
            return
        if result.eligible[0].id != 10:
            pytest.fail(f"wrong item in eligible list: id={result.eligible[0].id}")
            return


# ---------------------------------------------------------------------------
# Test: lifecycle_slug set but no matching directory → rejected
# ---------------------------------------------------------------------------

def test_lifecycle_slug_mismatch_rejected() -> None:
    """An explicit lifecycle_slug with no matching artifacts is rejected."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # No files created under lifecycle/missing-slug/

        item = BacklogItem(
            id=11,
            title="Mismatch Feature",
            status="backlog",
            priority="medium",
            type="feature",
            lifecycle_slug="missing-slug",
        )

        result = filter_ready([item], project_root=root)

        if result.eligible:
            pytest.fail(f"expected no eligible items, got {result.eligible}")
            return
        if not result.ineligible:
            pytest.fail("expected 1 ineligible item, got none")
            return
        _, reason = result.ineligible[0]
        expected = "research file not found: lifecycle/missing-slug/research.md"
        if expected not in reason:
            pytest.fail(f"expected reason to contain {expected!r}, got: {reason!r}")
            return


# ---------------------------------------------------------------------------
# Test: rejected — type is epic (non-implementable)
# ---------------------------------------------------------------------------

def test_rejected_epic_type() -> None:
    """An item with type='epic' is rejected with 'epic is non-implementable' even when all artifacts are present."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        slug = "epic-feature"
        research_path = root / "cortex" / "lifecycle" / slug / "research.md"
        spec_path = root / "cortex" / "lifecycle" / slug / "spec.md"
        research_path.parent.mkdir(parents=True, exist_ok=True)
        research_path.write_text("# Research\n")
        spec_path.write_text("# Spec\n")

        item = BacklogItem(
            id=12,
            title="Epic Feature",
            status="refined",
            priority="high",
            type="epic",
            lifecycle_slug=slug,
        )

        result = filter_ready([item], project_root=root)

        if len(result.eligible) != 0:
            pytest.fail(f"expected 0 eligible items, got {len(result.eligible)}")
            return
        if len(result.ineligible) != 1:
            pytest.fail(f"expected 1 ineligible item, got {len(result.ineligible)}")
            return
        _, reason = result.ineligible[0]
        if "epic is non-implementable" not in reason:
            pytest.fail(f"expected reason to contain 'epic is non-implementable', got: {reason!r}")
            return


# ---------------------------------------------------------------------------
# Test: spec backfill when item.spec is None
# ---------------------------------------------------------------------------

def test_spec_backfill_when_item_spec_is_none() -> None:
    """When item.spec is None but lifecycle/{slug}/spec.md exists, filter_ready backfills item.spec."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        slug = "test-slug"
        research_path = root / "cortex" / "lifecycle" / slug / "research.md"
        spec_path = root / "cortex" / "lifecycle" / slug / "spec.md"
        research_path.parent.mkdir(parents=True, exist_ok=True)
        research_path.write_text("# Research\n")
        spec_path.write_text("# Spec\n")

        item = BacklogItem(
            id=1055,
            title="Spec Backfill Feature",
            status="refined",
            spec=None,
            lifecycle_slug=slug,
        )

        result = filter_ready([item], project_root=root)

        assert len(result.eligible) == 1, f"expected 1 eligible, got {len(result.eligible)}; ineligible: {result.ineligible}"
        assert result.eligible[0].spec == f"cortex/lifecycle/{slug}/spec.md", f"expected spec backfill, got: {result.eligible[0].spec!r}"
        assert len(result.ineligible) == 0, f"expected 0 ineligible, got {len(result.ineligible)}"


# ---------------------------------------------------------------------------
# Test: intra-session blocked item promoted
# ---------------------------------------------------------------------------

def test_intra_session_blocked_item_promoted() -> None:
    """B blocked only by eligible A is placed in intra_session_blocked, not ineligible."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        slug_a = "blocker-a"
        slug_b = "dependent-b"

        for slug in (slug_a, slug_b):
            lc_dir = root / "cortex" / "lifecycle" / slug
            lc_dir.mkdir(parents=True, exist_ok=True)
            (lc_dir / "research.md").write_text("# Research\n")
            (lc_dir / "spec.md").write_text("# Spec\n")

        item_a = BacklogItem(
            id=101,
            title="Blocker A",
            status="refined",
            priority="high",
            type="feature",
            lifecycle_slug=slug_a,
        )
        item_b = BacklogItem(
            id=102,
            title="Dependent B",
            status="refined",
            priority="medium",
            type="feature",
            lifecycle_slug=slug_b,
            blocked_by=[str(item_a.id)],
        )

        result = filter_ready([item_a, item_b], all_items=[item_a, item_b], project_root=root)

        # A must be eligible
        if item_a not in result.eligible:
            pytest.fail(f"expected A in eligible, got eligible={[i.id for i in result.eligible]}")
            return

        # B must be in intra_session_blocked, not ineligible
        intra_items = [pair[0] for pair in result.intra_session_blocked]
        ineligible_items = [pair[0] for pair in result.ineligible]

        if item_b not in intra_items:
            pytest.fail(f"expected B in intra_session_blocked, got {[(i.id, r) for i, r in result.ineligible]}")
            return

        if item_b in ineligible_items:
            pytest.fail("B should not be in ineligible")
            return

        # Blocker slugs list must include A's slug
        blocker_slugs = next(slugs for item, slugs in result.intra_session_blocked if item is item_b)
        if slug_a not in blocker_slugs:
            pytest.fail(f"expected blocker slug {slug_a!r} in {blocker_slugs}")
            return


# ---------------------------------------------------------------------------
# Test: intra-session mixed blockers excluded
# ---------------------------------------------------------------------------

def test_intra_session_mixed_blockers_excluded() -> None:
    """B blocked by both eligible A and ineligible X lands in ineligible."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        slug_a = "blocker-eligible-a"
        # Create lifecycle artifacts only for A
        lc_dir_a = root / "cortex" / "lifecycle" / slug_a
        lc_dir_a.mkdir(parents=True, exist_ok=True)
        (lc_dir_a / "research.md").write_text("# Research\n")
        (lc_dir_a / "spec.md").write_text("# Spec\n")

        # X has status ready but NO lifecycle artifacts — will not be eligible
        item_x = BacklogItem(
            id=201,
            title="Ineligible X",
            status="refined",
            priority="medium",
            type="feature",
            # no lifecycle_slug, no artifacts under lifecycle/ineligible-x/
        )
        item_a = BacklogItem(
            id=202,
            title="Blocker Eligible A",
            status="refined",
            priority="high",
            type="feature",
            lifecycle_slug=slug_a,
        )
        item_b = BacklogItem(
            id=203,
            title="Mixed Dependent B",
            status="refined",
            priority="medium",
            type="feature",
            blocked_by=[str(item_a.id), str(item_x.id)],
        )

        all_items = [item_x, item_a, item_b]
        result = filter_ready([item_x, item_a, item_b], all_items=all_items, project_root=root)

        ineligible_items = [pair[0] for pair in result.ineligible]
        ineligible_reasons = {pair[0].id: pair[1] for pair in result.ineligible}

        if item_b not in ineligible_items:
            pytest.fail(f"expected B in ineligible; intra_session_blocked={[(i.id, s) for i, s in result.intra_session_blocked]}")
            return

        reason = ineligible_reasons[item_b.id]
        if "blocked by" not in reason:
            pytest.fail(f"expected reason to contain 'blocked by', got: {reason!r}")
            return


# ---------------------------------------------------------------------------
# Test: intra-session blocked item missing spec excluded
# ---------------------------------------------------------------------------

def test_intra_session_blocked_missing_spec() -> None:
    """B blocked only by eligible A but missing spec.md lands in ineligible."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        slug_a = "spec-blocker-a"
        slug_b = "spec-dependent-b"

        # A has full artifacts
        lc_dir_a = root / "cortex" / "lifecycle" / slug_a
        lc_dir_a.mkdir(parents=True, exist_ok=True)
        (lc_dir_a / "research.md").write_text("# Research\n")
        (lc_dir_a / "spec.md").write_text("# Spec\n")

        # B has research.md but NOT spec.md
        lc_dir_b = root / "cortex" / "lifecycle" / slug_b
        lc_dir_b.mkdir(parents=True, exist_ok=True)
        (lc_dir_b / "research.md").write_text("# Research\n")
        # spec.md deliberately omitted

        item_a = BacklogItem(
            id=301,
            title="Spec Blocker A",
            status="refined",
            priority="high",
            type="feature",
            lifecycle_slug=slug_a,
        )
        item_b = BacklogItem(
            id=302,
            title="Spec Dependent B",
            status="refined",
            priority="medium",
            type="feature",
            lifecycle_slug=slug_b,
            blocked_by=[str(item_a.id)],
        )

        result = filter_ready([item_a, item_b], all_items=[item_a, item_b], project_root=root)

        ineligible_items = [pair[0] for pair in result.ineligible]
        ineligible_reasons = {pair[0].id: pair[1] for pair in result.ineligible}

        if item_b not in ineligible_items:
            pytest.fail(f"expected B in ineligible; intra_session_blocked={[(i.id, s) for i, s in result.intra_session_blocked]}")
            return

        reason = ineligible_reasons[item_b.id]
        if "spec file not found" not in reason:
            pytest.fail(f"expected reason to contain 'spec file not found', got: {reason!r}")
            return


# ---------------------------------------------------------------------------
# Test: intra-session multi-level chain A→B→C all promoted
# ---------------------------------------------------------------------------

def test_intra_session_multilevel_chain() -> None:
    """A→B→C chain: A is eligible, B and C are both in intra_session_blocked."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        slug_a = "chain-item-a"
        slug_b = "chain-item-b"
        slug_c = "chain-item-c"

        for slug in (slug_a, slug_b, slug_c):
            lc_dir = root / "cortex" / "lifecycle" / slug
            lc_dir.mkdir(parents=True, exist_ok=True)
            (lc_dir / "research.md").write_text("# Research\n")
            (lc_dir / "spec.md").write_text("# Spec\n")

        item_a = BacklogItem(
            id=401,
            title="Chain Item A",
            status="refined",
            priority="high",
            type="feature",
            lifecycle_slug=slug_a,
        )
        item_b = BacklogItem(
            id=402,
            title="Chain Item B",
            status="refined",
            priority="medium",
            type="feature",
            lifecycle_slug=slug_b,
            blocked_by=[str(item_a.id)],
        )
        item_c = BacklogItem(
            id=403,
            title="Chain Item C",
            status="refined",
            priority="medium",
            type="feature",
            lifecycle_slug=slug_c,
            blocked_by=[str(item_b.id)],
        )

        all_items = [item_a, item_b, item_c]
        result = filter_ready(all_items, all_items=all_items, project_root=root)

        # A must be independently eligible
        if item_a not in result.eligible:
            pytest.fail(f"expected A in eligible, got eligible={[i.id for i in result.eligible]}")
            return

        intra_map = {item.id: slugs for item, slugs in result.intra_session_blocked}

        if item_b.id not in intra_map:
            pytest.fail(f"expected B in intra_session_blocked, got {list(intra_map.keys())}")
            return
        if item_c.id not in intra_map:
            pytest.fail(f"expected C in intra_session_blocked, got {list(intra_map.keys())}")
            return

        # B's blocker list should be [slug_a]
        b_blockers = intra_map[item_b.id]
        if b_blockers != [slug_a]:
            pytest.fail(f"expected B blocker list [{slug_a!r}], got {b_blockers}")
            return

        # C's blocker list should be [slug_b]
        c_blockers = intra_map[item_c.id]
        if c_blockers != [slug_b]:
            pytest.fail(f"expected C blocker list [{slug_b!r}], got {c_blockers}")
            return

        if result.ineligible:
            pytest.fail(f"expected no ineligible items, got {[(i.id, r) for i, r in result.ineligible]}")
            return


# ---------------------------------------------------------------------------
# Test: intra-session round assignment via filter_ready + score + group
# ---------------------------------------------------------------------------

def test_intra_session_round_assignment() -> None:
    """Dependent B gets batch_id == A's batch_id + 1 after full pipeline."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        slug_a = "blocker-item"
        slug_b = "dependent-item"

        for slug in (slug_a, slug_b):
            lc_dir = root / "cortex" / "lifecycle" / slug
            lc_dir.mkdir(parents=True, exist_ok=True)
            (lc_dir / "research.md").write_text("# Research\n")
            (lc_dir / "spec.md").write_text("# Spec\n")

        item_a = BacklogItem(
            id=501,
            title="Blocker Item",
            status="refined",
            priority="high",
            type="feature",
            lifecycle_slug=slug_a,
        )
        item_b = BacklogItem(
            id=502,
            title="Dependent Item",
            status="refined",
            priority="medium",
            type="feature",
            lifecycle_slug=slug_b,
            blocked_by=[str(item_a.id)],
        )

        all_items = [item_a, item_b]
        readiness = filter_ready(all_items, all_items=all_items, project_root=root)

        if item_a not in readiness.eligible:
            pytest.fail(f"expected A eligible, got {[i.id for i in readiness.eligible]}")
            return
        if not readiness.intra_session_blocked:
            pytest.fail("expected B in intra_session_blocked")
            return

        # Run score + group on the independent-eligible items
        scored = score_items(readiness.eligible)
        batches = group_into_batches(scored, batch_size_cap=5)

        # BFS round assignment matching select_overnight_batch logic
        slug_to_batch_id: dict[str, int] = {}
        for batch in batches:
            for item in batch.items:
                slug_to_batch_id[item.lifecycle_slug or item.title] = batch.batch_id

        from cortex_command.overnight.backlog import Batch as _Batch
        batches_by_id: dict[int, _Batch] = {b.batch_id: b for b in batches}

        intra_session_deps: dict[str, list[str]] = {}
        queue = list(readiness.intra_session_blocked)

        while queue:
            next_queue = []
            promoted_this_round = 0
            for item, blocker_slugs in queue:
                if all(s in slug_to_batch_id for s in blocker_slugs):
                    batch_id = max(slug_to_batch_id[s] for s in blocker_slugs) + 1
                    if batch_id in batches_by_id:
                        batches_by_id[batch_id].items.append(item)
                    else:
                        new_batch = _Batch(batch_id=batch_id, items=[item])
                        batches.append(new_batch)
                        batches_by_id[batch_id] = new_batch
                    dep_slug = item.lifecycle_slug or item.title
                    slug_to_batch_id[dep_slug] = batch_id
                    intra_session_deps[dep_slug] = blocker_slugs
                    promoted_this_round += 1
                else:
                    next_queue.append((item, blocker_slugs))
            if promoted_this_round == 0:
                break
            queue = next_queue

        # B's slug must appear in intra_session_deps
        if slug_b not in intra_session_deps:
            pytest.fail(f"expected {slug_b!r} in intra_session_deps, got {list(intra_session_deps.keys())}")
            return

        # Find A's batch_id and B's batch_id
        a_batch_id = slug_to_batch_id.get(slug_a)
        b_batch_id = slug_to_batch_id.get(slug_b)

        if a_batch_id is None:
            pytest.fail("could not find A's batch_id")
            return
        if b_batch_id is None:
            pytest.fail("could not find B's batch_id")
            return

        if b_batch_id != a_batch_id + 1:
            pytest.fail(f"expected B batch_id={a_batch_id + 1}, got {b_batch_id}")
            return
