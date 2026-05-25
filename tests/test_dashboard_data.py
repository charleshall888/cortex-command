"""Unit tests for cortex_command.dashboard.data helpers.

Currently covers the -paused widening on ``compute_slow_flags``: a paused
implement feature must still be subject to slow-flag classification on
its underlying base phase. Without the widening, paused features would
escape the median-duration tripwire silently.
"""

from __future__ import annotations

from cortex_command.dashboard.data import compute_slow_flags


def test_slow_flag_paused() -> None:
    """T8: paused implement features still classify against implement_to_review.

    A feature with current_phase=implement-paused, tier=complex, running
    well past 3x the metrics median for implement_to_review must show up
    in compute_slow_flags. Without removesuffix("-paused"), the closed-set
    membership check at the classifier rejects the paused phase and the
    feature escapes slow-flag detection.
    """
    slug = "paused-feature"
    feature_states = {
        slug: {
            "current_phase": "implement-paused",
            # Phase transition far in the past so the elapsed duration
            # comfortably exceeds 3x the synthetic median below.
            "phase_transitions": [
                {"ts": "2020-01-01T00:00:00Z", "from": "plan", "to": "implement"},
            ],
        },
    }
    overnight = {
        "features": {
            slug: {"status": "running"},
        },
    }
    # Synthetic metrics with a tiny median: any current run will exceed
    # 3 * 1.0 seconds. The exact key matches the classifier output for
    # base implement + complex tier.
    metrics = {
        "features": [
            {"tier": "complex", "phase_durations": {"implement_to_review": 1.0}},
        ],
    }
    pipeline_dispatch = {slug: {"complexity": "complex"}}

    result = compute_slow_flags(
        feature_states=feature_states,
        overnight=overnight,
        metrics=metrics,
        pipeline_dispatch=pipeline_dispatch,
    )

    assert result.get(slug) is True, (
        f"Expected paused implement feature to be flagged slow; "
        f"compute_slow_flags returned {result!r}"
    )


def test_slow_flag_implement_unchanged() -> None:
    """Regression guard: plain implement still classifies after T8 widening."""
    slug = "active-feature"
    feature_states = {
        slug: {
            "current_phase": "implement",
            "phase_transitions": [
                {"ts": "2020-01-01T00:00:00Z", "from": "plan", "to": "implement"},
            ],
        },
    }
    overnight = {"features": {slug: {"status": "running"}}}
    metrics = {
        "features": [
            {"tier": "complex", "phase_durations": {"implement_to_review": 1.0}},
        ],
    }
    pipeline_dispatch = {slug: {"complexity": "complex"}}

    result = compute_slow_flags(
        feature_states=feature_states,
        overnight=overnight,
        metrics=metrics,
        pipeline_dispatch=pipeline_dispatch,
    )

    assert result.get(slug) is True
