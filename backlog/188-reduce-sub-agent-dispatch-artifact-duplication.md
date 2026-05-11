---
schema_version: "1"
uuid: a03420eb-7778-4136-b75b-dfe4a445badd
title: "Reduce sub-agent dispatch artifact duplication"
type: feature
status: complete
priority: high
parent: 187
blocked-by: []
tags: [dispatch, critical-review, plan, review, token-efficiency]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/lifecycle-discovery-token-audit/research.md
complexity: complex
criticality: high
spec: lifecycle/reduce-sub-agent-dispatch-artifact-duplication/spec.md
areas: [skills]
session_id: null
---

# Reduce sub-agent dispatch artifact duplication

## Problem

Three sub-agent dispatch sites in cortex-command inline the full artifact content into each dispatched agent's prompt — producing N+1 or N+2 copies of the artifact per dispatch run:

- `skills/critical-review/SKILL.md:95-152, 209-211` — full artifact injected into each reviewer (3-4 reviewers) AND the synthesizer prompt AND the orchestrator's main context. For a 300-line plan with 4 reviewers: ~12-15k tokens worst case; for a 150-line plan with 3 reviewers: ~3-5k tokens typical.
- `skills/lifecycle/references/plan.md:43-46` — at critical tier, 2-3 plan agents each receive full `spec.md + research.md` body inline, while the main orchestrator already has both loaded. ~1.5-3k tokens per critical plan.
- `skills/lifecycle/references/review.md:30` — reviewer prompt receives full `spec.md` inline. ~500-1500 tokens per review.

## Why it matters

This is the audit's largest per-dispatch waste. Beyond the token cost, the inline-content approach has a correctness corollary: each reviewer + synthesizer + main session is seeing a dispatch-time *snapshot*, which masks any concurrent modification of the artifact during the parallel fan-out. A cleaner dispatch model improves both tokens and snapshot semantics.

## Constraints

- The fix must work for both auto-trigger and `<path>`-argument invocations of `/cortex-core:critical-review`.
- Must work for worktree-dispatched reviewers (overnight runner uses worktrees; reviewers may inherit worktree cwd, not the home repo's cwd — see `docs/overnight-operations.md:601`).
- Must preserve the synthesizer's evidence-quote re-validation step (`skills/critical-review/SKILL.md:218`), which requires the synthesizer and reviewers to see the same artifact content.
- Must define behavior under concurrent-write attempts during the parallel fan-out (today's inline-snapshot semantics are implicit; any new model must be explicit).
- Must define reviewer-Read failure behavior: a Read that returns empty must not be indistinguishable from "no concerns found."

## Out of scope

- The question of whether parallel multi-reviewer fan-out provides value over single-agent multi-angle review (user declined to investigate this spike). Treat parallel fan-out as a fixed design constraint.
- Changes to the angle-derivation logic in critical-review Step 2b.
- Changes to the synthesizer's A→B downgrade rubric.

## Acceptance signal

- Critical-review, critical-tier plan, and review.md reviewer dispatches no longer inline full artifact content per dispatched agent.
- Reviewer and synthesizer see consistent artifact state (no drift between them during one dispatch run).
- Worktree-dispatched reviewers resolve to the home repo's authoritative artifact path, not a worktree-local copy.
- Reviewer Read failures produce a structured signal distinguishable from "no concerns."
- Tests cover absolute-path emission, concurrent-write rejection, worktree dispatch resolution, sandbox-deny handling, and any size-threshold branching the chosen mechanism uses.

## Research hooks

The lifecycle's research phase should evaluate at least these candidate mechanisms before committing:

- Passing absolute artifact paths (resolved via `git rev-parse --show-toplevel`) and having each reviewer Read the path. Sub-questions: how to pin write-hold between dispatch and synthesis; whether a size-gated hybrid (inline for small artifacts, path for large) is warranted given per-Read tool-call overhead.
- Passing a content hash + path so reviewers can verify snapshot consistency on Read.
- Passing only the angle-relevant section of the artifact (orchestrator pre-slices), with the synthesizer alone seeing the whole.
- Other models surfaced during research.

Reviewer-2 of the audit (`research/lifecycle-discovery-token-audit/research.md` DR-1 and the alternative-exploration outputs) explores these and commits to a recommendation; treat that recommendation as an input to your own evaluation, not as a pre-decided answer.
