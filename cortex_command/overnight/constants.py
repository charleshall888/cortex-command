"""Shared constants for the overnight runner.

This module imports only from stdlib. Do not add cortex_command.overnight.*
imports here without checking the Phase 2 import graph.
"""

CIRCUIT_BREAKER_THRESHOLD = 3
SYSTEMIC_FAILURE_THRESHOLD = 3

# Cause-class label for a review-dispatch crash deferral (verdict ERROR or a
# raised dispatch exception). A single systemic review-dispatch failure mode can
# crash multiple features byte-identically, so review crashes feed the systemic
# circuit breaker (R11) alongside the worker-failure pause classes below.
REVIEW_DISPATCH_CRASH = "review_dispatch_crash"

# Error types that indicate systemic infrastructure failures.  Defined here
# (rather than feature_executor) to avoid a circular-import between
# feature_executor and outcome_router.  feature_executor re-exports this name
# so callers can import it from either module.  ``REVIEW_DISPATCH_CRASH`` is a
# member so a review-crash cause_class derived from it is recognized as
# systemic by the threshold derivation (R11).
_SYSTEMIC_ERROR_TYPES = (
    "infrastructure_failure",
    "worker_no_exit_report",
    "worker_malformed_exit_report",
    REVIEW_DISPATCH_CRASH,
)
