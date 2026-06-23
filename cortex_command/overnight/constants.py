"""Shared constants for the overnight runner.

This module imports only from stdlib. Do not add cortex_command.overnight.*
imports here without checking the Phase 2 import graph.
"""

CIRCUIT_BREAKER_THRESHOLD = 3
SYSTEMIC_FAILURE_THRESHOLD = 3

# Cause-class label for a genuine review-dispatch crash deferral (the review
# agent failed — ``success == False`` / a raised dispatch exception). A single
# systemic review-dispatch failure mode can crash multiple features
# byte-identically, so review crashes feed the systemic circuit breaker (R11)
# alongside the worker-failure pause classes below.
REVIEW_DISPATCH_CRASH = "review_dispatch_crash"

# Cause-class label for a could-not-run review deferral (the review agent
# completed — ``success == True`` — but produced no usable verdict, so the
# resolved verdict is the synthetic ``ERROR`` and the merge is PRESERVED). A
# systemic adherence failure (many reviews producing no artifact in one batch)
# should still pause the batch via the breaker, but under a distinct cause-class
# so operators can tell "the review tooling keeps producing no artifact" apart
# from "the review dispatch keeps crashing" (spec R7). The threshold counts the
# aggregate of both classes; this label only distinguishes the kinds in the
# emitted ``PIPELINE_SYSTEMIC_FAILURE`` event.
REVIEW_NO_ARTIFACT = "review_no_artifact"

# Error types that indicate systemic infrastructure failures.  Defined here
# (rather than feature_executor) to avoid a circular-import between
# feature_executor and outcome_router.  feature_executor re-exports this name
# so callers can import it from either module.  ``REVIEW_DISPATCH_CRASH`` and
# ``REVIEW_NO_ARTIFACT`` are members so a review cause_class derived from either
# is recognized as systemic by the threshold derivation (R11), which filters the
# combined arrival list against this tuple.
_SYSTEMIC_ERROR_TYPES = (
    "infrastructure_failure",
    "worker_no_exit_report",
    "worker_malformed_exit_report",
    REVIEW_DISPATCH_CRASH,
    REVIEW_NO_ARTIFACT,
)
