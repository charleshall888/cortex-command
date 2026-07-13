---
status: proposed
---

# Gate-time re-hash is the authoritative drift check on the absent branch

## Context

The critical-review drift gate relied on each async reviewer emitting a `READ_OK: <path> <sha>` read-sentinel in its output and treated the sentinel's absence as evidence of drift — invalidating the whole pass when every reviewer was excluded. Reviewers are dispatched via the Agent/Task tool, which returns only a sub-agent's *final message*; a sentinel emitted early (as the reviewer prompt instructed — "before the first `## ` heading") is structurally discarded when the reviewer concludes in a later turn. The failure was therefore systematic, not incidental: **88 `sentinel_absence` events across 33 lifecycles** since the prior #229 fix, on both model tiers, every one `reason: absent` — never a real SHA mismatch. The gate had no way to separate "the self-report was dropped" (benign; the artifact is unchanged) from "the artifact drifted" (real), because it never looked at the file itself — it trusted the reviewer's relayed attestation as the sole drift authority.

## Decision

Demote the read-sentinel to an **advisory** read-attestation, and on the `absent` branch make the gate wrapper's own **re-hash of the pinned artifact the authoritative** drift check:

- **Absence + stable re-hash → pass** (exit 0), recorded as a distinct `sentinel_advisory` event; the reviewer/synth is not excluded and the pass proceeds.
- **Absence + drifted or unreadable re-hash → hard-fail** (exit 3), recorded as `sentinel_absence` — which now fires only on *confirmed* drift.
- **A surviving sentinel with a mismatched SHA still hard-fails**; the `mismatch` and `read_failed` branches are untouched, so read-time attestation is retained on the now-rare occasions the sentinel survives.

The re-hash is layered in the CLI command wrappers (`_cmd_check_artifact_stable` / `_cmd_check_synth_stable`, via an optional `--artifact-path`) rather than in the pure text-parsing verifier, so the verifier's return contracts, its docstring honesty caveats, and its filesystem-free property are untouched, and no new pure-verifier status literal is minted. Re-hash reuses the existing `sha256_of_path` primitive.

## Trade-off

Drift authority for the absent case moves from the reviewer's self-report to **direct measurement by the gate** — deterministic, in-process, and covering every gated site uniformly, rather than depending on an async agent faithfully relaying an early-emitted line through its final message. The accepted cost is a narrow **transient-drift blind spot**: a file that changes and is restored to a byte-identical SHA within one review window (A→B→A) re-hashes clean at gate time and passes, admitting findings produced against the intermediate version — and, in a fanned-out review, admitting both the A-reading and B-reading **cohorts** into the single-artifact synthesizer contract with no per-finding provenance. This boundary is documented rather than engineered against: it is already unprotected today (every failing case is `absent`, so the read-time sentinel guard never actually fires), and closing it would require an edit-then-revert to round-trip to the *exact* pinned bytes within one window — a narrow residual accepted rather than closed.

This mirrors **[ADR-0015](0015-review-could-not-run-vs-dispatch-crash-split.md)**, which split a benign "could-not-run" review outcome from a genuine dispatch crash so the benign case stops discarding verified work. The same shape applies here: a benign dropped-sentinel is split from real drift, and only the real-drift branch retains the hard-fail. ADR-0015 is the precedent for distinguishing a non-run from a failure at a review gate; this ADR extends that discrimination to the drift check itself.

## Consequences

- **`sentinel_absence` narrows to mean confirmed drift.** Downstream consumers and telemetry reads that key on "total-failure = drift or Read failure" stay accurate by construction, but the historical event stream mixes the old (dropped-sentinel) and new (confirmed-drift) meanings; a dated rebaseline note in the events registry records the boundary, and the additive `sentinel_advisory` event carries the benign-omission volume that formerly polluted `sentinel_absence`.
- **Fail-closed on omission is preserved.** A caller that omits `--artifact-path`, or a gate-time file that is unreadable or deleted, degrades to today's exclusion (exit 3) — never a false pass — so the change adds a pass path only when stability is positively proven.
- **The blind spot is a known, documented limit, not a silent one.** Transient same-SHA round-trips (single- and mixed-cohort) are called out in the spec's edge cases; a future consumer must not assume gate-time re-hash certifies each reviewer's read-time state — it certifies the artifact's state at gate time, as an absent-branch tiebreaker only.

This decision clears the ADR three-criteria gate: it is **hard to reverse** (sibling gate sites, the `sentinel_absence`/`sentinel_advisory` telemetry semantics, and downstream consumers all depend on "total-failure = confirmed drift"), **surprising without context** (a maintainer would reasonably assume the emitted sentinel is the drift authority and try to restore it), and the **result of a real trade-off** (self-report attestation vs. direct measurement, with the transient-drift blind spot as the priced-in cost). This ADR — 0028 — is the canonical home for the decision and its trade-off; the implementing change lives in the #376 lifecycle, and the transient-drift boundary is owned by that spec's Edge Cases.
