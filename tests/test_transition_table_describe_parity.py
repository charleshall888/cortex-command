"""Freshness (CI-diffed golden) + render-integrity checks for the `describe` doc.

The lifecycle transition table has a single durable source of truth,
``cortex_command/lifecycle/transition_table.py`` (the closed, wheel-owned state
machine). The human/machine-readable rendering
``docs/lifecycle-transition-table.md`` is GENERATED from that table by the
``describe`` verb (``cortex_command.lifecycle.describe.generate_md``); never
hand-edit it. This test is the CI-diffed golden (spec R13): it regenerates the
doc in-memory from the live table and byte-diffs it against the committed file,
so a stale committed doc fails.

Mirrors ``tests/test_lifecycle_kept_pauses_parity.py``: a freshness invariant
plus negative controls that assert the freshness comparison actually fails on
drift, and that the pure renderers are total over the table.

Not self-sealing: ``generate_md`` reads the REAL ``transition_table`` module
(``STATES`` / ``TRANSITIONS``), so a change to the table that isn't
regenerated-and-committed fails ``test_committed_doc_is_fresh``. The generator
and this test share only the pure ``generate_md`` entry point over that live
table — there is no second copy of the table they could drift together against.
"""

from __future__ import annotations

import json
from pathlib import Path

from cortex_command.lifecycle import transition_table as tt
from cortex_command.lifecycle.describe import (
    _load,
    generate_json,
    generate_md,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DESCRIBE_DOC = REPO_ROOT / "docs" / "lifecycle-transition-table.md"


# ---------------------------------------------------------------------------
# Freshness — the CI-diffed golden (R13)
# ---------------------------------------------------------------------------


def test_committed_doc_is_fresh() -> None:
    """The committed transition-table doc byte-matches a fresh regeneration."""
    expected = generate_md(_load())
    actual = DESCRIBE_DOC.read_text(encoding="utf-8")
    assert actual == expected, (
        "docs/lifecycle-transition-table.md is stale — regenerate with "
        "`CORTEX_COMMAND_FORCE_SOURCE=1 cortex-lifecycle-describe --write` and "
        "commit the result."
    )


# ---------------------------------------------------------------------------
# Render integrity — the pure renderers are total over the live table
# ---------------------------------------------------------------------------


def test_load_covers_every_table_row() -> None:
    """``_load`` projects every live state and transition (no dropped rows)."""
    data = _load()
    assert {s["name"] for s in data["states"]} == {s.name for s in tt.STATES}
    assert {t["id"] for t in data["transitions"]} == {t.id for t in tt.TRANSITIONS}


def test_json_block_is_deterministic_and_valid() -> None:
    """The embedded JSON is stable, sorted, and round-trips every transition."""
    data = _load()
    payload = json.loads(generate_json(data))
    ids = [t["id"] for t in payload["transitions"]]
    assert ids == sorted(ids), "transitions must be id-sorted for a stable golden"
    names = [s["name"] for s in payload["states"]]
    assert names == sorted(names), "states must be name-sorted for a stable golden"
    assert {t["id"] for t in payload["transitions"]} == {t.id for t in tt.TRANSITIONS}


def test_generate_md_is_deterministic() -> None:
    """Regenerating twice yields byte-identical output (declaration-order-free)."""
    assert generate_md(_load()) == generate_md(_load())


# ---------------------------------------------------------------------------
# Negative controls — assert the freshness check actually fails on drift.
# These use synthetic in-memory data; they never touch the committed tree.
# ---------------------------------------------------------------------------


def test_negative_stale_committed_doc() -> None:
    """A hand-edited (drifted) doc does not match a fresh regeneration."""
    fresh = generate_md(_load())
    stale = fresh.replace("`plan.branch-mode-approved`", "`plan.TAMPERED`", 1)
    assert stale != fresh, "sentinel replacement did not apply"
    assert fresh != stale  # the freshness comparison would fail on this drift


def test_negative_dropped_transition_changes_output() -> None:
    """Dropping a transition row changes the rendered doc (renderer reads all)."""
    full = generate_md(_load())
    fewer = generate_md(_load(transitions=tt.TRANSITIONS[:-1]))
    assert full != fewer
