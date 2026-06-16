#!/usr/bin/env python3
"""Deterministic fail-loud verdict state machine for /pr-review.

Implements the Verdict derivation from spec `## Grounding & Verdict Vocabulary`
(Req 7). Pure stdlib, no `cortex_command` import — this is a plugin-local unit
that must run standalone.

The single reviewer agent emits findings using the schema owned by
`references/output-format.md`. `references/protocol.md` detects the four runtime
degradation signals, then pipes `{"findings": [...], "runtime_signals": [...]}`
to this script's stdin to compute the terminal verdict.

Degradation signals 5 (`surfaced_none_grounded`) and 6 (`evidence_weak_blocking`)
are NOT passed by the caller — they are derived here from `findings`. The caller
passes only the four runtime signals it can detect (`RUNTIME_SIGNALS`).
"""

import json
import sys

# The four runtime degradation signals the caller (protocol.md) detects and
# passes in. Authoritative single source: the contract test imports this
# constant rather than re-typing the strings, and protocol.md references it.
# Signals 5 and 6 are NOT here — they are derived internally from `findings`.
RUNTIME_SIGNALS = (
    "reviewer_error",       # signal 1: reviewer errored/timed out/unparseable
    "diff_missing",         # signal 2: diff missing or empty
    "grounding_incomplete",  # signal 3: grounding step could not complete
    "metadata_fetch_failed",  # signal 4: PR metadata fetch failed
)


def surfaced_none_grounded(findings: list[dict]) -> bool:
    """Signal 5: ≥1 surfaced finding but zero are grounded."""
    if not findings:
        return False
    return not any(f.get("grounding") == "grounded" for f in findings)


def evidence_weak_blocking(findings: list[dict]) -> bool:
    """Signal 6: any evidence-weak finding with severity == blocking."""
    return any(
        f.get("grounding") == "evidence-weak" and f.get("severity") == "blocking"
        for f in findings
    )


def derive_verdict(findings: list[dict], runtime_signals: set[str]) -> str:
    """Compute the terminal verdict, evaluated top-to-bottom.

    1. Any grounded finding with severity == blocking → REQUEST_CHANGES.
    2. Else if any degradation signal fired (runtime, or derived 5/6) →
       REVIEW_INCONCLUSIVE.
    3. Else → APPROVE.
    """
    if any(
        f.get("grounding") == "grounded" and f.get("severity") == "blocking"
        for f in findings
    ):
        return "REQUEST_CHANGES"

    if (
        runtime_signals
        or surfaced_none_grounded(findings)
        or evidence_weak_blocking(findings)
    ):
        return "REVIEW_INCONCLUSIVE"

    return "APPROVE"


def main() -> None:
    payload = json.load(sys.stdin)
    findings = payload["findings"]
    runtime_signals = set(payload["runtime_signals"])
    print(derive_verdict(findings, runtime_signals))


if __name__ == "__main__":
    main()
