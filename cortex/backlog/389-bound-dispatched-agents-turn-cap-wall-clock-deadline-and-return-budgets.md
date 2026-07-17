---
schema_version: "1"
uuid: 23ddd7ca-c593-4cf8-ba5e-e8c5ea75bff0
title: 'Bound dispatched agents: turn cap, wall-clock deadline, and return budgets'
status: backlog
priority: high
type: feature
created: 2026-07-16
updated: 2026-07-16
tags: ['token-efficiency', 'reliability', 'critical-review', 'subagents']
areas: ['skills', 'lifecycle']
---
## Why

Dispatched agents have no bound of any kind — no turn cap, no wall-clock deadline, no return budget. Measured across 1,458 subagent transcripts (2026-07-16):

| fact | value |
|---|---|
| worst single agent | **170 turns, 602k peak context, 58.8M cache-read tokens** |
| agents >60 turns | 2.9% of population — **19% of all fan-out spend** |
| top 5% of agents | **28% of all fan-out spend** |
| median agent | 12 turns, 81k peak |

And the governing law: **`subagent cache_read ∝ turns^1.55` (r=0.96, n=1167)**. An agent is a mini-orchestrator — it pays the same superlinear carry as the main loop. A runaway agent is not linearly expensive, it is quadratically expensive.

Modelled saving from a turn cap (using the measured exponent):

| cap | agents affected | saving |
|---|---|---|
| 60 turns | 3% | 3.5% of total spend |
| **40 turns** | **7%** | **6.4% of total** |
| 25 turns | 19% | 11.1% of total |

A 40-turn cap touches 7% of agents and saves more than halving the reviewer count — **while costing zero independent lenses**.

**The reliability half is worse than the cost half.** There is no timeout, deadline, or circuit breaker anywhere in `skills/critical-review/` (verified by grep for timeout|deadline|circuit|abort|stall|watchdog|wall-clock — zero hits). `SKILL.md` Failure Handling covers agents that **fail** (Partial / Total) but has **no branch for an agent that never returns**. Observed consequences: the maintainer burned ~25 minutes polling a hung critical-review before giving up on their own initiative; during the investigation that produced this ticket, six agents idled without reporting and one died of "Prompt is too long".

Polling is not free: 229 requests across the corpus were spent waiting, producing nothing.

## Proposed direction

> **RESCOPED 2026-07-16 (requirements decision + independent re-derivation).** The tail statistics reproduced near-exactly (worst agent 170 turns / 602k peak / 58.8M cache-read; 2.9% of agents >60 turns = 19% of fan-out spend; `∝ turns^1.55` holds), so the mechanism is sound — but the modelled saving is **~5.3%** of total spend at a 40-turn cap, not 6.4% (the original figure inherited an understated spend denominator; see #392's correction box). Scope trimmed from four mechanisms to the two below: the wall-clock deadline and the `truncated: true` marker are cut as scope creep (the cap subsumes the runaway case, and this ticket's own Edges note that a deadline would not have beaten the harness's error for `native`), and return budgets are cut per the same measurement (return payload is ~11% of orchestrator context — turns are the driver, not payload size). Mandated by `cortex/requirements/project.md` ("Dispatched agents are bounded").

- **Turn cap** — bound each dispatched agent (~40 turns as a starting point). On hit, the agent returns what it has; the synthesizer weighs partial coverage the same way the existing Partial route does.
- **Returned-nothing fallback** — extend the Partial/Total structure to a third case: agent returned nothing (died loudly, or idled silently). Today both collapse into "wait forever".

## Role

The only substantial finding from the 2026-07-16 token investigation that is BOTH new (unticketed) AND computed purely from raw `usage` fields with no content classification. See Edges — that distinction is load-bearing.

## Integration

- Extends the existing Partial/Total Failure Handling in `skills/critical-review/SKILL.md` (Step 2c) rather than replacing it.
- Sibling: #382 (payload-path efficiency) proposes return budgets as its mechanism 3 — that mechanism is verified TRUE and belongs here, since it is the same "nothing is bounded" defect.
- **This ticket is orthogonal to fan-out breadth — it neither requires nor forbids cutting agent count.** Bounding a runaway agent and choosing how many reviewers to dispatch are independent decisions; do not let this ticket settle that one.
- **On agent count, specifically: it is an open empirical question, not a fixed point.** Halving reviewers (4→2 per gate) measures at **~4.7% of total spend** — a real, non-trivial saving. The case against it is weaker than it is usually stated: it rests on **n=1** (one observed run where four independent reviewers found four *different* fatal defects, and a spec gate that produced 7 A-class findings). That is the same single-anecdote standard #383 correctly refuses to act on. Decide it from yield data (dispatches vs A-class findings across real runs, per #392 + #383), not from doctrine — and a modest trim may well be justified once measured.
- What this ticket *does* claim is narrower and better-evidenced: the **tail** is where the waste is, and it is independent of count. 2.9% of agents (>60 turns) consume 19% of fan-out spend regardless of how many agents are dispatched. Capping length is available whether you run 2 reviewers or 4.

## Edges

- **Trust the numbers in this ticket more than most.** The 2026-07-16 investigation produced four wrong figures, all of the same class: any number requiring the analyst to *classify* content (bucket a command, attribute a verb, infer thinking) was wrong. Every number read straight from the `usage` object held. The figures above (turn counts, peak context, cache_read, the ^1.55 fit) are all in the second class.
- Cost figures assume Opus 4.8 at $5/$25 per Mtok and dedup by billed `message.id` — a naive line-sum over the JSONL overcounts ~2.66x because one billed response is logged once per content block, each carrying the same cumulative `usage`.
- A cap set too low degrades the reviewers that are demonstrably earning their keep. Prefer escalate-on-hit over kill-on-hit; measure the hit rate before tightening.
- `native` (the agent that died of "Prompt is too long") shows a wall-clock deadline would NOT have caught it any faster than the harness's own error did. Two branches are needed, not one.

## Touch points

- skills/critical-review/SKILL.md (Step 2c dispatch, Failure Handling)
- skills/critical-review/references/reviewer-prompt.md (no return budget)
- skills/critical-review/references/verification-gates.md (Partial-coverage route)
- skills/research/SKILL.md, skills/research/references/angle-templates.md (no return budget)
- cortex/backlog/382-get-the-orchestrator-out-of-the-agent-payload-path-dispatch-prompts-review-envelopes-return-contracts.md (mechanism 3 overlaps)