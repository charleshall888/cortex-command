# Review: harden-lifecycle-complete-phase-finalization-and

Reviewed the four committed changes on `main` (`40db27e2`, `48707f26`, `fa212022`, `cf191b4a`) against spec.md, not the working tree.

## Stage 1: Spec Compliance

### Requirement 1: Defect 1 — working index-sync invocation
- **Expected**: `complete.md` Step 10 first fallback uses `python3 -m cortex_command.backlog.generate_index`; the `test -f ...generate_index.py` probe retained. grep bare-script = 0, grep `-m` form >= 1.
- **Actual**: Step 10 line changed to `python3 -m cortex_command.backlog.generate_index`; the `test -f cortex_command/backlog/generate_index.py` probe and success message are kept. Greps: bare = 0, `-m` = 1.
- **Verdict**: PASS
- **Notes**: Mirror at `plugins/cortex-core/skills/lifecycle/references/complete.md` carries the identical edit.

### Requirement 2: Defect 2 — stage the specific review-phase requirements-drift file on the trunk path
- **Expected**: Step 11a stages the requirements-drift edit by the exact `**File**:` path read from review.md's `## Suggested Requirements Update` section; skips silently when absent; no `git add -u cortex/requirements/` and no bare `git add cortex/requirements/`. Bound by the updated structural test.
- **Actual**: The `<!-- finalization-commit-step -->` region now reads `## Suggested Requirements Update` → `**File**:` from `cortex/lifecycle/{slug}/review.md`, runs `git add -- <that File path>`, and explicitly skips when no section exists. It explicitly forbids both the `-u` and bare directory-scoped requirements adds in prose. The strengthened test asserts presence of `"Suggested Requirements Update"` and absence of both forbidden requirements-add forms.
- **Verdict**: PASS

### Requirement 3: Defect 3 — scoped backlog staging that excludes unrelated untracked tickets
- **Expected (literal)**: `git add -u cortex/backlog/` plus an explicit add of the resolved item by slug-derived glob `git add -- cortex/backlog/*-{slug}.md`; enumerated lifecycle adds and stage-first guard preserved; no bare `git add cortex/backlog/`, no `git add cortex/lifecycle/`.
- **Actual**: Region uses `git add -u cortex/backlog/` (tracked-modified) plus a resolver-based explicit add — `cortex-resolve-backlog-item {slug}` → `filename` → `git add -- cortex/backlog/<resolved-filename>` — instead of the literal tail-anchored glob (deviation **A1**). Enumerated lifecycle-artifact adds and the `git diff --cached --quiet` guard preserved. Bare `git add cortex/backlog/` and `git add cortex/lifecycle/` both absent.
- **Verdict**: PASS
- **Notes (A1 assessment)**: The substitution is correct and preserves Requirement 3's intent. I verified the literal glob fails: the lifecycle slug (`harden-lifecycle-complete-phase-finalization-and`) is a truncated prefix of the backlog filename slug (`296-...-and-rework-cycles-counter.md`), so `cortex/backlog/*-{slug}.md` matches zero files — it would silently miss the created-but-untracked Edge Case the requirement exists to cover. The resolver (already relied on by Step 9, doing title-subset matching) returns the true filename and covers that case. Both intent clauses hold: (a) stage the resolved item + tracked cascade, (b) exclude unrelated untracked tickets. Spec Requirement 3's acceptance text literally asks for a `cortex/backlog/*-` token, but its prose intent ("stage the resolved item ... covers created-but-not-committed") is better served by the resolver. The deviation is flagged in the plan Risks (A1) and surfaced for approval. Correct substitution; not a fail.

### Requirement 4: Defect 4 — rework_cycles counts rework iterations from events.log
- **Expected**: `count_rework_cycles` re-sourced to count `review_verdict` events with `verdict == "CHANGES_REQUESTED"` in events.log; param `review_path` → events-log path; `main()` passes `feature_dir / "events.log"`; malformed lines skipped, not raised; missing/empty → 0; docstring rewritten off the review.md source.
- **Actual**: Function signature is now `count_rework_cycles(events_log_path: Path)`; reads line-by-line, `json.loads` per line in try/except for `(json.JSONDecodeError, ValueError)`, skips non-dict, counts `event == "review_verdict"` and `verdict == "CHANGES_REQUESTED"`. Missing → 0; `OSError` → 0; empty → 0. `main()` builds `events_log_path = feature_dir / "events.log"` and passes it. Module + function docstrings rewritten to describe the events.log CHANGES_REQUESTED source and the tolerant-reader convention. `RE_VERDICT` removed; `RE_TASKS_*` kept. grep `review.md` in counters.py = 0.
- **Verdict**: PASS
- **Notes**: All five spec cases verified via the new unit test (0/0/1/2/1-with-malformed) and pass.

### Requirement 5: Fifth writer — fix walkthrough.md crash-recovery
- **Expected**: step 6b emits `rework_cycles` as the count of `CHANGES_REQUESTED` `review_verdict` events (0 for clean approval), not the raw cycle number `C`; step-5 synthetic `APPROVED cycle 0` path left unchanged. grep `cycle number from the last` = 0, grep `CHANGES_REQUESTED` >= 1.
- **Actual**: Step 6b JSON now emits `"rework_cycles": R` and the prose reads "Where `R` is the number of `review_verdict` events with `verdict: CHANGES_REQUESTED` ... (0 when the only verdict was a clean `APPROVED`)." The synthetic step-5 path is untouched. Greps: `cycle number from the last` = 0, `CHANGES_REQUESTED` = 1.
- **Verdict**: PASS

### Requirement 6: Document the distinct sites; do not touch the already-correct one
- **Expected**: `dashboard/data.py` computation + docstring unchanged; `common.py`'s `cycle` logic unchanged with a one-line comment noting it is NOT `rework_cycles`; `pipeline/metrics.py:236` unchanged. grep `rework_cycles` in common.py >= 1, all occurrences comments.
- **Actual**: `git diff` over data.py / alerts.py / metrics.py across all four commits is empty. common.py adds exactly a two-line comment above the unchanged `cycle = review_verdict_count if ... else 1` line, naming counters.py as the home of the distinct `rework_cycles`. grep `rework_cycles` in common.py = 1 (the comment).
- **Verdict**: PASS

### Requirement 7: dashboard high_rework alert unchanged
- **Expected**: `alerts.py`'s `high_rework >= 2` threshold and its data.py source unchanged; `test_alerts.py` passes unmodified.
- **Actual**: alerts.py untouched (empty diff). `test_alerts.py` passes (run green).
- **Verdict**: PASS

### Requirement 8: Update the finalization-commit structural test to bind the scoping
- **Expected**: test asserts the review.md `File`-path staging (defect 2), forbids `-u`/bare requirements adds; asserts `git add -u cortex/backlog/` AND a resolver/slug-glob add (defect 3), keeps `git add cortex/lifecycle/`-forbidden, adds a negative for the unscoped bare backlog sweep, binds `-u` to the path same-line. Test fails if `-u` is dropped.
- **Actual**: Positive assertions added for `"Suggested Requirements Update"`, `"cortex-resolve-backlog-item"`, and `"git add -u cortex/backlog/"` (single substring binds `-u` to the path). Negative assertions added for `"git add -u cortex/requirements/"`, bare `"git add cortex/requirements/"`, unscoped `"git add cortex/backlog/"`, and the tail-anchored `"cortex/backlog/*-"` glob. Existing `git add cortex/lifecycle/` / `git push` / `gh pr create` negatives kept. The `git add -u cortex/backlog/` positive does not trip the bare-`git add cortex/backlog/` negative (the `-u ` flag means the bare string is not a substring) — verified.
- **Verdict**: PASS
- **Notes**: A scoping regression that drops `-u` would fail the positive assertion; the test binds the contract as specified.

### Requirement 9: Add unit coverage for count_rework_cycles
- **Expected**: new `cortex_command/lifecycle/tests/test_counters.py` covering Requirement 4's cases; >= 5 assertions over `count_rework_cycles`.
- **Actual**: New file with 8 test functions (no-events, empty, single-APPROVED, 1×CR, 2×CR, malformed-line, synthetic-cycle-0, REJECTED). grep `count_rework_cycles` = 10. Auto-collected and passing.
- **Verdict**: PASS

### Requirement 10: Rewrite parity fixtures and tests for the events.log source, non-vacuously
- **Expected**: golden-replay `multiple-phases` gets a `.events_log` with 1 CR + 1 APPROVED and stdout `rework_cycles: 1`; `multiple-phases.review_md` kept (2 verdicts) to prove review.md is no longer read; `malformed-events-log` asserts tolerance at 0; README updated; bin-parity recompute re-pointed to `count_rework_cycles`/events.log; `feat1/events.log` gains `review_verdict` events for a non-zero count.
- **Actual**: `multiple-phases.events_log` added (lifecycle_start + CR + APPROVED); `multiple-phases.stdout` → `rework_cycles: 1`; `multiple-phases.review_md` retained with 2 `"verdict"` entries — counter yields 1 (events.log) not 2 (review.md), proving the source change non-vacuously. README rewritten (sidecar description, case table, semantics, contract table) to state events.log is the source and the malformed case asserts tolerance. Bin-parity imports `count_rework_cycles` and computes `expected_rework = count_rework_cycles(events_log_path)`, drops `RE_VERDICT`/`review_text`. `feat1/events.log` gains CR + APPROVED (rework = 1). grep `CHANGES_REQUESTED` over bin_parity = 1 (feat1). Both parity suites pass.
- **Verdict**: PASS

### Requirement 11: complete.md mirror regenerated and committed with Phase-1 commit
- **Expected**: `plugins/cortex-core/skills/lifecycle/references/complete.md` mirror co-committed with the canonical edit in `40db27e2`; no uncommitted mirror drift.
- **Actual**: Commit `40db27e2` contains both canonical and mirror with identical diffs. `diff` of the two files reports IN SYNC; no working-tree drift.
- **Verdict**: PASS

### Requirement 12: walkthrough.md mirror regenerated and committed with Phase-2 commit
- **Expected**: walkthrough.md mirror co-committed with the canonical edit; no drift. (Plan named the mirror under `plugins/cortex-core/`; actual home is `plugins/cortex-overnight/`.)
- **Actual**: Commit `fa212022` contains the canonical `skills/morning-review/references/walkthrough.md` and the mirror `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md` with identical diffs. `diff` reports IN SYNC. No `plugins/cortex-core/skills/morning-review/` directory exists (no stale cortex-core mirror). The only morning-review walkthrough mirror under `plugins/` is the cortex-overnight one.
- **Verdict**: PASS
- **Notes**: The plan's cortex-core path was a plan-time misnaming; the implementation correctly placed the mirror in the cortex-overnight plugin (which owns morning-review) and noted the correction in the Task 3 status line. Verified no stale cortex-core mirror was created. Requirement 12's intent (mirror in sync, drift hook green) is satisfied.

**A2 assessment (four per-task commits vs the spec's idealized two-commit model)**: The spec's Technical Constraints "Sequencing" section idealized two commits (Phase 1; Phase 2). The implementation landed four harness-native per-task commits because the Implement builder template commits every dispatched task and marks no-commit tasks as failed — the deferred-staging model cannot be expressed. The four commits map cleanly onto the spec's two phases: `40db27e2` is the entire Phase 1 (defects 1–3 + test + mirror); `48707f26` + `fa212022` + `cf191b4a` are Phase 2's three tasks (counter-core, walkthrough, common.py comment). Each canonical-skill commit folds in its regenerated mirror (drift coupling preserved). The spec's safety argument for the ordering — Phase 1 shipping before Phase 2 leaves no inconsistent window — holds equally at finer granularity: each commit leaves `just test` green (verified against the implementation's own suites) and the drift hook passing. The grouping satisfies the spec's intent; the deviation is documented in plan Risks (A2). Not a fail.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

The implementation is a correctness fix within already-documented behavior. project.md's Philosophy of Work already records the multi-step Complete phase and the finalization tail (Steps 9–11a) committing lifecycle artifacts and the backlog write-back via a flag-gated, stage-first step on all completion paths; the staging-scope refinements (defects 2/3) tighten that step without introducing behavior the requirements do not reflect. The `rework_cycles` reconciliation is a metric-definition correction; project.md does not pin a `rework_cycles` definition, so no requirements statement is contradicted or newly required. No new events, fields, or architectural constraints were introduced (confirmed against the Non-Requirements list and the registry-unchanged claim).

## Stage 2: Code Quality
- **Naming conventions**: Consistent with project patterns. `count_rework_cycles(events_log_path: Path)` mirrors the sibling `count_tasks(plan_path: Path)` shape. Fixture sidecar naming (`multiple-phases.events_log`) matches the existing flat-sibling fixture convention documented in the README. The `common.py` comment names the canonical home (`cortex_command/lifecycle/counters.py`) so the cross-reference is greppable.
- **Error handling**: The new tolerant-reader in `counters.py` matches `common.py:_detect_lifecycle_phase_inner` exactly — `splitlines()`, skip blank, `json.loads` in try/except, `continue` on `JSONDecodeError`, `isinstance(event, dict)` guard. It additionally catches `ValueError` (a superclass of `JSONDecodeError`, harmless and slightly broader) and returns 0 on `OSError`/missing/empty — appropriate for a best-effort metric counter. The convention parity the spec called for is met.
- **Test coverage**: All plan verification steps execute green: `test_complete_md_finalization_commit.py`, `test_counters.py` (8 cases), `test_cortex_lifecycle_counters_parity.py`, `test_bin_lifecycle_state_parity.py`, and `test_alerts.py` (unmodified) all pass. The golden-replay fixture is non-vacuous (review.md kept at 2 verdicts while the counter yields 1 from events.log). The bin-parity fixture asserts a non-zero rework count (feat1 = 1). `just test` fails only on `tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`, which is unrelated to all four commits (untouched files) and fails solely because `uv run --script` cannot reach pypi.org under the sandbox (DNS error); the test passes (5.23s) when run with network access. This is an environment artifact, not a regression.
- **Pattern consistency**: Follows the structural-token-test pattern for skill-prose contracts, the flat-sibling fixture pattern, and the canonical-edit-plus-co-committed-mirror drift-coupling convention. The negative-assertion design (forbidding both the broken glob and the unscoped sweep) hardens against the exact regressions the defects represent.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
