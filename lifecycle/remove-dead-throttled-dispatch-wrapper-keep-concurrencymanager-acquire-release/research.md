# Research: Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release

Topic anchor (clarified intent): Delete the dead `throttled_dispatch()` wrapper and its rate-limit-reactive concurrency-shrinkage layer (`report_rate_limit`, `report_success`, `_effective_concurrency`/`_total_rate_limits` state, `throttle_backoff` event, `backoff_*` knobs) while preserving the live `ConcurrencyManager` semaphore (`acquire`/`release` and the tier cap).

## Codebase Analysis

### Surface area in `cortex_command/overnight/throttle.py`

Symbols to **DELETE**:
- `throttled_dispatch()` (lines 206-271) — async wrapper around `dispatch_task` with backoff/event emission.
- `ConcurrencyManager.report_rate_limit()` (lines 158-183) — tracks rate-limit events, shrinks `_effective`, manages `_rate_limit_timestamps`.
- `ConcurrencyManager.report_success()` (lines 185-199) — tracks consecutive successes, restores `_effective`.
- `ConcurrencyManager` private state added solely for shrinkage: `_total_rate_limits` (line 130), `_reductions` (131), `_restorations` (132), `_rate_limit_timestamps` (122), `_window_seconds` (123), `_consecutive_successes` (126), `_successes_to_restore` (127). Note: the actual private attribute is `_effective` (line 117), not `_effective_concurrency` (the latter does not exist; the ticket name is a proxy for the live `current_concurrency` property and its tracking state).
- `ThrottleConfig` fields: `backoff_base_seconds` (60), `backoff_max_seconds` (61), `rate_limit_threshold` (62).
- `throttle_backoff` event emission inside `throttled_dispatch` (lines 260-265). NOT registered in `events.py` `EVENT_TYPES` (verified: file lines 83-134); emission used `pipeline.state.log_event` (different validator) so deletion has zero schema impact.
- The "stats" fields that exist solely for the shrinkage layer: when removing `_total_rate_limits`/`_reductions`/`_restorations`, the `stats` property either returns `{}` or is updated to expose only `current_limit`/`max_limit` (caller-side decisions per below).

Symbols to **KEEP**:
- `ConcurrencyManager.acquire()` (line 150) and `release()` (line 154) — load-bearing tier semaphore.
- `ConcurrencyManager.current_concurrency` property (lines 135-137).
- `SubscriptionTier` enum (lines 25-30).
- `_TIER_DEFAULTS` (lines 33-37) — maps tier → `max_runners`/`max_workers`.
- `ThrottleConfig` minus the three backoff fields (i.e., `tier`, `max_concurrent_runners`, `max_concurrent_workers` survive).
- `load_throttle_config()` (lines 65-100) — still has purpose (tier→limits + override pass-through). Trim backoff-related override handling.

### Caller enumeration (verified by grep)

| Symbol | Callers |
|---|---|
| `throttled_dispatch` | `__init__.py:58` (re-export), `brain.py:194-196` (deadlock-explaining doc comment only). **Zero call sites in production code.** |
| `report_rate_limit` | `throttle.py:250` (inside `throttled_dispatch`, dead path), `brain.py:237` (in `request_brain_decision`, **live path**), `tests/test_brain.py:265` (single test — to delete). |
| `report_success` | `throttle.py:248` (inside `throttled_dispatch` only). |
| `_total_rate_limits` | Defined at throttle.py:130; incremented at 165; consumed by `stats` property at 143 and by backoff calculation at 253. |
| `throttle_backoff` event | Emitted at throttle.py:261; **zero consumers anywhere in the codebase** — morning report, dashboard, metrics computation, observability, schema. |
| `backoff_base_seconds` / `backoff_max_seconds` / `rate_limit_threshold` | Used only inside throttle.py shrinkage paths. |

### Additional load-bearing call site (surfaced by adversarial review — not in initial map)

**`cortex_command/overnight/orchestrator.py:449`** writes `manager.stats` into batch results JSON via `extra_fields={"throttle_stats": manager.stats}`. The keys (`total_rate_limits`, `reductions`, `restorations`, `current_limit`, `max_limit`) come from `ConcurrencyManager.stats` (throttle.py:140-148). **The deletion PR must drop or re-shape this `extra_fields` argument** — otherwise the post-deletion `stats` property either returns missing keys (silent regression) or has to keep a stub.

Verified: `tests/test_overnight_state.py:217-221` asserts `throttle_stats` is present in the written JSON, but it uses a self-supplied fixture (`{"total": 0, "delays": []}`), not real `manager.stats` keys. So dropping the `extra_fields` argument from orchestrator.py:449 does not break that test, but the contract change must be intentional. No other readers of `throttle_stats` (dashboard, morning report) — verified.

### `load_throttle_config()` post-deletion

Reads tier name → returns `ThrottleConfig` with `tier`, `max_concurrent_runners`, `max_concurrent_workers`. Override handling iterates `setattr` over the dataclass fields. After removing the three backoff fields, the function still has clear purpose: tier → concurrency limits + override pass-through. **Recommendation: keep `load_throttle_config()`; just trim the dataclass fields.** Called by `orchestrator.py:222` to configure the manager.

### `brain.py:194-196` deadlock comment

Docstring (lines 187-209) explicitly documents:
> "Calls ``dispatch_task`` directly (not ``throttled_dispatch``) because the caller already holds the semaphore slot — re-acquiring via ``throttled_dispatch`` would deadlock at MAX_5."

Only direct doc reference to `throttled_dispatch` in the repo. Should be removed or rewritten as part of the deletion (the rationale for direct dispatch becomes "there is no alternative" rather than "to avoid deadlock"). Adversarial review notes the deadlock framing is misleading: at MAX_5 the cap is 1 worker, so shrinkage 1→0 always deadlocks; the wrapper was misapplied to MAX_5, not "broken." Reword the rationale accordingly.

### `brain.py:237` semantics change

Today brain.py:237 calls `manager.report_rate_limit()` outside the wrapper (deliberate observability for brain dispatches, as commented at line 236: "Report rate limits without acquiring the semaphore"). After deletion that signal is gone. Brain 429s still propagate via `dispatch_task` → `dispatch.py:246` (`api_rate_limit` → `pause_session`). **Net effect: brain 429s no longer absorbed by an in-process backoff layer; they escalate to a session pause via the pipeline error path.**

### Pipeline-level rate-limit pause path

- `dispatch.py:246` maps `api_rate_limit` → `pause_session`.
- `dispatch.py:320-321` classifies any 429 matching `_RATE_LIMIT_PATTERNS` (`("rate_limit_error", "rate limit", "too many requests")`) as `api_rate_limit` on the FIRST occurrence — there is no "pause after N consecutive" gate.
- `retry.py:379-399`: `pause_session` performs zero retries and triggers immediate session-wide halt.

**Behavior change after deletion:** previously `throttled_dispatch` (when called) would absorb a transient 429 with exponential backoff (30s → 60s → 120s → … capped at 300s) before any pause fired. With it gone, AND given `throttled_dispatch` was already not in the live path, the practical change is in brain.py: a brain agent 429 now triggers session pause instead of being absorbed. Other paths already had this behavior because they never went through the wrapper.

### Tests

- **Delete:** `tests/test_brain.py:248-265` (`test_dispatch_failure_infrastructure_calls_report_rate_limit`) — exclusively tests `report_rate_limit()` invocation.
- **Keep unchanged:** All `test_orchestrator.py` and `test_lead_unit.py` tests that mock `manager.acquire`/`manager.release`. Verified that test fixtures use `mock_manager.stats = {}` (not real keys), so removing stats keys does not break test assertions.
- **Verify:** `tests/test_overnight_state.py:217-221` asserts `throttle_stats` key in batch-result JSON via a self-supplied fixture; safe to keep as-is even if orchestrator no longer passes the field, but the contract drift should be acknowledged.

### `orchestrator.py:248-272` and `feature_executor.py:188`

`orchestrator.py:248`: `await manager.acquire()` … `manager.release()` in finally — only uses load-bearing surface. ✅
`feature_executor.py:188`: passes `manager` to `request_brain_decision` for the rate-limit-reporting side-effect. After deletion, this argument can either be removed or kept (manager is still needed for other call sites). Likely keep the parameter; just remove the line in brain.py that uses it for `report_rate_limit`.

### Documentation references

- `claude/` directory: no matches for `throttled_dispatch`, `backoff_base_seconds`, `throttle_backoff`, or `_effective_concurrency`. ✅
- `docs/` directory: no matches. ✅
- `lifecycle/archive/replace-concurrency-cap-with-conflict-aware-round-scheduling/inner-task-investigation.md` lines 53-106 independently reached the same "dead code" conclusion (cited by ticket).
- **Surfaced by adversarial review:** `research/opus-4-7-harness-adaptation/research.md:195` references "monitor `throttle_backoff` event rates post-migration for one week" as a planned monitoring signal. Either supersede that line or update it to reference `api_rate_limit` events instead.
- **Surfaced by adversarial review:** `requirements/multi-agent.md:45` describes the adaptive shrinkage as a current behavior — see Requirements section below. **Must edit as part of deletion.**

### Files that will change

| File | Change |
|---|---|
| `cortex_command/overnight/throttle.py` | Major: delete `throttled_dispatch`, `report_rate_limit`, `report_success`, internal shrinkage state, three `ThrottleConfig` fields, module docstring update. |
| `cortex_command/overnight/__init__.py` | Delete `throttled_dispatch` from `__all__`/imports (line 58). |
| `cortex_command/overnight/brain.py` | Delete lines 235-237 (`report_rate_limit` call). Rewrite docstring at 194-196 (no longer cites "deadlock at MAX_5" as the reason — wrapper no longer exists). |
| `cortex_command/overnight/orchestrator.py:449` | Drop `extra_fields={"throttle_stats": manager.stats}` from `save_batch_result` call. |
| `cortex_command/overnight/tests/test_brain.py` | Delete `test_dispatch_failure_infrastructure_calls_report_rate_limit` (lines 248-265). |
| `requirements/multi-agent.md:45` | Rewrite acceptance-criterion line to describe fixed (non-adaptive) tier-cap concurrency; preserve "Concurrency limit is 1–3 agents." |
| `research/opus-4-7-harness-adaptation/research.md:195` | Mark `throttle_backoff` monitoring item superseded or repoint to `api_rate_limit` events. |

## Web Research

### Anthropic Python SDK retry behavior (with caveat about applicability)

The official `anthropic-sdk-python`:
- Default `max_retries=2` (3 total attempts), retries 408/409/429/≥500, honors `Retry-After`/`retry-after-ms` headers, applies exponential backoff with jitter, raises `anthropic.RateLimitError` on exhaustion (no silent fail).
- Layered retries (client + middleware + SDK) are an industry-recognized anti-pattern (Microsoft Azure "Retry Storm", AWS Builder's Library "Timeouts, Retries, and Backoff with Jitter").

**Critical caveat (raised by adversarial review):** cortex-command's overnight runner does NOT use the raw `anthropic` Python SDK directly. It uses `claude_agent_sdk` (a subprocess wrapper around the `claude` CLI binary). Verified: `.venv/.../claude_agent_sdk/_internal/{client,query}.py` contains zero `retry`/`429`/`max_retries` references. Whether 429s get retried at all in this dispatch path therefore depends on **Claude Code CLI's** internal behavior (the binary, not the Python SDK), which is not directly verifiable from the repo.

The "SDK already retries 429s" framing in the original ticket overstates certainty. This becomes an explicit residual risk: if Claude Code CLI does not retry 429s internally, the deletion makes the system fragile to any transient Anthropic API hiccup — every 429 escalates to `pause_session`. Open question carried below.

### Anti-patterns in adaptive concurrency shrinkage

- **Fixed-floor deadlock** (matches MAX_5): when a tier requires N workers minimum and reactive shrinkage drives the cap below that floor, all coroutines block forever.
- **Over-release / over-shrink asymmetry** in `asyncio.Semaphore` (vs `BoundedSemaphore`).
- **Fairness violations under resize** (Guido's note on `asyncio.Semaphore`).
- **Oscillation under AIMD-style shrinkage** (Uber Cinnamon, Vector Adaptive Request Concurrency notes).
- **Debuggability cost** of multiple layers reacting to the same 429.

### Safe-deletion methodology

"Delete unused code" guidance (Meta SCARF, jfmengels.net "Safe dead code removal", venantius/yagni) endorses removal when: zero static call sites + zero observed events + behavior covered by another layer. The signals here are weakened by the SDK-retry caveat above (the third signal is uncertain in this dispatch path).

### Key URLs

- https://platform.claude.com/docs/en/api/sdks/python (Anthropic Python SDK retry semantics)
- https://learn.microsoft.com/en-us/azure/architecture/antipatterns/retry-storm/ (Retry Storm anti-pattern)
- https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/ (AWS Builder's Library)
- http://neopythonic.blogspot.com/2022/10/reasoning-about-asynciosemaphore.html (asyncio.Semaphore fairness)
- https://www.uber.com/blog/cinnamon-auto-tuner-adaptive-concurrency-in-the-wild/ (oscillation discussion)
- https://vector.dev/blog/adaptive-request-concurrency/ (adaptive request concurrency design)
- https://understandlegacycode.com/blog/delete-unused-code/ (safe deletion methodology)

## Requirements & Constraints

### `requirements/project.md`

- "**Complexity**: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." (line 19)
- "**Maintainability through simplicity**: Complexity is managed by iteratively trimming skills and workflows." (line 32)
- "**Graceful partial failure**: Individual tasks in an autonomous plan may fail. The system should retry, potentially hand off to a fresh agent with clean context, and fail that task gracefully if unresolvable." (line 31)

### `requirements/pipeline.md`

- "**Graceful degradation**: Budget exhaustion and rate limits pause the session rather than crashing it." (line 128) — outcome-only NFR; mechanism not mandated.
- "Budget exhaustion transitions the session to `paused` without aborting in-flight features." (line 25)

### `requirements/multi-agent.md` — **load-bearing finding**

Line 45 reads:
> "Concurrency limit is 1–3 agents, **adaptive: reduces by 1 after 3 rate-limit errors within 5 minutes, restores after 10 consecutive successes**"

This is in the *Acceptance criteria* of the **must-have** "Parallel Dispatch" requirement. It literally describes the behavior the ticket proposes to delete. **Two consequences:**

1. The deletion PR must edit this line. Recommended replacement: "Concurrency limit is 1–3 agents, fixed at the tier cap (`SubscriptionTier`-bound). Rate limits surface via the pipeline `api_rate_limit` error type and pause the session per Model Selection Matrix." — preserves the "1–3 agents" cap and routes the rate-limit path to the existing `pause_session` mechanism.
2. Without this edit, the docs/code drift on a must-have acceptance criterion.

Other relevant lines:
- Line 75: "The tier-based concurrency limit (1–3 workers) is a hard limit enforced by `ConcurrencyManager`; it is not overridable at runtime by agents." — preserved.
- Line 63: "On `budget_exhausted` or `api_rate_limit`: pause the entire session (no new dispatches)." — load-bearing; the existing pipeline path satisfies this.

### `requirements/observability.md`

Required telemetry surfaces (morning report, dashboard, `metrics.json`) do **not** reference `throttle_backoff` or any throttle-specific event. Removing the event creates no documented telemetry gap. Required surfaces continue to surface `feature_complete`, `phase_transition`, `review_verdict`, escalation entries, and per-feature concurrency slot usage — none of which depend on the wrapper.

### Scope boundaries

In-scope (must preserve):
- `ConcurrencyManager.acquire()` / `release()` and tier cap (1–3 workers).
- Session pause on `api_rate_limit` / `budget_exhausted` (existing path via `dispatch.py` + `retry.py`).
- Pipeline-level rate-limit observability (`api_rate_limit` events still emitted in `pipeline-events.log`).

Out-of-scope (deletable):
- Reactive backoff mechanism (config knobs, internal shrinkage state, event emission).
- The specific "reduces by 1 after 3 rate-limit errors within 5 minutes" behavior described in `multi-agent.md:45` — but only IF that requirement line is also updated in this PR.

## Tradeoffs & Alternatives

Five alternatives evaluated. Detailed evaluation captured by Tradeoffs agent.

### Alternative A — Full deletion (ticket's proposal)

Remove all dead surfaces; preserve tier cap + acquire/release.

- **Implementation**: Mostly deletions. ~40 lines from throttle.py, ~20 from tests, exports + brain.py touchups + orchestrator.py:449 + requirements/multi-agent.md:45 edit.
- **Maintainability**: High. Clean single-purpose `ConcurrencyManager`.
- **Reversibility**: Low (requires rebuilding state machine if needed). Mitigation: commit message + lifecycle artifact records the revert path.
- **Alignment**: Strong. Matches "Complexity must earn its place."

### Alternative B — Quarantine / deprecation annotation

Keep wrapper, mark `@deprecated` with removal date.

- Dead code rots; deprecation signals decay; deadlock-at-MAX_5 still latent. Cortex-command ethos is decisive — either used or deleted. **Reject.**

### Alternative C — Move to opt-in / config flag

Keep wrapper behind `enable_adaptive_backoff: bool`.

- Worst of both worlds. Underlying deadlock bug remains latent; if anyone enables, they hit it again. Adds config debt. **Reject.**

### Alternative D — Replace with passive `rate_limit_observed` event (no shrinkage)

Delete shrinkage; add light observability event.

- Adds code instead of removing. "Instrumentation theater" for events that have never fired. Conflicts with ticket scope (delete dead, not refactor it). **Reject.**

### Alternative E — Delete wrapper, keep `load_throttle_config` knobs

Surgical: remove behavior, keep config surface.

- Orphan config fields create confusion. No external tools/configs reference these knobs (verified). **Reject** — Alternative A is cleaner.

### Recommended approach: A (full deletion) WITH expanded scope

Adversarial review converged on A but flagged the scope as **operationally incomplete** as written in the ticket. Expanded scope (verified necessary):

1. Drop `extra_fields={"throttle_stats": manager.stats}` at `orchestrator.py:449`.
2. Edit `requirements/multi-agent.md:45` to reflect fixed-cap concurrency.
3. Update `brain.py:235-237` and the docstring at 194-196 (no more `throttled_dispatch` reference; reword rationale).
4. Update `research/opus-4-7-harness-adaptation/research.md:195` (supersede or repoint).
5. Reword the deletion rationale: not "wrapper was broken at MAX_5" (misleading), but "wrapper was never wired into the live dispatch path."
6. Acknowledge sample-size limit in commit/lifecycle artifact: "zero events over the 3 sessions with `pipeline-events.log` files in the local lifecycle dir, in incident-free operation" — not "zero events ever."
7. Accept residual risk: post-deletion, a single transient 429 escalates to `pause_session` (no in-process absorption), unless Claude Code CLI internally retries 429s. The morning report surfaces the pause; human triage resumes.

## Adversarial Review

Findings worth carrying forward as residual risks / acceptance items (full review captured above):

- **`orchestrator.py:449` writes `manager.stats`** — was missed in initial codebase map; must be updated. ✅ Now in scope.
- **`requirements/multi-agent.md:45`** literally documents the deleted behavior. ✅ Now in scope.
- **`claude_agent_sdk` is a subprocess wrapper, no retries.** Anthropic-Python-SDK retry guarantees do NOT directly apply to this dispatch path. **Residual risk:** if Claude Code CLI doesn't internally retry 429s, the deletion makes the system fragile to transient API hiccups. This is the most material residual risk.
- **Brain agent 429 semantics change.** Previously `manager.report_rate_limit()` recorded the event without acquiring the semaphore. After deletion, brain 429s flow only through `dispatch.py` `api_rate_limit` → `pause_session`. Single-429 → session pause becomes the new default (already true for non-brain dispatches; this aligns brain with everything else).
- **Sample size of "zero events":** 3 sessions in the local lifecycle dir, in incident-free operation. Not "zero events ever." Acknowledge in commit/research.
- **MAX_5 deadlock framing is technically misleading.** Reword: wrapper was never wired into the live dispatch path; deadlock was a configuration issue at one tier. The deletion is justified because the wrapper has zero callers, not because it's intrinsically broken.
- **`research/opus-4-7-harness-adaptation/research.md:195`** references `throttle_backoff` as a planned monitoring signal. Update or supersede.
- **Reversibility**: commit body + lifecycle artifact should include a "if rate limits become a problem in production, restore via this commit" pointer. Don't just rely on git history.

## Open Questions

All five surfaced at the Research Exit Gate; user accepted all defaults on 2026-04-29.

1. **Claude Code CLI 429 retry behavior** — Resolved: accept the residual risk. Post-deletion, a single transient 429 may escalate to `pause_session`; this is recoverable on session resume and the morning report surfaces it for human triage. No empirical verification of CLI internals required as a precondition.

2. **`requirements/multi-agent.md:45` edit scope** — Resolved: include the edit in this same PR. Replacement language: "Concurrency limit is 1–3 agents, fixed at the tier cap (`SubscriptionTier`-bound). Rate limits surface via the pipeline `api_rate_limit` error type and pause the session per Model Selection Matrix."

3. **`research/opus-4-7-harness-adaptation/research.md:195` disposition** — Resolved: repoint the post-migration monitoring item to `api_rate_limit` events in `pipeline-events.log` (instead of the now-deleted `throttle_backoff` event).

4. **`request_brain_decision()` `manager` parameter** — Resolved: keep the parameter on the signature even after deletion (stable API; future uses may emerge). Inside the body, only the `report_rate_limit` call is removed.

5. **`load_throttle_config()` post-deletion shape** — Resolved: keep the function name and signature; trim `ThrottleConfig` to drop `backoff_base_seconds`, `backoff_max_seconds`, and `rate_limit_threshold`. Stable API for callers (`orchestrator.py:222`).
