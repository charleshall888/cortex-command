"""Shared phase-label rendering — single source of truth for the
wire-format → human-readable label mapping.

Used by:
- ``cortex_command.hooks.scan_lifecycle._phase_label`` (delegating wrapper)
- ``cortex_command.dashboard.app`` (registered as a Jinja filter)

Keep this function pure (no I/O, no side effects). The bash mirror of
the same mapping lives in ``hooks/cortex-scan-lifecycle.sh`` and is
covered by the parity test at ``tests/test_lifecycle_phase_parity.py``.
"""

from __future__ import annotations


def phase_label(encoded_phase: str) -> str:
    """Translate an encoded phase string into a human-readable label.

    Mapping rules:

    * ``"research"``                  -> ``"Research"``
    * ``"specify"``                   -> ``"Specify"``
    * ``"plan"``                      -> ``"Plan"``
    * ``"implement:<x>/<y>"``         -> ``"Implement (<x>/<y> tasks done)"``
    * ``"implement-rework:<n>"``      -> ``"Implement — rework (review cycle <n>)"``
    * ``"review"``                    -> ``"Review"``
    * ``"escalated"``                 -> ``"Escalated (REJECTED — needs user direction)"``
    * ``"complete:awaiting-merge"``   -> ``"Complete (awaiting merge)"``
    * ``"complete"``                  -> ``"Complete"``
    * any ``*-paused`` variant        -> base label + ``" — paused"``
    * any other phase                 -> the encoded phase string verbatim

    Parameters
    ----------
    encoded_phase:
        Wire-format phase string as produced by the canonical encoder.

    Returns
    -------
    str
        The human-readable phase label.
    """

    # Paused recognition: strip the -paused suffix, compute the base label
    # via the existing rules below, then append " — paused".
    if encoded_phase.endswith("-paused"):
        return f"{phase_label(encoded_phase.removesuffix('-paused'))} — paused"
    if "-paused:" in encoded_phase:
        base, _, payload = encoded_phase.partition("-paused:")
        return f"{phase_label(f'{base}:{payload}')} — paused"

    if encoded_phase == "research":
        return "Research"
    if encoded_phase == "specify":
        return "Specify"
    if encoded_phase == "plan":
        return "Plan"
    if encoded_phase.startswith("implement:"):
        progress = encoded_phase[len("implement:") :]
        return f"Implement ({progress} tasks done)"
    if encoded_phase.startswith("implement-rework:"):
        cycle = encoded_phase[len("implement-rework:") :]
        return f"Implement — rework (review cycle {cycle})"
    if encoded_phase == "review":
        return "Review"
    if encoded_phase == "escalated":
        return "Escalated (REJECTED — needs user direction)"
    if encoded_phase == "complete:awaiting-merge":
        return "Complete (awaiting merge)"
    if encoded_phase == "complete":
        return "Complete"
    return encoded_phase
