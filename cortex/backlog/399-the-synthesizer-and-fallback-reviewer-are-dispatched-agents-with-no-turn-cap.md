---
schema_version: "1"
uuid: e16ac07d-cc62-471f-93ae-5b96396e48e9
title: The synthesizer and fallback reviewer are dispatched agents with no turn cap
status: wontfix
priority: low
type: feature
created: 2026-07-17
updated: 2026-07-20
tags: ['token-efficiency', 'reliability', 'critical-review', 'subagents']
areas: ['skills', 'lifecycle']
lifecycle_phase: wontfix
lifecycle_slug: the-synthesizer-and-fallback-reviewer-are
---
## Why

`cortex/requirements/project.md` states the constraint absolutely: **"Dispatched agents are bounded — every dispatched agent carries a turn cap (~40; on hit it returns what it has)"**. #389 shipped that cap into the per-angle reviewer prompt and the research angle prompts. **Two dispatched agents were not in its scope and carry no cap:**

- `skills/critical-review/references/synthesizer-prompt.md` — the Step 2d Opus synthesizer. Dispatched on **every** critical-review run that clears the gate, and it is the most expensive agent in the fan-out: it runs on Opus while #383's routing put the reviewers on Sonnet (a 1.67x per-token gap), it Reads the artifact, and it now Reads the A→B rubric by path as well (#382).
- `skills/critical-review/references/fallback-reviewer-prompt.md` — the total-failure fallback reviewer. Dispatched precisely when things have already gone wrong, and it is the widest-mandate agent in the skill: it derives its own 3–4 angles and works through all of them in one agent.

The governing law is `subagent cache_read ∝ turns^1.55` (r=0.96, n=1167) — an agent is a mini-orchestrator paying superlinear carry. The measured tail (2.9% of agents >60 turns = 19% of fan-out spend) is a property of *agents*, not of the reviewer role. Nothing about being a synthesizer or a fallback makes an agent immune to it.

## Proposed direction

Add the same verbatim cap text #389 shipped to both prompt templates:

> Work within a ~40-turn cap. On reaching it, stop investigating and return what you have — a partial return beats no return.

Match the existing return contracts rather than inventing new ones: the synthesizer's deliverable is its named-section synthesis, the fallback's is its `## Objections` output. On cap, both return what they have — the synthesizer's partial synthesis routes through the existing Step 2d.5 gate unchanged; the fallback's output is surfaced directly, as it already is.

## Role

Closes the gap between what `project.md`'s "Dispatched agents are bounded" constraint says ("every") and what #389 actually shipped (three prompts). Purely additive prose; no mechanism, no new field.

## Integration

- Extends #389 (complete) — same constraint, same verbatim text, same Partial-coverage posture. This is the surviving remainder of its scope, not a rework of its decisions.
- The synthesizer's cap interacts with **nothing** in Step 2c.5/2d.5: those gates key off the `SYNTH_READ_OK` sentinel and a re-hash of the pinned artifact, neither of which a shorter synthesis disturbs.
- **Sizing depends on #392, and honestly this may be worth ~zero.** #389's own cap is unverified at n=0 runs; a cap on two more agents is worth measuring, not modelling. Do not inherit #389's ~5.3% figure — that was computed over the whole 1,458-agent population, not these two roles.

## Edges

- **Check the hit rate before tightening, and prefer escalate-on-hit over kill-on-hit** (#389's Edges). The synthesizer is the agent most likely to legitimately need turns: it re-reads every `evidence_quote` against the artifact, and a wide fan-out gives it more findings to verify. A cap that truncates synthesis degrades the one agent whose output the user actually reads.
- **The fallback reviewer's cap is the more defensible of the two.** It derives its own angles with no orchestrator bound, so it is the likelier runaway; the synthesizer's work is bounded by the finding count it was handed.
- **A prose cap may simply not bind.** Nothing in the harness enforces a turn count — #389 shipped an instruction, not a mechanism. If measurement shows the tail unchanged, the answer is not more prose in more prompts: it is moving the bound into the dispatch path, and this ticket should be closed in favour of that.

## Touch points

- skills/critical-review/references/synthesizer-prompt.md (Step 2d dispatch — no cap)
- skills/critical-review/references/fallback-reviewer-prompt.md (total-failure fallback — no cap)
- skills/critical-review/SKILL.md (Step 2c Failure Handling / Step 2d dispatch — where the cap is stated for the reviewers)
- cortex/requirements/project.md (Architectural Constraints — "Dispatched agents are bounded")
- cortex/backlog/389-bound-dispatched-agents-turn-cap-wall-clock-deadline-and-return-budgets.md (the ticket this completes)