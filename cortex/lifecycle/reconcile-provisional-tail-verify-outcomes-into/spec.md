# Specification: reconcile-provisional-tail-verify-outcomes-into (#363)

## Problem Statement

The #357 provisional-tail audit produced four children (#358–#361), each recording verify/refute verdicts on candidate skill-prose trims. A verdict only actually suppresses future re-proposal once it lands as a `status` field in `cortex/research/skill-value-scorecard/master_candidates.json`; a verdict left only in a lifecycle artifact is undiscoverable to a later audit (demonstrated by #353). #358 (direct-write) and #361 (via sibling #366, commit `16cc9429`) are already folded. This feature folds the **two remaining children** — #359 (discovery + backlog-author, 43 rows) and #360 (critical-review, 26 rows) — into the ledger, keyed on the composite `(file, id)`, so their 69 verdicts become discoverable and re-proposal is suppressed.

**Scope reconciliation with #363's Done-when (critical-review A1):** #363's original Done-when has two clauses — (1) all children's verdicts reflected as `(file,id)` status entries, **and** (2) "no applied candidate remains without an `applied_in_commit`." This feature satisfies clause 1 (in aggregate: #358 + #361/#366 + #359/#360 here) but **deliberately does not satisfy clause 2** — ~89 pre-existing orphaned `verified_survives` rows (incl. #353's) remain. To avoid a false completion that hides that debt behind a green checkmark, this feature (a) files a named successor ticket for the residual before closing, and (b) re-scopes #363's Done-when to clause 1 only. See R12/R13.

## Phases
- **Phase 1: Fold** — parse both children, reconstruct/resolve keys and provenance, and upsert the 69 verdicts into the ledger with full integrity guards.
- **Phase 2: Verify & discharge** — verify the post-fold ledger, file the residual-debt successor, re-scope + close #363.

## Requirements

**Priority (MoSCoW)**: R1–R11 are all **Must-have** — this mutates the correctness ledger, so each is a guard whose omission risks silent data corruption (wrong-row writes, lost updates, false provenance); there is no meaningful Should-have tier for a correctness-critical fold. R12–R13 (successor-ticket + re-scoped close) are **Must-have** to keep the residual debt tracked and avoid a false completion. The **Won't-do** set is the explicit Non-Requirements below.

1. **Parse #359 `outcomes.md`**: extract one record per bullet as `(file, id, disposition, commit_subject)`. Rows carry full ledger paths already. `APPLIED → verified_survives` (with the verbatim `(commit: <subject>)`), `REFUTED → verified_refuted` (no commit). The subject extractor MUST read from `(commit: ` to the **last** `)` on the line (subjects legitimately contain nested `(#359)` / `{s1,s4}`). Acceptance: `python3` parse of `cortex/lifecycle/sweep-provisional-tail-discovery-backlog-author/outcomes.md` yields the file's self-reported totals (31 APPLIED + 12 REFUTED = 43), the count of **distinct** `(file,id)` equals 43 (no parse produced a duplicate or dropped-and-compensated pair), and every extracted `commit_subject` resolves via `git log --fixed-strings --grep=<subject>` ≥ 1 (the `--fixed-strings` pin is required — subjects contain parens that a non-default `grep.patternType=extended/perl` would match to 0; verified `-E`→0, `-F`→1). **Note:** this git check is an *existence sanity-check only*, not provenance attribution — 31 APPLIED rows collapse to 11 distinct subjects, so a subject resolving proves it is real, not that it belongs to its `(file,id)`; attribution rests on the parse-pairing in the same line, not on this check. **Phase**: Fold

2. **Parse #360 `verdicts.md` with safe path reconstruction**: extract `(basename, id, disposition, short_sha)`. Reconstruct the full ledger path via an explicit map — `SKILL.md` is flat (`skills/critical-review/SKILL.md`); every other basename lives under `skills/critical-review/references/` (verified: only `SKILL.md` is flat). Hard-fail (raise, not skip) on any reconstructed `(file,id)` absent from the ledger. NO basename-only or fuzzy fallback (basename+id is ambiguous: `(SKILL.md, s3)` maps to 6 distinct ledger paths). Acceptance: `python3` parse yields the file's self-reported 26 (24 survives + 1 refuted + 1 correction), distinct `(file,id)` count = 26, every reconstructed `(file,id)` present in `master_candidates.json`; the run raises if any is absent. **Phase**: Fold

3. **Resolve #360 short-SHAs at execution**: resolve each bracketed short-SHA via `git rev-parse --verify <sha>^{commit}` then `git show -s --format=%s`, hard-failing on ambiguous or absent SHA (the active branch may rebase/amend). Acceptance: all applied #360 SHAs resolve to a unique commit at execution; the run raises on any `git rev-parse` failure. **Phase**: Fold

4. **Composite-keyed minimal upsert**: key strictly on `(file, id)`; mutate only rows with `status == "unverified"`. `verified_survives` → set `status` + add `applied_in_commit` (commit **subject-line string**, per the #361/#366 "ledger convention"); `verified_refuted` → set `status` only (no `applied_in_commit`). Leave `votes`, `survive_votes`, `verdict_summaries` untouched (minimal shape — #361/#366, superseding #358's richer shape). Reconciled rows are a distinct provenance class (verdict-derived, `votes=0` expected) — documented so a future report regeneration does not read `votes=0` as corruption. Acceptance: after fold, `python3` confirms each target `(file,id)` carries its mapped `status`; no `verified_refuted` row carries `applied_in_commit`; the vote/summary fields on target rows are unchanged from pre-fold. **Phase**: Fold

5. **`correction` row handling** (the single #360 `correction` row, `skills/critical-review/references/verification-gates.md` `s3`, commit `cd48c762` — the file *was* edited as a factual fix, but the proposed trim did not land; ~0 token savings). **Resolved at approval to option (b)**: set `status = "verified_refuted"` and add a `corrected_in_commit` key = `cd48c762`'s subject line. This keeps the 3-value status contract (savings-safe under any future inclusion- or exclusion-shaped filter) while preserving edit provenance in the extra key. Acceptance: `python3 -c` shows the row's `status == "verified_refuted"`, it carries `corrected_in_commit` referencing `cd48c762`, and it carries no `applied_in_commit` (so it is excluded from realized-savings totals, which sum `weighted_cost` over `verified_survives` only). **Phase**: Fold

6. **Assert-or-raise double-fold guard (status AND provenance)**: on any target `(file,id)` already non-`unverified` at fold time, compare **both** the existing `status` against the source verdict **and** (for `verified_survives`) the existing `applied_in_commit` against the source-derived subject; **raise on either disagreement** rather than silently skipping (a concurrent actor may have folded it with a different verdict, a divergent commit string, or the richer #358 shape). An already-present row that agrees on both fields is a no-op. Acceptance: Interactive/session-dependent — the guard is exercised by construction; unit-check via a `python3` dry-run asserting that injecting either a disagreeing status or a divergent `applied_in_commit` raises. **Phase**: Fold

7. **Pre-flight coherence check that still verifies consistency (critical-review A2)**: if ALL target `(file,id)` rows are already non-`unverified` at start (the concurrent actor folded #359/#360 first, as it did #361→#366), the run does **not** blindly declare success — it first runs the R6 status-AND-provenance comparison over every already-folded target and **raises on any disagreement**; only if all agree does it report "already reconciled, nothing to fold" and exit 0. A no-op is a valid success **only** when verified-consistent. Acceptance: Interactive/session-dependent — reconciler prints "already reconciled (verified consistent), nothing to fold" and exits 0 without writing when every target is already folded *and agrees*; a `python3` dry-run injecting one disagreeing pre-folded target makes the pre-flight raise rather than exit 0. **Phase**: Fold

8. **Drive folds from explicit child verdict rows, with a firing coverage assertion**: the authority for what to flip is each child artifact's explicit verdict list (43 + 26), not a ledger prefix scan. Cross-check: after parsing, assert `count(parsed) == count(distinct (file,id) parsed) == child's self-reported total` (catches a drop masked by a compensating duplicate parse, which a bare count would miss), and assert the parsed set equals the ledger's own filtered subset (`unverified`, under the child's prefixes, minus `overlaps_ticket`/`reproposal_of`) — **raising on any symmetric difference** (a row in one set but not the other). The 19 `overlaps_ticket`/`reproposal_of` rows and the pre-existing `skills/critical-review/references/reviewer-prompt.md` `s9` (already `verified_survives`, not in #360) MUST remain untouched. Acceptance: `python3` asserts the parsed set and the ledger filtered subset are equal (empty symmetric difference) and that those 19 rows + `reviewer-prompt.md s9` are byte-identical to their pre-fold state. **Phase**: Fold

9. **Best-effort optimistic write, bounded (critical-review B)**: the ledger sees **sequential-commit concurrency** — other agents/overnight commit to it between our read and write (not a byte-level daemon). Immediately before writing, re-read the ledger and compare a content hash against the value read at fold start; on change, re-run the fold from the fresh read, up to a bounded retry cap (e.g. 3); on exhausting the cap, abort and report rather than clobbering or looping forever. Write via atomic temp-file + `os.replace`. This is a best-effort optimistic check that converts the sequential-commit lost-update into a fail/retry — it narrows, and does not claim to eliminate, the residual read-to-replace window, which is acceptable at sequential-commit scale. Serialize with `json.dumps(data, indent=1, ensure_ascii=True)` and **no trailing newline** (byte-exact round-trip verified). Acceptance: (a) `python3 -c "import json; d=json.load(open(PATH)); print(open(PATH).read()==json.dumps(d,indent=1,ensure_ascii=True))"` prints `True` (minimal-diff serialization holds); (b) the reconciler defines a finite retry cap and an abort-and-report path (code inspection / dry-run confirms it does not loop unbounded). **Phase**: Fold

10. **One-off scratch implementation**: the reconciler is a scratch script (run from the lifecycle session or `scratchpad/`), NOT committed to `cortex_command/` or `bin/`, and NOT registered as a `[project.scripts]` console-script — matching both prior folds and avoiding SKILL.md-to-bin parity / events-registry / test obligations for a ledger no skill dispatches into. Acceptance: `git diff --name-only` for the discharge commit shows no new file under `bin/` or `cortex_command/` and no `[project.scripts]` change; the only ledger file changed is `master_candidates.json`. **Phase**: Verify & discharge

11. **Post-fold ledger integrity**: after folding, `(file, id)` remains unique across all ledger rows; the fold's target rows carry their mapped statuses; no `verified_refuted` row carries `applied_in_commit`; and the git diff touches only the intended rows/fields. Acceptance: `python3` integrity check passes all four assertions and prints a PASS line; `git diff --stat` on the ledger shows only the expected row count changed. **Phase**: Verify & discharge

12. **File the residual-debt successor ticket before closing #363 (critical-review A1)**: before marking #363 complete, create a backlog ticket that owns the residual debt #363 originally carried but this feature does not discharge — (a) the global `applied_in_commit` backfill of the ~89 pre-existing orphaned `verified_survives` rows (incl. #353's), and (b) the drifted line anchors (#340 s9, #186 s3, and the pervasive post-trim `start_line`/`end_line` staleness). Acceptance: a new `cortex/backlog/NNN-*.md` exists referencing #357/#363 and describing both (a) and (b); its id is cited in #363's completion commit. **Phase**: Verify & discharge

13. **Re-scope + discharge #363**: re-scope #363's Done-when to clause 1 only (all children's verdicts reflected as `(file,id)` status entries) — clause 2 is transferred to the R12 successor — then commit via `/cortex-core:commit` (message naming folded children #359/#360, the recomputed counts, and the successor ticket id), and mark #363 complete via `cortex-update-item`. Acceptance: #363 body's Done-when no longer asserts the global "no applied candidate remains without an `applied_in_commit`" clause; #363 frontmatter shows `status: complete`; the commit message names both children and the successor ticket id. **Phase**: Verify & discharge

## Non-Requirements

- **Global `applied_in_commit` backfill** of the ~89 pre-existing orphaned `verified_survives` rows (including #353's) — transferred to the R12 successor ticket (NOT silently dropped).
- **Re-location of drifted line anchors** — #340 s9, #186 s3, or the pervasive post-trim `start_line`/`end_line` staleness on other rows — also transferred to the R12 successor.
- **Bumping `votes` / `survive_votes` / `verdict_summaries`** — the minimal write shape deliberately leaves them (R4); reconciled rows are a distinct provenance class.
- **Regenerating `report.html`** — a static artifact; not refreshed here.
- **A reusable committed reconcile CLI verb** — over-built for a nearly-drained debt (research Tradeoffs).
- **Any `grep -c` acceptance token in a backlog file** — `verified_survives`/`verified_refuted`/`applied_in_commit`/`corrected` resolve in neither `bin/.events-registry.md` nor `cortex_command/`, so they would fail `test_backlog_grep_targets_resolve.py`; spec.md is exempt from that lint.

## Edge Cases

- **Concurrent actor folds #359/#360 first** → pre-flight (R7) verifies consistency over the already-folded rows and reports "already reconciled" only if all agree; raises on any disagreement (never a silent success).
- **Some-but-not-all targets pre-folded, one disagreeing** → R6 raises during the fold loop; combined with R9's single end-of-run write, no partial fold is written (the raise precedes `os.replace`).
- **Continuous writer** → R9's bounded retry aborts-and-reports after the cap rather than livelocking.
- **#360 short-SHA ambiguous/absent after a rebase** → hard-fail (R3), never a guessed subject.
- **#359 subject with nested parens** → last-`)` extraction (R1); existence check uses `--fixed-strings`.
- **Basename+id collision** (`(SKILL.md, s3)` → 6 paths) → explicit path map, no fallback, hard-fail on absent (R2).
- **A child row whose `(file,id)` is absent from the ledger** → hard-fail (R2/R8), never a silent skip.
- **A row pre-folded with correct status but a divergent `applied_in_commit`** → R6 raises on the provenance mismatch, not just status (critical-review B).

## Changes to Existing Behavior

- **MODIFIED**: 68 rows flip `status` from `unverified` to `verified_survives`/`verified_refuted`; `verified_survives` rows gain `applied_in_commit`.
- **ADDED**: the single `correction` row gains a new `corrected_in_commit` key (resolved to option (b) at approval); its `status` is `verified_refuted`, so no new enum value is introduced.
- **MODIFIED**: #363's backlog Done-when is re-scoped to clause 1 only (R13); clause 2 moves to the R12 successor ticket.

## Technical Constraints

- Serialization is exactly `json.dumps(data, indent=1, ensure_ascii=True)` with no trailing newline (byte-exact round-trip verified against the live file).
- Minimal write shape per the #361/#366 convention (commit `16cc9429`), which superseded #358's richer shape.
- The ledger has **no programmatic consumer** today (verified: 0 code files read the status enum or `weighted_cost`), so a 4th status value causes no current runtime break — but any *future* exclusion-shaped savings filter (`status != 'verified_refuted'`) would over-count a `corrected` row's `weighted_cost`, which is the load-bearing argument in the Open Decision below.
- Concurrency is sequential-commit-scale (agents/overnight committing between read and write), not a byte-level daemon — R9's optimistic check is right-sized to that, not a race-free CAS.
- No ADR warranted — repeats established precedent, no novel rejected-alternative trade-off (per `cortex/adr/README.md` three-criteria gate).
- Counts (69 targets, 43/26 split) are a snapshot; the reconciler recomputes them at execution rather than hardcoding.

## Open Decisions

None. (The `correction`-row status was resolved at approval to option (b) — `verified_refuted` + `corrected_in_commit` — per R5; every other decision is grounded in research/precedent.)

## Proposed ADR

None considered.
