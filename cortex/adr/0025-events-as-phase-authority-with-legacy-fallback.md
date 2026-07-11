---
status: proposed
---

# Events as phase authority with legacy fallback

_Decision date: 2026-07-11 (374 Phase 4 — phase-authority cutover)._

## Context

For a feature's lifecycle *phase*, the project has carried two derivations that could disagree:

1. **Artifact-presence derivation** (`common.detect_lifecycle_phase`): a state machine over the *presence* of `research.md` / `spec.md` / `plan.md` / `review.md` plus a handful of `events.log` sentinels. It answers "what phase does the working tree look like?" and is the derivation four read-path callers consumed directly — `lifecycle/resolve.py`, `backlog/generate_index.py`, `dashboard/data.py`, and `hooks/scan_lifecycle.py` (two sites) — plus, transitively, the `next` verb (via `resolve.resolve_invocation`).
2. **events.log** ([ADR-0001](0001-file-based-state-no-database.md) / [ADR-0004](0004-multi-step-complete-and-interactive-worktree-lifecycle.md)): the only durable lifecycle state. The 374 build makes `advance` and the composed B1 verb bodies write `phase_transition` (and, additively, `advance_started`/`advance_committed`) rows through the locked primitive, so the log now carries an authoritative record of every machine-driven transition.

When the two disagree — most concretely when a `plan.md` checkbox is hand-edited without an `advance` on a feature that already has machine rows — the reader had no principled rule for which wins. Two independent authorities for one fact is the drift ADR-0018 and the 374 spec set out to close. This cutover picks the winner and records why.

## Decision

**events.log is the authoritative phase source wherever machine rows exist. The artifact-presence derivation demotes to a *legacy fallback*, reached only when the log carries no state-establishing machine row.** The decision is implemented as **one shared resolver** — `common.resolve_lifecycle_phase(feature_dir)` — so there is exactly one place in the read path that decides "events-first, else artifacts":

- A **machine row** is a `phase_transition` (its `to` names the current state) or a terminal event (`feature_complete` / `feature_wontfix` → `complete`; `lifecycle_cancelled` → `cancelled`). `spec_approved`/`plan_approved` are deliberately **not** machine rows: a standalone (legacy) `refine` emits them *without* the `phase_transition` edge, so an approval-only log correctly falls through to the artifact fallback.
- When a machine row is present, the events-derived state supersedes the artifact-derived `route`/`phase`/`paused`. `checked`/`total`/`cycle` are always read from the artifact detector — plan progress and the review-cycle count are read-side artifact facts, not events-derived *state* — so every caller's consumed fields keep their shape.
- The four direct callers are migrated to `resolve_lifecycle_phase`; `next` inherits events-authority through `resolve.resolve_invocation`, so the whole read path shares one oracle by construction (spec R15).

The two transition-**decision** writers (`overnight/advance_lifecycle.py`, `pipeline/review_dispatch.py`) are **folded, not sanctioned** — their transition decisions route through the table/B1 bodies (spec R15, landed under Task 17a). "Sanctioned" remains available only for non-decision writers (the telemetry/judgment rows of [ADR-0020](0020-lifecycle-event-emission-contract.md)'s exempt class). Dual authority for the phase fact is refused.

## Permanent exceptions (named)

Two derivations are **permanently** out of scope for this cutover and keep their own phase logic by design:

- **`claude/statusline.sh`** keeps its own bash-side artifact derivation, pinned to `detect_lifecycle_phase` by `tests/test_lifecycle_phase_parity.py`. Rationale: the statusline renders under a sub-500ms budget with no Python import, so it cannot call the shared resolver. It is a *display* surface, not a decision surface; a stale render is cheap. This is a permanent exception, not a migration-window one.
- **The pipeline-run FSM** (overnight run-state, `overnight/state.py` and the review-dispatch run lattice) owns its own run-phase state and is untouched. It governs a *run's* progress, not a *feature's* lifecycle phase, and is not a consumer of `resolve_lifecycle_phase`.

The `scan_lifecycle` mismatch detector (`_is_terminal_mismatch`) runs **permanently** as the divergence tripwire — it is not migration-window scaffolding. Under events-authority it reports events-vs-backlog divergence forever, so a hand-edited artifact (which the resolver now overrides in favor of events) still surfaces for a human.

## Trade-off (stated honestly)

**This cutover forfeits the cheap prose-side rollback.** Before it, "undo the routing change" was a git revert of skill prose. After it, phase authority lives in events.log + the wheel resolver, and the artifact tree is no longer the fallback anyone can trust to override events. There is no one-file revert that restores artifact-authority without reintroducing the dual-authority drift the decision exists to kill.

**The standing exit is roll-forward, not revert.** The documented roll-forward procedure (spec R18 / Task 20) — prose-side de-routing, verbs left callable, vocabulary quarantined as `deprecated-pending-removal` registry rows with a named owner, dual-emission through the grace window — is the sanctioned way out, and the permanent mismatch detector is the tripwire that tells an operator a roll-forward is warranted. We accept a costlier exit in exchange for one predictable oracle with an explainable derivation trace.

## Rejected alternatives

- **Keep artifact-presence authoritative (rejected).** Leave `detect_lifecycle_phase` as the oracle and treat events as advisory. Rejected: hand-edited or half-written artifacts then silently define phase, which is the exact `#209`/`#075`-shape divergence the machine loop was built to end; events.log is already the only *durable* state, so making it authoritative for phase removes a second source of truth rather than adding one.
- **Migrate every consumer including statusline (rejected).** Route the statusline through the shared resolver too, for a single derivation with zero exceptions. Rejected on the render-latency budget: the statusline cannot pay a Python import per prompt, and a display surface does not need decision-grade authority. Parity-pinning it to the fallback is the honest bound.
- **Preserve the prose-side revert as the rollback (rejected).** Keep artifact derivation wired as a live override so a revert stays cheap. Rejected: a live artifact override *is* dual authority — it reintroduces the drift under a different name. Forfeiting the cheap revert is the price of the single oracle, and roll-forward is the deliberate replacement.

## Three-criteria gate clearance

- **Hard to reverse.** Phase authority becomes a property of events.log + the wheel resolver that four callers and the `next` verb depend on; unwinding it means re-wiring every caller back to artifact-authority and re-litigating which source wins — a coordinated multi-call-site change, and one that reintroduces the dual-authority drift. The forfeited-revert trade-off is itself the hard-to-reverse signal.
- **Surprising without context.** A contributor meeting `resolve_lifecycle_phase` would reasonably ask why `detect_lifecycle_phase` is still called inside it and still called directly by the statusline, and might "simplify" by collapsing them — not knowing the artifact path is a deliberately-kept legacy fallback and the statusline a deliberately-kept permanent exception.
- **Real trade-off.** Single-oracle events-authority (with a forfeited cheap rollback and a roll-forward standing exit) was chosen over keeping artifact-authority, migrating every consumer, and preserving the revert — each rejected for stated reasons above.
