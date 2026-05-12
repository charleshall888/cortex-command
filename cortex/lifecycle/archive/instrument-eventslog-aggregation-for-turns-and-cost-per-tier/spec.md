# Specification: instrument-eventslog-aggregation-for-turns-and-cost-per-tier

> Epic context: Child of [#082 Adapt harness to Opus 4.7](../../backlog/082-adapt-harness-to-opus-47-prompt-delta-capability-adoption.md). DR-4 in [`research/opus-4-7-harness-adaptation/research.md`](../../research/opus-4-7-harness-adaptation/research.md) is this ticket's motivating decision record.

## Problem Statement

DR-4 in the epic research says "no model-matrix recalibration without data." The pipeline's `dispatch_start` and `dispatch_complete` events already persist every signal needed to answer "for opus+complex tasks, what's the p95 turn usage?" and "what's actual vs budgeted cost per (model, tier)?" — but nothing aggregates them. This ticket produces the baseline measurement surface that `#088` (collect baseline rounds) and `#089` (measure xhigh vs high cost delta) depend on, and that any future matrix-recalibration decision requires before it can be made on evidence rather than intuition.

A critical review surfaced that the production dispatch events live in `lifecycle/pipeline-events.log` and its per-session archives `lifecycle/sessions/{id}/pipeline-events.log` — not in per-feature `lifecycle/{feature}/events.log`. The aggregator reads those pipeline logs. Because `dispatch_start` already emits `complexity`, `criticality`, and `model` (dispatch.py:446-448) and is written immediately before the matching `dispatch_complete` on the same log, the aggregator can pair them within the log itself — no event-schema changes and no emitter refactor are required. Grouping aggregates by `(model, tier)` handles the natural matrix-recalibration question "what did this cost when we ran complex work on sonnet vs opus?" and a `--since DATE` CLI flag cleanly carves a post-4.7 baseline window from the pre-4.7 history.

## Requirements

1. **Add a `dispatch_start`→`dispatch_complete` pairing function to `claude/pipeline/metrics.py`**: walk each pipeline log's events in order; for each `dispatch_complete` event, bind it to the most recent preceding `dispatch_start` event with the same `feature` field from the same file. Extract `(model, complexity, criticality)` from `dispatch_start`. A `dispatch_complete` with no matching `dispatch_start` (should be rare — any case would indicate a logging bug) aggregates under `untiered` with an explicit warning.
   - Acceptance: `pytest claude/pipeline/tests/test_metrics.py -k pair_dispatch_events` exits 0 and covers: (a) standard dispatch_start + dispatch_complete in sequence, (b) multiple concurrent features interleaved in one log, (c) dispatch_complete with no matching dispatch_start → bucketed as untiered with warning, (d) mixed daytime-schema dispatch_complete (mode/outcome/pr_url) in the same file → skipped rather than attributed.

2. **Aggregation input sources**: the aggregator reads `lifecycle/pipeline-events.log` (active session) and all `lifecycle/sessions/*/pipeline-events.log` files (archived sessions). Per-feature `lifecycle/{feature}/events.log` files are **not** read by this aggregator — dispatch events are not written there in the production path.
   - Acceptance: `python3 -m cortex_command.pipeline.metrics --report tier-dispatch` reads from the session pipeline log glob; `pytest claude/pipeline/tests/test_metrics.py -k pipeline_events_sources` exits 0 and verifies the glob matches the session archive layout using a hand-crafted fixtures directory.

3. **Compute aggregates grouped by `(model, tier)`**. For each `(model, tier)` pair that has at least one dispatch:
   - `n` (sample count)
   - `num_turns`: `mean`, `median`, and (when n≥30) `p95` via `statistics.quantiles(values, n=100, method='inclusive')[94]`; when n<30, emit `max(values)` in a `max_turns_observed` field and omit p95 with a `p95_suppressed: true` flag — the spec explicitly does not publish a p95 that's statistically noise.
   - `cost_usd`: `mean`, `median`, and `max`. Mean and median are both reported because LLM cost distributions are heavy-tailed; the median protects against single-outlier distortion in small samples. Label all cost fields as `estimated_cost_usd_{mean,median,max}` per Anthropic's Agent SDK cost-tracking guidance (`ResultMessage.total_cost_usd` is a client-side estimate, not authoritative billing).
   - `budget_cap_usd`: the tier's `max_budget_usd` constant from `dispatch.py:119-121` TIER_CONFIG.
   - `over_cap_rate`: fraction of dispatches where `cost_usd > budget_cap_usd`. This is the tail-frequency metric — it answers "how often does this (model, tier) blow budget?" rather than relying on human interpretation of mean-vs-max gap.
   - `turn_cap_observed_rate`: fraction of dispatches where `num_turns == max_turns` (for the tier). Proxy for "tier is probably hitting its turn budget."
   - Acceptance: `pytest claude/pipeline/tests/test_metrics.py -k model_tier_aggregates` exits 0 and covers: (a) n=3 bucket emits mean/median/max/p95_suppressed:true, (b) n=100 bucket emits real p95, (c) over_cap_rate is correctly computed as count-over-cap/total, (d) aggregates for distinct (sonnet, simple) and (opus, complex) are reported independently.

4. **Escalation frequency by error_type**: for each `(model, tier)` pair, count `dispatch_error` events grouped by `error_type` (the full set from `classify_error()` at dispatch.py:255-309: `agent_timeout`, `agent_test_failure`, `agent_refusal`, `agent_confused`, `api_rate_limit`, `task_failure`, `infrastructure_failure`, `budget_exhausted`, `unknown`). Unknown `error_type` values from future code are aggregated under their raw string value.
   - Acceptance: `pytest claude/pipeline/tests/test_metrics.py -k error_type_frequency` exits 0 and verifies: (a) counts are bucketed by exact classify_error() string, (b) a novel error_type string is aggregated under its raw value without erroring.

5. **Windowing via `--since DATE` CLI flag**: `python3 -m cortex_command.pipeline.metrics --report tier-dispatch [--since YYYY-MM-DD]` filters events to those with `ts >= DATE`. Defaults to all-time when `--since` is omitted. This is the mechanism for carving DR-4's post-4.7 baseline window.
   - Acceptance: `python3 -m cortex_command.pipeline.metrics --report tier-dispatch --since 2026-04-18` exits 0 and excludes events prior to 2026-04-18; `pytest claude/pipeline/tests/test_metrics.py -k since_flag` exits 0 and verifies the filter drops pre-DATE events from the aggregate.

6. **Write results to `lifecycle/metrics.json` under a new top-level key `model_tier_dispatch_aggregates`**. Top-level structure: `{ "(sonnet,simple)": {n:..., num_turns_mean:..., ...}, "(opus,complex)": {...}, ... }` — one entry per observed `(model, tier)` pair. Tuple keys serialize as the string `"model,tier"` for JSON compatibility. All existing top-level keys (`generated_at`, `features`, `aggregates`, `calibration`) remain byte-compatible for current consumers.
   - Acceptance: `python3 -m cortex_command.pipeline.metrics` produces a `metrics.json` whose top-level keys are a superset of the old set; `python3 -c "import json, pathlib; d = json.loads(pathlib.Path('lifecycle/metrics.json').read_text()); assert 'model_tier_dispatch_aggregates' in d"` exits 0; existing dashboard test `claude/dashboard/tests/test_data.py::TestParseMetrics::test_valid_json_returns_dict_unchanged` still passes.

7. **CLI reporter prints a human-readable table**: extend `python3 -m cortex_command.pipeline.metrics` with a `--report tier-dispatch` flag that reads the just-written `metrics.json` and prints a table with columns: `(model, tier)`, `n`, `mean_turns`, `p95_turns` (or `max_turns_observed [n<30]`), `mean_cost_usd`, `median_cost_usd`, `max_cost_usd`, `budget_cap_usd`, `over_cap_rate`. Empty aggregates produce "No dispatch data found" rather than a crash.
   - Acceptance: `python3 -m cortex_command.pipeline.metrics --report tier-dispatch` exits 0; `python3 -m cortex_command.pipeline.metrics --report tier-dispatch | grep -q '(estimated)'` exits 0 (cost columns are labeled estimated); `pytest claude/pipeline/tests/test_metrics.py -k report_tier_dispatch` exits 0.

8. **Tests**: Unit tests use hand-crafted JSONL fixtures in `claude/pipeline/tests/fixtures/` rather than live corpus data. No network, no real dispatch. Tests exercise: (a) normal paired events, (b) interleaved concurrent features, (c) orphan dispatch_complete (no matching dispatch_start), (d) daytime-schema dispatch_complete filtering, (e) `--since` filter boundary, (f) n<30 p95 suppression, (g) over_cap_rate math, (h) novel error_type string passthrough.
   - Acceptance: `pytest claude/pipeline/tests/` exits 0 and the added tests appear in the output.

## Non-Requirements

- **No changes to any event emitter.** `dispatch.py` and `throttle.py` are not modified. No new fields on `dispatch_complete`, `dispatch_error`, `throttle_backoff`, or any other event. The critical review identified that the emitter refactor previously in this spec was redundant with `dispatch_start`'s existing `complexity`/`criticality`/`model` fields — pairing events within the log gives the same result with zero write-side risk.
- **No rate-limit aggregation.** `throttle_backoff` events are emitted only by `throttled_dispatch`, which has zero call sites in production (see brain.py:194-196 comment). Zero such events exist across the entire corpus. A separate cleanup ticket will remove the dead wrapper; this ticket does not instrument dead code.
- **No reads of `lifecycle/{feature}/events.log`.** Dispatch events are not written there. The two legacy orchestrator-written `dispatch_complete` entries that exist in per-feature logs use an incompatible schema (`{mode, outcome, pr_url}`) and are not this ticket's concern.
- **No dashboard widget this round.** CLI only. A dashboard panel is a later ticket if quarterly recalibration review finds the CLI insufficient.
- **No model-level token decomposition.** `ResultMessage.model_usage` (input/output/cache tokens per model) is not persisted in events.log; extending persistence is out of scope.
- **No retroactive backfill of historical events.** Pre-4.7 events are filtered out via `--since DATE` at query time, not rewritten on disk.
- **No changes to existing `metrics.json` keys.** `features`, `aggregates`, `calibration` retain their current field sets; only the new top-level `model_tier_dispatch_aggregates` key is added.
- **No CI hook, no scheduled run, no pre-commit integration.** The aggregator runs on demand.

## Edge Cases

- **Dispatch with no matching `dispatch_start`**: should be rare — any case indicates a logging bug (dispatch.py writes them as a pair). Bucketed as `untiered` with a warning surfaced in the CLI output; count is reported so the warning is visible, not silenced.
- **Multiple concurrent features interleaved in one pipeline log**: pairing is anchored by `feature` field, not file position — `dispatch_complete(feature=A)` pairs to the nearest preceding `dispatch_start(feature=A)` even if `dispatch_start(feature=B)` or `dispatch_progress(feature=A)` events fall between them.
- **Daytime-schema `dispatch_complete`** (the orchestrator-written variant with `{mode, outcome, pr_url}` that appears in two per-feature logs): not present in pipeline logs. The aggregator detects the absence of `cost_usd`/`num_turns` fields and skips such events with a debug note; they are not aggregated and not counted as untiered.
- **Malformed or empty JSONL line in a pipeline log**: skipped with a warning (matches existing `parse_events()` pattern at `metrics.py:67-93`); aggregation continues.
- **YAML-formatted `events.log` files** (one such file exists at `lifecycle/document-claude-config-dir-direnv-pattern-for-per-repo-permissions-scoping/events.log`): not read by this aggregator — per-feature events.log is not in its input set.
- **Tier with n<30**: p95 suppressed; `max_turns_observed` reported in its place with `p95_suppressed: true` flag; CLI output marks the column with `[n<30]`.
- **No dispatch data at all** (brand-new repo, no session logs yet): aggregator emits empty `model_tier_dispatch_aggregates: {}`. CLI prints "No dispatch data found" rather than crashing.
- **Novel `error_type` string** emitted by future `classify_error()` changes: aggregated under the raw string value rather than lost.
- **`--since DATE` in the future**: aggregator returns empty aggregates and CLI prints "No dispatch data found after YYYY-MM-DD."
- **Timestamps with non-`Z` offsets** (corpus contains `-0400` format in two files): parsed via `datetime.fromisoformat` with a `replace("Z", "+00:00")` + offset normalization. Python 3.11+ handles both; the aggregator asserts Python ≥ 3.11 at startup to surface any version mismatch cleanly.
- **Out-of-order timestamps in a single log file**: the pairing walker sorts events by `ts` within a file before pairing, rather than relying on file order.
- **Recovery dispatches that hardcode complexity** (`merge_recovery.py:336`, `conflict.py:332`, `integration_recovery.py:220`): these still emit `dispatch_start` with the hardcoded `complexity` value, and the aggregator attributes them accordingly. The resulting `(model, "simple")` / `(model, "complex")` buckets will include recovery-agent cost profiles. This is a measurement-integrity concern tracked in Open Decisions below.

## Changes to Existing Behavior

- **ADDED**: `claude/pipeline/metrics.py` gains `pair_dispatch_events()`, `compute_model_tier_dispatch_aggregates()`, and the output key `model_tier_dispatch_aggregates` in `metrics.json`.
- **ADDED**: CLI flags `--report tier-dispatch` and `--since YYYY-MM-DD` on `python3 -m cortex_command.pipeline.metrics`.

(No emitter changes, no dashboard changes, no new event types.)

## Technical Constraints

- **stdlib-only Python** for the aggregator. No pandas, no numpy. `json`, `statistics`, `collections.defaultdict`, `pathlib.Path`, `datetime` only.
- **Atomic writes** via `tempfile + os.replace()`, matching the existing `metrics.py` pattern at lines 128-155.
- **Python 3.11+ assertion** at module startup for `datetime.fromisoformat` offset handling.
- **Additive `metrics.json` schema**: dashboard's `parse_metrics` returns the raw dict; adding a top-level key is safe by contract.
- **p95 quantile method**: `statistics.quantiles(values, n=100, method='inclusive')[94]`. `inclusive` is correct because events.log is a known-complete batch, not a sample.
- **n≥30 threshold for p95**: chosen as the approximate central-limit-theorem threshold at which p95 estimates stop oscillating under heavy-tailed distributions. Below 30, the aggregator reports `max_turns_observed` with `p95_suppressed: true` rather than publishing a noisy statistic.
- **Pairing is file-local**: `dispatch_start`→`dispatch_complete` pairing never crosses file boundaries. A dispatch that spans two log files (e.g., session rotation mid-dispatch — not currently possible but worth documenting) would result in an unpaired dispatch_complete bucketed as untiered.
- **Cost labeled "estimated"**: per Anthropic's Agent SDK cost-tracking guidance.

## Open Decisions

- **Recovery-site hardcoded complexity**: `merge_recovery.py:336`, `conflict.py:332`, and `integration_recovery.py:220` pass `complexity="simple"` or `"complex"` as static values, not as a reflection of the parent feature's actual tier. The aggregator attributes these dispatches to the hardcoded tier, which may inflate simple/complex buckets with recovery-agent cost profiles. Not resolving in this ticket because the right fix (thread the parent feature's tier through to the recovery dispatch site) is a dispatch-path refactor beyond this ticket's scope — worth a separate cleanup ticket if DR-4 consumers find the recovery skew distorts matrix decisions.
