---
schema_version: "1"
uuid: d744219f-a0b8-4eff-ac7f-62fda2847a3b
title: "Clean up events.log emission and reader discipline"
type: feature
status: open
priority: high
parent: 187
blocked-by: []
tags: [events-log, emission-discipline, escalations, clarify-critic, token-efficiency]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/lifecycle-discovery-token-audit/research.md
---

# Clean up events.log emission and reader discipline

## Problem

The events.log model has accumulated three distinct flavors of waste, plus a discipline gap that lets the waste continue accumulating:

- **Dead emissions** — ~10 event types are emitted by skill prompts (Claude follows JSONL-emit instructions in `skills/lifecycle/references/orchestrator-review.md`, `specify.md`, `review.md`, `skills/lifecycle/SKILL.md`, etc.) but have zero non-test Python consumers verified across `cortex_command/`, `bin/`, `hooks/`. `orchestrator_review` alone: 304 emissions × ~250 chars = ~76 KB write-only ceremony. The consumer-side `requirements_updated` scan at `skills/morning-review/references/walkthrough.md:303` is part of the same dead-event lifecycle.
- **`clarify_critic` payload accumulation** — 94+ rows in archive, avg ~1,969 chars, ~500 tok per future feature. Zero Python consumers verified. Audit (`research/lifecycle-discovery-token-audit/research.md`) and #172 both flagged this; #172 deferred remediation.
- **`escalations.jsonl` unbounded re-inline** — `cortex_command/overnight/orchestrator_context.py:23, 62-75` fully concatenates the file into `ctx["all_entries"]` every orchestrator round. Linear growth per session. The sole reader at `cortex_command/overnight/prompts/orchestrator-round.md:54-61` uses this only to filter prior resolutions per-feature.
- **Discipline gap** — emissions get added by 1-line skill-prompt edits with no consumer-declaration requirement. Audits add up dead types over time (~49 in the prior #172 audit, ~10 more in this one). The asymmetry is structural: emission is cheap, proving-no-consumer is repo-wide grep.

## Why it matters

Going-forward token cost (~500 tok/feature for clarify_critic + ~50 tok/round-of-emission for dead-events × all skill phases) is real but secondary. The structural concern is that without a discipline mechanism the next audit will find another batch of dead emissions. The audit identified the asymmetry; the fix is to close it.

## Constraints

- **Preserve consumed events**: `phase_transition`, `feature_complete`, `lifecycle_start`, `review_verdict`, `batch_dispatch` are live consumers of `extract_feature_metrics` at `cortex_command/pipeline/metrics.py:212-247`. Any deletion sweep must not touch these.
- **Preserve human-skimmability** of events.log (today's JSONL is `jq`/`grep`-friendly for debugging).
- **In-flight features** must not break — features with a tail of pre-cut events emitted before the change merged must continue parsing.
- **Dashboard `parse_feature_events`** at `cortex_command/dashboard/data.py:282-327` must keep working; the events.log temporal-record property is load-bearing for the phase-transition timeline view.
- **Backwards compatibility**: any "registry" or discipline mechanism must allow grandfathered names for some deprecation window.

## Out of scope

- Full 2-tier events.log split (events.log spine + events-detail.log) — deferred per epic #172 pending the ~71-event consumer audit.
- Retroactive deletion of archived events.log content.
- Replacing events.log with an OpenTelemetry-style structured tracing model (architectural shift not justified by current findings).
- Changes to the existing live-event consumers' parsing logic beyond what's strictly required for the cuts.

## Acceptance signal

- Verified-dead event emissions are gone from the skill prompts and the consumer-side `requirements_updated` scan is gone from `morning-review/walkthrough.md`. (List of names to delete is a research-phase deliverable, with the cross-check against `metrics.py:212-247` documented.)
- `clarify_critic` no longer pollutes events.log with payloads that have no consumer; whatever signal it preserves (if any) lives somewhere with a declared reader.
- Escalation passing to orchestrator-round is bounded — does not grow linearly with session history.
- Some emission-discipline mechanism prevents the next audit from finding the same accumulation. CI-time check, runtime gate, or other; the choice is research-phase work.
- Dashboard's phase-transition view continues to render correctly under the new emission shape.

## Research hooks

Open questions for the research phase:

- For each dead-event type currently emitted (the audit's verified list is in `research/lifecycle-discovery-token-audit/research.md`), is the right action delete-without-replacement, relocate-to-artifact (e.g., the clarify_critic case), or relocate-to-events-detail (note: detail-log relocation pre-decides #172's deferred 2-tier scheme)?
- What's the right primitive for bounded escalation passing? `cap to N entries`, `since=last_round_ts`, `unresolved + prior_resolutions_by_feature`? The reader's actual use shape (filter prior resolutions per-feature) constrains this.
- What's the right discipline mechanism for emission? Runtime registry (rejects unregistered names), CI-time test (greps for `"event":` and asserts registry membership with consumer citation), human-review checklist, something else? The asymmetry diagnosis suggests an automated check; the mechanism is research-phase work.
- Should the dashboard parser get a schema-version check while it's open for changes?

The audit's DR-2 area and the alternative-exploration outputs surfaced specific options; treat those as inputs, not pre-decided answers.
