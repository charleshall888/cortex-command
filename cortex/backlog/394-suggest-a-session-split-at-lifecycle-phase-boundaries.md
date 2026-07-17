---
schema_version: "1"
uuid: f0306e22-2dc0-4031-93cc-751862d16c8e
title: Suggest a session split at lifecycle phase boundaries
status: done
priority: high
type: feature
created: 2026-07-16
updated: 2026-07-16
tags: ['token-efficiency', 'lifecycle', 'session-economics']
areas: ['lifecycle', 'skills']
---
## Why

Session carry is superlinear in turns — `cache_read ∝ requests^1.68` (r=0.98, n=126, independently re-derived 2026-07-16) — so the cheapest token in the corpus is the one a fresh session never re-reads. Splitting sessions at lifecycle phase boundaries is worth **37–61% of orchestrator carry**, the largest lever the 2026-07-16 investigation measured, an order of magnitude above every ticketed lever (#389 ~5.3%, #382 ~1–2%, #391 low single digits). A fresh session re-caches for ~50k tokens, ~0.7% of one long session's cache-read.

The practice already exists as maintainer habit — a fresh session after refine runs plan+implement, and a plan that consumed heavy context hands implement to another fresh session — and the infrastructure already serves it: `resume` routing is phase-keyed (`skills/lifecycle/SKILL.md:42`, `cortex_command/lifecycle/resolve.py:216`), artifacts are the interchange format, and the orchestrator already re-reads `spec.md`/`plan.md` from disk in 24% of late-session tool calls rather than trusting its own memory. What is missing is the nudge: nothing in the served loop ever suggests ending the session. Three prior tickets (#381, #390, #392) each cited the 37–61% figure to defend some other keep, and none proposed building the nudge — the classic shape of the lever that changes workflow losing to levers that only touch code.

`cortex/requirements/project.md` ("Phase boundaries are session boundaries", 2026-07-16) now makes the split the stated default.

## Proposed direction

At `phase_transition` on the interactive path, surface a one-line suggestion to end the session and resume fresh — strongest at the refine→plan and plan→implement boundaries. Candidate seams, in preference order:

- A `session_split_hint` field in the `cortex-lifecycle-next`/`advance` served envelope, rendered by the lifecycle skill's interactive loop. Preferred because it is served per-call, not carried in prose.
- One line of skill prose at the transition step, if the envelope key needs schema churn beyond a single optional field.

Overnight runner: no change where sessions are already per-dispatch; verify and note any path where they are not.

## Role

The structural nudge that converts the largest measured lever from personal habit into default behavior. S effort; builds nothing new.

## Integration

- Mandated by `cortex/requirements/project.md` ("Phase boundaries are session boundaries").
- Siblings from the same investigation: #389 (subagent bounds), #391 (event hygiene) — independent of both.
- Consumes the existing phase-keyed `resume` routing; no new state.

## Edges

- A suggestion, not a gate: the user can decline and keep the session; overnight paths that already split stay untouched.
- One hint at one seam — do not proliferate mechanism. If the envelope route needs more than a single optional key, fall back to prose.
- The 37–61% range is modelled from the measured exponent, not an A/B; re-measure with the ad-hoc prototype (`cortex/research/token-economics-2026-07-16/analyze.py`, dedup by `message.id`) after it ships.

## Touch points

- cortex_command/lifecycle/next_verb.py (served envelope)
- skills/lifecycle/SKILL.md (interactive loop rendering)
- cortex/requirements/project.md (the mandating constraint)
