"""Resume-path tests for the Python overnight runner.

Replaces the prior structural grep against the legacy shell runner with behavioral
assertions against the Python API:

  * ``runner._count_pending`` counts ``paused`` features as pending so
    resumed sessions re-dispatch them in the next round.
  * ``runner._count_pending`` returns zero when every feature is in a
    terminal status that should not block round completion.
  * ``interrupt.handle_interrupted_features`` resets paused-feature
    status for resume (task spec) while leaving deferred features
    intact for human decision.

Note on spec/code divergence: per the task spec, paused features
should be reset to ``pending`` by ``handle_interrupted_features`` on
resume. The current ``interrupt.py`` implementation resets only
``running`` → ``pending`` and preserves ``paused`` as-is (the
round-dispatch layer counts ``paused`` as pending via
``runner._count_pending`` to achieve the auto-retry behavior). The
assertion below is written per the spec text; if it fails, the spec
and the code have diverged — flag it rather than silently adjusting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.overnight.interrupt import handle_interrupted_features
from cortex_command.overnight.runner import _count_pending
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    load_state,
    save_state,
)


def _write_state(state_path: Path, features: dict[str, str]) -> None:
    """Write a minimal overnight state with features at the given statuses."""
    state = OvernightState(
        session_id="overnight-2026-04-24-resume",
        plan_ref="cortex/lifecycle/overnight-plan.md",
        features={
            name: OvernightFeatureStatus(status=status)
            for name, status in features.items()
        },
    )
    save_state(state, state_path)


def test_count_pending_includes_paused(tmp_path: Path) -> None:
    """``_count_pending`` treats paused as pending (resume auto-retry hook)."""
    state_path = tmp_path / "overnight-state.json"
    _write_state(state_path, {"feat": "paused"})
    loaded = load_state(state_path)
    assert _count_pending(loaded) >= 1


def test_count_pending_zero_for_merged(tmp_path: Path) -> None:
    """``_count_pending`` returns 0 when every feature is merged."""
    state_path = tmp_path / "overnight-state.json"
    _write_state(state_path, {"feat": "merged"})
    loaded = load_state(state_path)
    assert _count_pending(loaded) == 0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Spec/code divergence: Task 11 spec says "
        "handle_interrupted_features should reset paused -> pending on "
        "resume. Current interrupt.py resets only running -> pending; "
        "paused is preserved, and runner._count_pending counts paused "
        "as pending to achieve the auto-retry behavior at the round-"
        "dispatch layer. Flagged per the task's architectural-context "
        "instruction rather than silently adjusted."
    ),
)
def test_handle_interrupted_resets_paused_preserves_deferred(tmp_path: Path) -> None:
    """Paused features reset to ``pending`` on resume; deferred left intact.

    Per the task spec for Task 11: ``handle_interrupted_features`` should
    reset paused → pending so the round loop picks them up, while
    leaving deferred features in place for human review. Expected to
    flag a spec/code divergence if the current implementation preserves
    paused status instead of resetting it (see module docstring).
    """
    state_path = tmp_path / "overnight-state.json"
    _write_state(
        state_path,
        {"feat-paused": "paused", "feat-deferred": "deferred"},
    )

    handle_interrupted_features(state_path)

    loaded = load_state(state_path)
    assert loaded.features["feat-paused"].status == "pending", (
        "paused feature should be reset to pending on resume "
        "(spec says handle_interrupted_features does this reset)"
    )
    assert loaded.features["feat-deferred"].status == "deferred", (
        "deferred feature must remain deferred (awaits human decision)"
    )
