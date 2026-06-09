# Research: Make the overnight post-merge review gate fail-safe and root-cause-correct

**Scope anchor (from Clarify):** (A) diagnose and fix the *systemic* review-subprocess exit-1 crash, and (B) ensure any review that crashes, errors, or defers reverts its feature merge so unreviewed/broken code can never ship on the integration branch `overnight/{session_id}`. Complexity: complex · Criticality: high. The user explicitly opted into fixing the root cause this lifecycle, not just hardening the handling.

> **Headline:** Research confirmed the two ticketed bugs **and uncovered two more defects of equal or greater severity** plus a prerequisite that the crash is not currently diagnosable at all. The fix surface is materially larger than the ticket's two suggested fixes. The Spec phase must make a scope decision (see Open Questions).

---

## Codebase Analysis

**The merge→review→defer flow** lives in `cortex_command/overnight/outcome_router.py`, async `apply_feature_result` (~939–1101):
- `async with ctx.lock:` opens at `:939` and is held across **both** the merge and the entire review dispatch.
- `merge_feature(...)` merges to the integration branch at `:984` (with `--no-ff`, `merge.py:262`). `merge_result` does **not** expose a merge commit SHA — `MergeResult` (`merge.py:30-39`) has fields `success, feature, conflict, test_result, error, classification`, no SHA field.
- `FEATURE_MERGED` is emitted at `:994` — **before** review, so a later-deferred feature has already logged a merge event.
- `requires_review(tier, criticality)` gating at `:1001-1004`; `dispatch_review(...)` at `:1006`.
- `if rr.deferred:` path (`:1019-1040`): appends to `features_deferred`, emits `FEATURE_DEFERRED` (details `review_verdict`, `review_cycle`), writes backlog status `"in_progress"`, best-effort `cleanup_worktree`, `return`. **No merge revert. No deferral file.**
- `except Exception` path (`:1041-1080`): emits `FEATURE_DEFERRED` with `review_dispatch_crashed: True`, writes a full blocking `DeferralQuestion` via `write_deferral`, `return`. **No merge revert.**
- Standard merged success path (`:1082-1101`): appends to `features_merged`, writes `"merged"`.

**`cortex_command/pipeline/review_dispatch.py`:** `dispatch_review` (~122) reads `spec_path` in-process *before* dispatch (`:197-217`, returns a clean spec-ERROR if unreadable), calls `result = await dispatch_task(...)` at `:253` **without checking `result.success`**, falls through to `parse_verdict(review_md_path)` at `:266`. `parse_verdict`/`_ERROR_RESULT` at `:48-80`. The cycle-1 rework loop **re-merges** via `merge_feature(ci_check=False)` at `:444-465`, creating a *second* merge commit.

**`cortex_command/pipeline/merge.py`:** `merge_feature` (158-332); the **test-failure revert precedent** at `:294-324` runs `git revert -m 1 --no-edit HEAD` inline while that merge is still HEAD (but `:309` only *logs* `merge_revert_error` on failure and still returns `success=False` — not `check=True`). `revert_merge()` (`:335-367`) is **dead code, zero non-test callers**, uses `git checkout base` + `git revert -m 1 --no-edit HEAD` with `check=True`.

**Files that will change:** `outcome_router.py` (rollback on defer/crash paths; possibly the recovery path — see Adversarial #3), `merge.py` (capture+return merge SHA; SHA-anchored revert), `review_dispatch.py` (result.success check / retry; ERROR path deferral file; surface re-merge SHA), `dispatch.py` (log child stderr — see Root-Cause), `report.py`/surfacing, and `bin/.events-registry.md` (line-number drift, see Adversarial #10). Existing events `merge_reverted`/`merge_revert_error`/`auth_probe`/`pipeline_systemic_failure` are already registered — no new event strictly required for the revert.

**Test gaps:** no test asserts deferred-review-reverts-merge, the ERROR-no-deferral-file behavior, the except-crash path, or the recovery-path review bypass. Template: `test_outcome_router.py::test_review_gated_dispatches_review_once`.

---

## Web Research

**Gate-ordering prior art.** The "Not Rocket Science Rule" (bors/homu, GitHub merge queue) is **review-then-merge**: a speculative merge is tested and only fast-forwarded on pass — nothing unverified touches the shared branch, so no rollback is ever needed. Google's **TAP** is **merge-then-review** (optimistic): merge after a short battery, then *"if a batch fails, TAP automatically begins rolling back the changes."* The cortex pipeline is the TAP model, so **automatic rollback-on-failed-postmerge-check is the load-bearing completion of that design, not an add-on.** Moving to the bors model (merge-after-approval) is a legitimate but larger architectural bet.

**Git mechanics (authoritative — MIT/Linus revert-faulty-merge howto, git-scm).** Always revert a merge **by its SHA** with the mainline flag: `git revert -m 1 <merge-sha>`. `-m 1` keeps parent 1 (the branch merged *into* = the integration branch); the wrong parent inverts which side is discarded. Revert-by-SHA is **position-independent** — it works even when later merges sit on top, which is exactly why `git revert -m 1 HEAD` is dangerous on a shared sequential-merge branch. **Footgun:** a revert undoes the *data* but not the *history*, so a later naive re-merge of the (now-fixed) feature brings nothing back — you must "revert the revert" before re-merging. `git merge --abort` only applies to an *uncommitted* in-progress merge; once committed (as here, before review runs), revert-by-SHA is the only tool.

**Detached/headless CLI exit-1 checklist.** A `claude` subprocess exiting 1 within ~150ms (pre-first-token) implies a *pre-model* failure: missing/unexported/expired auth (`CLAUDE_CODE_OAUTH_TOKEN` / `ANTHROPIC_API_KEY`), interactive-vs-`-p` mode (interactive ignores the API key), stripped `PATH`/`HOME`/`cwd` under launchd, missing `--dangerously-skip-permissions`/no-TTY, sandbox denial, or an **unknown/rejected CLI flag**. An expired token produces a *systemic* (every-spawn-identical) failure — matching the observed symptom. (SDK TS #255 nuance: a true spawn failure can *hang* rather than exit-1; an actual exit-1 means the process started then died — points at auth/permission/arg errors, not a missing binary.)

**Fail-safe vs fail-loud.** Mature systems separate "check **failed**" (ran, found non-compliance — a real verdict) from "check **could not run**" (infra/spawn/auth crash — no verdict). Retry-with-backoff applies only to the transient could-not-run class; permanent failures (401/expired token/bad flag) must not be blind-retried — trip a circuit breaker and escalate loudly. For a gate protecting a shared branch, "fail-safe" = default to the harm-preventing state = **roll back the unreviewed merge**, *and* surface a triage signal. Rollback and defer are orthogonal and complementary — do not replace defer with a silent halt.

---

## Requirements & Constraints

**Must-haves the fix must preserve (`cortex/requirements/pipeline.md`):**
- Architecture is **merge-first, review-after** ("After a feature merges successfully, the pipeline checks whether it qualifies for ... review"). The 2-cycle rework loop **re-merges mid-review with `ci_check=False`**. ⇒ The ticket's alternative "move merge after APPROVED" contradicts this *and* collides with the re-merge step — it is a **spec-level restructure**, not a code change.
- **Defer-on-review-failure is REQUIRED:** "Non-APPROVED after cycle 2, REJECTED at any cycle, **or review agent failure → feature status `deferred`; deferral file written for morning triage**." ⇒ The fix *preserves* defer and *adds* rollback; it does not replace defer with halt/fail-loud. (Note: the live `rr.deferred` path violates the "deferral file written" half of this requirement today — see Surfacing.)
- **Repair-attempt-cap is a fixed architectural constraint** (single Sonnet→Opus for conflicts; max-2 for test failures). ⇒ Any retry-before-defer must be bounded and circuit-breaker-backed; unbounded review-retry is forbidden.
- **Fail-forward** (one feature's failure doesn't block others) is the mechanism behind the HEAD-revert hazard. **Integration-branch persistence** ⇒ rollback must be a *revert commit on the branch*, not branch deletion. **Atomic writes** for state/deferral files.
- **Abort-on-failure precedent** exists: the merge-conflict path already aborts the in-progress merge on repair exhaustion and routes to `deferred`. The review-crash rollback is the same precedent extended to a different gate.

**`cortex/requirements/project.md`:** "Surface failures in the morning report" (directly indicts the green-PR surfacing defect). "Solution horizon" favors the **durable SHA-anchored revert** over the HEAD shortcut (the shortcut sidesteps the known fail-forward constraint). "Graceful partial failure" / "Destructive operations preserve uncommitted state" bound how the revert may run.

**Gaps the fix fills (requirements are silent):** no requirement says unreviewed code must be reverted off the branch on a review crash (the central Bug-B gap — likely warrants a pipeline.md acceptance-criteria addition); no requirement names the systemic exit-1 failure mode; the sentinel-detection mechanism (verdict==ERROR, not cycle==0) is unspecified. **No ADR governs this path** — SHA-anchored revert likely needs none; a merge-after-approval restructure could clear the ADR bar. **Sibling ticket #294** separately covers `report.py` globbing the entire lifecycle tree (related, out of scope here). Editing `cortex_command/pipeline/` and `overnight/` is **not** itself lifecycle-gated; only `common.py:TERMINAL_STATUSES` is (the fix should not need a new terminal status — `deferred` suffices).

---

## Root-Cause Diagnosis (subprocess exit-1)

**The exact invocation** built for a review dispatch (`dispatch.py:650-662` → SDK `subprocess_cli.py`): `claude --output-format stream-json --verbose --system-prompt <...> --allowedTools ... --max-turns 30 --model <opus|sonnet> --permission-mode bypassPermissions --settings <sandbox-tempfile> --setting-sources "" --effort <xhigh|high> --input-format stream-json`, `cwd=worktree_path`, env = `{**os.environ, ...}` forwarding `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN` when present.

**#1 — The crash is NOT currently diagnosable, because the child stderr is discarded (this is the real blocker and a prerequisite fix).** The SDK's `ProcessError.stderr` is a hardcoded placeholder `"Check stderr output for details"` (`_errors.py:36`, `subprocess_cli.py:583`). The real child stderr arrives via the `_on_stderr` callback into `_stderr_lines`, which `dispatch_task` feeds to `classify_error` but **never writes into the `dispatch_error` event** — `:797-805` logs only `error_detail = f"{type(exc).__name__}: {exc}"` (the placeholder). Historical April-2026 logs show the identical signature recurring → long-standing blind spot. **Fix #1: log `_stderr_lines` + `exit_code` into the `dispatch_error` event (`dispatch.py:799-805`).** Without it, every occurrence is a black box.

**#2 — `--effort xhigh` rejected by an installed CLI predating effort support (PROMOTED to top live candidate by the adversarial pass).** `_EFFORT_MATRIX` yields `xhigh` for `(complex, high)` and `(complex, critical)` — and `requires_review` gates review on exactly `tier=="complex" or criticality in (high,critical)`. Crucially, **implement** at `(complex, low/medium)` resolves to `high`, not `xhigh`. So a CLI that accepts `--effort high` but rejects `xhigh` would crash *only* review/review-fix and leave implement working — **exactly the observed pattern** (#206, #202 were reviewed features; the run's implement dispatches succeeded). An unknown-flag rejection exits in <200ms, matching the 134-176ms timing. **Checkable without a repro:** run `claude --effort xhigh -p "test"` against the installed CLI and compare to `MINIMUM_CLAUDE_CODE_VERSION`.

**#3 — Auth present-but-unreadable in detached launchd.** The auth probe (`auth.py:82-121`) checks Keychain *presence*, not readability; a locked login keychain can pass the probe yet fail the child. **Weakened** because pure auth failure should have broken implement identically (it didn't). `auth_probe` telemetry already exists to support this vector.

**RULED OUT:** relative `spec_path` (read by the *parent* before dispatch; the ticket's `issues:[]` proves the spec WAS read); sandbox denial / missing cwd (would surface mid-run or as `CLIConnectionError`→`infrastructure_failure`, not a startup `ProcessError`→`task_failure`).

**Verdict:** a live repro OR Fix #1 is required to distinguish #2 from #3 from committed evidence — *except* that #2 is independently checkable via the one-line CLI test above. Latent (not the crash, but flagged): the review prompt's relative `review.md` write target resolves under the worktree, and the home `cortex/lifecycle/` is not in sandbox `allowWrite`.

---

## Merge-Rollback Mechanism

**Round-execution model.** Features run **concurrently** within a round (`asyncio.gather`, `orchestrator.py:488`), bounded by a semaphore, onto **one shared** long-lived integration branch/worktree. A shared `asyncio.Lock` is held across merge+review in `apply_feature_result` (`:939`→`:1006`).

**Approach 1 — revert HEAD (`revert_merge()` as-is): UNSAFE today.** The Merge-Rollback agent argued HEAD==the feature's merge at defer time *because the lock spans merge+review*. The **adversarial pass refuted this**: `recover_test_failure` runs **outside** `ctx.lock` and itself calls `merge_feature` → `git merge` on the shared home worktree, while other features run concurrently. So feature B's out-of-lock recovery can advance HEAD while A holds the lock and reverts — A would revert **B's** commit. Revert-HEAD is **racy today**, not just after a hypothetical future optimization. It also silently **breaks on the rework path** (the cycle-1 re-merge creates a 2nd merge commit; revert-HEAD undoes only the re-merge).

**Approach 2 — SHA-anchored revert: RECOMMENDED (and required for correctness, not just robustness).** Add `merge_sha` to `MergeResult` (capture `git rev-parse HEAD` on the **success** return only — `run_tests` never commits, so this is sound; do NOT capture if `merge.py` already reverted on test failure). Revert via `git revert -m 1 --no-edit <sha>`, **capture-not-`check=True`**; on conflict `git revert --abort` + escalate to a blocking deferral (naming the dependent later feature, if any — see Adversarial #12). **The revert MUST run under `ctx.lock`** (concurrent `git checkout`+`revert` on one physical checkout corrupts the index). Reuse/extend the existing `revert_merge()` helper (add a `sha` param) rather than adding a fourth divergent revert site. `--no-ff` guarantees a revertable merge commit always exists.

**Approach 3 — move merge after APPROVED: rejected as disproportionate.** Collides head-on with the rework loop's re-merge and the post-merge test gate timing; touches both the sync and async appliers and `merge.py`'s test coupling. It is the right *long-horizon* destination but a multi-surface refactor — file as a follow-up, not a Bug-B point fix.

---

## Error-Path Control Flow & Verdict Handling

**Which path fires — definitive, with an adversarial refinement.** For the **exit-1 ProcessError** scenario: `dispatch_task` CATCHES `(ProcessError, CLIConnectionError, TimeoutError)` and bare `Exception` (`dispatch.py:795-832`) and **returns `DispatchResult(success=False)` — never raises**. `dispatch_review` ignores `result.success` (`:253`) → `parse_verdict(missing)` → `_ERROR_RESULT` → `ReviewResult(deferred=True, verdict="ERROR", cycle=0)` → **the `if rr.deferred:` path at `outcome_router.py:1019` fires.** *However* (adversarial #1): `resolve_effort()` and the model/tier matrix lookups run **before** the try block and **outside** any try/except in `dispatch_review`. A non-canonical tier from `read_tier` → `KeyError` in `_MODEL_MATRIX`, or a `ValueError` from `resolve_effort`, or an SDK-import `RuntimeError`, propagates out and hits the **`except Exception` path at `:1041`**. ⇒ **Both paths are reachable in production; the fix must harden both.**

**Sentinel / cycle:0 semantics — the ticket's "collision" claim is cosmetic and the named collision does not even exist.** Every consumer (`metrics.py::_extract_verdict`, `common.py` phase detection) keys off the **verdict string**, never `cycle`. The synthetic "morning-review skip APPROVED cycle:0" event the requirement describes is **not emitted anywhere in code** (confirmed `complete_morning_review_session.py` is a pure state transition) — a **requirement-vs-code drift to resolve before coding**. The real defect: `verdict="ERROR"` (could-not-run) is collapsed into the same `deferred=True` outcome as REJECTED/CHANGES_REQUESTED (review-ran-and-said-no), and the live `rr.deferred` ERROR path writes **no deferral file** (the ERROR handler at `review_dispatch.py:300-314` doesn't call `_write_review_deferral`, unlike the REJECTED/CHANGES_REQUESTED paths).

**Retry-before-defer.** Belongs in `dispatch_review`, gated on `result.success` (the single missing branch after `:263`), bounded to **1 retry** (matching `outcome_router.py:214`'s "prune and retry once"), **separate from** the 2-cycle rework content budget (a crash never produced a verdict, so it must not consume a rework cycle or trigger the SHA circuit breaker). On retry-exhaustion, fall through to a **crash-distinct** defer that writes a real blocking `DeferralQuestion`. **Caveat (adversarial #11):** if the crash is systemic, retry doubles wasted dispatches; and review crashes route to `features_deferred`, NOT `features_paused`, so they **never increment** `systemic_pauses_in_batch` → the `pipeline_systemic_failure` circuit breaker is **blind to a review-crash cascade**. Gate retries with a systemic-crash detector and consider feeding review-crash deferrals into the systemic counter.

---

## Surfacing & Observability

**Confirmed: surfacing is a genuine THIRD defect, and the "green-looking summary" claim is substantiated at the PR surface.** The morning report reads **OvernightState** (`overnight-state.json`), not backlog status. A merged-then-deferred feature takes the `rr.deferred` path → appended only to `features_deferred` → `map_results.py` sets state status `"deferred"` (recoverable_branch=None). Consequences:
- Exec summary counts it under `deferred` (honest bare integer; verdict is "Needs attention", not "Clean run").
- But because the `rr.deferred` path **omits `write_deferral()`**, it is **absent** from the Deferred Questions section (`report.py:978-1025`, renders only from `deferred/*-q*.md` files); the **"Feature is on the integration branch — do NOT re-run" warning never fires** (gated on a deferral file + a `feature_merged` event — the event exists, the file doesn't); it **vanishes from the action checklist**; and `create_followup_backlog_items` mints a follow-up ticket pointing at a q-file that was never written (q_count=0, misleading).
- **The session PR is the green surface:** body says "N features merged" (non-draft, no feature names, no deferral mention); **ZERO PROGRESS gating ignores it** (counts toward neither merged nor recoverable), so the deferred-but-already-merged code rides along on a green, non-draft PR with no flag.

**Minimal, high-leverage fix:** make the `rr.deferred` path call `write_deferral()` (mirroring the crash/CI paths), carrying the review verdict/cycle at `SEVERITY_BLOCKING`. That single change reactivates the existing, already-tested surfacing machinery. Secondary: reconsider the `"in_progress"` backlog write-back (`"deferred"` is more honest; `"in_progress"` isn't even a valid OvernightState status); consider listing deferred-feature names in the PR body. **Caveat (adversarial #8):** `_write_review_deferral` uses `question_id=0` (scan-for-next), while the except path uses `_next_escalation_n` — two different ID sources; on session **resume** this can mint duplicate/conflicting `-q00N.md` files. Reconcile the ID sources and add resume-idempotency.

---

## Adversarial Review

Findings that materially reshape scope (verified against code):

1. **Both error paths fire** (not just `rr.deferred`) — pre-spawn raises (tier `KeyError`, `resolve_effort` `ValueError`, SDK import) route to the `except` path. Harden both. *(Refines the Codebase/Error-Path "only rr.deferred fires" conclusion.)*
2. **`--effort xhigh` promoted to top root-cause candidate** — review uses `xhigh`, implement uses `high`; a CLI rejecting only `xhigh` produces the exact observed review-only crash pattern.
3. **NEW Bug D — total review-gate bypass on the test-recovery path (missed by all six core agents, arguably the most severe).** When a merged feature fails the post-merge test gate and is recovered via `recover_test_failure` (`outcome_router.py:1217`), the success branches (`:1234` flaky, `:1253` recovered) append to `features_merged` and write `"merged"` **without ever calling `dispatch_review`** — even when `requires_review` is True. So complex/high/critical features that need test-recovery already ship **with zero review**, independent of the exit-1 crash. A fix that only hardens the `:1006` path gives false confidence that "unreviewed code can't ship."
4. **revert-HEAD is racy today** (recovery runs out-of-lock on the shared worktree) → SHA-anchored revert under `ctx.lock` is required for correctness, not just robustness. *(Refutes the Merge-Rollback "works by accident today" framing.)*
5. **Rework dual-SHA revert is tangled** — `merge.py` already reverts the re-merge on test failure (not `check=True`), so a naive "revert both SHAs" may double-revert an already-reverted commit. The rollback must query actual branch state.
6. **The sync `_apply_feature_result` review-defer branch (`:657-678`) is DEAD CODE** (`review_result` is always `None` there). *(Corrects the Codebase agent's "Bug B has two live code paths.")* Decide delete-vs-wire.
7. **`write_deferral` on the ERROR path has resume-idempotency + dual-ID-source hazards** (see Surfacing caveat).
8. **events-registry drift gate will block the obvious fix** — `review_verdict` and `dispatch_error` rows hard-code producer line numbers; inserting code shifts them and trips the pre-commit gate unless the registry is updated in the same commit (`pipeline_systemic_failure`'s producer line is already `<TBD>` — registry partially stale).
9. **Circuit breaker is blind to review-crash cascades** (deferrals don't increment the systemic-pause counter).
10. **Dependent-feature revert conflict** — reverting feature X when later feature Y merged dependent code conflicts; the escalation must flag Y as now referencing reverted code.

---

## Open Questions

The load-bearing scope decision (Q1) was resolved by the user at the Research Exit Gate; Q2–Q7 are explicitly deferred to the Spec interview (they are design/investigation items that do not change scope).

1. **SCOPE — how many defects are in scope? → RESOLVED (user, 2026-06-09): FULL TRUST-FIX.** All four defects are in scope: (A) ERROR-verdict-handling + missing deferral file; (B) no merge rollback on defer/crash (both error paths hardened); (C) green-PR surfacing; (D) total review bypass on the test-recovery path. Plus the diagnosability prerequisite (Fix #1: log child stderr) and the root-cause fix (#2: validate/gate `--effort` against the installed CLI; auth-readability probe included as the secondary root-cause vector). Rationale accepted: B and D are the same "no unreviewed code ships" invariant; shipping B without D re-creates the headline outcome.
2. **Requirement-vs-code drift → DEFERRED to Spec.** `pipeline.md` describes a synthetic "morning-review skip `APPROVED, cycle:0`" event and line refs that do not match current code / the restructured `docs/internals/pipeline.md`. Spec §1 re-reads requirements and reconciles: determine whether the requirement is stale or implemented elsewhere before encoding any "preserve this contract" criterion. Investigation, not a user decision.
3. **Root-cause confirmability → DEFERRED to Spec.** Spec confirms `--effort xhigh` via `claude --effort xhigh -p test` against the installed CLI (no overnight repro needed). If unconfirmable pre-repro, the spec lands Fix #1 (instrumentation) + the strongest tractable fix and states explicitly that final root-cause confirmation may need the next overnight run.
4. **Retry vs systemic detection → DEFERRED to Spec.** Design decision: should review-crash deferrals feed the `pipeline_systemic_failure` circuit breaker (currently blind), and should retry short-circuit on N identical exit-1 `dispatch_error`s? Resolved in the Spec interview.
5. **Rework-path rollback design → DEFERRED to Spec/Plan.** `merge.py` already reverts the re-merge on test failure (not `check=True`), so the dual-SHA revert must query branch state, not assume both SHAs are live.
6. **Dead sync path (`:657-678`) → DEFERRED to Spec.** Confirm it is dead and decide delete-vs-wire.
7. **Dependent-feature revert conflict → DEFERRED to Spec.** Handling + the escalation message contract (name the dependent later feature).

---

## Considerations Addressed

- **Which error path fires on exit-1** — Resolved: for the exit-1 ProcessError, `dispatch_task` returns `success=False` (never raises) → `parse_verdict`→ERROR sentinel → the `rr.deferred` path at `outcome_router.py:1019` fires (NOT the except path). The ticket's mechanism narrative was correct; the clarify-time guess that the except path fires was wrong. **Refinement:** pre-spawn raises (tier `KeyError`, `resolve_effort`) DO hit the except path, so both are reachable and both need hardening.
- **Root cause of the systemic exit-1** — Partially resolved: not diagnosable from committed logs because child stderr is dropped (Fix #1 is the prerequisite). Top candidate is `--effort xhigh` rejected by an outdated CLI (fits the review-only, sub-200ms pattern; checkable via a one-line CLI test); auth-unreadable is the weaker secondary. Relative spec_path and sandbox/cwd ruled out.
- **`revert_merge()` HEAD hazard / SHA-anchored alternative** — Resolved: revert-HEAD is racy *today* (out-of-lock recovery on the shared worktree) and wrong on the rework path. SHA-anchored revert (capture merge SHA → `git revert -m 1 <sha>`, under `ctx.lock`, capture-not-check, abort+escalate on conflict) is required, reusing/extending the existing `revert_merge()` helper.
- **Move-merge-after-APPROVED alternative** — Resolved: it conflicts with the merge-first requirement AND collides with the rework loop's mid-review re-merge and the post-merge test-gate timing. It is an architecture-level restructure; SHA-anchored revert-on-defer is the lower-blast-radius, requirements-consistent fix. File merge-after-approval as a follow-up.
- **Reconcile with the defer-on-failure must-have / retry vs repair-cap** — Resolved: defer + deferral-file is REQUIRED; the fix preserves defer and ADDS rollback (does not replace defer with halt). Retry-before-defer is a bounded (cap 1) infra recovery distinct from the 2-cycle rework content budget, and must be systemic-crash-aware.
- **report.py surfacing / third defect** — Resolved: confirmed as a real third defect. The live `rr.deferred` path omits `write_deferral()`, so the deferred-but-merged feature is invisible across the Deferred Questions section, the "on integration branch — do NOT re-run" warning, the action checklist, and the non-draft green PR. Minimal high-leverage fix: call `write_deferral()` on the ERROR/deferred path (with resume-idempotency + dual-ID reconciliation).
