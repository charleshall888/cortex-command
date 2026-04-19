# Specification: instrument-eventslog-aggregation-for-turns-and-cost-per-tier

> Epic context: Child of [#082 Adapt harness to Opus 4.7](../../backlog/082-adapt-harness-to-opus-47-prompt-delta-capability-adoption.md). Broader context lives in [`research/opus-4-7-harness-adaptation/research.md`](../../research/opus-4-7-harness-adaptation/research.md) — DR-4 is this ticket's motivating decision record.

## Problem Statement

DR-4 in the epic research says "no model-matrix recalibration without data." The `events.log` schema already persists `num_turns` and `cost_usd` per dispatch, but no pipeline aggregates them — so questions like "for complex tasks in the past month, what's the p95 turn usage?" and "what's actual vs budgeted cost per tier?" cannot be answered. This ticket produces the baseline measurement surface that `#088` (collect baseline rounds) and `#089` (measure xhigh vs high cost delta) depend on, and that any future matrix-recalibration decision requires before it can be made on evidence instead of intuition.

A cleaner long-term design is possible here than a simple join-after-the-fact: `dispatch.py` and `throttle.py` already have each dispatch's complexity/criticality in scope at emission time. Carrying those fields on the `dispatch_complete`, `dispatch_error`, and `throttle_backoff` events eliminates the lifecycle-directory join for all future events, handles `complexity_override` chronological attribution automatically (tier is stamped at the moment the dispatch happens), and gives review/repair/fix agents — which often run outside a feature's lifecycle directory — correct tier attribution without any untiered bucket. For events already on disk (no `complexity`/`criticality` field), a best-effort lifecycle_start join with chronological walking covers the backfill case.

## Requirements

1. **Emit complexity and criticality on dispatch events**: `dispatch_complete`, all three `dispatch_error` call sites, and `throttle_backoff` must include `complexity` and `criticality` fields at emit time, using the parameters already in scope at each call site.
   - Acceptance: `grep -rn '"event": "dispatch_complete"' claude/` shows the emission site writes both fields, and `python3 -c "from claude.pipeline.state import log_event; ..."` style synthetic write + read produces an event with both fields populated. Automated verification: new/updated unit tests in `claude/pipeline/tests/test_dispatch.py` and `claude/overnight/tests/test_throttle.py` assert the events contain `complexity` and `criticality`; `pytest claude/pipeline/tests/test_dispatch.py claude/overnight/tests/test_throttle.py` exits 0.

2. **Extend `claude/pipeline/metrics.py` with per-dispatch aggregation**: a new function (e.g. `extract_dispatch_records()`) reads `dispatch_complete`, `dispatch_error`, and `throttle_backoff` events from every `lifecycle/*/events.log` file, preferring the per-event `complexity`/`criticality` fields. When either field is absent (legacy event), fall back to walking the same file's `lifecycle_start` and `complexity_override` events chronologically and attributing the dispatch to the tier active at the dispatch's timestamp.
   - Acceptance: `pytest claude/pipeline/tests/test_metrics.py -k dispatch_records` exits 0 and covers: (a) events with native tier fields, (b) legacy events joining via `lifecycle_start`, (c) events from a feature with a `complexity_override`, (d) events in a file with no `lifecycle_start` (remain untiered).

3. **Compute all four deliverable dimensions** in `compute_tier_dispatch_aggregates()`:
   - Mean and p95 `num_turns` per tier. Use `statistics.quantiles(values, n=100, method='inclusive')[94]` for p95; when `len(values) < 10` emit `max(values)` in place of p95 and record a `p95_suppressed: true` flag for that tier.
   - Mean and max `cost_usd` per tier, each reported alongside the tier's `max_budget_usd` constant from `TIER_CONFIG` (`dispatch.py:119-121`) so the CLI can show actual-vs-cap.
   - Escalation frequency per `error_type`: for each distinct `error_type` value in `dispatch_error` events across the corpus, report a count per tier.
   - Rate-limit incidents per tier: two numbers — incident count (count of `throttle_backoff` events) and sum of `delay_seconds`.
   - Every aggregate includes `n` (sample count). Untiered dispatches with no resolvable tier aggregate under a distinct `untiered` key only if the fallback join also fails (the emission-time field fix makes this bucket near-empty for future data).
   - Acceptance: `pytest claude/pipeline/tests/test_metrics.py -k tier_dispatch_aggregates` exits 0 and covers: (a) a tier with n<10 emits `p95_suppressed: true`, (b) a tier with n≥10 emits a real p95, (c) error_type buckets are keyed by the exact strings in `classify_error()`, (d) rate_limit bucket reports both count and sum.

4. **Write results to `lifecycle/metrics.json` under new top-level keys** `tier_dispatch_aggregates` and `rate_limit_incidents`. All existing top-level keys (`generated_at`, `features`, `aggregates`, `calibration`) remain byte-compatible for consumers that ignore unknown keys.
   - Acceptance: `python3 -m claude.pipeline.metrics` produces a `metrics.json` whose top-level keys are a strict superset of the old set; `python3 -c "import json, pathlib; d = json.loads(pathlib.Path('lifecycle/metrics.json').read_text()); assert 'tier_dispatch_aggregates' in d and 'rate_limit_incidents' in d"` exits 0. Existing dashboard tests in `claude/dashboard/tests/test_data.py::test_parse_metrics_valid_returns_dict` still pass.

5. **CLI reporter**: extend the existing `python3 -m claude.pipeline.metrics` entry point with a `--report tier-dispatch` flag that reads `metrics.json` (not the raw events.log — reuse the already-written artifact) and prints a human-readable table to stdout covering all four dimensions plus per-tier `n`. The cost column label must include the word "estimated" per Anthropic's cost-observability guidance.
   - Acceptance: `python3 -m claude.pipeline.metrics --report tier-dispatch` exits 0 and prints a report containing the strings `"n="`, `"p95"` (or `"p95_suppressed"`), `"mean_cost_usd (estimated)"`, `"rate_limit_incidents"`; `pytest claude/pipeline/tests/test_metrics.py -k report_tier_dispatch` exits 0.

6. **Backward-compatibility fallback**: the aggregator tolerates events.log files containing any mixture of legacy-schema and new-schema events without errors. A file with only legacy events produces correct output via the `lifecycle_start`+`complexity_override` chronological walker; a file with only new-schema events produces correct output via the per-event tier fields; a file with both (typical during the transition window) produces correct output by preferring the per-event tier where present.
   - Acceptance: `pytest claude/pipeline/tests/test_metrics.py -k fallback` exits 0 and runs three fixture permutations (legacy-only, new-only, mixed) producing the same aggregated totals.

7. **Tests**: Unit tests use hand-crafted JSONL fixtures in `claude/pipeline/tests/fixtures/` (or extend the existing `tests/fixtures/state/`) rather than the current repo's real events.log data. No live network, no real dispatch.
   - Acceptance: `pytest claude/pipeline/tests/` exits 0 and test count increases by at least 5 over the baseline on `main`.

## Non-Requirements

- **No events.log schema rethink**. The only schema change is adding `complexity` and `criticality` to three existing event types. The JSONL append-only structure, atomic-write semantics, and per-feature file organization all stay as-is.
- **No dashboard widget this round**. CLI only. A dashboard panel reading the new `metrics.json` keys is a later ticket if quarterly recalibration review finds the CLI insufficient.
- **No model-level (Haiku/Sonnet/Opus) cost decomposition**. `ResultMessage.model_usage` is not currently persisted in events.log; extending persistence is out of scope. If future recalibration needs model-level splits, that's a separate ticket.
- **No retroactive backfill of historical events**. The 2,709 existing events will not be rewritten. They flow through the fallback join path. After 2–3 rounds on the new schema, the legacy share shrinks naturally.
- **No changes to existing `metrics.json` keys** beyond the two new additive top-level entries. `features`, `aggregates`, `calibration` retain their current field sets.
- **No CI hook, no scheduled run, no pre-commit integration**. The aggregator runs on demand.

## Edge Cases

- **Feature with no `lifecycle_start` event and legacy dispatches**: the chronological-walker fallback yields no tier; those dispatches aggregate under `untiered`. This bucket appears in the output as a named category — do not silently drop.
- **Feature with `complexity_override` mid-run and legacy dispatches**: the walker attributes each dispatch by timestamp — dispatches before the override land in the original tier, dispatches after in the new tier. For new-schema events, this happens automatically via the emission-time field.
- **Feature with both legacy and new-schema dispatches** (transition window): each event is attributed independently — new-schema events use their embedded tier, legacy events fall back to the walker. No cross-contamination.
- **Malformed or empty JSONL line in events.log**: skip with a warning (matches existing `parse_events()` pattern at `metrics.py:67-93`); do not fail the aggregation.
- **Tier with n<10**: `p95_suppressed: true`, p95 replaced by `max`. The CLI surfaces this with a visible marker so humans don't misread max as p95.
- **No dispatch data at all** (brand-new repo or post-reset): aggregator emits empty `tier_dispatch_aggregates: {}` and `rate_limit_incidents: {}`. CLI prints "No dispatch data found" rather than crashing.
- **Actual cost exceeds budget cap**: report both `mean_cost_usd` and `max_cost_usd` alongside `budget_cap_usd`; the CLI highlights when `max > cap` with a visible marker. No alerting, no failure — this is observability.
- **`dispatch_error` with `error_type` absent from `classify_error()`'s known set**: aggregate under the raw string value (future-proofs against new error types without requiring code changes to the aggregator).
- **Feature lifecycle dir containing only `dispatch_complete` from a non-primary agent (e.g., review)**: new-schema events carry tier; legacy events in this case attribute correctly if the parent feature's `lifecycle_start` is in the same events.log — otherwise `untiered`.

## Changes to Existing Behavior

- **MODIFIED: `dispatch_complete` event schema** — adds `complexity: str` and `criticality: str` fields. Call site: `claude/pipeline/dispatch.py:510-516`.
- **MODIFIED: `dispatch_error` event schema** — adds `complexity` and `criticality` fields at all three emit sites in `dispatch.py` (lines 528-533, 553-558, 571-577).
- **MODIFIED: `throttle_backoff` event schema** — adds `complexity` and `criticality` fields. Call site: `claude/overnight/throttle.py:260-265`. Both parameters are already in scope.
- **ADDED: `claude/pipeline/metrics.py`** gains `extract_dispatch_records()`, `compute_tier_dispatch_aggregates()`, and output keys `tier_dispatch_aggregates` + `rate_limit_incidents` in `metrics.json`.
- **ADDED: CLI flag `--report tier-dispatch`** on `python3 -m claude.pipeline.metrics`.

## Technical Constraints

- **stdlib-only Python** for the aggregator. No pandas, no numpy. `json`, `statistics`, `collections.defaultdict`, `pathlib.Path` only. Rationale: small personal tooling; maintainability through simplicity.
- **Atomic writes** via `tempfile + os.replace()`, matching the existing `metrics.py` pattern.
- **Additive `metrics.json` schema**: dashboard's `parse_metrics` returns the raw dict; additive top-level keys are safe by contract.
- **p95 quantile**: `statistics.quantiles(values, n=100, method='inclusive')[94]`. `inclusive` (not default `exclusive`) is correct here because events.log is a known-complete batch, not a sample — `exclusive` would never return the observed max.
- **p95 suppression at n<10**: surfaces `max` with an explicit `p95_suppressed: true` flag rather than lying about a statistic that is noise at small sample sizes.
- **Cost output labeled "estimated"**: per Anthropic's Agent SDK cost-tracking guidance (`ResultMessage.total_cost_usd` is a client-side estimate, not authoritative billing).
- **Rate-limit reporting**: both incident count AND sum of `delay_seconds`, because "one long backoff vs many short backoffs" is a meaningful distinction that a single metric collapses.
- **Emission-time tier is authoritative when present**: the aggregator does not try to "validate" the per-event tier against `lifecycle_start` — the emission-time value reflects the actual complexity passed to `dispatch.py`, which is what the downstream matrix-recalibration consumer wants to measure.
- **No event removals**: existing consumers of `dispatch_complete`, `dispatch_error`, `throttle_backoff` continue to receive the old fields; the new fields are additive.

## Open Decisions

None. All design decisions are resolved; the two items flagged as deferred during research (non-feature dispatch bucketing and `complexity_override` attribution) were resolved by the user during the Specify interview in favor of the emission-time-tier refactor.
