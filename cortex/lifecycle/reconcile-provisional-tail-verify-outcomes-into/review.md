# Review: reconcile-provisional-tail-verify-outcomes-into

## Stage 1: Spec Compliance

### Requirement 1: Parse #359 `outcomes.md`
- **Expected**: extract `(file, id, disposition, commit_subject)` per bullet; APPLIED→verified_survives (verbatim `(commit: ...)` subject, last-`)` extraction); REFUTED→verified_refuted (no commit); totals 31+12=43, distinct=43; every subject resolves via `git log --fixed-strings --grep=<subject>`.
- **Actual**: Ran `parse_359()` live: returns 43 records, 43 distinct `(file,id)`, split 31 verified_survives / 12 verified_refuted — matches `outcomes.md`'s own "Totals: 31 APPLIED, 12 REFUTED, 43 in-scope." The 31 APPLIED rows collapse to 11 distinct subjects (matches spec's stated collapse); ran `git log --fixed-strings --grep=<subject>` for all 11 and every one resolves ≥1. `_extract_commit_subject` uses `line.rfind(")")`, i.e. last-`)` extraction, correctly handling nested `(#359)`/`{s1,s4}` parens.
- **Verdict**: PASS
- **Notes**: none.

### Requirement 2: Parse #360 `verdicts.md` with safe path reconstruction
- **Expected**: reconstruct full path via explicit basename→path map (`SKILL.md` flat, else under `references/`); hard-fail on any reconstructed `(file,id)` absent from ledger; no fuzzy fallback; totals 26, distinct=26, all present in ledger.
- **Actual**: `parse_360()` returns 26 records, 26 distinct `(file,id)`, all `⊆` ledger keys (verified live). `_BASENAME_PATH_MAP_360` is an explicit dict (7 entries, `SKILL.md` flat, rest under `references/`) with a hard `raise ValueError` on an unmapped basename — no fuzzy/basename-only fallback path exists in the code. Injected a synthetic ledger missing one of the 26 real keys via monkeypatch: `parse_360()` raised `ValueError: ... is absent from the ledger` as required. The `## Parity residual` `cortex-resolve-model` bullet is correctly excluded (regex anchors on `<id>(<basename>) → <disposition> — `, which that bullet does not match) — did not become a 27th record.
- **Verdict**: PASS
- **Notes**: none.

### Requirement 3: Resolve #360 short-SHAs at execution
- **Expected**: resolve each bracketed short-SHA via `git rev-parse --verify <sha>^{commit}` then `git show -s --format=%s`; hard-fail on ambiguous/absent.
- **Actual**: `_resolve_commit_subject` implements exactly this two-step resolution and raises `RuntimeError` on `git rev-parse` failure. Verified live: calling it with a bogus SHA (`0000000`) raises `RuntimeError: ... did not resolve to exactly one commit (fatal: Needed a single revision)`. SHA resolution is **not** gated on disposition — the regex search for `[sha]` runs on every record's trailing text regardless of `disposition`, correctly picking up the bracket on the `correction` row (`cd48c762`) as well as `verified_survives` rows, and correctly finding none on `verified_refuted` rows (verified: `parse_360()`'s `s3(SKILL.md)` refuted record has `commit_subject=None`).
- **Verdict**: PASS
- **Notes**: none.

### Requirement 4: Composite-keyed minimal upsert
- **Expected**: key on `(file,id)`; mutate only `status=="unverified"` rows; `verified_survives`→status+`applied_in_commit`; `verified_refuted`→status only; `votes`/`survive_votes`/`verdict_summaries` untouched.
- **Actual**: Diffed the live ledger against `HEAD~1` (pre-fold) programmatically: exactly 69 rows changed, and for every changed row the only fields that differ are `{status, applied_in_commit, corrected_in_commit}` — no row had `votes`/`survive_votes`/`verdict_summaries` touched. Status distribution moved `unverified 90→21`, `verified_survives 166→221` (+55), `verified_refuted 9→23` (+14), matching the plan's checkpoint exactly. Confirmed 0 `verified_refuted` rows carry `applied_in_commit`.
- **Verdict**: PASS
- **Notes**: none.

### Requirement 5: `correction` row handling
- **Expected**: the single `verification-gates.md` `s3` row → `status="verified_refuted"` + `corrected_in_commit` = `cd48c762`'s subject, no `applied_in_commit`.
- **Actual**: Read the live row directly: `{"status": "verified_refuted", ..., "corrected_in_commit": "Correct SHA-computation path and drop path restatement in vgates"}`, no `applied_in_commit` key present. Subject matches `cd48c762`'s actual commit subject (cross-checked via git log). `votes`/`survive_votes`/`verdict_summaries` on this row are untouched (0/0/[]).
- **Verdict**: PASS
- **Notes**: none.

### Requirement 6: Assert-or-raise double-fold guard (status AND provenance)
- **Expected**: raise on either a disagreeing `status` or a disagreeing `applied_in_commit` for an already-non-`unverified` target; agreement on both is a no-op.
- **Actual**: Ran two live injection tests against `validate()`: (a) flipped an already-folded `verified_survives` target's `status` to `verified_refuted` → raised `ValueError: double-fold guard: ... existing status='verified_refuted' ... disagrees with source verdict ...`; (b) left status correct but set `applied_in_commit` to a divergent string on the same target → raised `ValueError: double-fold guard: ... existing status='verified_survives' applied_in_commit='some totally different subject line' disagree[s] ...`. Both fire correctly; `_agrees()`/`check_double_fold()` branch on the raw disposition (verified_survives / correction / plain verified_refuted) to compare the right provenance key per Adversarial #8's requirement.
- **Verdict**: PASS
- **Notes**: none.

### Requirement 7: Pre-flight coherence check that still verifies consistency
- **Expected**: if all 69 targets are already non-`unverified`, run the R6 comparison over all of them first and raise on any disagreement; only exit "already reconciled" with no write if all agree.
- **Actual**: Ran `validate()` against the live (already-folded) ledger with freshly parsed records: raised `AlreadyReconciled("already reconciled (verified consistent), nothing to fold")` — the intended non-error control-flow signal. Ran `apply()` and `dry_run()` live: both correctly caught `AlreadyReconciled` and returned/printed `{"already_reconciled": True, "message": "already reconciled (verified consistent), nothing to fold"}` with exit 0 and no write (`master_candidates.json` unchanged after the call, confirmed via the earlier byte-exact serialization check). The Requirement-6 injection tests above double as the "one disagreeing pre-folded target raises rather than exit 0" case, since `check_double_fold` is invoked from inside the pre-flight partition loop before the `AlreadyReconciled` branch is reached.
- **Verdict**: PASS
- **Notes**: none.

### Requirement 8: Drive folds from explicit child verdict rows, with firing coverage assertion
- **Expected**: parsed set == target-membership set (empty symmetric difference); the 19 `overlaps_ticket`/`reproposal_of` rows + `reviewer-prompt.md s9` remain untouched (byte-identical vs pre-fold).
- **Actual**: Computed the 19 `overlaps_ticket`/`reproposal_of` rows under the child prefixes from `HEAD~1` plus `reviewer-prompt.md s9` (20 total) and diffed each against the live ledger: 0 mutated, all byte-identical. `reviewer-prompt.md s9` confirmed still `verified_survives` with no `applied_in_commit` change (unaffected, as expected — it was never `unverified`). `validate()`'s gates (1)/(2)/(4) ran clean against real data (no raise), and the code confirms gates run as separate structural branches in the documented order — not nested inside an `else`.
- **Verdict**: PASS
- **Notes**: none.

### Requirement 9: Best-effort optimistic write, bounded
- **Expected**: CAS baseline hash compare before write; on mismatch, discard and re-fold from fresh bytes, bounded retry (e.g. 3), abort-and-report on cap exhaustion; atomic temp-file + `os.replace`; serialization `json.dumps(data, indent=1, ensure_ascii=True)`, no trailing newline, byte-exact.
- **Actual**: `serialize(d) == open(LEDGER).read()` returns `True` live; `tail -c 5` on the ledger confirms it ends in `}\n]` with no trailing newline after `]`. Simulated a continuous-writer scenario (every `open()` call returns different bytes) with `fold_once` mocked out: `apply(max_retries=3)` made exactly 6 reads (2 per attempt × 3 attempts) then raised `RuntimeError: CAS write aborted after 3 attempts: ... kept changing underneath the fold. No write was performed.` — confirms the bounded retry/abort path is real, not just documented. `atomic_write` uses `tempfile.mkstemp` in the same directory + `os.replace`, matching the atomicity requirement.
- **Verdict**: PASS
- **Notes**: none.

### Requirement 10: One-off scratch implementation
- **Expected**: reconciler not committed to `cortex_command/`/`bin/`, not a `[project.scripts]` entry; discharge commit touches no such file; only ledger file changed among tracked artifacts.
- **Actual**: `git show --name-only --format= 9eef8b87` lists exactly 5 files: the two backlog `.md` files, `events.log`, `plan.md`, and `master_candidates.json` — no `bin/`, `cortex_command/`, or `pyproject.toml` entries. `scratchpad/` is confirmed untracked (`git status --short` shows `?? scratchpad/`) and not gitignored (`git check-ignore` reports no match), consistent with the plan's explicit-staging caution. `git show --name-only --format= HEAD | grep -c '^scratchpad/'` = 0.
- **Verdict**: PASS
- **Notes**: none.

### Requirement 11: Post-fold ledger integrity
- **Expected**: `(file,id)` unique; target rows carry mapped statuses; no `verified_refuted` row carries `applied_in_commit`; git diff touches only intended rows/fields.
- **Actual**: Verified all four independently against the live ledger: (1) `len(set(keys))==len(keys)` holds; (2) all 69 targets (from `expected_status_map()`) carry their mapped status; (3) 0 `verified_refuted` rows carry `applied_in_commit`; (4) diffed against `HEAD~1` — exactly 69 rows changed, and every changed row's field-diff is a subset of `{status, applied_in_commit, corrected_in_commit}`. Note: re-running the shipped `scratchpad/verify_363_integrity.py` **today** fails its assertion 6 (`changed rows != 69 targets (0)`), because that script diffs the working tree against `git show HEAD:...`, and HEAD now *is* the post-fold commit (9eef8b87) — so the working tree trivially equals HEAD. This is a script-repeatability artifact of a HEAD-relative diff, not a correctness defect in the fold: at the time Task 7 actually ran (per `events.log`, batch 6 at 18:10:58Z, before the Task 9 commit at ~18:15:23Z), HEAD was still the pre-fold commit `bb05c61b`, so the script's assertions were valid and true when it mattered. I re-derived the same check against `HEAD~1` directly and it passes. See Stage 2 for the durability note.
- **Verdict**: PASS
- **Notes**: the integrity script is not safely re-runnable after the discharge commit lands (a HEAD-relative diff against a moving target) — flagged in Stage 2, does not affect the Stage-1 rating since R11's acceptance was genuinely satisfied at execution time and is independently reproducible against `HEAD~1` today.

### Requirement 12: File the residual-debt successor ticket before closing #363
- **Expected**: new backlog ticket referencing #357/#363, describing both (a) the ~89-row `applied_in_commit` backfill and (b) the drifted line anchors; its id cited in #363's completion commit.
- **Actual**: `cortex/backlog/368-backfill-orphaned-applied-in-commit-and-relocate-drifted-ledger-anchors.md` exists, `parent: "357"`, body cites both `#357` and `#363`, and contains both `backfill` (case-insensitive) and `anchor` (case-insensitive) content — confirmed via the exact acceptance one-liner from the plan (`test -f "$T" && grep -q "#357" "$T" && grep -q "#363" "$T" && grep -qi "backfill" "$T" && grep -qi "anchor" "$T"`, all passed). It additionally captures item (c) — the `corrected_in_commit` future-audit convention — beyond the spec's literal (a)/(b), which is a superset, not a gap. The discharge commit message (`9eef8b87`) names `#368` explicitly.
- **Verdict**: PASS
- **Notes**: none.

### Requirement 13: Re-scope + discharge #363
- **Expected**: #363's Done-when no longer asserts the global "no applied candidate remains without an `applied_in_commit`" clause; `status: complete`; commit message names both children + successor id.
- **Actual**: `grep -c "no applied candidate remains without" cortex/backlog/363-*.md` = 0; frontmatter `status: complete`; the Done-when section is explicitly re-scoped ("Re-scoped to this clause-1 condition only... transferred to successor #368"). Commit `9eef8b87`'s message body explicitly names `#359 (43)`, `#360 (26)`, and `#368` (the successor).
- **Verdict**: PASS
- **Notes**: none.

**All 13 requirements PASS. Proceeding to Stage 2.**

## Stage 2: Code Quality

- **Naming conventions**: Consistent with the documented #361/#366 "ledger convention" — `applied_in_commit` as a subject-line string, minimal write shape leaving `votes`/`survive_votes`/`verdict_summaries` alone. Function names (`parse_359`, `parse_360`, `validate`, `target_membership`, `upsert`, `expected_status_map`, `fold_once`, `apply`, `dry_run`) map cleanly onto the plan's task breakdown and the spec's requirement numbers are cited in nearly every docstring/comment, which makes the R-number ↔ code correspondence easy to audit (verified directly against R1–R11 above).
- **Error handling**: Hard-fails (raises, never silent-skips) are exercised, not just asserted in prose: confirmed live that (a) an absent `(file,id)` in `parse_360` raises `ValueError`; (b) an unresolvable short-SHA raises `RuntimeError`; (c) a disagreeing already-folded row (status or provenance) raises `ValueError` from the double-fold guard; (d) CAS retry exhaustion raises `RuntimeError` rather than looping — verified with a mocked continuous-writer scenario making exactly `2×max_retries` reads before aborting. `AlreadyReconciled` is deliberately a non-`ValueError` exception class so callers can distinguish "clean no-op" from "genuine violation" — a good design choice, and both `apply()` and `dry_run()` correctly special-case it.
- **Test coverage**: Every plan Task's stated Verification command was re-run live against the actual state (not trusted from the plan's claims) and reproduced the plan's expected output exactly (43/43/31, 26/26/True, `True 55 13 1`, `ALL_TARGETS_OK 69`, the dry-run report shape, the integrity script's PASS on the correct historical ref). Additionally ran `tests/test_backlog_grep_targets_resolve.py` and the broader `backlog`/`scorecard`/`363`/`368`-scoped test subset (190 tests) — all pass, confirming #368's Done-when prose doesn't trip the grep-target lint the spec's Non-Requirements section warned about.
- **Pattern consistency**: Follows the #358/#361 fold precedent (composite `(file,id)` key, minimal write shape, uncommitted scratch location) faithfully; the `corrected_in_commit` key is a deliberate, spec-approved (R5 option (b)) extension rather than an ad hoc addition, and its forward-compatibility risk (a future exclusion-shaped savings filter over-counting a `corrected` row) is explicitly commented in `upsert()` and tracked in successor #368 item (c).
- **Durability note (not a Stage-1 blocker)**: `scratchpad/verify_363_integrity.py` diffs the working tree against `git show HEAD:<ledger>`. That was correct when it ran (pre-discharge-commit), but the script is a one-shot artifact — re-running it after the discharge commit lands makes the HEAD-relative diff vacuous (working tree == HEAD), which could mislead a future reader who reruns it expecting a live regression check. Since this is an uncommitted, one-off scratch script per R10 (not a maintained tool), this is a documentation/expectation-setting nit rather than a functional defect — worth a one-line comment if the script is ever reused as a template, but not worth a rework here.

## Requirements Drift
**State**: none
**Findings**:
- None. `cortex/requirements/project.md` contains no mentions of `master_candidates.json`, the skill-value-scorecard ledger, provisional-tail reconciliation, or scratch-script conventions — this feature operates entirely within a research-artifact surface the project requirements don't govern, follows the pre-established #358/#361 fold convention, and introduces no new skill/hook/lifecycle-governing behavior. The one genuinely new element (`corrected_in_commit`) is scoped, spec-approved, and its forward-compatibility caveat is tracked in successor #368 — not silently introduced.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
