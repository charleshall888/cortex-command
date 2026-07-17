---
schema_version: "1"
uuid: 32f3d2d2-76b7-4f05-8458-748e65ea5d35
title: Measure runtime agent payload accumulation — the cost model only sees resident prose
status: superseded
priority: high
type: feature
created: 2026-07-16
updated: 2026-07-16
tags: ['telemetry', 'token-efficiency', 'cost-model']
areas: ['lifecycle', 'report']
---
## Why

> **SUPERSEDED 2026-07-16 by #392 (`cortex-session-tokens`). Do not work this ticket. Read this box, then #392.**
>
> The instinct — measure before ranking — was exactly right, and #392 carries it forward. Every specific below is wrong:
>
> - **The core premise is false.** "The harness cannot report its own runtime cost" — it can, and always could. Every session transcript at `~/.claude/projects/<repo>/<session>.jsonl` carries a complete per-request `usage` object (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` with a per-TTL `cache_creation` breakdown) plus `model` and `attributionSkill`; subagents live in `<session>/subagents/*.jsonl`. Exact billing is reconstructible today. This ticket proposes reconstructing *estimates* from `subagent_tokens` — the exact data was already on disk.
> - **Its own numbers are the failure mode it was written to end.** The estimated split ("~150k agent reports returning verbatim, ~50k dispatch prompts") measures at **57k / 42.5k** — 2.6x over on the figure the whole ticket rests on. It opens by criticising an audit done "using a model recollection", and is itself a model recollection.
> - **The Edges claim is backwards.** "Prompt caching makes resident tokens cheap in dollars but does nothing for attention-dilution or the context ceiling" — cache-read is **61% of cost-weighted** orchestrator spend (97.6% of raw tokens). Caching *discounts* carry ~10x; it does not remove it. Measured cache hit rate is already 98.1% — there is no caching win left to chase.
> - **The metric is wrong.** Return-payload tokens is not the driver. The law is `cache_read ∝ turns^1.68` (r=0.98, n=126 sessions) — cost is the *integral of context over turns*, so the lever is turn count and session length, not payload size.
> - **Its foreclosure of phase-isolation is contradicted by evidence.** "The fix is **not** re-opening the L/XL context-architecture rewrite" — but sessions already span 3+ lifecycle phases, the orchestrator already re-reads `spec.md`/`plan.md` from disk in 24% of late-session tool calls (it does not trust its own memory), human steering is 2.3% of turns, and a fresh session costs ~50.7k to re-cache the floor (~0.72% of one session's read). Splitting is worth **37–61%** and is not an architecture project — the maintainer already does it by habit. The `resume` routing state (`SKILL.md:42`, `resolve.py:216`) already serves it phase-keyed.
>
> **The one durable lesson**, recorded here because it generalises: across this investigation, *every* number read straight from `usage` held, and *every* number requiring the analyst to classify content (bucket a command, attribute a verb, infer thinking) was wrong — including four produced while auditing this ticket. #392 is scoped to read `usage` and classify nothing, deliberately.

Every measurement tool in this repo points at **static/resident** surface: `cortex-count-tokens` counts documentation tokens, `cortex-measure-l1-surface` measures skill `description:`/`when_to_use:` bytes, `cortex-invocation-report` aggregates *which* `bin/cortex-*` scripts ran. Nothing observes the **transient** payload that dispatched agents send back into the orchestrator context.

That blind spot has already produced a wrong decision record. #340 research (`cortex/research/skill-efficiency-remaining-work/research.md:59`) declined phase-isolation partly on this premise, at stated high confidence:

> **Phase-isolation declined.** The accumulation ceiling is real, but the heavy *work* is already dispatched to fresh sub-agents (research fan-out, builders, reviewer, critical-review, competing plans); **only instruction-prose accumulates** ... Verdict held at high confidence.

**"Only instruction-prose accumulates" is false.** Dispatching work to a sub-agent does not stop accumulation — the agent return payload lands in the orchestrator context and stays there. The audit modelled the dispatch side and never modelled the return side.

Measured counter-evidence from one interactive `/cortex-core:lifecycle` run in a consumer repo (wild-light #362, 2026-07-16), on a ticket whose final deliverable is two lines of GDScript:

- **366k tokens of messages** at plan-approval time. The audit verified accumulation ceiling was **~51K** — off by roughly **7x**.
- ~15 subagents dispatched (1 explore, 1 clarify-critic, 5 research angles + 2 retries, 1 adversarial, 4 critical-review reviewers, 1 Opus synthesizer, 3 plan reviewers).
- Estimated split of the 366k: ~150k agent reports returning verbatim, ~50k orchestrator-authored dispatch prompts, ~30k reference-doc reads, ~20k artifacts, ~20k narration, ~10k wasted on 529 retries paying prompt cost twice.

Those numbers are **estimates from a single anecdote** — which is the point. The maintainer is currently auditing token spend using a model recollection because the harness cannot report its own runtime cost.

## Proposed direction

A verb — `cortex-lifecycle-tokens --feature <slug>` (JSON + human) — that reconstructs per-phase and per-dispatch token spend for a run from artifacts already on disk:

- The harness writes per-agent transcripts (`agent-<id>.jsonl`) and a `journal.jsonl` under the session/transcript dir; agent completions already carry a `subagent_tokens` figure. Attribute each dispatch to its phase via `events.log` `phase_transition` rows.
- Report, per phase: dispatches, subagent tokens (work done *inside* agents — cheap), and **return-payload tokens** (what re-entered the orchestrator — expensive). The second number is the one nothing currently sees.
- Flag the switchboard cases explicitly: payload that entered the orchestrator only to be re-emitted into another agent prompt (see the sibling ticket on the critical-review payload path).

Then re-run the #340 cost model against real numbers and amend or retire the phase-isolation decision record on evidence rather than argument.

## Role

Measure-first. This should land before the payload-path work is prioritised, so the ranking rests on telemetry instead of one session anecdote. It does not block that work — the switchboard wins are self-evident — but it is what makes the next round of efficiency decisions defensible.

## Integration

- Consumes: the harness per-session agent transcripts + `cortex/lifecycle/{feature}/events.log`.
- Sibling: #340 (core-skill efficiency) — same goal, different axis. #340 ranks **resident** prose by hot-path tokens and clarity-harm; this ticket supplies the **transient** axis that discipline is missing. The two rankings may disagree, which is worth knowing.
- Amends: `cortex/research/skill-efficiency-remaining-work/research.md` Decision Records (the phase-isolation entry).

## Edges

- The fix is **not** re-opening the L/XL context-architecture rewrite. That was declined for reasons that still hold (it fights interactive human-in-the-loop steering; selective ref-shedding does not exist in the harness). What changes is the *premise* — accumulation is dominated by return payloads, which are fixable with prompt-contract changes, not architecture.
- `subagent_tokens` measures the agent internal spend, NOT what it returned. Do not conflate them: internal spend is nearly free to the orchestrator; the returned report is not. The report must separate them or it reproduces the same blind spot.
- Prompt caching makes resident tokens cheap in dollars but does nothing for attention-dilution or the context ceiling — #340 own discipline. The same caveat applies here.

## Touch points

- bin/cortex-count-tokens, bin/cortex-measure-l1-surface, bin/cortex-invocation-report (the existing, static-only measurement surface)
- cortex/research/skill-efficiency-remaining-work/research.md (the decision record to amend)
- cortex/backlog/340-core-skill-efficiency-survivors-of-the-post-336-adversarial-audit.md