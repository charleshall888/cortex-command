"""R26 resume-semantics coverage for paused and deferred features.

Closes two R16 [M]-tagged pipeline.md gaps:

  (a) Paused features are auto-retried on resume — covered by the
      interrupt-handling convention across ``interrupt.py`` and
      ``feature_executor.py``.  ``handle_interrupted_features()`` preserves
      paused status (not overwritten), and ``runner._count_pending`` counts
      paused as pending so the feature is picked up in the next round.

  (b) Deferred features are not auto-retried on resume — they await human
      decision.  ``handle_interrupted_features()`` leaves deferred status
      intact, and deferred is treated as terminal-for-session by the
      resume logic.

Tests exercise ``interrupt.handle_interrupted_features`` directly against
a fixture ``overnight-state.json`` and reload the state to assert the
post-resume contract.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from cortex_command.overnight.interrupt import handle_interrupted_features
from cortex_command.overnight.runner import _count_pending
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    load_state,
    save_state,
)


def _write_fixture_state(state_path: Path, feature_status: str) -> None:
    """Write an overnight state fixture with one feature at *feature_status*."""
    state = OvernightState(
        session_id="overnight-2026-04-24-resume",
        plan_ref="lifecycle/overnight-plan.md",
        features={
            "feat-x": OvernightFeatureStatus(status=feature_status),
        },
    )
    save_state(state, state_path)


# ---------------------------------------------------------------------------
# (a) Paused feature retried on resume
# ---------------------------------------------------------------------------

def test_paused_feature_retried_on_resume() -> None:
    """A paused feature is available for retry in the next round after resume.

    Preservation contract (pipeline.md R16 [M] convention):
      - ``handle_interrupted_features`` leaves paused status intact (it only
        resets features stuck in ``running`` to ``pending``).
      - ``_count_pending`` counts the paused feature as pending so the
        orchestrator picks it up in the next round — this is the "auto-retry
        on resume" mechanism.
    """
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "overnight-state.json"
        _write_fixture_state(state_path, feature_status="paused")

        handle_interrupted_features(state_path)

        loaded = load_state(state_path)
        fs = loaded.features["feat-x"]

        # Status preserved — interrupt.py touches only 'running' features.
        assert fs.status == "paused", (
            f"paused should be preserved by handle_interrupted_features; "
            f"got {fs.status!r}"
        )

        # And the feature is available for re-run in the next round
        # (the pipeline.md "auto-retry on resume" convention).
        assert _count_pending(loaded) == 1, (
            "paused feature should count as pending for next-round dispatch"
        )


# ---------------------------------------------------------------------------
# (b) Deferred feature skipped on resume
# ---------------------------------------------------------------------------

def test_deferred_feature_skipped_on_resume() -> None:
    """A deferred feature is not auto-retried on resume — it awaits humans.

    ``handle_interrupted_features`` leaves deferred status intact, and
    ``_count_pending`` excludes deferred so the feature is not redispatched
    until human intervention flips its status.
    """
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "overnight-state.json"
        _write_fixture_state(state_path, feature_status="deferred")

        handle_interrupted_features(state_path)

        loaded = load_state(state_path)
        fs = loaded.features["feat-x"]

        # Status still deferred — awaiting human decision.
        assert fs.status == "deferred", (
            f"deferred should be preserved by handle_interrupted_features; "
            f"got {fs.status!r}"
        )

        # And the feature is NOT queued for next-round dispatch.
        assert _count_pending(loaded) == 0, (
            "deferred feature must not count as pending; it awaits humans"
        )
