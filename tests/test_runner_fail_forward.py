"""R26 fail-forward coverage for sibling feature continuation.

Closes the R16 [M]-tagged pipeline.md gap: "Fail-forward (one feature's
failure doesn't abort round siblings) — no dedicated test".

The test creates a two-feature state fixture, simulates a batch where
feature A fails and feature B merges, and asserts that B still reaches
``merged`` even though A failed.

Uses ``map_results._map_results_to_state`` — the module that applies
per-feature outcomes to overnight state — to exercise the fail-forward
path without the overhead of spawning subprocess dispatches.  This is the
same code path that the runner's round loop takes when writing
``batch-<n>-results.json`` back into the state file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from cortex_command.overnight.map_results import _map_results_to_state
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    load_state,
    save_state,
)


def test_sibling_continues_after_one_fails() -> None:
    """When feature A fails in a round, feature B still reaches merged.

    This verifies the fail-forward contract: sibling features within a
    single round are independent — one feature's failure does not short-
    circuit siblings that were already processed successfully.
    """
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "overnight-state.json"

        # Two-feature fixture, both initially pending.
        state = OvernightState(
            session_id="overnight-2026-04-24-fail-forward",
            plan_ref="lifecycle/overnight-plan.md",
            features={
                "feat-a": OvernightFeatureStatus(status="pending"),
                "feat-b": OvernightFeatureStatus(status="pending"),
            },
        )
        save_state(state, state_path)

        # Simulate a round where A fails and B merges.  This mirrors the
        # batch-results JSON that the orchestrator agent writes and that
        # the runner feeds into _map_results_to_state after round
        # completion — the fail-forward point is that both outcomes land
        # in the same results payload without A's failure aborting B.
        batch_results = {
            "features_merged": ["feat-b"],
            "features_failed": [
                {"name": "feat-a", "error": "simulated dispatch failure"},
            ],
        }

        # Patch feature_executor.execute_feature per spec intent (the
        # overnight dispatcher entry point, named ``execute_feature``
        # rather than the spec's ``dispatch_feature``).  State is mutated
        # via _map_results_to_state, so the patch guards against any
        # accidental live dispatch that would bypass the fixture.
        async def _side_effect(feature: str, *args, **kwargs):
            return "failed" if feature == "feat-a" else "merged"

        with patch(
            "cortex_command.overnight.feature_executor.execute_feature",
            side_effect=_side_effect,
        ):
            _map_results_to_state(batch_results, state_path, batch_id=1)

        # Reload state and assert sibling continuation.
        loaded = load_state(state_path)

        fs_a = loaded.features["feat-a"]
        fs_b = loaded.features["feat-b"]

        assert fs_a.status == "failed", (
            f"feat-a should be failed after simulated dispatch failure; "
            f"got {fs_a.status!r}"
        )
        assert fs_b.status == "merged", (
            f"feat-b should reach merged despite feat-a's failure "
            f"(fail-forward contract); got {fs_b.status!r}"
        )
