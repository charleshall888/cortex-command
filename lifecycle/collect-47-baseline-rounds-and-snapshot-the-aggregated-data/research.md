# Research: Collect 4.7 baseline rounds and snapshot the aggregated data

> Generated: 2026-04-20. Lifecycle slug: `collect-47-baseline-rounds-and-snapshot-the-aggregated-data`. Tier: complex. Criticality: high.

## Epic Reference

This ticket is a child of epic [#082 Adapt harness to Opus 4.7](../../backlog/082-adapt-harness-to-opus-47-prompt-delta-capability-adoption.md). Epic research at [`research/opus-4-7-harness-adaptation/research.md`](../../research/opus-4-7-harness-adaptation/research.md) — specifically DR-3 and DR-4 — is the motivating decision record. DR-4 establishes the ordering discipline: "(1) ship 4.7 with existing prompts → (2) collect 2–3 rounds of baseline data → (3) only then ship Wave-1 prompt changes → (4) revisit matrix recalibration decision." This ticket is step 2. The snapshot artifact at `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` gates #092 (Wave-1 scaffolding removal) and is a comparison anchor for #090 (Wave-2 xhigh adoption).

## Clarified Intent

Run 2–3 overnight rounds on Claude 4.7 with prompts frozen (no prompt changes during the measurement window), execute `#087`'s tier-dispatch aggregator via `--since <window-start-date>` over that window, and commit a baseline snapshot markdown at `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` containing per-(model, tier) mean/p95 `num_turns`, mean/max `cost_usd`, and escalation frequency by error type. The rate-limit field is dropped (#087 Non-Requirement #2 explicitly excludes throttle_backoff aggregation; zero such events exist in the corpus). Snapshot feeds #092 and #090 per DR-4 ordering discipline.

## Codebase Analysis

### #087 aggregator — production-ready, 1:1 fit with ticket

`claude/pipeline/metrics.py:442` defines `compute_model_tier_dispatch_aggregates(paired)`. Output schema written to `lifecycle/metrics.json` under top-level key `model_tier_dispatch_aggregates`:

```
"<model>,<tier>": {
  "n_completes": int, "n_errors": int,
  "num_turns_mean": float|null, "num_turns_median": float|null,
  "num_turns_p95": float|null,          # only when n_completes ≥ 30
  "max_turns_observed": int|null,       # when 0 < n_completes < 30
  "p95_suppressed": bool,
  "estimated_cost_usd_mean": float|null, "estimated_cost_usd_median": float|null, "estimated_cost_usd_max": float|null,
  "budget_cap_usd": float|null, "over_cap_rate": float|null, "turn_cap_observed_rate": float|null,
  "error_counts": {"<error_type>": int, ...},
  "is_untiered": bool
}
```

CLI: `python3 -m claude.pipeline.metrics --since YYYY-MM-DD --report tier-dispatch`. The `--since` flag is the mechanism for carving the post-4.7 baseline window (`claude/pipeline/metrics.py:1042`). Writes JSON atomically via tempfile + `os.replace()` (`metrics.py:1104–1114`). When `--since` is used, `model_tier_dispatch_aggregates_window` is also emitted with window metadata (`metrics.py:1093–1097`). The human-readable table is formatted by `_format_tier_dispatch_report()` at `metrics.py:890`.

**No code changes to #087 required by #088 to produce the snapshot.**

### Event emission surface (the bare-model-name finding)

`claude/pipeline/dispatch.py:118–122` defines `TIER_CONFIG` with bare family names as the `model` key:

```python
TIER_CONFIG = {
    "trivial": {"model": "haiku", "max_turns": 15, "max_budget_usd": 5.00},
    "simple":  {"model": "sonnet", "max_turns": 20, "max_budget_usd": 25.00},
    "complex": {"model": "opus",   "max_turns": 30, "max_budget_usd": 50.00},
}
```

`dispatch_start` events emit this bare family name (`dispatch.py:444–452`). `dispatch_complete` records `feature`, `cost_usd`, `duration_ms`, `num_turns` but **does not capture `ResultMessage.model`** — the resolved version ID (e.g. `claude-opus-4-7-20260501`) is never persisted. `claude/settings.json:221` sets `"model": "opus[1m]"` at the session level, also unversioned.

All three existing session pipeline-events.log files confirm this: `"model": "sonnet"` or `"model": "haiku"`, no version suffix. Two of the three sessions (2026-04-01, 2026-04-07) predate ticket #088's creation date (2026-04-18) and cannot be honestly relabeled as a "4.7 baseline by intent."

### Overnight round boundary surface

`claude/overnight/events.py:33,40` defines `ROUND_START` and `ROUND_COMPLETE` event types. Each carries a `"round"` integer (1-based). Rounds live within a larger `SESSION_START…SESSION_COMPLETE` span in `lifecycle/overnight-events.log` (session-specific logs at `lifecycle/sessions/{id}/overnight-events.log`). The pipeline events (`dispatch_start/complete/error`) are in the separate `lifecycle/pipeline-events.log` and `lifecycle/sessions/{id}/pipeline-events.log`. Round boundaries are reconstructable by cross-referencing session IDs and timestamp ranges.

### Downstream consumer paths

- `backlog/092-remove-progress-update-scaffolding-from-long-running-prompts-dr-3-wave-1.md` is blocked by #088's terminal status plus the snapshot file existing at the exact committed path.
- `backlog/090-adopt-xhigh-effort-default-for-overnight-lifecycle-implement.md` is transitively gated via #089 and #092; uses the baseline as measurement context.

### Existing research/opus-4-7-harness-adaptation/ artifacts

`research.md` (epic research), `decomposed.md`, `claude-api-migrate-results.md`, `reference-loading-verification.md`, plus this ticket's lifecycle `events.log`. Convention: ISO-date header, epic reference, specific file:line citations, tables over prose for numeric data. The target file `4-7-baseline-snapshot.md` does not yet exist.

### 4.7 shipping status

Dispatch uses unversioned aliases; whatever Anthropic resolves `opus`/`sonnet`/`haiku` to at dispatch time is what runs. There is no explicit opt-in "we have shipped 4.7" config. The release-window question (exactly when the baseline starts) is therefore a calendar decision keyed to the `--since` date rather than a code-level flag.

## Web Research

### Cost-reporting ground truth

Anthropic docs ([code.claude.com/docs/en/agent-sdk/cost-tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)) explicitly warn that `ResultMessage.total_cost_usd` is a **client-side estimate, not authoritative billing data**: "Do not bill end users or trigger financial decisions from these fields." The baseline snapshot must label cost numbers accordingly. #087's existing field naming (`estimated_cost_usd_*`) already reflects this.

### Baseline statistics: industry standard

Standard practice is mean/median/p90/p95/p99/min/max captured together. The existing `p95_suppressed:true` at n<30 rule matches industry practice (normal-approximation requires n≥30). For prompt-change attribution, n<30 is "directional only, not conclusive" per multiple references (Latitude evaluation guide, Signal-and-Noise framework at arXiv:2508.13144). The overnight round reality (~10–30 dispatches total per round) places this baseline firmly in the directional-only band.

### Claude 4.7 confounders relevant to the baseline

From [platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7](https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7):

1. **New tokenizer produces 1.0–1.35× more tokens than 4.6 for the same text.** Any baseline straddling a 4.6→4.7 transition will show illusory 0–35% cost delta with zero prompt change.
2. 4.7 has "fewer tool calls by default, using reasoning more" and "fewer subagents spawned by default" — both reduce `num_turns` independent of prompt changes.
3. `temperature`/`top_p`/`top_k` now return 400 when non-default. Extended-thinking `budget_tokens` removed (only adaptive supported).
4. Thinking content omitted by default; may appear as illusory cost reduction.

**Implication for the ticket**: the baseline is only meaningful as a *same-version* comparison anchor. Cross-version comparisons (4.6 vs 4.7) are invalid without explicit model-version evidence, which current events.log cannot provide (see the bare-model-name finding above).

## Requirements & Constraints

### From `requirements/project.md`

- **Handoff readiness**: "A feature isn't ready for overnight until the spec has no open questions, success criteria are verifiable by an agent with zero prior context, and all lifecycle artifacts are fully self-contained."
- **Complexity**: "Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."
- **Quality bar**: "Tests pass and the feature works as specced. ROI matters."
- **File-based state**: lifecycle artifacts, backlog, pipeline state all use plain files; no database.

### From `requirements/pipeline.md`

§ Metrics and Cost Tracking (should-have) acceptance criteria: per-feature metrics by tier, tier aggregates (mean duration, task count, batch count, approval rate per tier). Forward-only session phase transitions.

### From `requirements/multi-agent.md`

Model selection matrix: trivial+low→haiku, simple/trivial+high/critical→sonnet, complex+high/critical→opus. Escalation ladder haiku→sonnet→opus on specific error types. Concurrency adaptive 1–3, reduces on rate-limit errors.

### From epic research `research/opus-4-7-harness-adaptation/research.md`

DR-3 (verbatim): "**Wave 1 (gate on DR-4 baseline)**: Remove progress-update scaffolding from long-running prompts (Approach D). **Must not ship until DR-4 has collected 2–3 overnight rounds of clean 4.7 baseline data.** Rationale: this change will shift `num_turns` and `cost_usd` distributions, so shipping it before the baseline contaminates the matrix-validation data DR-4 exists to gather."

DR-4 (verbatim): "Keep matrix as-is. Add a backlog item to instrument turn usage and cost per tier from `events.log`; revisit after 2–3 overnight rounds on 4.7. … the 2–3 baseline rounds **must execute before** any Wave-1 prompt change from DR-3. Explicit ordering: (1) ship 4.7 with existing prompts → (2) collect 2–3 rounds of baseline data → (3) only then ship Wave-1 prompt changes → (4) revisit matrix recalibration decision."

## Tradeoffs & Alternatives

| Alt | Description | Verdict |
|-----|-------------|---------|
| **A** | As-specified: 2–3 fresh overnight rounds with frozen prompts, then run aggregator and commit snapshot. | **Recommended** — only option that matches DR-4's "ordering discipline" literally. |
| **B** | Use the three existing on-disk sessions (2026-04-01, -07, -11) as the baseline. | **Rejected**. Pipeline events emit bare family names only; two of three predate ticket creation; retrospective relabeling falsifies the artifact. |
| **C** | Extend window to 4–5 rounds to cross n=30 and get real p95. | **Rejected**. DR-4 says 2–3 rounds; paired delta comparison (baseline vs post-change) is valid at equal n on both sides. Keep as a contingency only. |
| **D** | Schema: preserve native `(model, tier)` keys vs. collapse to tier-only vs. publish both. | **Preserve (model, tier) primary, add tier-only secondary view if cheap.** Native keys match #087 output. Tier-only loses the dimension the ticket exists to measure (one model changed). Not publishing both is fine given the JSON is embedded. |
| **E** | Commit a new `bin/generate-baseline-snapshot.py` script for reproducibility. | **Rejected**. #092's need is *compare-against-baseline*, not *regenerate-baseline*. The existing `python3 -m claude.pipeline.metrics --since …` CLI already produces the numbers; record that invocation in the snapshot's YAML frontmatter. |
| **F** | Single markdown + JSON sidecar file. | **Rejected**. Creates drift risk. Use one markdown file with an embedded fenced JSON block for machine-parseable access. |
| **G** | Add per-record `ResultMessage.model` capture to `dispatch_complete` as a prerequisite. | **Resolve in Spec.** The adversarial review argues this is effectively blocking for any valid baseline-vs-post-change comparison. ~3-line pipeline change. Out of scope as ticket is currently written but critical to the snapshot's downstream usefulness. See Open Questions. |
| **H** | Attribute the window via date + git SHA in prose/frontmatter only. | **Adopt as fallback if G is not pursued.** Weaker evidence than G; document the limitation plainly. |

## Adversarial Review

The adversarial agent surfaced several findings that the other four agents under-called:

1. **The "frozen prompts" invariant has no enforcement mechanism.** Symlinks from `~/.claude/skills/` → this repo mean prompt edits land instantly with zero deploy step. The rendered system prompt is not captured in `pipeline-events.log`. Any in-flight ticket work the user picks up mid-window mutates the treatment silently. Concrete risk: #067/#068/#069 remediations are complete in this repo, but any *future* in-flight ticket during the baseline window reshapes the prompts DR-4 wants frozen. Git SHA at round start is necessary-but-not-sufficient — it records *state*, not *whether that state applied to the run*.

2. **The bare-model-name confounder is structurally blocking, not aesthetic.** Dispatch events emit `"sonnet"`/`"haiku"`/`"opus"` with zero version suffix. If Anthropic ships a point-release of `claude-opus-4-7` mid-window, the baseline was collected on version A and #092's measurement is collected on version B with no way to detect it from the committed artifact. "Pin SDK version" does not help — the SDK is unchanged while the resolved model weights could shift. The only real fix is capturing `ResultMessage.model` in `dispatch_complete`.

3. **The n<30 "directional only" framing will be ignored in practice.** A reviewer reading `mean num_turns: 12.3` will not mentally carry the caveat. Realistic math: 2–3 rounds × ~5–10 features × few complex+high dispatches = n≈2–6 in the critical bucket. Any "within ±X%" claim at that n is noise. The ticket's acceptance criterion ("non-zero entries per tier that had dispatches") is vacuous — it passes at n=1 and trivially passes with an entire tier absent.

4. **"Run an extra round if anomalous" is a p-hacking gate** unless the anomaly criteria are pre-committed. "Looks weird" as a rejection reason invalidates the statistical legitimacy of the baseline regardless of n.

5. **Downstream unblock rule is undefined.** The ticket's completion criterion is on-disk technicality ("at least 2 overnight rounds, sanity checks pass"), not methodological soundness. Realistic outcome without a stronger gate: #088 closes complete on n=3 per bucket, #092 ships "within-noise, proceed" and we have quietly degraded DR-4 from "gated ordering" to "procedural theater."

6. **Several Agent-4 recommendations are scope creep by the `project.md` rule.** Skip: committed generator script, JSON sidecar. Keep: YAML frontmatter (structured metadata), "directional not conclusive" disclaimer (single line, required). Hypothesis block is nice-to-have, not required.

## Open Questions

1. **Model-version capture (Alternative G)** — Should `dispatch_complete` be extended to persist `ResultMessage.model` (resolved version ID) as a prerequisite for running the baseline? This is a ~3-line change to `claude/pipeline/dispatch.py` that would make the baseline-vs-post-change comparison methodologically sound. Without it, the snapshot must be explicitly labeled "directional only; model version not evidence-captured." **Deferred to Spec — this is a scope-gate question: is #088 a bigger ticket than it looks, or does it ship with the weaker-evidence caveat?**

2. **Frozen-prompts enforcement** — Do we hash `skills/` + `claude/reference/` at `ROUND_START` and disqualify rounds where the hash changes mid-window, or do we rely on the user's voluntary discipline? If we do add a hash mechanism, that is in-scope extra work that the ticket text does not currently cover. **Deferred to Spec.**

3. **Pre-committed anomaly criteria for "clean round"** — What exactly disqualifies a round? Proposed objective criteria (Spec should confirm or revise): (a) `api_rate_limit` error count > 0 in round; (b) fewer than N dispatches completed; (c) session terminated abnormally (detected in overnight-events.log). Must be written into the snapshot's YAML frontmatter *before* any round runs. **Deferred to Spec.**

4. **Minimum-viability rule for "baseline adequate"** — What's the objective bar for #088 to close `complete` and unblock #092? Proposed threshold (Spec should confirm or revise): complex+high bucket has n ≥ 5 dispatches across ≥ 2 clean rounds; tokenizer/model-ID evidence captured or explicit limitation noted. If unmet after 3 rounds, escalate the decision rather than close on technicality. **Deferred to Spec.**

5. **`--since` window-start date** — What exact ISO date marks "post-4.7" for the window? Since dispatch events emit unversioned model aliases, this is a calendar decision the user picks at snapshot time (most likely the day the frozen-prompts measurement window begins). **Deferred to Spec — operational question with no codebase-discoverable answer.**

6. **Schema granularity in the snapshot** — Preserve `(model, tier)` only (recommended), add a tier-only collapsed secondary table, or publish both? The ticket text says "per-tier" but #087 outputs `(model, tier)`. **Resolved: preserve native `(model, tier)` primary; tier-only collapse is not needed since JSON is embedded and readers can aggregate.** Spec may revise if #092's consumer logic needs tier-only.

7. **Schema evolution resilience** — Embedded JSON fence in the markdown vs. sidecar file vs. prose-only tables. **Resolved: single markdown file with embedded fenced JSON block containing the raw `model_tier_dispatch_aggregates` dict. Rejects drift risk of a sidecar.**
