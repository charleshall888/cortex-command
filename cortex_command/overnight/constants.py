"""Shared constants for the overnight runner.

This module imports only from stdlib. Do not add cortex_command.overnight.*
imports here without checking the Phase 2 import graph.
"""

CIRCUIT_BREAKER_THRESHOLD = 3
SYSTEMIC_FAILURE_THRESHOLD = 3

# Error types that indicate systemic infrastructure failures.  Defined here
# (rather than feature_executor) to avoid a circular-import between
# feature_executor and outcome_router.  feature_executor re-exports this name
# so callers can import it from either module.
_SYSTEMIC_ERROR_TYPES = (
    "infrastructure_failure",
    "worker_no_exit_report",
    "worker_malformed_exit_report",
)
