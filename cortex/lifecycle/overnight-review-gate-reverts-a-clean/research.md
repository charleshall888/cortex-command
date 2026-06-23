# Research: Overnight review gate reverts a clean merged feature on no-parseable-review.md

**Clarified intent**: When the overnight review agent completes cleanly (`stop_reason=end_turn`) but writes no parseable `review.md`, the gate must distinguish a tooling/adherence miss from a genuine dispatch crash, **preserve** the already-merged feature on the overnight integration branch, and surface a "review could-not-run — needs human re-review" deferral instead of reverting verified work. Rename/split the misleading `review_dispatch_crashed` signal. **Scope excludes** retry/escalation (user-chosen Clarify policy). Tier: complex · Criticality: high.

> **Reframe that drives the design (Tradeoffs)**: The review prompt's verdict vocabulary is exactly `APPROVED / CHANGES_REQUESTED / REJECTED`. The agent **never legitimately writes `verdict: ERROR`** — `"ERROR"` is a *synthetic sentinel* invented only inside `parse_verdict()`. So there is no pre-existing "real ERROR verdict" to disambiguate from "no artifact." The actual split is **genuine dispatch crash** (`DispatchResult.success == False`) vs. **review could-not-produce-a-usable-verdict** (`success == True` but the final verdict is the synthetic `ERROR`).

## Codebase Analysis

**Primary files**
- `cortex_command/pipeline/review_dispatch.py`
  - `parse_verdict()` (L60–89): returns the synthetic `_ERROR_RESULT` `{"verdict":"ERROR","cycle":0,"issues":[]}` for **three collapsed sub-cases** — file missing (`FileNotFoundError`/`OSError`), present but no ```` ```json ```` block, present but unparseable JSON. A present-but-missing-`verdict`-key file falls through to the caller's `.get("verdict","ERROR")` default. Pure string→dict parser; sees only the file, never the dispatch result.
  - `dispatch_review()` (~L131–602): step 5 (~L276–278) calls `parse_verdict(review_md_path)` and reads `verdict_dict.get("verdict","ERROR")` **without consulting the `DispatchResult` captured at ~L264** (`result.success`, `result.error_type`) or `review_md_path.exists()`. The cycle-2 path (~L530) and the "unexpected verdict value → treat as ERROR" fallthrough (~L584) also map non-canonical verdict strings to `ERROR`.
  - `ReviewResult` dataclass (L28–54): `approved, deferred, verdict, cycle, issues, merge_sha` — **no field** separating "could-not-run" from a real verdict.
  - Precedent: fix-agent-failure (~L415), SHA-circuit-breaker (~L441), re-merge-failure (~L470), cycle-2 ERROR (~L564) all **write a deferral WITHOUT feeding the systemic breaker** — an established "deferral that doesn't feed the breaker" pattern to mirror.
- `cortex_command/overnight/outcome_router.py` — **three duplicated gate sites** (ticket named only two):
  - `_recovery_review_gate()` ~L1144/1156 (test-recovery path)
  - `_repair_review_or_revert()` ~L1468/1480 (repair ff-merge path)
  - `apply_feature_result()` ~L1801/1817 (**primary integration path — the one that fired in the incident**)
  - Each: on `rr.verdict == "ERROR"` sets `deferred_details["review_dispatch_crashed"]=True` + `["could_not_run"]=True`, emits `FEATURE_DEFERRED`, then calls `_record_review_crash_systemic(name, ctx)`. The **merge revert runs earlier on the deferred path** (e.g. ~L1080–1095, ~L1728–1736), gated on "deferred," not on ERROR — so preserving the merge requires guarding the revert itself, at all three sites.
  - `_record_review_crash_systemic()` (L937–987): increments `cb_state.systemic_pauses_in_batch`, appends `REVIEW_DISPATCH_CRASH` to `review_crash_classes`; at `>= SYSTEMIC_FAILURE_THRESHOLD` emits `PIPELINE_SYSTEMIC_FAILURE` and sets `global_abort_signal` (pauses the batch).
  - Three `except`-block raised-dispatch paths (ProcessError/CLIConnectionError/TimeoutError) hard-code `review_dispatch_crashed=True` + unconditional breaker feed — these are **genuine crashes** and should keep current behavior.
- `cortex_command/pipeline/dispatch.py` — `DispatchResult` (L318–340): `success, output, error_type, error_detail, cost_usd, diagnostics`. **`stop_reason` is logged to events.log but NOT carried on the result object.** `budget_exhausted` takes the normal-completion route but sets `is_error`/`success=False`.
- `cortex_command/overnight/report.py` — `render_deferred_questions()` (L1211–1282): reads `merge_reverted` (~L1248) to pick "Merge reverted — safe to re-review/re-run" vs legacy "do NOT re-run"; **never reads `could_not_run`**.

**Fix #5 (complexity mislabel) — premise likely wrong**: review dispatch uses `read_tier(name)` (correct feature tier). The `complexity="complex"` hardcode is in `integration_recovery.py` (~L220) and is intentional for repair agents. Recommend **drop #5** unless re-confirmed against the incident.

## Web Research

Convergent industry prior art endorses a **tri-state separation** and a deliberate middle path:
- **GitHub Checks API** splits `status` (queued/in_progress/completed) from `conclusion` (success/failure/**neutral**/skipped/…). A could-not-determine check maps to `neutral`, deliberately not `failure`. *Caveat*: GitHub treats neutral/skipped as **success for gating (fail-open)** — the opposite of reverting; we choose a middle path (preserve + flag).
- **EviBound** (arXiv 2511.05524): a Verification Gate confirms the required artifact *exists* + run `FINISHED` before accepting a claim; three-outcome model verified / failed / **blocked** (no-artifact ≠ failed-verification).
- **Artifact-faithfulness study** (OpenReview 40wuXQMQRU): agents call the verifier yet emit a non-honoring artifact in **46–68%** of reward-0 trajectories — the failure mode is pervasive, not a corner case; end-to-end reward cannot distinguish "didn't honor the output contract" from a real result.
- **Rollback-free recovery patents** (US 7457984/7174479) + **Azure Well-Architected** transient-fault guidance: do **not** perform destructive rollback on an infra/tooling failure; never bundle non-idempotent revert with transient handling.
- **AuthZed fail-open/fail-closed**: the dangerous bug is letting an *error* silently flow into pass-or-fail logic — errors must get their **own branch**. Maps to: don't conflate a tooling miss with a blocking review verdict, and don't fail-open into silently accepting unreviewed work either.

**Anti-pattern (canonical)**: web-platform-tests/wpt#18392 — when the platform stopped carrying the `neutral` (could-not-run) signal, every could-not-run was silently reinterpreted as failure. Exactly this bug class.

## Requirements & Constraints

- **Direct conflict with a deliberate prior decision**: `cortex/requirements/pipeline.md` (~L86) states: *"On any non-APPROVED outcome (REJECTED, CHANGES_REQUESTED after rework, or a could-not-run/crashed review with verdict ERROR), the feature's live merge commit is reverted SHA-anchored under `ctx.lock` before deferring, so no unreviewed code remains on the integration branch."* This is from the prior shipped lifecycle `overnight-review-gate-crashes-to-cycle`, which deliberately chose to revert unreviewed merges **and** feed the breaker. The split this ticket introduces (genuine crash still reverts+feeds; no-artifact preserves) **must amend this contract** so requirement and code stay consistent.
- **Aligned requirements**: `project.md` "Graceful partial failure" (retries/hands off/**fails gracefully**), "Failure handling: surface failures in the morning report; keep working unless blocked," day/night split (morning = human review gate), "Complexity must earn its place / simpler wins" (supports the no-retry, minimal scope).
- **Events-registry gate** (`bin/.events-registry.md`): `feature_deferred` and `pipeline_systemic_failure` rows exist; `review_dispatch_crashed`/`could_not_run`/`merge_reverted` are **field-additive** details (not enumerated rows). A renamed/new detail key or a new `cause_class` value must be documented (field-additive schema-extension note + registry update in the same commit). `pipeline_systemic_failure` producer line at `outcome_router.py:980` is **line-pinned** by the prior lifecycle's R11 — keep pin current.
- **Doc ownership** (CLAUDE.md): `docs/internals/pipeline.md` + `cortex/requirements/pipeline.md` own this behavior; `docs/overnight-operations.md` owns the round loop. Update the owning doc(s), cross-link from others.
- **Constants**: `SYSTEMIC_FAILURE_THRESHOLD=3`, `REVIEW_DISPATCH_CRASH="review_dispatch_crash"` in `cortex_command/overnight/constants.py`; `CircuitBreakerState.review_crash_classes` in `types.py`.

## Tradeoffs & Alternatives

Where to detect & signal "could-not-run":
- **(a) `parse_verdict()` sentinel (`NO_ARTIFACT`)** — leaks a parser-internal failure into the verdict namespace that the prompt, `review_verdict` events, and every `verdict_str ==` comparison reason about. Highest downstream-consumer count; muddies the malformed-but-present case. **Rejected.**
- **(b) `dispatch_review()` gate** — the only layer holding **both** the `DispatchResult` and `review_md_path`; produces a structured result. **Core of the recommendation.**
- **(c) `outcome_router` only** — it receives only `rr.verdict == "ERROR"`, can't distinguish the cases without reaching back into pipeline internals (layering inversion), replicated ×3. **Rejected as sole mechanism.**

**Recommended: hybrid (b)+(c), orthogonal boolean.** Add `ReviewResult.could_not_run: bool` (default `False`, backward-compatible), **set in `dispatch_review` by gating on `result.success` + the final verdict being the synthetic `ERROR`** (not a tri-state verdict — a tri-state repeats the overloading that caused this bug, collapsing two independent axes: *what the review concluded* vs *whether it produced a usable verdict*). In `outcome_router`, replace the three `if rr.verdict == "ERROR":` predicates with `if rr.could_not_run:`. Genuine `except`-block crashes keep reverting + feeding the breaker; only the `could_not_run` (success-true) path is preserved + flagged. Lowest downstream-change count: `parse_verdict` and its 5 tests untouched; the in-`dispatch_review` `verdict_str ==` comparisons untouched; only the 3 outcome_router predicates + `report.py` change.

## Downstream Consumers (rename/split safety map)

- **Decision-readers**: `_record_review_crash_systemic` (the systemic breaker — the only behavioral consumer); `report.py:1248` `merge_reverted` reconciliation (chooses the operator annotation).
- **Display/aggregate-readers**: `report.py` deferred-questions section (reads `review_verdict`, `review_cycle`, `merge_reverted`; **does not read `could_not_run`** — the gap). `metrics.py` reads only `review_verdict` (not the flags). Dashboard reads feature `status` only, not these details.
- **Tests asserting on the signals**: `test_outcome_router.py` L1693–1707 (`could_not_run`+`review_dispatch_crashed` both set on ERROR / neither on REJECTED); `test_report.py` L136–220 (`merge_reverted` reconciliation); `test_review_dispatch.py` (`parse_verdict` ERROR cases).
- **Systemic breaker mechanics**: threshold 3; cause_class is a trailing-window list; tripping sets `global_abort_signal` and emits `PIPELINE_SYSTEMIC_FAILURE`. **Removing the no-artifact feed entirely removes the systemic safety net for a systemic adherence failure** (the exact incident at scale).

## Verdict-Discriminator Semantics

- **Primary discriminator: `DispatchResult.success`** (captured but currently discarded). `success == True` + final verdict `ERROR` → **could-not-run (preserve+flag)**. `success == False` → **genuine crash (revert + breaker)**, regardless of any on-disk file.
- **Do not depend on `stop_reason`** — not carried on `DispatchResult` (only in events.log); threading it through is an unnecessary cross-cutting dependency.
- **Ambiguous edge (must be fixed): stale `review.md`.** Today `parse_verdict` runs even when `success == False`; a stale prior-cycle `APPROVED` file can be parsed and **wrongly approve a feature whose fresh dispatch failed** (a latent bug, independent of this ticket). The fix: when `success == False`, force the failure path and **ignore on-disk files**.
- **Mirror existing patterns**: review_dispatch already inspects `result.success` for fix-agent (~L415) and re-merge (~L470) failures — extend the same idiom to step 5.

## Test & Observability Surface

- **Model the new test on** `TestReviewDeferredSurfacingCorrections` (`test_outcome_router.py` ~L1619–1778) — mock `dispatch_review` to return `deferred=True, could_not_run=True`; assert `revert_merge` **not** called (merge preserved), `_record_review_crash_systemic` behavior per the chosen breaker policy, `feature_deferred` carries the new flag, backlog status `deferred`. Add `test_review_dispatch.py` coverage for the `success`-gated discriminator (success-false→crash even with stale APPROVED on disk; success-true+no-file→could_not_run).
- **Report surface (mandatory)**: add a **third branch** in `render_deferred_questions()` for `could_not_run == True AND merge_reverted == False` → an explicit "⚠️ UNREVIEWED MERGE PRESERVED — review could not run; kept on the integration branch for human re-review (intentional, not an error)" annotation, plus an executive-summary sub-count. Without this, a preserved merge renders with the wrong legacy "do NOT re-run" text and the operator gets no distinct signal.
- **Gates that fire**: events-registry doc update for the renamed/added detail key (+ any new `cause_class`); `test_report.py` reconciliation tests; `test_outcome_router.py` marker tests (move from verdict-string trigger to the boolean).

## Adversarial Review (high/critical pass)

1. **Circuit-breaker removal inverts the safety model.** Today: 3 no-artifacts revert + trip the breaker → batch pauses, operator notices. Proposed "don't feed": a batch where the review model fails to write the artifact for N features **preserves N genuinely-unreviewed merges, none halting, batch looks green** — and the report currently shows them as "do NOT re-run" (wrong). In aggregate this can be **worse** than today. Mitigation: either **keep feeding the breaker with a distinct `cause_class`** (systemic no-artifact still pauses the batch while individual merges are preserved), or treat the report-surface change as a hard precondition of removing the feed.
2. **`success` discriminator + stale file (latent bug)** — must force the failure verdict when `success == False`; never let a stale on-disk verdict win.
3. **Non-canonical verdict** (`verdict:"BLOCKED"` → mapped to ERROR with `success==True`, file present): correctly handled by gating `could_not_run` on `success==True AND final verdict=="ERROR"` (covers no-file, no-block, unparseable, and non-canonical) — but name it `could_not_run`, **not** `no_artifact` (a file may exist).
4. **Three-site duplication + revert ordering** — preserving the merge requires guarding the revert at all three sites with consistent, **exception-safe** flag handling; extract a shared helper so `merge_reverted`/`could_not_run` are always set coherently (incl. the revert-failure exception handler).
5. **Report false-negative** — a preserved merge (`merge_reverted=False`, in `merged_to_integration`) currently gets "do NOT re-run"; the new third branch fixes this.
6. **Resume/idempotency** — a preserved-but-unreviewed merge re-entering the pipeline: `deferred` may be terminal-for-the-run, so it is **not** auto-re-reviewed. Consistent with the no-retry "preserve + flag for human" scope (operator handles it manually); flagged below as a boundary to confirm.

## Open Questions

All resolved at the Research Exit Gate (2026-06-23) before Spec.

1. **Systemic circuit-breaker policy for the no-artifact case — RESOLVED: (B) feed with a distinct `cause_class`.** Keep feeding the systemic breaker for the no-artifact (could-not-run) case, tagged with a distinct cause_class (`review_no_artifact`) separate from genuine crashes (`review_dispatch_crash`), so a systemic no-artifact pattern still pauses the batch at `SYSTEMIC_FAILURE_THRESHOLD` — while each individual merge is **preserved** (not reverted) and the per-feature signal is renamed/split. Rationale: the adversarial pass showed "don't feed at all" inverts the safety model and can silently ship N unreviewed merges (worse in aggregate than today's revert-and-trip). (B) preserves individual work *and* the systemic safety net. (User delegated: "think critically and do the best option.")
2. **Resume boundary — RESOLVED: manual operator handling.** Preserved `could_not_run` features carry no new status and are not auto-re-reviewed on resume; the morning-report "unreviewed merge preserved" surface + the deferral file are the operator's handle. Consistent with the no-retry scope.
3. **Fix #5 (complexity mislabel) — RESOLVED: dropped from scope.** Review dispatch already uses the correct feature tier (`read_tier`); the observed `complexity="complex"` was the intentional repair-agent path (`integration_recovery.py`), not a review-dispatch bug.
4. **Latent stale-verdict bug — RESOLVED: fix here.** When `result.success == False`, force the failure path and ignore any stale on-disk `review.md` (today a stale prior-cycle `APPROVED` can wrongly approve a feature whose fresh dispatch failed). Same `success`-gating conditional and same discriminator as the primary fix — splitting it would duplicate the change.
