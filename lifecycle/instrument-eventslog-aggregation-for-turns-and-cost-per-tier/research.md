# Research: instrument-eventslog-aggregation-for-turns-and-cost-per-tier

> Generated: 2026-04-18. Topic: aggregate `dispatch_complete` / `dispatch_error` / `throttle_backoff` events from per-feature `events.log` files into per-tier summaries, as baseline data for future Opus 4.7 matrix recalibration (DR-4).

## Epic Reference

Parent epic: [#082 Adapt harness to Opus 4.7](../../backlog/082-adapt-harness-to-opus-47-prompt-delta-capability-adoption.md). Epic research at [`research/opus-4-7-harness-adaptation/research.md`](../../research/opus-4-7-harness-adaptation/research.md). This ticket is the instrumentation surface DR-4 requires before any matrix recalibration; its direct downstream consumers are `#088` (collect baseline rounds) and `#089` (measure xhigh vs high cost delta). No events.log format rethink is in scope for this ticket — confirmed during Clarify that the existing JSONL schema already carries every required signal.

## Codebase Analysis

### Event emitter surface (schema confirmed)

| Event | Emitter | Fields |
|---|---|---|
| `dispatch_complete` | `claude/pipeline/dispatch.py:510-516` | `ts`, `event`, `feature`, `cost_usd`, `duration_ms`, `num_turns` |
| `dispatch_error` | `dispatch.py:528-533`, `553-558`, `571-577` (three call sites) | `ts`, `event`, `feature`, `error_type`, `error_detail` |
| `throttle_backoff` | `claude/overnight/throttle.py:260-265` | `ts`, `event`, `feature`, `delay_seconds`, `current_concurrency` |
| `lifecycle_start` (tier source for join) | written by lifecycle skill / `seed.py` | `ts`, `event`, `feature`, `tier`, `criticality` |
| `complexity_override` (tier can change mid-feature) | written by lifecycle skill | `ts`, `event`, `feature`, `from`, `to` |

`classify_error()` at `dispatch.py:255-309` enumerates the `error_type` values: `agent_timeout`, `agent_test_failure`, `agent_refusal`, `agent_confused`, `api_rate_limit`, `task_failure`, `infrastructure_failure`, `budget_exhausted`, `unknown`. `throttle_backoff` is emitted only when `result.error_type == "infrastructure_failure"` (`throttle.py:249`) — this is the rate-limit-detection coupling.

Per-feature `events.log` also carries `dispatch_start` (captures `complexity`, `criticality`, `model`, `effort`, `max_turns`, `max_budget_usd`), useful for cross-checking the tier used at dispatch time against the `lifecycle_start` tier.

### Existing aggregation pipeline (the load-bearing overlap)

`claude/pipeline/metrics.py` already:
- Discovers all `lifecycle/*/events.log` via `discover_event_logs()` (line 217-229)
- Parses JSONL via `parse_events()` (line 67-93), with backfilled-timestamp detection at `metrics.py:32-47`
- Joins tier via `lifecycle_start` event (line 157-159)
- Produces `lifecycle/metrics.json` with per-feature records + per-tier aggregates + calibration summaries
- Runs as `python3 -m claude.pipeline.metrics [--root PATH]` (line 493-548)

**Gap**: metrics.py reads `feature_complete`, `phase_transition`, `review_verdict`, `batch_dispatch` — it does **not** read `dispatch_complete`, `dispatch_error`, or `throttle_backoff`. The per-dispatch `num_turns` and `cost_usd` fields are emitted and persisted but never aggregated. This is exactly the gap #087 fills.

**Reusable helpers in metrics.py**: `_safe_mean()` (line 332-340), tier-grouping pattern (line 343-421), backfilled-timestamp detection — all directly applicable.

### Dashboard read path

`claude/dashboard/data.py:parse_metrics` already reads `lifecycle/metrics.json` into a dict and returns it raw. Additive top-level keys are safe for existing consumers (confirmed by Tradeoffs agent via grep); any future dashboard widget would read the new section via this same function.

### CLI deployment pattern

`bin/` scripts → deployed to `~/.local/bin/` via justfile symlink recipes (justfile:120-140). Examples: `bin/overnight-status`, `bin/audit-doc`, `bin/count-tokens`. For a new reporter, either:
- Expose via `python3 -m claude.pipeline.metrics --report tier-dispatch` (extend existing module), OR
- Add `bin/overnight-metrics` wrapper that invokes the module

### Test fixtures and patterns

Minimal fixtures: `tests/fixtures/state/*/events.log` (typically lifecycle_start + feature_complete only — not enough for dispatch-metric testing).
Richer: `claude/overnight/tests/fixtures/batch_runner/events_completed.jsonl`.
New tests go in `claude/pipeline/tests/test_tier_aggregator.py` (or extended `test_metrics.py`) and should exercise: `dispatch_complete` + `dispatch_error` + `throttle_backoff` with/without matching `lifecycle_start`, with `complexity_override` mid-feature, and with missing-tier fallback buckets.

### Data volume

88 completed features currently with ~2,709 total events across all `events.log` files. Load-all-in-memory is fine — no streaming needed.

### Files that will change

- `claude/pipeline/metrics.py` — extend with `extract_dispatch_records()`, `compute_tier_dispatch_aggregates()`, new `tier_dispatch_aggregates` / `rate_limit_incidents` top-level keys in output
- `claude/pipeline/tests/test_metrics.py` (or new `test_tier_aggregator.py`) — unit tests over hand-crafted fixtures
- Possibly `bin/overnight-metrics` (shell wrapper) + `justfile` symlink recipe — only if a dedicated command name is preferred over `python3 -m claude.pipeline.metrics --report tier-dispatch`

## Web Research

### Stdlib-only aggregation (Python)

- Pattern: `for line in path.open(): rec = json.loads(line)` → bucket by tier into lists → `statistics.fmean`, `max`, `statistics.quantiles(values, n=100, method='inclusive')[94]` for p95.
- `method='inclusive'` (not default `exclusive`) is the right choice when summarizing a known-complete batch — `exclusive` never returns the observed max.
- `statistics.quantiles` raises on <2 points (Python <3.13). Guard with `if len(values) < 10: return max(values)` — below that sample size p95 is essentially max anyway.
- Always report `n` alongside aggregates; summaries without sample counts are misleading at this scale.
- [Python statistics docs](https://docs.python.org/3/library/statistics.html)

### Budget / cost observability prior art

Common shape across [Langfuse](https://langfuse.com/docs/observability/features/token-and-cost-tracking), [LiteLLM](https://www.litellm.ai/), [FOCUS](https://www.datadoghq.com/blog/anthropic-usage-and-costs/): `(timestamp, grouping_key, model, cost, input_tokens, output_tokens, cache_*)`. Our minimal `(tier, cost_usd, num_turns)` is a legitimate subset — we don't need token decomposition for matrix recalibration, which is the only downstream consumer.

### Rate-limit instrumentation patterns

No canonical "concurrency reduction duration" metric. Industry (Vector ARC, Gravitee, Zuplo) pairs **incident count** with **total throttled time**. "Sum of `delay_seconds`" is a reasonable proxy for the latter; theoretically cleaner would be a time-weighted concurrency integral but events.log doesn't capture actual concurrency over time, only at backoff events. Report both (count + sum) to disambiguate "one long backoff vs many short."

### CLI vs dashboard widget

Community pragmatism: CLI-first for small personal tooling. A dashboard widget is a second step if the metric is consulted often enough to justify an always-on surface. Matrix-recalibration is a quarterly-ish activity, so CLI is the right first form; widget can be added later if human review wants in-flight visibility.

### Anthropic cost observability

[Agent SDK cost-tracking doc](https://code.claude.com/docs/en/agent-sdk/cost-tracking):
- `ResultMessage.total_cost_usd` is a **client-side estimate**, not authoritative billing. Label the output as estimated.
- Per-model breakdown exists via `ResultMessage.model_usage`, but our events.log currently persists only the aggregated `cost_usd`. Model-level decomposition would require a dispatch.py change — out of scope for this ticket.

## Requirements & Constraints

### `requirements/project.md`

- Line 25 — **File-based state**: "Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files (markdown, JSON, YAML frontmatter). No database or server." → output must be a file, not a service.
- Lines 37-46 — In-scope: "Observability (statusline, notifications, metrics, cost tracking)".
- Line 19 — "Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." → prefer minimal extension over new subsystem.

### `requirements/pipeline.md` §Metrics and Cost Tracking (lines 94-105)

> Description: The pipeline collects execution metrics from lifecycle event logs for post-session review and calibration.
> Inputs: `lifecycle/*/events.log` (JSONL event streams per feature)
> Outputs: `lifecycle/metrics.json` with per-feature metrics, tier aggregates, and calibration summaries
> Priority: should-have

**This is the directly adjacent existing requirement.** Acceptance criteria enumerate per-feature fields (tier, task count, batch count, rework cycles, review verdicts, phase durations, total duration) and tier aggregates — none mention `num_turns` or `cost_usd`. The gap is unambiguous.

Invariants that carry forward:
- In-progress features excluded
- Backfilled synthetic timestamps (T00:0X:00Z) → phase durations marked `null`
- Duplicate `feature_complete` events → last one canonical

### `requirements/pipeline.md` architectural constraints

- Line 131-132 — State file reads unprotected by locks; writers use atomic `os.replace()`. New output writes must follow this pattern (metrics.py:128-155 already does).
- Integration branch / session semantics — not relevant to a read-only aggregator.

### `requirements/observability.md`

- Dashboard is read-only wrt session files; can read `metrics.json` via `parse_metrics` (no-writes constraint satisfied automatically).
- Line 83 — Dashboard total refresh ≤ 7s latency budget. A future widget reading new top-level keys must stay within this.

### `requirements/multi-agent.md`

- Budget caps $5/$25/$50 and turn limits 15/20/30 per tier are hardcoded in `dispatch.py:119-121` TIER_CONFIG. The ticket's `vs budget caps` framing maps directly to these constants — the aggregator should compare against them, not against user-supplied inputs.

## Tradeoffs & Alternatives

### A. Extend `metrics.json` + CLI-only (Recommended)

**What gets built**: new functions in `claude/pipeline/metrics.py` that parse `dispatch_complete` / `dispatch_error` / `throttle_backoff` events from the same `events.log` files `metrics.py` already discovers, join tier via `lifecycle_start`, and emit new top-level keys in `metrics.json` (e.g. `tier_dispatch_aggregates`, `rate_limit_incidents`). Small CLI reporter — either an added `--report tier-dispatch` flag or `bin/overnight-metrics` — reads `metrics.json` and prints a formatted table to stdout.

**Pros**:
- One aggregation surface; reuses `discover_event_logs`, `parse_events`, `_safe_mean`, backfill detection, tier-grouping.
- Tier join already solved in metrics.py — extending avoids duplicating it.
- `metrics.json` is already the contract the dashboard reads; #088's snapshot artifact slots in naturally.
- Additive top-level keys are safe for existing consumers.

**Cons**:
- `metrics.json` schema now spans three cardinalities: per-feature, per-tier-feature-aggregate, per-dispatch-tier-aggregate. Mitigated by namespacing under distinct top-level keys.
- Requires a p95 helper (~5 lines new).

### B. Separate standalone aggregator + CLI-only

**What gets built**: `claude/pipeline/dispatch_metrics.py` (or `bin/overnight-metrics`) reads events.log independently, prints to stdout. Does not write JSON anywhere.

**Pros**: Leaves `metrics.json` untouched; cleaner separation of concerns; easier to retire post-recalibration.

**Cons**: Duplicates event discovery + JSONL parsing + tier join logic — guaranteed drift over time. No machine-readable artifact for #088's snapshot comparison → #088 depends on shell redirection conventions. Dashboard can't surface without re-running the script.

### C. Extend `metrics.json` + CLI + dashboard widget

Same producer as A, plus a new dashboard panel reading the new section via `parse_metrics`.

**Pros**: Glanceable in-flight visibility; mirrors existing producer/consumer pattern.

**Cons**: Adds template + data.py + test surface for a tool consulted quarterly. "Complexity must earn its place" — dashboard widget is speculative value for a medium-criticality instrumentation tool.

### Recommended approach: A (extend `metrics.json` + CLI-only)

Rationale: Minimum viable change that (a) gives #088 a stable diffable artifact for snapshotting across rounds, (b) gives humans a CLI report, (c) reuses all tier-joining + backfill + discovery logic already written, and (d) respects "simpler solution is correct when in doubt." Dashboard widget (C's increment) can be added later if human review wants in-flight surface; deferring it avoids spec-phase scope creep.

### Risks for recommended approach

1. **Schema cardinality mismatch in `metrics.json`**: per-feature records (one-per-feature) + tier aggregates (one-per-tier) + new per-dispatch tier aggregates (one-per-tier, different fields). Mitigation: put new data under distinct top-level keys (e.g. `tier_dispatch_aggregates`, `rate_limit_incidents`) so existing consumers can ignore them.
2. **Backwards-compat for dashboard**: `parse_metrics` returns the raw dict; additive keys should be safe. Spec phase should verify by reading `test_parse_metrics_valid_returns_dict`.
3. **Tier attribution gap for non-feature dispatches**: review agents, repair agents, and fix agents all emit `dispatch_complete` but may not have a matching `lifecycle_start` in their feature's events.log (they run in different lifecycle dirs or none at all). The missing-tier bucket is itself a signal for recalibration — don't silently drop.
4. **p95 on tiny samples**: early rounds will have n<10 per tier. Always emit `n` alongside aggregates; suppress p95 and fall back to `max` when n<10.
5. **`complexity_override` mid-feature**: dispatches before the override should arguably attribute to the original tier; dispatches after, to the new tier. Requires walking events.log by timestamp per-feature rather than taking first tier value — small but real design detail.

## Open Questions

- **Non-feature dispatch bucketing**: dispatches from review/repair/fix agents emit `dispatch_complete` but may not have a matching `lifecycle_start` with tier. Options: (i) drop silently, (ii) aggregate into an `untiered` bucket, (iii) attribute to the parent feature's tier. _Deferred: will be resolved in Spec by asking the user — this is a scope/interpretation choice, not a codebase-readable fact. Research recommends option (ii) — untiered is itself signal for recalibration — but leaves the final call to Spec._
- **`complexity_override` tier attribution**: should dispatches in a feature that override from simple→complex attribute to the original tier, the new tier, or split by timestamp? _Deferred: will be resolved in Spec by asking the user — research recommends split-by-timestamp (walk events chronologically) since that matches the downstream DR-4 consumer's intent (measure what was actually used), but confirms the decision belongs to Spec._

## Summary

Every research angle converges on the same recommendation: **extend `claude/pipeline/metrics.py`** with per-dispatch aggregation under new top-level keys in `lifecycle/metrics.json`, and ship a small CLI reporter. No events.log schema changes needed, no new file-state artifacts, no dashboard widget this round, stdlib-only Python. The existing metrics pipeline provides the reusable scaffolding (event discovery, JSONL parse, tier join, backfill detection, atomic writes). Two design details — non-feature dispatch bucketing and complexity_override tier attribution — are deferred to Spec for user decision.
