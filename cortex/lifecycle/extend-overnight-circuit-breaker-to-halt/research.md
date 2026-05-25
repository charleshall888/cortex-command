# Research: Extend overnight circuit breaker to halt on systemic worker failures

## Codebase Analysis

### Files that will change (verified)

- `cortex_command/overnight/feature_executor.py`
  - `_SESSION_HALT_ERROR_TYPES` tuple at **line 70** (currently `("budget_exhausted", "api_rate_limit")`). Slice A would extend this — but see Adversarial Review for why a tuple append alone is insufficient.
  - `WORKER_NO_EXIT_REPORT` emit site at **lines 773–779**. **Critical gap**: the no-exit-report branch logs the event but does NOT set `result.error` on the returned `FeatureResult`. The branch marks the task done at line 782 (`mark_task_done_in_plan(...)`) and then returns `FeatureResult(name=feature, status="completed")` at line 785. Halting on this string therefore requires restructuring the branch to return a paused `FeatureResult` with `error="worker_no_exit_report"`, not just appending to the tuple.
  - `_read_exit_report` (**lines 139–181**) returns `(None, None, None)` for both missing-file and malformed-JSON cases; `worker_malformed_exit_report` (events.py:54) is defined but currently silent.
- `cortex_command/overnight/orchestrator.py`
  - Two circuit-breaker check sites: **lines 404–427** and **lines 505–519**. Both use `result.error in _SESSION_HALT_ERROR_TYPES` and set `batch_result.global_abort_signal = True`. New cascade detector can hook here.
  - `cb_state = CircuitBreakerState()` at **line 351** is constructed fresh inside `run_batch()` — no persistence into `OvernightState`. Cross-round and cross-resume cascades are invisible to the counter.
- `cortex_command/overnight/outcome_router.py`
  - `consecutive_pauses` increment sites: lines 509, 536, 657, 706, 725, 1098 (14 mutation sites total). Reset sites: 470, 589, 914, 1052, 1071. All mutations happen under `ctx.lock`. The existing breaker fires a logged event at line 741 **but does not set `global_abort_signal`** — so its semantics differ from the session-halt tuple.
- `cortex_command/overnight/types.py` — `CircuitBreakerState` at **line 35**. New field needed (`consecutive_systemic_pauses` or equivalent).
- `cortex_command/overnight/constants.py` — `CIRCUIT_BREAKER_THRESHOLD = 3` at **line 7**.
- `cortex_command/overnight/events.py` — `WORKER_NO_EXIT_REPORT` constant at **line 53**, `WORKER_MALFORMED_EXIT_REPORT` at line 54. New constant required for the cascade event (proposed `PIPELINE_SYSTEMIC_FAILURE`).
- `cortex_command/overnight/report.py` — EPERM taxonomy at **lines 1908–1921**: keys `plumbing_eperm`, `unclassified_eperm`. **This taxonomy is computed post-hoc by `collect_sandbox_denials` (line 1312)** from `bash.log` and `sandbox-deny-lists/` sidecars. It is never written to `FeatureResult.error` or `RetryResult.error_type`. The "alignment with report.py:1916" claim in the ticket needs careful framing — see Open Questions.
- `cortex_command/pipeline/retry.py`
  - `pause_session` branch at line 398 sets `error_type=error_type`.
  - `pause_human` branch at **lines 370–377** (which handles `infrastructure_failure` and `agent_refusal`) returns `RetryResult(paused=True)` **without** setting `error_type`. Latent bug — any new tuple entry covering these strings is silently neutered today.
- `bin/.events-registry.md` — needs a new row for the cascade event with producer/consumer (consumer can be TBD).

### Existing patterns

- **Session-halt tuple pattern**: tuple of literal strings checked via `in` membership at orchestrator gates; trip sets `global_abort_signal = True`.
- **Class-blind consecutive-pause breaker**: `CircuitBreakerState.consecutive_pauses` + `CIRCUIT_BREAKER_THRESHOLD=3`; fires a logged event without halting the session. Two breakers therefore already coexist (event-only + session-halt); a third would extend this dimensionality.
- **Event emission**: `overnight_log_event(EVENT_TYPE, batch_id, feature, details={...}, log_path=...)`; events.py constants + `EVENT_TYPES` tuple + registry row.
- **State writes**: file-based, atomic via tempfile + `os.replace()` (ADR-0001). `CircuitBreakerState` is currently **in-memory only**.

### Integration points

- Slice A: feature_executor.py post-success no-exit-report branch must be restructured to return a paused FeatureResult. Orchestrator gate (404–427, 505–519) will then pick it up via existing tuple-membership check — no orchestrator change needed once feature_executor is right.
- Slice B: cascade detector lives alongside the existing `consecutive_pauses` increment in outcome_router.py. Classification reads `result.error` / `result.error_type`. New event emit on threshold trip.
- Pre-dispatch gate (`orchestrator.py:357, 376–384`) blocks new features after `global_abort_signal=True`. Mid-flight features continue (this is true of the existing budget breaker as well).

### Test fixtures

- `tests/test_feature_executor.py` — Slice A behavior.
- `tests/test_lead_unit.py`, `tests/test_brain.py` — `CircuitBreakerState` fixtures.
- `tests/test_report.py`, `tests/test_report_sandbox_denials.py` — classification logic if Slice B parallels morning-report EPERM rendering.

## Web Research

### Threshold patterns

- **Hystrix / Resilience4j**: rate-over-window is the canonical pattern, but with a *minimum volume* (Hystrix default `requestVolumeThreshold=20`) to avoid tripping on small samples. At cortex's small per-round volumes, consecutive-count is the right adaptation.
- **Celery + SQS broken-worker breaker** ([dev.to](https://dev.to/ivoronin/celery-sqs-stop-broken-workers-from-monopolizing-your-queue-with-circuit-breakers-11dj)): the closest analog — `fail_max=3, reset_timeout=60` at the worker-process level for systematic (GPU/hardware) failures while letting isolated data problems pass. Direct citation for **N=3 consecutive**.
- **Apache Airflow `max_consecutive_failed_dag_runs_per_dag`** ([config ref](https://airflow.apache.org/docs/apache-airflow/stable/configurations-ref.html)): default `0` (disabled), operator opt-in. Counter-example to "halt by default" — a major orchestrator declined that posture.
- **Laravel Fuse**: N=5 consecutive for queue jobs.
- **Microsoft Azure Circuit Breaker pattern** ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)): explicitly endorses **per-error-class thresholds** and **"accelerated circuit breaking"** for unambiguous signals (N=1 for the unambiguous, N=3 for the accumulator).

### Classifying transient vs systemic errors

- **arXiv 2508.13143** ("Why Autonomous Agents Fail"): three-tier failure taxonomy; **Tier 2 Execution errors** map directly to EPERM/sandbox/seatbelt-probe-fail. Recommends: *"if the system detects repetitive, unresolved errors, the mechanism should trigger an 'early stop', halting the process before it hits the maximum round limit, thereby saving resources."*
- **arXiv 2507.03870**: formalizes "**environment errors**" (unfavorable environment makes task success inherently infeasible) vs "**agent errors**". Detection: differential testing across configurations — repeated failure across task identities sharing an environment fingerprint = environment error. EPERM/sandbox-denied are textbook environment errors.
- **Sidekiq**: `SyntaxError` should never be retried — errors-that-cannot-succeed-on-retry deserve distinct handling. Direct analog for promoting systemic-class errors to halt.

### Over-halt vs under-halt bias

- **GitHub Actions matrix `fail-fast: true`** is the default — over-halt is industry norm for CI/batch.
- **Hystrix**: explicit fail-fast philosophy — over-halt as safety default.
- **Airflow's opt-in default**: counter-example specifically from the **overnight-batch** family (not the request-response family). Suggests over-halt bias may not transfer cleanly from request-response circuit breakers to overnight-batch breakers — the cost of a wrong halt is "operator wakes up to a paused session that could have produced 4 more merged features."

### Anti-patterns

- **Bazel silent fallback to weaker sandboxing**: an explicit anti-pattern in the literature. Whatever the cortex runner does on sandbox-init failure, it should NOT silently degrade.
- **pytest-xdist endless crash-restart loop** ([issue #440](https://github.com/pytest-dev/pytest-xdist/issues/440)): historical bug — workers crashing, restarting, crashing. Exactly the failure mode this ticket prevents.
- **EPERM misclassification cascades**: openclaw#62099 — treating environmental EPERM as fatal in fallback chains caused full system unresponsiveness.

## Requirements & Constraints

### Status-transition vocabulary (pipeline.md)

- Feature lifecycle: `pending → running → merged | paused | deferred | failed`. Session-halt is **session-level**, distinct from feature pause.
- Session phases: `planning → executing → complete`; any phase → `paused`. Session resume re-enters the phase it paused from.
- Current session-halt set: `_SESSION_HALT_ERROR_TYPES = ("budget_exhausted", "api_rate_limit")` (feature_executor.py:70). When `result.status == "paused"` and `result.error in _SESSION_HALT_ERROR_TYPES`, the orchestrator sets `global_abort_signal = True` and the session transitions to `paused`.

### Existing batch circuit breaker (multi-agent.md, constants.py)

- Threshold: `CIRCUIT_BREAKER_THRESHOLD = 3` consecutive pauses (any class).
- On trip: logged event, no `global_abort_signal` set. Differs from the session-halt tuple.

### Event registration (project.md, bin/.events-registry.md)

- New event constant in `events.py`, add to `EVENT_TYPES` tuple, register in `bin/.events-registry.md` with producer file:lines, consumer (may be `TBD`), category `live`, registered date, rationale, owner.

### ADRs

- **ADR-0001 (file-based state)**: state writes are atomic (tempfile + `os.replace()`). New events go to `overnight-events.log` JSONL. Cross-session state needs `OvernightState` field per ADR.
- **ADR-0002 (CLI wheel + plugin)**: `_SESSION_HALT_ERROR_TYPES` exported by `cortex_command.overnight.feature_executor` — new strings importable from sibling modules.

### Out of scope

- Application code, dotfiles, reusable libraries (project.md).
- Inline EPERM classifier hoisting (`collect_sandbox_denials` from morning-report time into per-feature time) — separate ticket; see Open Question 2.

## Tradeoffs & Alternatives

Five alternative designs surveyed for the cascade detector (Slice B):

- **Alternative A — Hardcoded `_SYSTEMIC_ERROR_TYPES` tuple + flat consecutive counter (N=3)**. Same idiom as existing budget-exhaustion breaker — sibling tuple, sibling counter on `CircuitBreakerState`, threshold-compare call site. ~30 LOC + tests. **Trades away**: under-halts on unanticipated error strings, cannot tolerate intervening idiosyncratic pause, duplicates a small fragment of `report.py:1916`.
- **Alternative B — Regex pattern list + rolling window (3 of last 5)**. Open-set classification catches unknown EPERM variants by lexical markers. ~80 LOC + tests. **Trades away**: introduces new pattern abstraction, regex over free-form error strings risks surprise matches, misaligns with existing tuple idiom.
- **Alternative C — Lift `collect_sandbox_denials` taxonomy + rate-over-window**. Highest semantic alignment with report.py:1916 — literally the same enum. ~150+ LOC including refactor. **Trades away**: wall-clock dependency awkward to test, requires hoisting refactor as prerequisite.
- **Alternative D — Inverted (over-halt) classifier**. Halt on any pause NOT on a small known-task-specific allowlist. **Trades away**: very high false-positive rate by construction; misaligns with ticket's "align with EPERM enum" framing.
- **Alternative E — Per-task-type counters**. Each systemic class has its own counter. **Trades away**: splits the systemic-cascade signal across counters that never individually trip — anti-aligned with the cascade motivation.

**Initially-recommended approach** (pre-Adversarial-Review): Alternative A. Cleanest extension of the existing budget-exhaustion breaker shape; capable maintainers see one mechanism, two tuples. Migration path to B is additive if production needs open-set classification later.

**Caveat surfaced by Adversarial Review**: Alternative A's correctness depends on the systemic error strings actually reaching `FeatureResult.error` / `RetryResult.error_type`. Today, several do not (see Open Questions 3, 4). The recommendation stands as the **design shape** but the spec must address the upstream wiring as a prerequisite.

## Adversarial Review

Replay across the in-tree corpus of `lifecycle/sessions/**/overnight-events.log` produced these material findings:

1. **The "rare" framing is empirically false.** 71 `worker_no_exit_report` events across 9 of ~24 inspected sessions. Specific cases: session `overnight-2026-03-27-0121` had 21 `worker_no_exit_report` events alongside 7 `feature_complete` events in the same session — features like `arena-setup-camera2d-...` and `combat-feedback-hit-flash` emitted `worker_no_exit_report` on intermediate tasks and *still* reached `feature_complete`. Slice A as ticketed (halt on first occurrence) would have aborted multiple historical sessions that succeeded. The ticket's Edges line — "silent workers are rare and usually mean something deeper is wrong" — does not survive contact with the data.

   **Root cause**: `_read_exit_report` returns `(None, None, None)` for the legitimate case of a successful worker that didn't write the JSON sidecar. The no-exit-report logging at lines 773–779 happens **after** `result.success=True` — today's "no exit report" is mostly a bookkeeping omission, not a systemic failure.

2. **Slice A is not a 10-line tuple addition.** Two distinct restructurings are required:
   - feature_executor.py post-success no-exit-report branch must return paused `FeatureResult` with `error="worker_no_exit_report"` instead of `status="completed"`.
   - `pipeline/retry.py:370-377` (`pause_human` branch) must thread `error_type` through (line 398 already does this for `pause_session`).
   The session-halt check at `feature_executor.py:688` runs on `result.error_type`; the orchestrator check at line 406 runs on `result.error`. Tuple membership tests both paths but each producer must set both fields.

3. **The cascade detector cannot read EPERM/sandbox-denial labels because none exist inline.** `report.py:1916`'s closed enum is computed by `collect_sandbox_denials` at morning-report time from `bash.log` and `sandbox-deny-lists/` sidecars. It is never threaded through `RetryResult.error_type` or `FeatureResult.error`. The "align with EPERM taxonomy" framing in the ticket is architecturally aspirational — the two taxonomies live at different layers and will diverge unless inline EPERM classification is hoisted (separate ticket).

4. **`infrastructure_failure` cannot reach session-halt today.** retry.py:370–377 pause_human branch does not set `error_type`. Latent bug — any tuple expansion that adds `infrastructure_failure` is silently neutered.

5. **CircuitBreakerState resets every batch round.** `cb_state = CircuitBreakerState()` constructed inside `run_batch()` (orchestrator.py:351). No `OvernightState` persistence (zero hits for `consecutive_pauses` in state.py). Cross-round and cross-resume cascades are invisible.

6. **Concurrency makes effective N larger than configured N.** 3 features dispatched concurrently can all fail and increment the counter under lock from 0→3, but each was already past the pre-dispatch gate. Pre-dispatch gate (orchestrator.py:357, 376–384) only blocks **new** features after `global_abort_signal=True`. Effective N ≈ configured N + concurrent_inflight. This is true of the existing budget breaker as well, but the ticket should acknowledge it.

7. **Counter race at threshold.** If both class-blind `consecutive_pauses` and new `consecutive_systemic_pauses` are at 2 and the next pause is systemic, both increment to 3; both threshold checks fire; one sets nothing, the other sets `global_abort_signal=True`. Duplicate events. Interaction is not specified in the ticket.

8. **"Consecutive" semantics is ambiguous for class-aware counters.** What resets the systemic counter?
   - Any success → cascade with intervening merge-conflict is hidden.
   - Any non-systemic pause → an EPERM-cascade interrupted by one merge-conflict resets, hiding the cascade.
   - Only systemic-class pauses count, never reset by anything else → renames to `systemic_pauses_in_batch`, not "consecutive".
   The existing budget breaker dodges this — its session-halt strings short-circuit to `global_abort_signal` without going through the counter at all.

9. **`worker_malformed_exit_report` is symmetric with `worker_no_exit_report` but excluded from Slice A.** Bad JSON in the exit report is at least as diagnostic as missing file. Slice A drops it. Symmetry violation.

10. **`integration_degraded` is a Bazel-style silent fallback in the runner.** `state.py:240` defines `integration_degraded: bool = False`; `runner.py:1498, 1549` show the runner has a degraded-mode path that downgrades rather than halts. If the systemic-environment cascade happens during integration-worktree setup and gets coerced into `integration_degraded=True`, the cascade is invisible to per-feature error_type — only surfaced in the PR body. Per-feature breaker cannot see upstream silent degradation.

### Recommended mitigations (input to Spec)

- Drop "Slice A as 10-line tuple addition" framing. Re-scope Slice A's halt trigger to gate on `worker_no_exit_report` AND no commits produced AND retry budget exhausted — i.e., only when the silence is genuinely diagnostic, not bookkeeping. Include `worker_malformed_exit_report` for symmetry.
- Reject "align with `report.py:1916` taxonomy" as written. Either (a) file a prerequisite ticket to hoist inline EPERM classification before Slice B, or (b) restrict Slice B's systemic-class membership to errors that *already* reach `FeatureResult.error` (dispatch-layer types: `infrastructure_failure`, `agent_timeout`, `worker_no_exit_report`, etc.) and explicitly note the morning-report taxonomy is a separate concern.
- File `pipeline/retry.py:370-377` `error_type` propagation fix as a prerequisite ticket. Block Slice B on it (or fold the fix into Slice B's commit).
- Decide persistence: per-batch only (in-memory `CircuitBreakerState`) or persist `consecutive_systemic_pauses` in `OvernightState`. Document the choice explicitly.
- Define `cause_class` as a list (the three triggering pauses likely have different classes; preserving all three matters for morning-report drill-down).
- Decompose the "consecutive vs total" question explicitly. Whichever the spec picks, name the field accordingly.
- Validate N empirically against the historical corpus before committing to a value.
- Audit `integration_degraded` set-sites for masking.

## Open Questions

These questions are load-bearing for the spec. Items marked **(decide in Spec)** are deferred to the structured interview in Step 5; items marked **(blocks Spec entry)** require user resolution before transitioning.

1. **(blocks Spec entry) Slice A scope, given the empirical refutation.** The historical corpus shows `worker_no_exit_report` co-occurring with successful feature completions ~10× more often than with failures. The ticket's framing assumed rarity. Options the spec must pick from:
   - (1a) Drop Slice A entirely; the per-event halt is empirically wrong.
   - (1b) Re-scope Slice A: halt only when `worker_no_exit_report` AND retry exhausted AND no commits produced (the "genuinely diagnostic" gate). Include `worker_malformed_exit_report` for symmetry.
   - (1c) Accept Slice A as ticketed despite the empirical refutation — i.e., explicit decision that over-halt is preferred even at the demonstrated false-positive rate.
   - Recommendation: 1b.

2. **(blocks Spec entry) "Align with `report.py:1916` EPERM taxonomy" claim.** The two taxonomies live at different layers. Options:
   - (2a) File and block on a prerequisite ticket to hoist inline EPERM classification before Slice B is built. Slice B then reuses the lifted classifier.
   - (2b) Restrict Slice B's systemic-class to dispatch-layer error strings already reaching `FeatureResult.error`. Document that the morning-report EPERM taxonomy is a separate concern, not aligned-by-construction.
   - Recommendation: 2b for now; 2a as a follow-up.

3. **(blocks Spec entry) `pipeline/retry.py:370-377` `error_type` propagation.** `pause_human` returns `RetryResult(paused=True)` without `error_type`. Today this is a latent bug; any tuple expansion is silently neutered. Options:
   - (3a) File as prerequisite ticket and block Slice B.
   - (3b) Fold into Slice B's commit (add `error_type` to `pause_human` returns).
   - Recommendation: 3b — the fix is local and the test surface is shared.

4. **(decide in Spec) Persistence.** Per-batch only (in-memory) vs persisted in `OvernightState`. Per-batch only is simpler and matches existing `consecutive_pauses`; persistence catches cross-round/cross-resume cascades.

5. **(decide in Spec) "Consecutive" semantics.** What resets the systemic counter — any success, any non-systemic pause, or never (rename to total-in-batch)?

6. **(decide in Spec) N (threshold).** Industry precedent supports 3 (Celery+SQS) or 5 (Laravel Fuse, Airflow example). Replay against the in-tree corpus should inform the choice. Default proposal: N=3, configurable via `constants.py`.

7. **(decide in Spec) `cause_class` field shape.** Scalar (last/most-common class) vs list (preserve all three triggering classes). Recommendation: list.

8. **(decide in Spec) Mid-flight halt check.** Add a check inside `execute_feature` to abort in-flight features after `global_abort_signal=True`, or accept that concurrent in-flight features finish (current budget-breaker behavior).

9. **(decide in Spec) Concrete systemic-class membership.** Confirmed candidates (dispatch-layer strings that already reach `FeatureResult.error_type`): `infrastructure_failure`, `worker_no_exit_report`, `worker_malformed_exit_report`. Open: should `agent_refusal` count? `agent_confused`? These appear in the `pause_human` branch and may also be environment-driven.

10. **(decide in Spec) `integration_degraded` audit.** Whether to explicitly add a guard so silent degraded-mode coercion does not mask the systemic cascade. May expand Slice B's footprint.
