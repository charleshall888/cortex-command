# Skill Value Scorecard — ledger conventions

This directory is the closed skill-value audit's data home (#347 epic; sweeps
#348–#353, #357–#361, reconciliations #363/#366/#368). `report.html` is the
human-readable audit report; `master_candidates.json` is the per-candidate
ledger; `dup_groups.json` lists cross-file duplication groups.

## Ledger schema (`master_candidates.json`)

One row per trim candidate, keyed on `(file, id)`. Load-bearing fields:

- `status` — `verified_survives` (adversarially verified and applied),
  `verified_refuted` (verified and rejected; do not re-propose), or
  `unverified` (excluded from execution: overlaps an open ticket or is a
  re-proposal — see `overlaps_ticket` / `reproposal_of`).
- `applied_in_commit` — subject line of the commit that landed the trim.
  Present on every `verified_survives` row (backfilled by #368).
- `corrected_in_commit` — subject line of a commit that edited the row's
  span *without* landing the trim as proposed (the proposal was refuted but
  investigation surfaced a correction). See the convention below.

## Line anchors are advisory (frozen at audit baseline)

`start_line`/`end_line` describe the file as of the audit baseline commit
`2e703bea` (2026-07-02, "Add skill value scorecard audit report and candidate
data"). Applied trims removed or moved those spans, so the anchors no longer
match current file contents **by design**. Per the #368 decision they are
advisory-historical and are NOT maintained: to see what a row referred to,
read the file at `2e703bea` (`git show 2e703bea:<file>`); do not "fix"
anchors against current contents.

## Rules for any future re-proposal audit

1. **The ledger is the suppression surface.** A verdict recorded only in a
   lifecycle artifact does not suppress re-proposal (#353 demonstrated
   this); fold outcomes into this ledger, keyed on `(file, id)`.
2. **`verified_refuted` + `corrected_in_commit` means already-actioned.**
   The file was edited by the named commit; treat the row as resolved — do
   not re-propose a trim against the corrected text. (First instance:
   `skills/critical-review/references/verification-gates.md` s3.)
3. **`verified_refuted` without `corrected_in_commit` means keep.** The span
   was adversarially confirmed load-bearing; re-proposing it needs new
   evidence, not a re-run of the same lens.
4. The corpus is at its audited floor (campaign closed) — a new audit needs
   a changed corpus or a genuinely new evaluation lens to be worth running.
