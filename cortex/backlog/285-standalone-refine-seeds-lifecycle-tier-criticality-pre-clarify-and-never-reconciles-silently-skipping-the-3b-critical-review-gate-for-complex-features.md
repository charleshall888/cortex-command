---
schema_version: "1"
uuid: f83a53ca-7f6f-43ca-b5b8-e03c6cf968cf
title: "Standalone /refine seeds lifecycle tier/criticality pre-Clarify and never reconciles, silently skipping the §3b critical-review gate for complex features"
status: complete
priority: medium
type: bug
created: 2026-06-02
updated: 2026-06-02
complexity: complex
criticality: high
spec: cortex/lifecycle/standalone-refine-seeds-lifecycle-tier-criticality/spec.md
areas: ['skills']
---
**Why:** When `/cortex-core:refine` is invoked directly on a backlog item, the lifecycle `events.log` is seeded with stale tier/criticality and never reconciled with the Clarify assessment, which can silently skip the §3b critical-review gate for a complex feature. The chain: `cortex-refine emit-lifecycle-start` (refine Step 2) seeds `lifecycle_start` by reading backlog frontmatter (`refine.py:123` → `_read_backlog_frontmatter`), but it runs before Clarify (Step 3). A freshly-created ticket has neither `complexity` nor `criticality` set at that point, so the seed defaults to `tier=simple, criticality=medium`. Clarify then determines the real values and writes them to the backlog only (`cortex-update-item --complexity --criticality`); nothing writes them to the lifecycle `events.log`. specify §3a/§3b read tier/criticality from `cortex-lifecycle-state` (events.log), not the backlog, so they observe the stale seed. Because the §3b critical-review run rule is `tier=complex AND criticality ∈ {medium,high,critical}`, a Clarify-assessed-complex feature that reads as `simple` has critical-review silently skipped — the adversarial gate whose purpose is to catch fix-invalidating spec defects before approval. Observed during the refine of #281: the lifecycle state read `simple/medium` while Clarify assessed `complex/high`; a manual `complexity_override`/`criticality_override` reconciliation was required for the gate to fire, after which critical-review surfaced 4 fix-invalidating objections and forced a scope split.

**Role:** A directly-invoked `/refine` should run the same spec-phase quality gates as `/lifecycle` does for the same feature. The complexity/criticality determined during Clarify should drive the lifecycle-state reads that §3a/§3b consume, not only the backlog frontmatter.

**Integration:** `/cortex-core:lifecycle` does not have this gap — it emits `lifecycle_start` after the full Clarify phase, sourcing tier/criticality from the post-critic, post-Q&A values (`lifecycle/SKILL.md:150-152`). The natural reconciliation point in refine is the Step-3 Clarify write-back: alongside the existing `cortex-update-item --complexity --criticality` (backlog), bring the lifecycle `events.log` into agreement (e.g. emit `complexity_override`/`criticality_override`, or a single helper that updates both the backlog and the lifecycle state). Considerations recorded so they are not re-discovered:
- The §3b run rule hinges on tier (`complex` plus any non-`low` criticality runs), so the load-bearing reconciliation is the tier; criticality medium-vs-high does not change whether critical-review runs but does feed the criticality-matrix (sub-agent model selection, parallel-vs-single dispatch).
- The complexity-escalator (`cortex-complexity-escalator --gate research_open_questions`) is not a substitute: its gates are documented as running during `/lifecycle` delegation and are not invoked by `refine/SKILL.md`, and it keys on research open-question count rather than the Clarify assessment — so a complex feature whose open questions are all deferred is not escalated by it.
- `criticality_override` currently has no Python emitter (only prose emission); any reconciliation that emits it matches the read shape in `cortex_command/lifecycle/state_cli.py` (`record.get("to") or record.get("criticality")`).
- `emit-lifecycle-start` is intentionally early (Step 2) so `lifecycle_start` anchors before `clarify_critic` and other rows; moving it after Clarify conflicts with that ordering, so reconciliation (not re-seeding) is the fitting shape.

**Edges:**
- Only affects directly-invoked `/cortex-core:refine`; `/cortex-core:lifecycle` is unaffected.
- Bites the common case: a freshly-created, un-triaged ticket (no complexity/criticality in frontmatter) that Clarify assesses as complex. A ticket already carrying those fields before refine seeds correctly.
- Silent — no error is raised; the gate simply does not fire. Detectable only by noticing that the `cortex-lifecycle-state` read disagrees with the Clarify assessment.
- §3a orchestrator-review is not skipped by this (it runs for everything except `simple AND low`; the seed `simple/medium` still runs it).

**Touch-points:**
- `cortex_command/refine.py` (`_cmd_emit_lifecycle_start`, `_read_backlog_frontmatter`).
- `skills/refine/SKILL.md` (Step 2 emit-lifecycle-start; Step 3 Clarify write-back; Step 5 §3b adaptation).
- `skills/lifecycle/references/specify.md` (§3a/§3b tier/criticality reads via `cortex-lifecycle-state`).
- `cortex_command/lifecycle/state_cli.py` (reader of `lifecycle_start`/`complexity_override`/`criticality_override`).
- `cortex_command/lifecycle/complexity_escalator.py` (the tier-only escalator that is not a substitute here).
- `skills/lifecycle/SKILL.md:150-152` (the unaffected post-Clarify `lifecycle_start` emission, for reference).

Discovered during the refine of #281.