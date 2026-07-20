---
schema_version: "1"
uuid: ff919988-d939-47f5-8aa0-c14914e424fa
title: Reconcile the 'Dispatched agents are bounded' constraint with where turn caps actually earn their place
status: backlog
priority: low
type: chore
created: 2026-07-20
updated: 2026-07-20
tags: ['token-efficiency', 'requirements', 'skills', 'subagents']
areas: ['skills', 'lifecycle']
---
## Why

`cortex/requirements/project.md` states an absolute rule: **"every dispatched agent carries a turn cap (~40; on hit it returns what it has)"**. The codebase does not match it, and #399's measurement says it mostly shouldn't.

**Coverage.** A repo-wide grep finds the cap text in exactly two prompt sources (`skills/critical-review/references/reviewer-prompt.md`, `skills/research/SKILL.md`). Roughly ten other files dispatch agents from verbatim templates with no cap: `skills/refine/references/clarify-critic.md`, `skills/lifecycle/references/{orchestrator-review,fix-agent-prompt-template,review,competing-plans,implement}.md`, `skills/discovery/references/research.md`, `skills/backlog-author/SKILL.md`, `plugins/cortex-pr-review/skills/pr-review/references/protocol.md`.

**Enforcement is split.** The overnight path enforces a real, tighter bound — `cortex_command/pipeline/dispatch.py:129-131` sets `max_turns` 15/20/30 via the Agent SDK. The interactive skill path has no equivalent knob (the Agent tool exposes no turn limit), so its "cap" is prose an agent may or may not honour.

**Measurement says the rule over-generalizes.** #399 measured billed turns per dispatched role (dedup by `message.id`; script archived at `cortex/lifecycle/archive/the-synthesizer-and-fallback-reviewer-are/measure.py`):

| Role | Dispatches | Median | Max | >40 |
|---|---|---|---|---|
| synthesizer (uncapped) | 43 | 3 | 5 | 0 |
| clarify-critic (uncapped) | 52 | 7 | 16 | 0 |
| reviewer (capped) | 287 | 10 | 45 | 3 |
| fallback reviewer (uncapped) | 1 ever | - | - | - |

Only the reviewer — an open-ended "go investigate this artifact" mandate — ever approaches 40. The others self-limit on task shape, not prose. Sample caveat: only recent subagent transcripts survive (`n=11` synthesizer, `n=51` reviewer), but the gap between max-5 and a 40-cap is far too wide for sampling bias to close.

## Proposed direction

Soften the constraint to match where a bound earns its place, rather than pasting prose into ten more templates. Candidate shape: cap agents whose mandate is **self-directed investigation** (reviewer, research angles, fallback), and state explicitly that agents bounded by their input (synthesizer, critic, per-task builders) need none.

Consider also whether the prose cap should be dropped in favour of naming `dispatch.py`'s enforced `max_turns` as the real mechanism, with the interactive path documented as unenforced.

## Role

Closes the gap between an absolute requirement and a codebase that satisfies it in 2 of ~12 places — by fixing the requirement, not the codebase. Follow-up to #399 (closed wontfix on the measurement above).

## Edges

- **Do not resolve this by adding the cap everywhere.** That was #399's premise and the measurement rejected it; a cap on a structurally-bounded agent is redundant at best, and at worst truncates output invisibly (a capped critical-review synthesizer produces text indistinguishable from a clean "no objections" verdict — `synthesizer-prompt.md:32` + `verification-gates.md:74`).
- `project.md:39`'s second conjunct — "dispatch handling includes a returned-nothing branch" — is met only for the parallel reviewers (`skills/critical-review/SKILL.md:53`). Decide whether that clause generalizes or is likewise reviewer-scoped.
- Requirements edits are cheap to write and expensive to get wrong; this is a wording change to a load-bearing constraint, so it wants the escalator's judgment on tier.

## Touch points

- cortex/requirements/project.md (Architectural Constraints - "Dispatched agents are bounded")
- cortex_command/pipeline/dispatch.py:129-131 (the enforced overnight bound)
- skills/critical-review/references/reviewer-prompt.md, skills/research/SKILL.md (the two prompts that carry the cap today)
- cortex/backlog/389-bound-dispatched-agents-turn-cap-wall-clock-deadline-and-return-budgets.md (shipped the cap)
- cortex/backlog/399-the-synthesizer-and-fallback-reviewer-are-dispatched-agents-with-no-turn-cap.md (wontfix; carries the measurement)