---
schema_version: "1"
uuid: 8393ea1a-f711-48ac-9c58-5f3b7dc193ca
title: "Adapt harness to Opus 4.7 (prompt delta + capability adoption)"
status: complete
priority: high
type: epic
created: 2026-04-18
updated: 2026-05-04
tags: [opus-4-7-harness-adaptation]
discovery_source: research/opus-4-7-harness-adaptation/research.md
---

# Adapt harness to Opus 4.7 (prompt delta + capability adoption)

Parent epic for Opus 4.7 migration work derived from `research/opus-4-7-harness-adaptation/research.md`. The discovery contracted the original "harness re-think" framing to a **prompt-delta audit plus targeted capability adoption** after five-agent research and one critical-review cycle.

## Scope

Nine child tickets across three tracks.

**Pre-audit spikes** (must land before #085 to avoid duplicate work):
- #083 — run `/claude-api migrate this project to claude-opus-4-7` on throwaway branch, report diff
- #084 — verify `claude/reference/*.md` conditional-loading under 4.7 (resolves OQ5)

**Audit and codification**:
- #085 — audit 7 dispatch-skill prompts + `claude/reference/*.md` for patterns P1–P6 and `consider` hedges
- #086 — extend `claude/reference/output-floors.md` with M1 Subagent Disposition section (dispatch-skill scope)

**Instrumentation and capability adoption** (DR-3 Wave 1 and Wave 2):

> **Update 2026-04-21**: #088 (baseline rounds) closed as wontfix. DR-4's "collect baseline → then ship Wave 1" ordering is no longer enforced. Downstream tickets #092 and #090 must decide individually whether to ship without before/after measurement or defer. See #088 closure note for rationale.

- #087 — instrument `events.log` aggregation for `num_turns` and `cost_usd` per tier
- ~~#088 — collect 2–3 overnight 4.7 baseline rounds and commit snapshot artifact (step 2 of DR-4)~~ — closed wontfix 2026-04-21
- #092 — remove progress-update scaffolding (step 3 of DR-4; originally blocked by #088, now unblocked but ships without baseline comparison)
- #089 — measure `xhigh` vs `high` effort cost delta on representative task
- #090 — adopt `xhigh` effort default for overnight lifecycle implement (Wave 2)
- #091 — decide and document post-4.7 policy settings (`MUST`-escalation norm, tone regression)

## Discovery context

`research/opus-4-7-harness-adaptation/research.md` covers:
- Seven Decision Records (DR-1 through DR-7)
- Six open questions for follow-up; one (adaptive-thinking) resolved during research as null work
- Critical-review cycle summary: four objections Applied, two Asks resolved 2026-04-18
- Observed failures F1–F5 split into three mechanisms (M1 audience/routing, M2 length-calibration, M3 output-gate) — tickets #067/#068/#069 already cover the first wave; this epic covers the second wave

## Implementation order

1. #083 and #084 run in parallel (independent spikes)
2. #085 runs after both spikes complete
3. #086 can run in parallel with #085 (different surface)
4. #087 runs independently (any time)
5. ~~#088 requires #087's instrumentation; commits the baseline snapshot artifact~~ — closed wontfix 2026-04-21
6. #092 originally required #088's snapshot (step 3 of DR-4); with #088 closed, ships without baseline comparison
7. #089 requires #087's instrumentation; runs in parallel with #092
8. #090 requires #089 and #092
9. #091 runs after #085 provides OQ3 calibration evidence. OQ6 (tone) needs no evidence but stays consolidated in #091
