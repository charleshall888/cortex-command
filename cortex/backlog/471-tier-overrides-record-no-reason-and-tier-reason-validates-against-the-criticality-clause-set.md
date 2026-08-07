---
schema_version: "1"
uuid: 392984f6-c998-4e17-9a2d-128716e9f6e0
title: Tier overrides record no reason, and --tier-reason validates against the criticality clause set
status: complete
priority: medium
type: feature
created: 2026-08-07
updated: 2026-08-07
tags: ['lifecycle', 'tiering', 'criticality']
areas: ['lifecycle', 'skills']
complexity: moderate
criticality: high
spec: cortex/lifecycle/tier-overrides-record-no-reason-and/spec.md
lifecycle_phase: complete
---
## Why

#452 gave `reconcile-clarify` optional clause-tagged override reasons so the criticality axis could be audited, and wired only `--criticality-reason` into `skills/refine/SKILL.md` Step 4. `--tier-reason` shipped on the verb, tested by hand, with **zero tests and zero callers**.

The measured gap it would close is slightly *larger* than the one #452 just closed. Reason-less rows at `gate=clarify_reconcile`, counted across both corpora with the ADR-0036 recipe:

| Event | cortex-command | wild-light | total |
|---|---|---|---|
| `criticality_override` (closed by #452) | 72 | 79 | **151** |
| `complexity_override` (still open) | 54 | 99 | **153** |

Both sit at 0% reason fill. For contrast the manual-verb path, where `--reason` has existed all along, fills at 39% (21 of 54 rows).

This matters more than the criticality half did. ADR-0036's re-open trigger is explicitly *"if the tier axis is ever corrected — the change worth 33.1% on the representative corpus — criticality becomes the binding clause and this decision must be revisited."* Tier reasoning is the evidence that decision will be made against, and it is currently not being recorded anywhere at the moment the tier is first ratcheted off its seed.

## Role

Give the tier axis its own clause vocabulary and wire it into the reconcile call, so `complexity_override` rows written at Clarify carry why.

## Integration

`--tier-reason` currently validates against `_ALLOWED_REASON_CLAUSES` in `cortex_command/refine.py` — `reversibility`, `exposure`, `consequence`, `other`. Those four are derived from `skills/refine/references/clarify.md` §5.3's **criticality** OR-bundle. They are the wrong set for tier: §5.2 bundles different things — *"competing designs, a blast radius you can't enumerate, or a precedent others follow"*.

#452's plan recorded this as an accepted Risk, predicting a tier author would reach for `design-fork:` and be rejected. The cycle-2 review confirmed it by running exactly that tag.

## Edges

- **Reusing the criticality set was deliberate in #452**, chosen because R6 was written unscoped and `other:` is an escape hatch. Reopening it needs the §5.2-derived set, not a second free-text field.
- **The short-circuit is in scope and only here.** `refine.py:353` validates with `or`, so when both flags carry bad tags only the first is reported — two fix round-trips. It is unreachable today (zero callers on `--tier-reason`) and becomes reachable exactly when this ships. Two-line fix in the function this ticket already edits; do not file it separately.
- **Do not widen `--complexity` to `--tier`.** The verb mixes vocabularies (`--complexity` sets what the glossary now calls tier, and writes `complexity_override`). Renaming is a breaking CLI change across many callers for cosmetics; the cycle-2 review rated it non-blocking and it stays out.
- **The `noop` arm drops a supplied reason silently** — already-reconciled or a suppressed downgrade appends nothing. Correct, matches today's behavior, not a defect to fix here.
- **The seeded-`high` blind spot has a tier twin.** A ticket whose frontmatter already names the final tier never ratchets, so no row exists to carry a reason. #452 measured 10.5%/16.7% for criticality; the tier equivalent is unmeasured and this ticket should state it rather than assume it away.

## Touch points

- `cortex_command/refine.py` — `_ALLOWED_REASON_CLAUSES`, `_reason_clause_ok`, the `or` short-circuit at `:353`, and the `reconcile-clarify` parser
- `skills/refine/references/clarify.md` §5.2 — source of the tier clause vocabulary (read, not edited)
- `skills/refine/SKILL.md` Step 4 — the invocation to extend; note the contiguous-substring pins in `tests/test_refine_reconcile_clarify.py:333-339`
- `tests/test_refine_reconcile_clarify.py` — the five #452 tests are the template; assert exact exit codes and positive row shapes, never absence alone
- `cortex/adr/0036-ceremony-relief-is-not-taken-on-the-criticality-axis.md` — the clause-distribution recipe and its re-open trigger
- `cortex/requirements/project.md` — the "Override-reason clause vocabulary" constraint names the three co-edit sites; adding tags edits all of them
