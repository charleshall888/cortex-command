# Research: Write-boundary coherence guardrail for the review-gate deferral flags

**Feature:** `review-gate-flag-coherence-a-feature` (backlog #320) · complex / high

**Goal:** make `could_not_run == True AND review_dispatch_crashed == True` impossible to
**emit** on a `FEATURE_DEFERRED` event, so the ADR-0015/R6 mutual-exclusion cannot silently
regress as future write sites or edits accrue. Regression insurance, not a live fix — the combo is
already unreachable in current code. Out of scope: the ADR-0015 preserve-vs-revert *policy*; the
#319 path-contract fix; the read-side mis-trust asymmetry (see Adversarial).

> ADR reference: `cortex/adr/0015-review-could-not-run-vs-dispatch-crash-split.md` is the canonical
> home for the policy this guard protects. The guard codifies that policy's *derived* invariant; it
> does not reopen the policy.

## Codebase Analysis

**Only production file that changes: `cortex_command/overnight/outcome_router.py`.**
`cortex_command/pipeline/review_dispatch.py` does **not** change — it carries `could_not_run` only as
a `ReviewResult` dataclass field (`:65`) and never writes `merge_reverted` / `review_dispatch_crashed`
nor emits `FEATURE_DEFERRED`. The ticket's touch-point list naming `review_dispatch.py` as a flag
origin is inaccurate for the *event-detail* flags (clarify-critic obj 2, confirmed).

**Emit topology — 10 real `FEATURE_DEFERRED` emissions** (the earlier "11" over-counted the import at
`:47` and a comment at `:2060`):

| # | Emit line | Function | context | sets the 3 flags? |
|---|-----------|----------|---------|-------------------|
| 1 | 759 | `_apply_feature_result` | CI-error | none |
| 2 | 801 | `_apply_feature_result` | merge-conflict | none |
| 3 | 842 | `_apply_feature_result` | deferred passthrough | none |
| 4 | 1210 | `_recovery_review_gate` | in-band ERROR (via helper @1206) | `could_not_run`+`merge_reverted` |
| 5 | 1259 | `_recovery_review_gate` | **crash-`except`** | `could_not_run` XOR `review_dispatch_crashed` |
| 6 | 1566 | `_repair_completed_review_gate` | in-band ERROR (via helper @1562) | `could_not_run`+`merge_reverted` |
| 7 | 1638 | `_repair_completed_review_gate` | **crash-`except`** | `could_not_run` XOR `review_dispatch_crashed` |
| 8 | 1954 | `apply_feature_result` | in-band ERROR (via helper @1950) | `could_not_run`+`merge_reverted` |
| 9 | 2020 | `apply_feature_result` | **crash-`except`** | `could_not_run` XOR `review_dispatch_crashed` |
| 10 | 2130 | `apply_feature_result` | CI-error (sync top-level) | none |

- **6 review-gate emits** = #4–#9. The other 4 (#1,2,3,10) never set any of the three flags → any
  conjunction-keyed guard is **vacuous** for them.
- The forbidden combo can **only** arise at the **3 crash-`except` emits** (1259/1638/2020) — the only
  places `review_dispatch_crashed` is ever written.
- The in-band helper `_set_review_error_detail_flags` (`:1024`) mutates `details` in place, sets
  `could_not_run=True` + `merge_reverted`, and **by contract never sets `review_dispatch_crashed`**.
- Each crash-`except` computes `preserved = rr is not None and rr.could_not_run`, then
  `if preserved: could_not_run=True / merge_reverted=False` else `review_dispatch_crashed=True` —
  already disjoint branches (this is why the combo is unreachable today).

**Conventions to mirror:**
- Existing fail-loud guard idiom: `_guard_no_review_qualifying_sync_merge(name, site)` (`:1319-1341`) —
  a module-level message constant + a `None`-returning validator that `raise RuntimeError(...)`. A new
  `_guard_review_flag_coherence(details, *, site)` fits this idiom exactly.
- `overnight_log_event` (= `events.py:log_event`, `:200`) **already raises `ValueError`** when
  `event not in EVENT_TYPES` (`:222-225`) — fail-loud-at-emit precedent. It serializes `details`
  synchronously (`json.dumps`, `:243-247`); "attaches by reference" is true but inert (no post-emit
  mutation window).
- `raise RuntimeError`/`ValueError` is the module convention; **no `assert` exists in the module**.
  Module header forbids importing `batch_runner`/`orchestrator`.

## Web Research

External prior art converges on the design the ticket implies:
- **`raise`, not `assert`.** `assert` is stripped under `python -O`/`PYTHONOPTIMIZE`; it is for
  *programmer-error* invariants, not data invariants at a serialization boundary. Use an explicit
  `raise` (named `ValueError`/`RuntimeError` subclass) so the check always runs and names the violated
  invariant.
- **Single choke point = the Python-idiomatic "make illegal states unrepresentable."** Python can't
  type-enforce mutual exclusion at runtime, so the practical form is *centralize emission behind one
  funnel and validate once there* (smart-constructor / `__post_init__` / factory).
- **Keep the guard off the `except` path, or `raise … from err` (never `from None`)** so it cannot
  mask the original exception via context-chaining.
- **Write-strict / read-permissive asymmetry** is the documented event-sourcing **tolerant-reader**
  pattern: enforce new invariants at the *write* boundary; keep *read/replay* permissive (defaults,
  upcasters), never rejecting historical data. This is a backward-compatible change by construction.

## Requirements & Constraints

- **pipeline.md §Post-Merge Review** documents the could-not-run (preserve, `merge_reverted=False`,
  positive `could_not_run` discriminator, `review_no_artifact`) vs dispatch-crash (revert,
  `review_dispatch_crashed`, `review_dispatch_crash`) split as a must-have. The positive
  `could_not_run` is **never inferred from `merge_reverted=False`** (a failed-revert crash also yields
  `False`). The guard protects exactly this discriminator.
- **MUST-escalation policy (CLAUDE.md) does NOT govern a code `raise`/`assert`.** It is scoped to
  prose MUST/CRITICAL imperatives aimed at *model behavior* (evidence artifact = an F-row of Claude
  skipping a soft form). A deterministic code-level guard is the *structurally preferred* enforcement
  (CLAUDE.md "structural separation over prose-only"). **No effort-first / evidence-artifact gate
  applies** to this change.
- **No events-registry edit required.** The three flags are already declared field-additive on
  `feature_deferred` (`bin/.events-registry.md:174-176`), whose prose already states
  `review_dispatch_crashed` "denotes a crash exclusively." The registry static gate doesn't scan
  `outcome_router.py` (Python emit = `manual`/out-of-scan). A registry edit is needed **only** if the
  change mints a *new* event (e.g. a `flag_coherence_violation` telemetry event — not recommended).
- **Historical-compatibility-shim constraint (project.md):** read-side consumers tolerate archived
  schemas with `.get(..., False)`. The guard must live at the **write** boundary and must not be wired
  into any reader/replay path — pre-R6 archived events legitimately co-set both flags.
- **Complexity must earn its place / Solution horizon:** the "rule replicated across three sites + a
  shared helper" is the named-multiple-places condition that authorizes a single coherence authority
  over per-site patches — but proportional to the ticket's **low** value (favor the minimal mechanism).

## Tradeoffs & Alternatives

- **A — Single-authority rewrite** (consolidate the in-band helper + the 3 inline crash sets into one
  coherent-by-construction setter). *Rejected:* highest blast radius; rewrites the delicate
  exception-safety contracts (the `preserved` branch must skip the revert/reset; `rr is None` must
  still fire it) for a provably-unreachable combo. Inverts cost/value.
- **B — Adjacent write-boundary guard** keyed on the conjunction
  (`details.get("could_not_run") and details.get("review_dispatch_crashed")`). Vacuously safe for the
  other emits; cheap; touches no control flow. The live consideration: 3 of the 6 covered emits are
  inside `except` bodies, so a raise there fires inside exception handling (blast radius bounded — see
  Safety).
- **C — Minimal hybrid** (extract the 3 crash sets into a companion setter that is the sole writer of
  `review_dispatch_crashed`, guard inside it). *Rejected by Adversarial:* under-delivers on the
  ticket's "catch a 4th site" ask — a setter-internal guard is reached only by callers that *use* the
  setter; a future 4th inline-built emit bypasses it (see Adversarial 4th-site gap).

**Recommended (research's lean, Spec decides): the minimal write-boundary guard (B)** — a
`_guard_review_flag_coherence(details, *, site)` mirroring `_guard_no_review_qualifying_sync_merge`,
that `raise`s when both flags are set, invoked immediately before each **review-gate** `FEATURE_DEFERRED`
emit (all 6; vacuous on the in-band 3, load-bearing on the crash 3). This is the ticket's explicit
second option ("a `_set_review_error_detail_flags`-adjacent assertion that loudly rejects … at the
write boundary"), is cheapest, and (placed at the emit boundary) catches a future edit that wrongly
co-sets — more than a setter-internal guard.

## Safety & Placement

**A raise inside the crash-`except` blocks is survivable — never session-fatal:**
- **Path 1** (`orchestrator.py:447` in `_run_one`, dispatched via
  `asyncio.gather(..., return_exceptions=True)` `:488`): the exception is captured as a return value →
  re-wrapped `FeatureResult(status="failed")`. **Blast radius: one feature.** Primary in-flight path
  for all three gates.
- **Path 2** (`orchestrator.py:539` post-gather reconciliation, uncaught → `run_batch` →
  `batch_runner` subprocess nonzero exit → `runner.py:3114` logs `ORCHESTRATOR_FAILED` and **falls
  through**, does not `break`): **blast radius: at most one round's batch subprocess, never the
  session.** And #539 only routes `status="failed"` results to non-review emits (759/801/842), where
  the guard is vacuous — so it can't actually fire there.
- **`ctx.lock` is NOT leaked.** The gate runs inside `async with ctx.lock` (`:1743`, re-acquired
  `:2214`); `__aexit__` releases on exception. Siblings are not wedged.
- **Side-effect ordering nuance:** the raise fires *after* the revert/preserve decision (revert at
  1239/1626/2003 precedes the emit at 1259/1637/2019). A fired guard therefore leaves the worktree
  consistent but loses *that one feature's* deferral file + backlog write-back (both come after the
  emit) → the feature shows `failed` with no deferral artifact. Degraded, non-corrupting, acceptable
  for a provably-unreachable path.
- **In-band path is a *worse* placement:** a raise on an in-band emit is caught by the crash-`except`
  below it and silently transformed into a crash-path deferral (with a duplicate emit) — swallowed,
  not surfaced. So the guard's value at in-band sites is purely "catch a future wrong-co-set"; it must
  not be the *only* placement.

**Read/replay surfaces the guard must avoid** (keep `.get(..., False)`-tolerant; never wire a raise
in): `report.py:528-539 / 1276-1305 / 1470-1525` (the `:1470` comment literally says "for archived-log
tolerance"), plus `metrics.py`, `status.py`, `map_results.py`, `dashboard/data.py`, `logs.py`.

## Testing & Done-Criterion

Tests live in `cortex_command/overnight/tests/test_outcome_router.py`; `just test-overnight`
auto-discovers (`pytest cortex_command/overnight/tests/ -q`). **No registry/parity test is tripped**
(no new event/field; `log_event` validates event type only, not `details` sub-keys).

- **Primary done-criterion (unit, sync `TestCase`):** call the guard with the exact incident reproducer
  `{"could_not_run": True, "review_dispatch_crashed": True, "merge_reverted": True}` → `assertRaises`.
  Plus `could_not_run`-alone and `review_dispatch_crashed`-alone → no raise. Deleting the guard makes
  `assertRaises` fail. This is the test that "would fail if a future site set both flags."
- **Defense-in-depth (path-level, new `TestReviewDeferralFlagCoherence(IsolatedAsyncioTestCase)`
  adjacent to `TestCouldNotRunPreservesMerge` @2601):** drive each of primary/recovery/repair through
  both the could-not-run and genuine-crash cases (reuse `_could_not_run_review`, `_crash_review`,
  `_run_recovery`, `_ff_subprocess_side_effect`, `_deferred_event_details`) and assert each emits a
  coherent **single-flag** event. Generalizes the existing pin
  `test_error_verdict_event_carries_could_not_run_marker` (`:1822`, already asserts `could_not_run` set
  + `assertNotIn("review_dispatch_crashed")`).

## Adversarial Review

- **assert-vs-raise → `raise` (decisive).** No `-O`/`PYTHONOPTIMIZE` anywhere in the production spawn
  chain (`cli_handler.py:303` runner self-spawn; `runner.py:1806` `cortex-batch-runner` console-script;
  zero grep hits outside tests/docstrings). Safety's "assert compiles out in production" premise is
  false — an assert *would* run and abort with a bare `AssertionError`. Precedent: `dispatch.py:270-277`
  converted a spec'd `assert`→`ValueError` for exactly this reason.
- **The 4th-site gap (sharpest finding).** The ticket's literal ask (lines 56-61) is to reject the
  combo "if a fourth site or a future edit ever sets the flags wrong." A guard **inside a setter**
  (C/d) is reached only by callers that use the setter; a future 4th emit built inline (the current 3
  crash sites' own style) bypasses it. **Only an emit-boundary guard catches a bypassing 4th site.**
  Honest residual: *no* in-process guard catches a 4th site that calls `overnight_log_event` raw —
  only a `log_event`-level guard is bypass-proof, at the cost of putting a domain rule in the generic
  event sink (poor cohesion). The Spec must not claim "catches a 4th site" while shipping a
  setter-internal guard.
- **Read-side asymmetry is the real operational harm and is out of scope.** `report.py:535/1286/1476`
  keys *only* on `could_not_run`, never cross-checking `review_dispatch_crashed` — exactly the #319
  misread. The write-boundary guard prevents *future* co-set emits but does nothing for already-archived
  incident events; readers keep trusting `could_not_run`. Per the ticket Boundary this is acceptable —
  but Spec should state the guard fixes the *cause* going forward and does not retro-fix the artifact.
- **No false-positive risk:** ADR-0015 makes the two flags definitionally disjoint; the conjunction
  guard cannot fire on any reachable emit. Future-policy only: a later ADR introducing a
  "crashed-but-preserved" state would have to revisit this guard explicitly.
- **Systemic-breaker safe:** the emit precedes `_record_review_crash_systemic`; a fired guard aborts
  before the counter increments (no double-count) but skips systemic accounting for that one feature
  (minor under-count, acceptable for an impossible path).

## Synthesis & Recommended Approach

A single fail-loud coherence guard at the **review-gate emit boundary**, written in the module's
existing idiom:

- `_guard_review_flag_coherence(details, *, site)` (mirroring `_guard_no_review_qualifying_sync_merge`,
  `:1319-1341`): a module-level message constant + a `None`-returning validator that
  `raise RuntimeError` (or a named subclass) when `details.get("could_not_run") and
  details.get("review_dispatch_crashed")`.
- Invoked immediately before each of the **6 review-gate** `FEATURE_DEFERRED` emits (in-band 1210/1566/
  1954 + crash 1259/1638/2020). Conjunction-keyed ⇒ vacuous for the 4 non-review emits and every other
  event; load-bearing at the 3 crash emits.
- `raise`, never `assert` (no `-O` in prod). Write-boundary only; **not** wired into any reader/replay
  surface. No events-registry edit.
- Done = the unit test (incident reproducer → `assertRaises`) + the per-path single-flag coherence
  sweep.
- **Reject mechanisms A and C** as over-built / under-delivering. Prefer the thin guard.

This is the ticket's second stated option, proportional to its low value, and (at the emit boundary)
strictly catches more than a setter-internal guard.

## Open Questions

Each is a design decision for **Spec** to finalize (the operator may redirect at the spec approval
surface); research's recommendation is given inline so the Research Exit Gate is satisfied by explicit
deferral, not left bare.

- **Guard placement breadth & altitude.** Options: (i) a guard *call* before each of the 6 review-gate
  emits; (ii) a thin review-gate emit *wrapper* the 6 sites route through; (iii) a guard inside
  `events.py:log_event` (bypass-proof, but couples a domain rule into the generic sink).
  *Deferred → Spec.* Recommendation: **(i) or (ii)** at the review-gate altitude — `log_event`-level
  only if bypass-proofness against a raw-`overnight_log_event` 4th site is deemed worth the cohesion
  cost. Spec must state the residual explicitly (no in-process guard catches a wrapper-bypassing 4th
  site except the `log_event`-level one) and not over-claim "catches a 4th site."
- **Fired-guard production posture.** A raise at a crash-`except` emit loses that one feature's deferral
  file (the raise fires after the revert). *Deferred → Spec.* Recommendation: accept it — fail-loud,
  one-feature-degraded, non-corrupting, and only reachable on a future bug; document the outcome.
  (`raise … from err` is moot here since the guard runs on assembled `details` before re-touching the
  caught exception, but if placed mid-`except`, prefer bare `raise`/`from err`, never `from None`.)
- **Exception type.** *Deferred → Spec.* Recommendation: `RuntimeError` (matches the in-module
  `_guard_no_review_qualifying_sync_merge` precedent) or a named `ReviewFlagCoherenceError` subclass for
  greppability — Spec's call; both satisfy "loud."
- **Read-side asymmetry (`report.py` trusting `could_not_run` alone).** Real operational harm, but the
  ticket Boundary scopes this work to *emission* coherence. *Deferred → Spec.* Recommendation: keep
  **out of scope**; note it in the spec's non-goals (and optionally as a follow-up ticket) so no one
  expects the write-guard to retro-fix the #319 read misdiagnosis.
