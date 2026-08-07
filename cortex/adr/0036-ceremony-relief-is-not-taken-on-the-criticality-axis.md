---
status: accepted
---

# 0036 — Ceremony relief is not taken on the criticality axis

_Decision date: 2026-08-07 (#452 — criticality-pins-the-corpus-to-the)._

## Context

The short-road predicate is `criticality ∈ {high, critical} OR tier == complex` (`project.md:40`, which
carries no ADR back-pointer and no ticket number). #449 and #452 both asked whether relief should come from
the criticality axis. Measured marginal relief from dropping the criticality clause is 5.0% (cortex-command,
17/337) and 2.6% (wild-light, 8/311); dropping the tier clause frees 10.7% and 33.1%. The Plan-skip arm has
never executed in ~650 lifecycle logs. Review returns CHANGES_REQUESTED at 6.5–15.7%, and criticality does
not predict it (16.0% vs 12.8%). A prior narrowing on this axis was reverted 30 minutes after shipping.

## Decision

Ceremony relief is not taken on the criticality axis **while `tier == complex` remains the dominant clause**.
A future rubric or predicate change on that axis requires recorded per-clause justification data plus a
measured CHANGES_REQUESTED rate for the affected class, stated against the corpus baseline. Classification
outcomes are recorded with the clause that produced them so the axis stays auditable.

## Scope and re-open trigger

This decision is conditional on the measured tier distribution, not permanent. The 5.0%/2.6% marginal
figures hold the tier distribution fixed at today's values, where the large majority of lifecycles are
`tier == complex`. Among lifecycles that are *not* `tier == complex`, criticality still pins **24.7%**
(cortex-command) and **9.4%** (wild-light). **So if the tier axis is ever corrected — the change worth 33.1%
on the representative corpus — criticality becomes the binding clause and this decision must be revisited.**
Re-open when the `tier == complex` share falls materially, or when the criticality-only cell exceeds 10% of
lifecycles in the representative corpus.

## Trade-off

This forecloses relief on argument alone and defers it by at least one ticket. It is accepted because the
axis has produced one same-day revert already, because a reduction in Review coverage is not observable after
the fact — the counterfactual defect is never seen — and because 87% of `high` calls in the representative
corpus currently carry no recorded reasoning, making any rubric change there unfalsifiable. The cost is that
the structural defect the prior art identifies (that `high` OR-bundles consequence, reversibility, and
exposure) stays unfixed until the data exists to fix it against — and, per the scope clause, that this
decision must be actively re-checked rather than treated as settled.

## Reading the clause distribution

Phase 2 of this lifecycle starts collecting the per-clause data this decision defers behind. Once
`reconcile-clarify` is emitting tagged `reason` keys, the clause distribution for `criticality_override` rows
is greppable without new tooling:

```
find cortex/lifecycle -name events.log -exec cat {} + | python3 -c "import sys,json,collections; c=collections.Counter(); [c.update([r['reason'].split(':')[0]]) for l in sys.stdin for r in [json.loads(l)] if r.get('event')=='criticality_override' and r.get('reason')]; print(c)" 2>/dev/null
```

A bare `grep … cortex/lifecycle/*/events.log` is **not** valid on two counts: the glob matches 188 of 353
`events.log` files, missing all of `archive/` — while the research behind this decision covered `archive/` —
and `reason` already appears on **16 event types** (92 rows on `sentinel_absence`), with the tier-side
`--tier-reason` flag writing the same key onto `complexity_override`, so an unscoped tally merges both axes.

A successor reading this data must also subtract a population the recording mechanism cannot reach and treat
what remains as a sample, not a census:

- **Already-`high`-seeded lifecycles never produce an override row.** `reconcile-clarify` appends only when
  the desired rank exceeds the current one, so a lifecycle whose backlog frontmatter already says `high`
  produces no row to attach a reason to. Measured bound: 10.5% (cortex-command, 4/38) and 16.7% (wild-light,
  10/60) of modern-era (`lifecycle_start` ≥ 2026-07-01) final-`high` lifecycles are unreachable this way.
- **Partial fill is the expected outcome, not a failure.** On the existing manual-override path, where
  `--reason` already exists, reasons appear on 22–63% of rows (cortex-command 6/21 criticality, wild-light
  10/16); on the `clarify_reconcile` path, before this ticket, 0 of 149 rows carried one. A non-zero clause
  distribution is success — complete coverage is not the bar.

## Cross-references

- Spec: `cortex/lifecycle/criticality-pins-the-corpus-to-the/spec.md` — Requirements 1, 4, 6, 8; Edge Cases;
  Proposed ADR (numbered 0035 there; renumbered to 0036 here, as 0035 was taken by
  `0035-reviewer-brief-emitted-by-verb-not-reference-prose.md` before this ADR landed).
- Research: `cortex/lifecycle/criticality-pins-the-corpus-to-the/research.md`.
- Ticket: #452.
- Glossary: `cortex/requirements/glossary.md` — *tier*, *criticality*, *short road*.
