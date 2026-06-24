---
schema_version: "1"
uuid: 2d207318-fd0c-4102-aafa-6a5ddb1b2bf3
title: 'Review-gate flag-coherence: a feature_deferred event asserted merge_reverted + could_not_run + review_dispatch_crashed together'
status: complete
priority: low
type: bug
created: 2026-06-23
updated: 2026-06-24
lifecycle_phase: research
lifecycle_slug: review-gate-flag-coherence-a-feature
complexity: complex
criticality: high
spec: cortex/lifecycle/review-gate-flag-coherence-a-feature/spec.md
areas: ['overnight-runner']
---
## Why

Surfaced during the #319 research/critical-review pass. The overnight incident
`overnight-2026-06-23-0605` (feature `occlusion-field-max-ray-steps24-under`) emitted a
`feature_deferred` event carrying `merge_reverted: true`, `could_not_run: true`, **and**
`review_dispatch_crashed: true` **simultaneously**. Under ADR-0015 and the installed code these are
mutually exclusive: a could-not-run review (`success == True`, no usable verdict) **preserves** the
merge (`merge_reverted == False`) under cause-class `review_no_artifact`, while a genuine dispatch
crash (`success == False`) reverts and is `review_dispatch_crashed` under `review_dispatch_crash` — and
`review_dispatch_crashed` is set only when the merge was NOT preserved. An event asserting all three at
once should not be reachable.

This matters beyond bookkeeping: the morning report and the integration-PR marker key on these flags
to decide whether unreviewed code was preserved or reverted, so an incoherent flag set can mislead the
operator's merge decision. It also left #319's path-divergence diagnosis resting on selectively trusting
`could_not_run` while disregarding the contradicting `review_dispatch_crashed` from the same event.

## Finding (2026-06-23 — post-#319 code investigation; downgraded medium → low)

The incoherent combination is **not reachable in the current code**, so the (a)/(b) question below is
resolved toward **(a): a stale / pre-ADR-0015 build artifact**, not a live defect. All three review-gate
write sites set the discriminators mutually exclusively:

- The in-band could-not-run path at each site routes through `_set_review_error_detail_flags`
  (`outcome_router.py:1024`), which sets `could_not_run` + `merge_reverted` and, by contract, **never**
  sets `review_dispatch_crashed`.
- The crash-`except` at each site computes `preserved = rr is not None and rr.could_not_run`, then
  `if preserved:` sets `could_not_run=True` / `merge_reverted=False` while `else:` sets
  `review_dispatch_crashed=True` — disjoint branches. Sites: recovery (`outcome_router.py:1238-1257`),
  repair (`:1622-1636`), primary (`:1996-2018`).

So a `feature_deferred` asserting `could_not_run` **and** `review_dispatch_crashed` together cannot be
produced today; the incident event is almost certainly from a build predating the
`_set_review_error_detail_flags` consolidation + `preserved` branching (#314 / ADR-0015). **Not
empirically nailed:** the actual wheel version running at incident time is still unverified (uv receipt
mtime postdates the run) — that's the only remaining confirmation of (a), and it is low-value to chase.

## Scope / role

The (a)/(b) determination is resolved toward (a) (see Finding). The reproducer is already prevented,
so this ticket is **regression insurance, not a live fix**. Remaining ask: coherence is currently
enforced by the same `if preserved/else` discipline **replicated across three separate sites** plus a
shared helper — correct today, but each site independently re-derives the rule and nothing rejects an
incoherent combination if a fourth site or a future edit ever sets the flags wrong. Establish a single
authority for the three flags (or a `_set_review_error_detail_flags`-adjacent assertion that **loudly
rejects** `could_not_run && review_dispatch_crashed` at the write boundary) so the coherence cannot
silently regress.

## Boundary

This is the flag-emission coherence question only. The preserve-vs-revert **policy** decided in
ADR-0015 is not being reopened — the ask is that the emitted flags faithfully reflect whichever policy
branch actually ran. The #319 path-contract fix is separate and does not depend on this.

## Touch-points

- `cortex_command/pipeline/review_dispatch.py` — where `could_not_run` / `review_dispatch_crashed` /
  `merge_reverted` originate on the deferral path.
- `cortex_command/overnight/outcome_router.py` — the `_set_review_error_detail_flags` helper and the
  crash/except branches that set these flags per site.
- `bin/.events-registry.md` — the `feature_deferred` field-additive entries for the three flags.
- Editing `cortex_command/pipeline/` or `cortex_command/overnight/` requires its own lifecycle.
- Related: #314 (gate robustness), #319 (path-contract fix), ADR
  `cortex/adr/0015-review-could-not-run-vs-dispatch-crash-split.md`.

## Evidence

`overnight-2026-06-23-0605`, feature `occlusion-field-max-ray-steps24-under`: the `feature_deferred`
event in the feature's `events.log` carries `merge_reverted: true`, `could_not_run: true`, and
`review_dispatch_crashed: true` together. ADR-0015 and `outcome_router.py` (the
`_set_review_error_detail_flags` helper plus the except branches) treat these as mutually exclusive.
