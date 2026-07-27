"""Critical-review support verbs.

Scope is deliberately small: resolving the active lifecycle feature from a
session id, and writing the B-class residue sidecar the morning report reads
(``cortex_command/overnight/report.py`` :func:`render_critical_review_residue`).

The former SHA-drift verification gate (``prepare-dispatch``,
``check-artifact-stable``, ``check-synth-stable``, ``record-exclusion``) was
retired: across the 2026-05..2026-07 event corpus it produced 104 over-fires
against 2 true detections, had no telemetry consumer, and cost three lifecycles
of false-positive repair.
"""
