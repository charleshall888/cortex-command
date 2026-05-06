# Research: Instrument skill-name on dispatch_start for per-skill pipeline aggregates

## Epic Reference

Background context only — do not reproduce: `research/extract-scripts-from-agent-tool-sequences/research.md` (parent epic 101, observability floor section). Epic 101 ranks 15 script-extraction candidates (C1–C15); ticket 104 produces the per-skill cost data needed to rank pipeline-side candidates (C8, C9 in particular) and validate post-ship ROI for anything the pipeline dispatches. This research is scoped to ticket 104 only.

## Clarified Intent (carried from §4)

Add a `skill` parameter to `dispatch_task` (`cortex_command/pipeline/dispatch.py`) so the `dispatch_start` event in `lifecycle/pipeline-events.log` records which call-site originated each sub-agent dispatch, using caller-named string constants typed as `Literal[...]`. Extend `cortex_command/pipeline/metrics.py` with a `(skill, tier)` aggregator over `pipeline-events.log` and a new `--report skill-tier-dispatch` CLI mode.

**Locked in §4**:
- Aggregator data source: `pipeline-events.log` (NOT `agent-activity.jsonl`).
- Skill vocabulary: caller-named string constants typed as `Literal[...]`; each call site passes an explicit string.

## Codebase Analysis

### Dispatch_task call sites and proposed skill assignments

| File:Line | Context | Proposed skill | Notes |
|-----------|---------|----------------|-------|
| `cortex_command/overnight/feature_executor.py` (via `retry_task` → `retry.py:240`) | Per-task implement dispatch | `implement` | Pass-through via retry layer |
| `cortex_command/pipeline/retry.py:240` | Generic retry wrapper | *pass-through from caller* | Adds `skill` param, forwards unchanged |
| `cortex_command/pipeline/review_dispatch.py:252` | Initial review agent | `review` | First-pass review against spec |
| `cortex_command/pipeline/review_dispatch.py:383` | Cycle-1 fix dispatch (after CHANGES_REQUESTED) | `review-fix-cycle1` | **See Open Questions: collapse cycle into sibling field?** |
| `cortex_command/pipeline/review_dispatch.py:496` | Cycle-2 review re-pass | `review-fix-cycle2` | **See Open Questions** |
| `cortex_command/pipeline/conflict.py:328` | Merge-conflict repair (Sonnet, may escalate to Opus) | `merge-repair` | **See Open Questions: rename for clarity?** |
| `cortex_command/pipeline/merge_recovery.py:332` | Post-integration test-failure repair | `test-repair` | **See Open Questions: rename for clarity?** |
| `cortex_command/overnight/integration_recovery.py:216` | Integration-branch failure CLI | `integration-recovery` | Standalone CLI, not retry-wrapped |
| `cortex_command/overnight/brain.py:224` | Post-retry triage (skip/defer/pause decision) | `brain` | **See Open Questions: N=1/run cardinality concern** |

**Single emission point confirmed**: `dispatch_start` is emitted only at `dispatch.py:446`. All seven (`feature_executor`, `retry`, `conflict`, `review_dispatch`, `merge_recovery`, `integration_recovery`, `brain`) callers route through `dispatch_task`. Editing the single emission point captures every pipeline sub-agent dispatch.

### Existing tier-dispatch aggregator (the mirror target)

- `compute_model_tier_dispatch_aggregates()` — `metrics.py:442` — groups paired dispatch records by `(model, tier)`; ~165 lines.
- `_format_tier_dispatch_report()` — `metrics.py:890–1016` — produces the human-readable report.
- argparse choice — `metrics.py:1042–1046` — `--report` accepts `choices=["tier-dispatch"]`.
- Conditional print — `metrics.py:1118–1121`.
- p95 suppression — `metrics.py:534–541` — suppresses p95 when `n_completes < 30`.
- Untiered sentinel — `metrics.py:496–497` — uses `"unknown"` for unbucketed records. **The new aggregator must NOT collide with this sentinel** when bucketing missing-skill historical events (see Open Questions).

**Reusable helpers**:
- `discover_pipeline_event_logs()` (`metrics.py:270`) — finds all `pipeline-events.log` files.
- `parse_events()` (`metrics.py:75`) — JSONL parsing with malformed-line tolerance.
- `filter_events_since()` (`metrics.py:104`).
- `pair_dispatch_events()` (`metrics.py:312–439`) — FIFO pairs `dispatch_start` ↔ `dispatch_complete`/`dispatch_error` per feature. **Only emits a paired record when a terminal event is seen** — orphaned starts (crashed dispatches) sit in `unmatched_starts` forever and are silently dropped from `paired`. The new aggregator inherits this blind spot.
- `TIER_CONFIG` import from dispatch.py for budget/turn cap lookups.

### Recommended new-aggregator shape: parallel function

`compute_skill_tier_dispatch_aggregates(paired: list[dict]) -> dict[str, dict]` mirroring `compute_model_tier_dispatch_aggregates()` but grouping by `(skill, tier)`. Bucket keys formatted as `"<skill>,<tier>"`. Computed alongside the existing aggregator in `main()` (around `metrics.py:1071–1082`); both included in the output JSON and both available via the CLI `--report` flag.

Rationale for parallel-function over parameterized-existing or generic-refactor: the existing function is 165 lines of complex grouping/stats; refactoring opens a regression surface for marginal code savings. Mirror is a known-good pattern; epic 101 can demand a generic refactor later when 3+ aggregators exist.

### `dispatch_start` event shape (dispatch.py:445–454)

```json
{"event": "dispatch_start", "feature": ..., "complexity": ..., "criticality": ..., "model": ..., "effort": ..., "max_turns": ..., "max_budget_usd": ...}
```

**Proposed `skill` placement**: after `"feature"`, before `"complexity"`. Python dict insertion order is the JSONL key order, but downstream consumers (dashboard) parse by name, not position — confirmed by `requirements/observability.md` schema-agnostic acceptance criteria and the absence of any positional parsing in `cortex_command/`.

### `Skill` Literal placement

Top of `dispatch.py` after imports (around line 40, after logger). Existing convention places dataclasses (`DispatchResult`), constants (`TIER_CONFIG`, `EFFORT_MAP`, `ERROR_RECOVERY`, `MODEL_ESCALATION_LADDER`), and frozensets (`_VALID_CRITICALITY`) at module scope. No `*_types.py` module exists in `pipeline/`; module-scope is the natural home.

### `state.log_event` signature

`log_event(path: Path, event_dict: dict)` accepts an arbitrary dict and writes JSONL (one JSON line appended). Already used by dispatch.py for `dispatch_start`/`dispatch_progress`/`dispatch_complete`/`dispatch_error`. No signature change required.

### Test surface

- `cortex_command/pipeline/tests/test_metrics.py:54–287` — `TestPairDispatchEvents` class uses synthetic `_start()`/`_complete()`/`_error()`/`_progress()` helper methods (no fixture files).
- Mirror plan: extend `_start()` to accept `skill` kwarg (default `"implement"`); add `TestSkillTierDispatchAggregates` class testing single bucket, multi-bucket grouping, orphaned starts/completes, p95 suppression. Add CLI test for `--report skill-tier-dispatch`.
- Signature changes to `dispatch_task` (new required kwarg) belong in `cortex_command/pipeline/tests/test_dispatch.py` and `test_dispatch_instrumentation.py`.

## Web Research

### Caller-tagging conventions (OTel / Datadog)

Both standardize a low-cardinality logical-operation name vs a high-cardinality instance name:
- **OTel**: `span.name` = `{verb} {object}` (e.g., `process payment`); `code.function.name` = physical call site.
- **Datadog**: `operation_name` (low-cardinality, group-by; e.g., `http.request`) vs `resource_name` (high-cardinality instance; e.g., `GET /productpage`).

`skill` maps to operation_name; `feature` maps to resource_name. Avoid generic field names like `caller` (implies actor lineage, which is parent-span semantics, not operation semantics).

### Closed Literal enum vs free-string

Closed enum is the right choice when the producer is in the same repo (mypy/pyright catches drift at type-check). Free-string fragmentation modes seen in practice: case drift (`Review` vs `review`), separator drift (`code-review` vs `code_review`), synonym drift (`pr-review` vs `code-review`) — all eliminated by Literal typing. **Reject the hybrid "closed enum + escape-hatch `other` value with free-text `skill_detail`" pattern** — it defeats the closed-vocabulary guarantee.

### Aggregation join-key patterns

OTel Span Metrics Connector pairs on stable correlation ID (span_id-equivalent) and emits R.E.D. metrics (Requests / Errors / Duration). Orphan-handling patterns: timeout-based eviction, synthetic complete with `status=orphaned`, or surface as a separate `null`-cost row. Cardinality circuit-breaker (`aggregation_cardinality_limit`) is also standard.

### CLI report design

- Composable (`--group-by skill,tier`) follows clig.dev / AWS Cost Explorer conventions — scales gracefully as dimensions multiply.
- Named-mode (`--report skill-tier-dispatch`) is more discoverable but combinatorial — every new dimension doubles the mode count.
- Pragmatic middle: keep current named reports as **presets** that internally desugar to `--group-by`. (git log `--pretty=oneline` pattern.)
- Ticket 104 specifies named-mode; user confirmed in §4. Sticking with named-mode for this ticket; flag for revisit if `--report` choices grow past 5.

### Vocabulary management

OTel guidance: prefer **local consistency** over global. Inside one repo: `{verb}-{object}` (kebab), singular nouns, no version suffixes, no IDs. Drift mitigations: lint rule rejecting new string literals outside the canonical enum module; periodic vocab audit (Levenshtein < 3). For a closed Literal, mypy is the lint.

### Key sources

- OpenTelemetry Span Naming spec
- Datadog Span Tag Semantics
- ClickHouse `LowCardinality` vs `Enum` guide
- clig.dev Command Line Interface Guidelines
- OTel Span Metrics Connector README

## Requirements & Constraints

### `requirements/pipeline.md` — Metrics & Cost Tracking (lines 97–108)

> **Inputs**: `lifecycle/*/events.log` (JSONL event streams per feature)
> **Outputs**: `lifecycle/metrics.json` with per-feature metrics, tier aggregates, and calibration summaries
> Tier aggregates: mean duration, task count, batch count, rework cycles, and approval rate per tier (simple / complex)

The requirements doc names per-feature `events.log` — not `pipeline-events.log` — as the input. Existing `model_tier_dispatch_aggregates` already extends beyond the doc by reading `pipeline-events.log`. Adding `(skill, tier)` aggregates is a coherent extension of existing capability, not a literal alignment with documented text. Acceptance criteria do not forbid schema additions.

### `requirements/pipeline.md:129` — Audit trail invariant

`pipeline-events.log` is **append-only JSONL**. New `skill` field is forward-compatible if readers handle missing key gracefully. Historical events lack `skill` — bucketing decision required (see Open Questions).

### `requirements/observability.md:30–34` — Dashboard cost tracking

Dashboard's incremental cost-tracking input is **`agent-activity.jsonl`**, NOT `dispatch_start`. The dashboard reads `pipeline-events.log` for status/badges but has no documented dependency on `dispatch_start` field shape. Adding `skill` to `dispatch_start` is safe for the dashboard subsystem.

### `requirements/multi-agent.md`

No documented "skill" vocabulary. No central registry. Ticket 104 establishes the first canonical list.

### `docs/pipeline.md` & `docs/overnight-operations.md`

Both documents reference `dispatch_start` as an event emitted to `pipeline-events.log` but do not enumerate its fields. Adding `skill` requires updating any doc that lists the event keys (grep needed at spec time).

### Parent epic 101

104 sits in wave-1 (S-effort, parallel with 102 and 103). Epic identifies 15 script-extraction candidates (C1–C15); 104 produces the data needed to rank C8/C9 (pipeline-side candidates) and validate post-ship ROI. Epic does not enforce a canonical skill list — caller-named is acceptable.

### Architectural constraints

1. Append-only JSONL: schema additions are forward-compatible; never modify historical events.
2. Caller-named vocabulary: no central registry; each call site owns its skill string.
3. Dashboard independent: no dashboard changes required.
4. File-based: pure file I/O, no database.

## Tradeoffs & Alternatives

### Skill argument shape

| Option | Tradeoff | Verdict |
|--------|----------|---------|
| Required positional | Atomic update; positional args are fragile at call site | Rejected (less readable) |
| Required kwarg | Atomic update; explicit at call site | **Recommended** for end state |
| Optional kwarg with default `None` | Gradual rollout; risk of silent miss | **Recommended for initial ship** then flip to required (see Open Questions for in-flight crash mitigation) |

### Aggregator implementation

| Option | Tradeoff | Verdict |
|--------|----------|---------|
| Parallel function | Mirror is safe; 165 lines duplicated | **Recommended** |
| Parameterize existing | Smaller diff; refactor risk on complex function | Rejected (regression surface too wide for marginal gain) |
| Generic refactor | Best long-term; over-engineering for one new aggregator | Defer to epic-101 horizon when 3+ aggregators exist |

### Retry plumbing

Pass-through (retried = caller's skill). Retry attempts share the caller's identity in the aggregator (e.g., all "implement" attempts including escalations roll into one bucket). **Caveat surfaced by adversarial review**: retry escalation (Sonnet → Opus per `retry.py:212`) means an Opus dispatch may be either organic-Opus or escalated-Opus. Without an `attempt`/`escalated` field on `dispatch_start`, the aggregator cannot disentangle them. See Open Questions.

### CLI flag style

Named-mode `--report skill-tier-dispatch` as user-locked in §4. Revisit composable `--group-by` if `--report` choices grow past 5.

### Test placement

- Signature changes to `dispatch_task` → `test_dispatch.py` and `test_dispatch_instrumentation.py`.
- Aggregator + CLI tests → extend `test_metrics.py` with new `TestSkillTierDispatchAggregates` class (mirror `TestPairDispatchEvents`).

## Adversarial Review

### Failure modes confirmed

1. **Retry escalation collapses load-bearing distinctions**. Pass-through `skill="implement"` puts first-try Opus and Sonnet→Opus escalation in the same `(implement, opus)` bucket. Per-skill cost reports will overstate organic-Opus share. The `retry_attempt` event (`retry.py:230–292`) carries attempt number but `dispatch_start` will not — aggregator can't disentangle. See Open Questions for `attempt`/`escalated` stamp decision.

2. **Brain dispatches at N=1 per overnight run**. A `(skill=brain, tier=simple)` bucket has trivial sample size. Mean/median noise; the existing `n_completes < 30` p95 suppression (`metrics.py:534–541`) helps but mean and max still print. Most `(skill, model, tier)` cells will sit at N=1–3 across a single overnight run. **Acceptable**: per-skill aggregates are meant for cross-session cumulative analysis (parent epic 101 ROI ranking), not single-session inference.

3. **Orphan dispatch_start events dropped silently**. `pair_dispatch_events()` only emits paired records when a terminal event is seen. Crashed/killed dispatches sit in `unmatched_starts` forever, never reaching `paired`. Existing aggregator has this bug; new aggregator inherits it. **Out of scope for 104**: orphan-handling fix should be a separate ticket; document the gap in the report header.

4. **Idempotency-skipped tasks** (`feature_executor.py:574–585`) emit `task_idempotency_skip` with no `dispatch_start` — under-counts work-attributable-to-implement vs `task_*` event count. Probably correct (no real spend) but document divergence.

### Anti-patterns rejected

- Hybrid "Literal + escape-hatch `other` + free-text `skill_detail`" — defeats closed-vocabulary guarantee.
- Free-string fallback for missing-skill events bucketed as `"unknown"` — collides with existing untiered sentinel at `metrics.py:496–497`. Use `"legacy"` or `"<missing>"` instead.

### Assumptions challenged

- "Single PR atomicity" assumes all 8 call sites land in one merge. **In a worktree-based overnight pipeline, an in-flight session that started before the merge keeps running with the old code path.** If that session's dispatched agents call into a refactored module expecting the new required kwarg, the running session crashes mid-feature with `TypeError: dispatch_task() missing 1 required keyword-only argument: 'skill'`. Blast radius: feature aborts, retry exhausts, brain marks paused. **Mitigation**: ship with `skill: Skill | None = None` for one release (or one clean overnight cycle), then flip to required.

- "review-fix-cycle1 / review-fix-cycle2 as distinct skills" — cycle is metadata, not identity. Aligns with OTel operation_name vs attribute split. **Recommended**: collapse to single `skill="review-fix"` with sibling `cycle: int` field.

- "merge-repair vs test-repair" — `merge_recovery.py:332` is the test-repair caller; `conflict.py:328` is merge-repair. A reader expects "merge-repair" to live in the merge-recovery module. Rename to disambiguate context-vs-action (e.g., `conflict-repair` and `merge-test-repair`).

### Recommended mitigations (folded into Open Questions where consequential)

- Runtime guard at `dispatch.py:446`: `assert skill in get_args(Skill)` to catch typos that mypy missed (defense-in-depth).
- Stamp `attempt` and `escalated` on `dispatch_start` so the aggregator can split organic-Opus from escalated-Opus.
- Document the orphan blind spot in the new report header; file a separate ticket to fix `pair_dispatch_events()`.
- Bucket missing-`skill` historical events as `"legacy"`, not `"unknown"`.
- Reject `"other"` escape hatch; rely on closed Literal + mypy.
- Document idempotency-skip vs dispatch-count divergence in `pipeline.md` or report header.

Grounding cites: `cortex_command/pipeline/dispatch.py:444–454, 540–587`; `cortex_command/pipeline/retry.py:212, 230–292`; `cortex_command/pipeline/metrics.py:299, 312–439, 442–561`; `cortex_command/overnight/feature_executor.py:574–585`; `cortex_command/overnight/brain.py:224–232`; `cortex_command/pipeline/review_dispatch.py:252, 383, 496`.

## Open Questions

These are spec-time decisions that affect what gets built. Each must be resolved (or explicitly deferred) before transitioning to Plan.

- **Q1 — Skill rollout shape**: Ship `skill` as required kwarg from day 1, OR ship as optional (default `None`) and flip to required after one clean overnight cycle? Tradeoff: required-from-day-1 is cleaner but risks `TypeError` for in-flight overnight sessions; optional-then-required is safer but leaves a window where missing-skill events are produced. *Deferred: will be resolved in Spec by asking the user.*

- **Q2 — Cycle modeling for review-fix**: Use distinct skills `review-fix-cycle1` and `review-fix-cycle2`, OR collapse to single `review-fix` skill with sibling `cycle: int` field on `dispatch_start`? Adversarial recommends the collapsed form (matches OTel operation/attribute split, prevents N=1 dilution). *Deferred: will be resolved in Spec by asking the user.*

- **Q3 — Naming clarity for repair skills**: Keep `merge-repair` (`conflict.py:328`) and `test-repair` (`merge_recovery.py:332`), OR rename to disambiguate context-vs-action (e.g., `conflict-repair`, `merge-test-repair`)? *Deferred: will be resolved in Spec by asking the user.*

- **Q4 — Stamp `attempt`/`escalated` on `dispatch_start`**: Should this ticket also add `attempt: int` and `escalated: bool` fields to `dispatch_start` so the aggregator can disentangle organic-Opus from escalated-Opus dispatches under a pass-through skill? Adds scope; arguably required for the per-skill aggregate to be meaningful. *Deferred: will be resolved in Spec by asking the user — possibly carved into a follow-up ticket.*

- **Q5 — Bucket name for missing `skill` in historical events**: Use `"legacy"`, `"<missing>"`, drop them entirely, or surface as a separate report section? Cannot use `"unknown"` (collides with `metrics.py:496–497` untiered sentinel). *Deferred: will be resolved in Spec by asking the user.*

- **Q6 — Runtime `assert skill in get_args(Skill)` guard**: Add defense-in-depth at `dispatch.py:446` to catch typos that mypy missed, OR rely solely on type-check at CI time? Tradeoff: extra runtime cost (negligible) vs failing-loudly on invalid skill at dispatch time. *Deferred: will be resolved in Spec by asking the user.*

- **Q7 — Orphan dispatch_start handling**: This research confirmed the existing `pair_dispatch_events()` silently drops crashed dispatches. **Out of scope for 104** (separate ticket needed). Flag for backlog. *Deferred: file as a new backlog item; do not block 104 on this.*

- **Q8 — Idempotency-skip / dispatch-count divergence**: Report header should document that idempotency-skipped tasks (no `dispatch_start`) under-count vs `task_*` events. Spec decision: where does this disclosure live (report header, pipeline.md, both)? *Deferred: will be resolved in Spec.*
