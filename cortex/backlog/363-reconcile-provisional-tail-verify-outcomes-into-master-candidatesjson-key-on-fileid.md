---
schema_version: "1"
uuid: 8b39eaa5-881b-4430-8dca-022a82480f5a
title: Reconcile provisional-tail verify outcomes into master_candidates.json (key on file,id)
status: backlog
priority: low
type: chore
created: 2026-07-03
updated: 2026-07-03
parent: "357"
---
## Why

#358 (provisional-tail sweep of `cortex/requirements`) resolved OQ3 to **direct-write**: it wrote its own 31 `verified_survives` rows — keyed on the composite **`(file, id)`** — into `cortex/research/skill-value-scorecard/master_candidates.json`, each with an `applied_in_commit` hash, discharging its own reconciliation debt in-batch. Its `(file,id)`-keyed delta lives at `cortex/lifecycle/sweep-provisional-tail-cortex-requirements-area/verify-outcomes.md`.

The broader reconciliation debt remains for the OTHER provisional-tail children and prior batches:
- #359 / #360 / #361 (still `status: refined`; their ledger rows not yet written).
- #353's applied candidates (`verified_survives` with no `applied_in_commit` — only 8/96 rows ever carried it).

The promised single #357 reconciliation pass has never run. A verdict recorded only in a lifecycle artifact or commit is undiscoverable by a future audit (demonstrated by #353): re-proposal is only actually suppressed once the verdict lands as a `status` field in `master_candidates.json`.

## Scope

When the sibling children complete, ensure their verify/refute verdicts land as `status` entries in `master_candidates.json`. The reconciler **MUST key on the composite `(file, id)`** — `id` alone is non-unique (12 ids over 32 rows in #358 alone; `s3` appears 31×, `s4` 26× across the full ledger), the plausible cause of the prior 0-for-1 failure. #358's own rows are already discharged; this item tracks the remaining children.

## Done when

All provisional-tail children's verify outcomes are reflected as `(file,id)`-keyed `status` entries in `master_candidates.json`, and no applied candidate remains without an `applied_in_commit`.