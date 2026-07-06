---
schema_version: "1"
uuid: 4557df28-4a0f-41f3-8f4a-ccaec5f746b0
title: Backfill orphaned applied_in_commit and relocate drifted ledger anchors in master_candidates.json
status: complete
priority: low
type: chore
created: 2026-07-03
updated: 2026-07-06
parent: "357"
areas: ['skills']
---
## Why

#363 folded the last two #357 provisional-tail children (#359, #360) into `cortex/research/skill-value-scorecard/master_candidates.json`, keyed on `(file, id)`. That satisfied #363's clause-1 Done-when (all children's verdicts reflected as `(file,id)` status entries), but it deliberately did **not** discharge the residual ledger-hygiene debt #363 originally also carried. Rather than hide that debt behind a green checkmark, #363 was re-scoped to clause 1 only and this successor was filed to own the remainder. See #357 (umbrella), #363 (the fold), and #353 (the demonstration that a verdict discoverable only in a lifecycle artifact does not suppress re-proposal).

## Scope

Three residual items against `cortex/research/skill-value-scorecard/master_candidates.json`:

**(a) Global `applied_in_commit` backfill.** Roughly 89 pre-existing `verified_survives` rows (including #353's) carry no `applied_in_commit` provenance string. Backfill each with the subject-line of the commit that actually landed its trim, so realized-savings provenance is complete across the whole ledger — not just the rows folded by #358/#361/#363.

**(b) Relocate drifted line anchors.** Post-trim edits have left `start_line`/`end_line` anchors stale across many rows (pervasive, not isolated) — with #340 s9 and #186 s3 as named instances. Re-derive the anchors against current file contents, or agree a policy that ledger anchors are advisory-only and stop maintaining them.

**(c) Future-audit convention for `corrected_in_commit` rows.** #363 introduced a first-of-its-kind `corrected_in_commit` key on the single correction row (`skills/critical-review/references/verification-gates.md` s3): its status is `verified_refuted`, but the file *was* edited — the proposed trim just did not land. A future re-proposal audit scanning `verified_refuted` rows MUST treat a `corrected_in_commit`-bearing row as already-actioned, not as a live trim candidate to re-propose against the corrected text. Encode that rule wherever the next audit's candidate-selection lives.

## Done when

Every `verified_survives` row carries an `applied_in_commit` provenance string; the drifted line anchors are either re-derived to match current file contents or explicitly reclassified as advisory (with the maintenance obligation dropped); and the re-proposal-audit selection logic honors the `corrected_in_commit` already-actioned convention. This item is the sole owner of clause 2 transferred out of #363.
