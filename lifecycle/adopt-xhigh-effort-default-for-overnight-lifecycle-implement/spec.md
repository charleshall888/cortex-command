# Specification: Adopt comprehensive effort policy for overnight dispatches

## Problem Statement

The overnight runner's effort selection is currently a 1D map keyed only on complexity (`EFFORT_MAP[trivial]="low"`, `EFFORT_MAP[simple]="medium"`, `EFFORT_MAP[complex]="high"`). This predates Opus 4.7's `xhigh` setting and Anthropic's explicit guidance: *"Start with `xhigh` for coding and agentic use cases, and use `high` as the minimum for most intelligence-sensitive workloads."* It also predates Sonnet 4.6's elevated baseline expectations. The current 1D map cannot encode a per-(model, criticality, skill) policy that aligns with Anthropic's recommendations, and silent truncations under higher effort levels go undetected because the dispatch path never inspects `stop_reason`. This work introduces a centralized 2D effort matrix with selective skill-based overrides, raises Sonnet's baseline to `high` per Anthropic guidance, lifts complex+high/critical Opus dispatches to `xhigh`, reserves `max` for the highest-stakes recovery paths (`review-fix`, `integration-recovery`), and wires `stop_reason == "max_tokens"` detection into dispatch event logging via an SDK upgrade. The benefit is across-the-board quality alignment with Anthropic's current model recommendations, plus first-class observability of truncation events that today are silent.

> **Scope caveat — observability axes**: This ticket adds *truncation visibility* (via `stop_reason`) AND closes the structural cost-observability gap (via `metrics.py` extension to bucket by `(model, tier, skill, effort)`). Both work together: post-flip, an operator can slice `metrics.json` by effort to detect cost regressions and by `stop_reason` to detect quality regressions.

> **Adaptive-thinking framing**: Per Anthropic, `effort` is "a behavioral signal, not a strict token budget" — the model adapts thinking depth to task complexity, capped by the configured effort level. So `xhigh` sets the *maximum* reasoning the model may use, not a fixed amount. Simple tasks under `xhigh` may use little more than under `high`; complex tasks under `xhigh` may use meaningfully more. This bounds the cost-regression risk to actually-complex work — a key consideration for the rollback monitoring story.

## Requirements

1. **Centralized 2D effort matrix replaces `EFFORT_MAP`**:
   - Acceptance: After implementation, `grep -n "_EFFORT_MATRIX" cortex_command/pipeline/dispatch.py` returns ≥1 match and `grep -n "EFFORT_MAP" cortex_command/pipeline/dispatch.py` returns 0 matches in non-test code (the constant is renamed/replaced, not added alongside).
   - Acceptance: `python -c "from cortex_command.pipeline.dispatch import _EFFORT_MATRIX; assert len(_EFFORT_MATRIX) == 12"` exits 0 (12 cells: 3 complexity × 4 criticality).

2. **Effort matrix values match the policy table below**:
   - Acceptance: Each cell of the matrix matches the table in Technical Constraints §1. A unit test (added in this ticket) iterates all 12 cells and asserts the policy. `pytest cortex_command/pipeline/tests/test_dispatch.py::test_effort_matrix_policy` exits 0.
   
3. **Skill-based overrides on Opus only**: `review-fix` and `integration-recovery` get `effort="max"` when the resolved model is Opus; for any other model, the matrix value applies. The override is computed using the *effective* model — i.e., `model_override` (when passed by the caller) takes precedence over `_MODEL_MATRIX` resolution before the gate is evaluated.
   - Acceptance: A unit test asserts `resolve_effort(complexity="complex", criticality="high", skill="review-fix", model="opus")` returns `"max"`; `resolve_effort(complexity="simple", criticality="high", skill="review-fix", model="sonnet")` returns `"high"`; `resolve_effort(complexity="complex", criticality="high", skill="integration-recovery", model="opus")` returns `"max"`; `resolve_effort(complexity="complex", criticality="medium", skill="integration-recovery", model="sonnet")` returns `"high"`. `pytest cortex_command/pipeline/tests/test_dispatch.py::test_effort_skill_overrides` exits 0.

3a. **`integration-recovery` dispatch site forces Opus**: The single production caller at `cortex_command/overnight/integration_recovery.py:215–225` adds `model_override="opus"` to its `dispatch_task` invocation so the skill override fires reliably (without this change, the dispatch defaults to criticality="medium" → Sonnet → override never fires). This is the dispatch-site fix that makes Req #3's `integration-recovery → max` policy actually take effect in production.
   - Acceptance: `grep -n 'model_override="opus"' cortex_command/overnight/integration_recovery.py` returns ≥1 match adjacent to the existing `dispatch_task` call.
   - Acceptance: An integration-style test in `cortex_command/overnight/tests/test_integration_recovery.py` asserts that the `dispatch_task` call receives `model_override="opus"`. `pytest cortex_command/overnight/tests/test_integration_recovery.py::test_integration_recovery_forces_opus` exits 0.

4. **`dispatch_task` consults the matrix at the existing call site (`dispatch.py:439`)**: The call shape becomes `effort = effort_override if effort_override is not None else resolve_effort(complexity, criticality, skill, model)`, where `model` is the *post-override* model (i.e., `model_override` already applied at line 438 in the existing code).
   - Acceptance: `grep -n "resolve_effort" cortex_command/pipeline/dispatch.py` returns ≥1 match adjacent to the existing line 439 logic; `grep -n "EFFORT_MAP\\[complexity\\]" cortex_command/pipeline/dispatch.py` returns 0 matches.

5. **`dispatch_task` docstring (line 391–393) lists the new effort vocabulary AND notes the adaptive-thinking framing**: The list of valid `effort_override` values reads `"low", "medium", "high", "xhigh", "max"`. The docstring notes that `xhigh` is Opus-4.7-only AND that effort is a behavioral signal that caps the *maximum* reasoning depth — the model adapts thinking down for simpler tasks. (Per Anthropic's effort docs: "Effort is a behavioral signal, not a strict token budget.")
   - Acceptance: `grep -c '"low", "medium", "high", "xhigh", "max"' cortex_command/pipeline/dispatch.py` returns ≥1; `grep -c "Opus 4.7" cortex_command/pipeline/dispatch.py` returns ≥1; `grep -c "adaptive\|maximum\|behavioral signal" cortex_command/pipeline/dispatch.py` returns ≥1 in proximity to the effort docstring.

6. **`claude-agent-sdk` upgraded to a version that exposes `stop_reason` on `ResultMessage` AND ships a parser that extracts `stop_reason` from CLI JSON**: `pyproject.toml` pins `claude-agent-sdk` to a specific version (no longer unconstrained); the upgraded SDK's `ResultMessage` includes `stop_reason: str | None`; the SDK's `_internal/message_parser.py` extracts the field from the CLI JSON.
   - Acceptance: `python -c "from claude_agent_sdk.types import ResultMessage; from dataclasses import fields; assert 'stop_reason' in {f.name for f in fields(ResultMessage)}"` exits 0.
   - Acceptance: `grep -c '"claude-agent-sdk"' pyproject.toml` returns ≥1 with an explicit version constraint (e.g., `claude-agent-sdk = ">=X.Y.Z,<W.0"` or equivalent).
   - Acceptance: A new test feeds a canned CLI-format JSON line containing `"stop_reason": "max_tokens"` to the SDK's `_internal/message_parser` and asserts the resulting `ResultMessage.stop_reason == "max_tokens"`. `pytest cortex_command/pipeline/tests/test_dispatch.py::test_sdk_parser_extracts_stop_reason` exits 0. (Closes the parser-extraction-fallback gap acknowledged in Edge Cases — if the upgraded SDK's parser drops the field, this test fails and the implementation must add a wrapper/extractor before merge.)

7. **`_stubs.py:ResultMessage` mirrors the upgraded SDK shape**: includes `stop_reason: str | None = None`. The new field MUST be appended as the LAST dataclass field (after `structured_output`) so that existing positional `ResultMessage(...)` constructions in tests do not break. If the upgraded SDK adds further fields beyond `stop_reason`, the stub mirrors those too (to prevent silent stub-vs-SDK divergence in field-introspection paths).
   - Acceptance: `python -c "from cortex_command.tests._stubs import ResultMessage; from dataclasses import fields; ff=[f.name for f in fields(ResultMessage)]; assert ff[-1] == 'stop_reason'"` exits 0.
   - Acceptance: All existing `ResultMessage(...)` test constructions continue to pass — `pytest cortex_command/pipeline/tests/ cortex_command/tests/` exits 0.

8. **Dispatch event logging captures `stop_reason` and surfaces truncation events** at BOTH dispatch_complete emitters:
   - `cortex_command/pipeline/dispatch.py` ResultMessage handler (lines 554–575): emit `stop_reason` (string or null) on `dispatch_complete`; emit a separate `dispatch_truncation` event before `dispatch_complete` when `stop_reason in {"max_tokens", "model_context_window_exceeded"}`.
   - `cortex_command/overnight/runner.py:_emit_orchestrator_round_telemetry` (lines 807–819): extract `stop_reason` from the orchestrator envelope JSON (already present in `fixtures/orchestrator_envelope_success.json:12` as `"stop_reason": "end_turn"`) and include it in the emitted `dispatch_complete` event. Apply the same truncation-event rule.
   - Acceptance: Unit tests mock `ResultMessage(stop_reason="max_tokens", ...)` for the SDK path AND a synthetic envelope dict with `"stop_reason": "max_tokens"` for the runner path; both assert `dispatch_truncation` then `dispatch_complete` are logged. `pytest cortex_command/pipeline/tests/test_dispatch_instrumentation.py::test_max_tokens_truncation_emits_dispatch_truncation_event_via_dispatch_task` exits 0; `pytest cortex_command/overnight/tests/test_orchestrator_round_telemetry.py::test_max_tokens_truncation_emits_dispatch_truncation_event_via_orchestrator_round` exits 0.
   - Acceptance: `grep -c "dispatch_truncation" cortex_command/pipeline/dispatch.py cortex_command/overnight/runner.py` returns ≥2 (≥1 in each file).
   - Acceptance: `grep -c "stop_reason" cortex_command/overnight/runner.py` returns ≥1.

9. **A new exact-key-list assertion test for `dispatch_complete` events is added** to `tests/test_dispatch_instrumentation.py` (no such assertion exists today; existing line 287/302/347 lists are for `dispatch_start`). The new test asserts `dispatch_complete` events have the exact key set `{event, feature, cost_usd, duration_ms, num_turns, stop_reason}` (snake_case ordered as listed).
   - Acceptance: `pytest cortex_command/pipeline/tests/test_dispatch_instrumentation.py::test_dispatch_complete_exact_key_list` exits 0.

10. **Regression test for `effort` value passthrough to the SDK CLI subprocess**: A test verifies that `ClaudeAgentOptions(effort=<value>)` for each value in `{"low", "medium", "high", "xhigh", "max"}` constructs without exception AND that the SDK's `subprocess_cli` propagates the value as `["--effort", <value>]` to the CLI argv. The test covers passthrough; runtime CLI-acceptance is verified empirically post-flip via the truncation observability stack (Reqs 6–9). When SDK PR #835 (xhigh typing) merges and the project upgrades to a version including it, this test should be tightened to assert the typed Literal accepts xhigh — but that is a follow-up ticket, not blocking.
    - Acceptance: `pytest cortex_command/pipeline/tests/test_dispatch.py::test_effort_value_passthrough` exits 0 with the SDK installed.

11. **`docs/sdk.md` documents the new effort matrix and skill overrides** (per project convention, sdk.md is the source-of-truth for SDK model-selection mechanics).
    - Acceptance: `grep -c "_EFFORT_MATRIX" docs/sdk.md` returns ≥1; `grep -c "review-fix" docs/sdk.md` returns ≥1 in proximity to `max`; the doc explicitly notes that the override fires only for the subset of cells that resolve to Opus (i.e., `(complex, high)` and `(complex, critical)`), not for every review-fix dispatch.

12. **`docs/overnight-operations.md` documents the rationale, adaptive-thinking framing, and rollback monitoring procedure**:
    - Cites the Anthropic migration guide + xhigh-for-coding recommendation.
    - Cites the #089 closure rationale.
    - Notes that effort is a behavioral signal capping *maximum* reasoning depth; cost regression is bounded by task complexity, not by the effort setting alone.
    - Documents the rollback monitoring procedure now that `metrics.py` buckets by effort (per Req #13): how to query post-flip vs pre-flip aggregates by `(model, tier, skill, effort)`, what threshold (>2× per-bucket mean cost over 2-3 rounds) triggers human investigation, and the rollback path (revert the matrix flip).
    - Acceptance: `grep -c "xhigh" docs/overnight-operations.md` returns ≥1; `grep -c "rollback" docs/overnight-operations.md` returns ≥1; `grep -c "adaptive\|maximum reasoning\|behavioral signal" docs/overnight-operations.md` returns ≥1; the doc references the new effort-bucketed aggregator with a query example.

13. **`metrics.py` aggregator extended to bucket by `(model, tier, skill, effort)`**: The structural cost-observability gap is closed in this ticket. `pair_dispatch_events` propagates `effort` from `dispatch_start` events into the paired record schema; `compute_skill_tier_dispatch_aggregates` (and `compute_model_tier_dispatch_aggregates` if appropriate) extends its bucket key to include effort. Existing aggregator outputs gain an `effort` axis; downstream consumers (dashboard, morning report) gracefully tolerate the additional axis (per research, no consumer schema-validates the bucket key set).
    - Acceptance: `grep -c '"effort"' cortex_command/pipeline/metrics.py` returns ≥1 inside the paired-record schema definition AND inside the bucket-key construction.
    - Acceptance: A unit test in `cortex_command/pipeline/tests/test_metrics.py` synthesizes dispatch events at multiple effort levels for the same `(model, tier, skill)` and asserts they land in distinct buckets in the aggregated output. `pytest cortex_command/pipeline/tests/test_metrics.py::test_aggregator_buckets_by_effort` exits 0.
    - Acceptance: An end-to-end test feeds a realistic event log (mix of pre-flip-style and post-flip-style records) and asserts the operator-facing `metrics.json` slice exposes per-effort cost means. `pytest cortex_command/pipeline/tests/test_metrics.py::test_metrics_json_exposes_effort_bucket` exits 0.
    - Backwards compatibility: existing tests/snapshots that assume `(model, tier, skill)` bucketing must be updated in lockstep — the new `effort` axis splits old buckets into per-effort sub-buckets.

## Non-Requirements

- **Per-call `effort_override` plumbing through `retry_task`**: Not added. The 2D matrix + skill overrides resolve effort centrally in `dispatch_task`; no caller needs to thread an override (the existing `effort_override` parameter on `dispatch_task` remains as a forced-override escape hatch but is not used by overnight callers).
- **3D matrix keyed by `(skill, complexity, criticality)`**: Out of scope. Skill overrides are a small flat dict that applies *after* matrix lookup, not a full 3D structure. Reserve the 3D refactor for if/when a third skill-specific exception lands.
- **Setting `max_tokens` on dispatches**: Not in scope. `ClaudeAgentOptions` has no `max_tokens` field and the CLI has no flag in v2.1.x. Anthropic's recommendation to raise `max_tokens` to ≥64k under xhigh is acknowledged but unactionable in this codebase; this ticket addresses *visibility* of truncation (via `stop_reason`), not avoidance.
- **Bumping Haiku effort**: Not in scope. Trivial+low/medium dispatches stay at `low` effort — Haiku is for cheap fast tasks where effort gains do not pay off.
- **Per-attempt effort variation in the retry loop**: Not in scope. Effort is resolved per-dispatch from the matrix; the same dispatch under retry uses the same matrix entry. Effort does not change on retry-without-escalation. On model escalation, the new dispatch re-resolves effort from the matrix and the skill-override gate re-evaluates against the post-escalation model — so the override CAN flip on/off across an escalation boundary (e.g., review-fix on `(complex, low)` starts on Sonnet at `high`, escalates to Opus, and then fires the `max` override on the post-escalation dispatch).
- **Detection of `stop_reason == "refusal"` or other non-truncation values**: Not surfaced as a separate event. The full `stop_reason` is logged on `dispatch_complete`; only `max_tokens` and `model_context_window_exceeded` get the dedicated `dispatch_truncation` event.

## Edge Cases

- **`effort_override` parameter still passed explicitly**: The `effort_override` parameter on `dispatch_task` continues to take precedence over matrix lookup. Behavior unchanged for callers that already pass it (none in current production code per research).
- **Model escalation crossing matrix cells AND firing/un-firing the skill override**: When a (complex, low) review-fix retry escalates from Sonnet to Opus, the new dispatch re-resolves effort: matrix says `high`, but the skill override now fires (gate switches to true at `model == "opus"`) and bumps effort to `max`. Under-test requirement: the matrix path AND the skill-override gate are both re-evaluated on the post-escalation dispatch — no caching of pre-escalation values across the retry boundary.
- **Skill override on non-Opus**: If `review-fix` runs at (simple, *) → Sonnet, the override does not fire (gated on `model == "opus"`); the matrix value (`high`) applies. No silent downgrade.
- **`stop_reason` is null on a successful response**: The field is logged as null in `dispatch_complete`; no `dispatch_truncation` event is emitted.
- **`stop_reason == "refusal"` or other non-truncation values**: Logged as the value of `stop_reason` on `dispatch_complete`; no separate event. The full event log preserves the value for downstream analysis.
- **CLI emits a `stop_reason` value the parser doesn't yet handle**: The `stop_reason` field on `ResultMessage` is `str | None` — any string passes through. The dedicated `dispatch_truncation` event uses an explicit allow-list of truncation reasons (`{"max_tokens", "model_context_window_exceeded"}`) so unknown future values do not generate spurious truncation events.
- **SDK upgrade introduces other breaking changes**: 30 releases lie between current pin (0.1.41) and latest. Known intermediate hazards: v0.1.55 added an `int` arm to `ClaudeAgentOptions.effort` (perturbs type narrowing if any consumer narrows on effort); v0.1.67 adds `sniffio>=1.0.0` runtime dep; v0.1.70 raises `mcp` dependency floor to `>=1.19.0`. The implementation must run the full test suite after the upgrade AND confirm the three known hazards do not regress (specifically: type-checker run, dependency resolution under uv lock, and any direct `mcp` import sites). If the test suite reveals unrelated regressions, those must be addressed in this ticket.
- **Dashboard or seed-data consumers of `dispatch_complete` events**: Per research, no consumer schema-validates the key list except `tests/test_dispatch_instrumentation.py`. Adding `stop_reason` is non-breaking for `pair_dispatch_events`, the dashboard, and seed data — but the asserted key list test (added by Req #9) must include the new key.
- **Activity log fanout under xhigh**: xhigh causes more tool calls per dispatch (per Anthropic). The activity-log writer (`dispatch.py:533–541`) runs in `asyncio.to_thread` and is best-effort. No new code change. Operational signal: the morning reviewer should compare last-night dispatch counts and per-feature tool-use counts against a rolling 7-day baseline visible in `metrics.json`; sustained >2× regression triggers human investigation.
- **Runtime guard failure mode**: When `resolve_effort` would request an unsupported effort value for a model (e.g., `xhigh` on Sonnet — should not happen given the matrix design, but guards future regressions), the guard MUST fail loudly with `assert` raising `AssertionError` at dispatch time, not silently downgrade. This makes test-mode and dev-mode defects visible. In production overnight runs, the assertion failure surfaces as a feature-level pause via the existing dispatch error path (not a session abort).

## Changes to Existing Behavior

- **MODIFIED**: `EFFORT_MAP` (`dispatch.py:127–131`) → replaced by `_EFFORT_MATRIX` keyed by `(complexity, criticality)`. Direct lookups via `EFFORT_MAP[complexity]` are eliminated.
- **MODIFIED**: `dispatch_task` effort-resolution at `dispatch.py:439` → calls `resolve_effort(complexity, criticality, skill, model)` instead of indexing `EFFORT_MAP[complexity]`. Effort still respects `effort_override` first.
- **MODIFIED**: Sonnet-tier dispatches (every cell that resolves to Sonnet) bumped from current effort (`medium` for simple-tier, `high` for complex+low/medium) to `high` uniformly.
- **MODIFIED**: Opus-tier dispatches at `(complex, high)` and `(complex, critical)` bumped from `high` to `xhigh`.
- **MODIFIED**: `review-fix` dispatches running on Opus bumped from `xhigh` (per matrix) to `max`. Note: only ~25% of review-fix dispatches resolve to Opus (cells `(complex, high)` and `(complex, critical)`); the other ~75% (cells that trigger review per `requires_review()` but resolve to Sonnet) are unaffected.
- **MODIFIED**: `integration-recovery` dispatches now force `model_override="opus"` at the dispatch site (`integration_recovery.py:215–225`); the resulting Opus dispatch then receives the `max`-effort override per Req #3.
- **MODIFIED**: `metrics.py` aggregator extended to bucket by `(model, tier, skill, effort)`; `pair_dispatch_events` propagates `effort` from `dispatch_start` into the paired record schema. Closes the structural cost-observability gap so post-flip cost regressions can be sliced by effort in `metrics.json`.
- **ADDED**: `dispatch_complete` events from BOTH emitters (`dispatch.py` ResultMessage path AND `runner.py:_emit_orchestrator_round_telemetry`) now carry a `stop_reason` field (string or null).
- **ADDED**: New `dispatch_truncation` event fires from BOTH emitters when `stop_reason in {"max_tokens", "model_context_window_exceeded"}`. Includes `feature`, `stop_reason`, `model`, and `effort` fields at minimum.
- **ADDED**: New exact-key-list test for `dispatch_complete` events in `test_dispatch_instrumentation.py` (no such test existed before).
- **MODIFIED**: `dispatch_task` docstring effort vocabulary expanded from `"low", "medium", "high", "max"` to `"low", "medium", "high", "xhigh", "max"` with a note that `xhigh` is Opus-4.7-only.
- **MODIFIED**: `claude-agent-sdk` dependency in `pyproject.toml` pinned to a specific version range (was unconstrained per Adversarial §5).
- **ADDED**: `_stubs.py:ResultMessage` gains `stop_reason: str | None = None` as the LAST dataclass field; mirrors any other new fields in the upgraded SDK.
- **ADDED**: New regression tests `test_effort_value_passthrough`, `test_sdk_parser_extracts_stop_reason`, `test_effort_matrix_policy`, `test_effort_skill_overrides`, `test_dispatch_complete_exact_key_list`, plus the two truncation-event tests covering both emitters.

## Technical Constraints

### 1. Effort policy table (the matrix)

| (complexity, criticality) | Resolved model (per `_MODEL_MATRIX`) | Effort (new) | Effort (current) |
|---|---|---|---|
| (trivial, low) | haiku | low | low |
| (trivial, medium) | haiku | low | low |
| (trivial, high) | sonnet | high | low |
| (trivial, critical) | sonnet | high | low |
| (simple, low) | sonnet | high | medium |
| (simple, medium) | sonnet | high | medium |
| (simple, high) | sonnet | high | medium |
| (simple, critical) | sonnet | high | medium |
| (complex, low) | sonnet | high | high |
| (complex, medium) | sonnet | high | high |
| (complex, high) | opus | xhigh | high |
| (complex, critical) | opus | xhigh | high |

Rows that change effort: 8 of 12.

### 2. Skill-based effort overrides (applied after matrix lookup, gated on resolved model == "opus")

| Skill | Effort override | Applies when |
|---|---|---|
| review-fix | max | Resolved post-`model_override` model is opus; otherwise matrix value applies |
| integration-recovery | max | Resolved post-`model_override` model is opus. The dispatch site at `integration_recovery.py:215–225` forces `model_override="opus"` (Req #3a), so this override fires reliably for every integration-recovery dispatch. |

`model` in `resolve_effort(complexity, criticality, skill, model)` is the *effective* model — i.e., `model_override` (passed by callers like `merge_recovery.py` and `conflict.py`) takes precedence over `_MODEL_MATRIX` resolution before the override gate is evaluated.

All other skills (`implement`, `review`, `conflict-repair`, `merge-test-repair`, `brain`) use the matrix value with no override.

**Coverage note**: `requires_review()` (`common.py:322`) returns true for `(complex, *) OR (*, high|critical)` — six cells trigger review. Of these, only `(complex, high)` and `(complex, critical)` resolve to Opus; the remaining four resolve to Sonnet. So the `review-fix → max` override fires for ~25% of review-fix dispatches in practice. Operators reading aggregate cost metrics should account for this when interpreting per-skill cost shape.

### 3. Effort-vocabulary support per model

| Model | Supported effort levels |
|---|---|
| haiku | low, medium, high (xhigh/max unverified — assume not supported) |
| sonnet | low, medium, high, max (xhigh NOT supported — silently downgrades) |
| opus 4.7 | low, medium, high, xhigh, max |

The matrix and overrides are designed so no cell + override combination requests `xhigh` on a non-Opus model. Implementation must include a runtime guard: an `assert` in `resolve_effort` that raises `AssertionError` when an unsupported effort value would be returned for the resolved model. The assertion failure surfaces at dispatch time, not silently — the existing dispatch error path handles it as a feature-level pause.

### 4. SDK upgrade

- Current pin: `claude-agent-sdk` (unconstrained — verify in `pyproject.toml`); installed version is `0.1.41` per `uv.lock`.
- Required: a version where `ResultMessage` exposes `stop_reason: str | None` AND `_internal/message_parser.py` extracts it from CLI JSON. Per Reviewer 1 investigation, `stop_reason` was added by SDK v0.1.46 (PR #718); 30 releases exist between 0.1.41 and current latest (v0.1.71), so the implementation must choose a stable version `>=0.1.46` that passes the full test suite.
- Note: `ClaudeAgentOptions.effort` typing for `xhigh` is NOT yet shipped in any released SDK (PR #835 unmerged as of 2026-04-29). The runtime contract test (Req #10) covers passthrough only — the SDK accepts `xhigh` as an opaque string and forwards `--effort xhigh` to the CLI subprocess. CLI binary acceptance of `xhigh` is verified empirically post-flip via the truncation observability stack.
- Pin the SDK version range in `pyproject.toml` so a silent SDK upgrade cannot blindside production.
- The parser-extraction acceptance test (Req #6, third bullet) is the load-bearing gate: if the upgraded SDK's parser drops `stop_reason`, this test fails and merge is blocked until a wrapper/extractor is added or a different SDK version is chosen.

### 5. Event-log key invariants

- `dispatch_complete` events MUST include `stop_reason` (string or null) regardless of emitter (`dispatch.py` ResultMessage handler OR `runner.py:_emit_orchestrator_round_telemetry`).
- `dispatch_truncation` events MUST include at minimum `feature`, `stop_reason`, `model`, `effort`. Snake_case for all keys per existing convention.
- The new exact-key-list test for `dispatch_complete` (Req #9) asserts the key set; both emitters must satisfy it.

### 6. Test surface

- New unit tests in `cortex_command/pipeline/tests/test_dispatch.py`:
  - `test_effort_matrix_policy` — iterates all 12 matrix cells.
  - `test_effort_skill_overrides` — exercises review-fix AND integration-recovery on opus and on sonnet.
  - `test_effort_value_passthrough` — passes each effort value through `ClaudeAgentOptions` and asserts CLI argv propagation.
  - `test_sdk_parser_extracts_stop_reason` — feeds a canned CLI JSON line containing `"stop_reason": "max_tokens"` to the SDK parser and asserts extraction.
- New unit tests in `cortex_command/pipeline/tests/test_dispatch_instrumentation.py`:
  - `test_max_tokens_truncation_emits_dispatch_truncation_event_via_dispatch_task` — SDK path.
  - `test_dispatch_complete_exact_key_list` — exact key set assertion for `dispatch_complete` (no such test exists today).
- New unit test in `cortex_command/overnight/tests/test_orchestrator_round_telemetry.py`:
  - `test_max_tokens_truncation_emits_dispatch_truncation_event_via_orchestrator_round` — runner.py path.
- Existing tests/fixtures that hardcode effort values must update in lockstep:
  - `cortex_command/pipeline/tests/test_metrics.py` — lines 74, 837, 966, 986 (the `_start` helper-generated events).
  - `cortex_command/pipeline/tests/test_dispatch_instrumentation.py` — the `expected_with_cycle` / `expected_without_cycle` `dispatch_start` key lists at lines 287/302 (these are NOT the dispatch_complete lists; the new exact-key-list test is added separately).
  - `cortex_command/pipeline/tests/fixtures/dispatch_since_boundary.jsonl` — lines 1, 3, 5 use `(simple, low) sonnet effort=low`; under the new matrix this cell maps to `effort=high`. Update to match.
  - `cortex_command/pipeline/tests/fixtures/dispatch_over_cap.jsonl` — lines 1, 3, 5, 7 use `(complex, high) opus effort=high`; under the new matrix this maps to `effort=xhigh`. Update to match.
  - The `_start` helpers in `test_metrics.py:65–77` and `test_metrics.py:827–843` — convert to compute effort via `resolve_effort(complexity, criticality, skill, model)` rather than hardcoding `"high"`, so future fixture-vs-matrix consistency is preserved.

### 7. Documentation

- `docs/sdk.md` — primary destination per project convention. Owner of SDK model-selection mechanics. Add the matrix + override tables, the ~25% review-fix-on-Opus coverage note, and link from overnight-operations.md.
- `docs/overnight-operations.md` — add the rationale section (Anthropic guidance citation, #089 closure citation, adaptive-thinking framing) AND the post-flip rollback monitoring procedure now that `metrics.py` buckets by effort (per Req #13): how to query `(model, tier, skill, effort)` aggregates from `metrics.json`, what threshold triggers human investigation, and the rollback path.

## Open Decisions

None. All three Critical Review Ask items are resolved:
- **xhigh runtime contract test design**: Resolved as passthrough+CLI-argv test (Req #10). Tightening to a typed-Literal assertion is a follow-up ticket once SDK PR #835 merges.
- **integration-recovery override firing**: Resolved by adding `model_override="opus"` at the dispatch site (Req #3a) — the override now fires reliably in production.
- **Cost regression observability**: Resolved by extending `metrics.py` to bucket by `(model, tier, skill, effort)` in this ticket (Req #13) — closes the structural gap before the post-flip risk window.
