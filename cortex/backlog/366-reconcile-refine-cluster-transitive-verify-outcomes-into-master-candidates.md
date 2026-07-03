---
schema_version: "1"
uuid: 831e9f7c-28a9-4842-b09f-305d4a978f1e
title: Reconcile #357 refine-cluster + transitive verify-outcomes into master_candidates.json (key on file,id)
status: backlog
priority: low
type: chore
tags: ['skill-value-scorecard']
areas: ['skills']
created: 2026-07-03
updated: 2026-07-03
parent: "357"
---
## Why

Child #361 (the refine-cluster + transitive-tail provisional-tail sweep) recorded 42 verify verdicts but deliberately did **not** write them into `cortex/research/skill-value-scorecard/master_candidates.json` — per its spec (Req 12) the ledger write-back is deferred to the shared #357 reconciliation so parallel sessions never contend on the ledger. Without a tracked discharge, a recorded verdict evaporates: a `verified_refuted` produces no diff, and a `verified_survives` is undiscoverable to a future audit until it lands as a `status` field in the ledger. This is the demonstrated #357 debt — only ~8/96 `verified_survives` rows across the whole audit carry `applied_in_commit`; the promised single reconciliation pass has never run. This item is the tracked follow-up (sibling of the general #363), scoped to *this child's* specific delta and its manufactured line-anchor drift.

## Scope

Fold this child's `(file,id)`-keyed delta into `master_candidates.json`:

- **Delta source**: `cortex/lifecycle/sweep-provisional-tail-refine-cluster-transitive/verify-outcomes.md` — 42 rows, one per candidate.
- **Key on the composite `(file,id)`, never the bare `id`.** The 42 rows carry only **23 distinct ids** (e.g. `s3`×5, `file-compress`×4), so keying on the non-unique `id` alone would silently overwrite ~**19** of the 42 rows. The correct key is the composite `(file,id)` (42 distinct pairs).

## Manufactured cross-ticket anchor drift (must re-locate by heading+token)

This child's trims to `clarify.md` and `clarify-critic.md` shifted the un-applied ledger line anchors of two rows owned by other tickets:

- **#340's s9** — `clarify.md`, heading `### 6. Research Sufficiency Criteria` (`overlaps_ticket: #340`). This child's trims *above* that section moved it.
- **#186's s3** — `clarify-critic.md`, heading `## Parent Epic Loading (orchestrator)` (`overlaps_ticket: #186`). Same drift.

The span text of both was left byte-identical (checked by content-identity, not diff-line-range), but their `start_line`/`end_line` in the ledger are now stale. The reconciler — and #340 / #186 themselves — **must re-locate those rows by heading + pinned token, not by line number.**

## Done when

This child's 42 verify/refute verdicts are reflected as composite-`(file,id)`-keyed `status` entries in `master_candidates.json`, every applied candidate carries an `applied_in_commit` hash, and #340's s9 / #186's s3 ledger anchors are re-located by heading+token.
