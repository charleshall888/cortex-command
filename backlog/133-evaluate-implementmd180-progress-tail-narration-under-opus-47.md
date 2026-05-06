---
schema_version: "1"
uuid: daf2f648-6cf3-4322-9971-a7cee01cce6f
title: "Evaluate implement.md:119 progress-tail narration under Opus 4.7"
status: complete
priority: low
type: feature
created: 2026-04-22
updated: 2026-05-04
parent: "82"
tags: [opus-4-7-harness-adaptation, capability-adoption]
complexity: complex
criticality: high
spec: lifecycle/archive/evaluate-implementmd119-progress-tail-narration-under-opus-47/spec.md
areas: [lifecycle]
session_id: null
lifecycle_phase: complete
---

# Evaluate implement.md:119 progress-tail narration under Opus 4.7

## Motivation

Spun out from #092's research on 2026-04-22. #092 was closed wontfix after research confirmed the canonical Anthropic target ("summarize every N tool calls") is not present in the codebase. One ambiguous site remains: `skills/lifecycle/references/implement.md:117-120` — the daytime-dispatch polling loop's per-iteration step (b):

```
(b) Progress tail: `tail -n 5 lifecycle/{feature}/events.log` and surface a brief summary of the 5 most recent events to the user. The tail is capped at 5 (not 20) to limit context accumulation over long runs.
```

This fires every 120 seconds for up to 120 iterations (~4 hours). It is the one site in the codebase that structurally matches Anthropic's "scaffolding to force interim status messages" language — time-cadence trigger, forced user-facing narration — though its semantic role is orchestrator-monitoring a detached background subprocess rather than model self-narration of agentic work.

## Deliverable

Apply Anthropic's 3-step 4.7 guidance (Opus 4.7 migration guide, item 4) to this single site:

1. **Try removing** the "surface a brief summary of the 5 most recent events to the user" clause. Keep the `tail` call itself as a watchdog (liveness + log aggregation), drop the narration directive.
2. **Observe** 1–2 daytime dispatch runs in the resulting polling loop. Note whether 4.7's orchestrator session naturally narrates the subprocess state, and whether user visibility into the detached subprocess is preserved.
3. **If mis-calibrated** — narration absent entirely, or over-emitted, or losing the 5-event cap's context-hygiene benefit — add a shaped example in the prompt rather than reverting wholesale. Example: "When the tail shows a new `task_complete` or `phase_transition` event since the previous poll, briefly note it; otherwise stay quiet."

## Scope

- `skills/lifecycle/references/implement.md:117-120` only
- No other prompt changes

## Note on line drift

This ticket was originally filed against `implement.md:178-181` on 2026-04-22. Upstream edits to `implement.md` shifted the same content to `:117-120` by 2026-04-29; the line numbers above were updated then. Verify the target text ("(b) Progress tail: `tail -n 5 ...`") at the cited lines before acting; if it has drifted again, search for the verbatim text rather than trusting the line number.

## Scope bounds

- Do NOT touch other "announce/summarize" patterns identified in #092's research (phase-transition floor, approval-surface floor, end-of-skill announces, multi-agent between-waves summaries) — those are structural content specifications or brief confirmations, not cadence-triggered scaffolding. See `lifecycle/archive/remove-progress-update-scaffolding-from-long-running-prompts-dr-3-wave-1/research.md` for the per-site analysis.
- Regression detection is qualitative (as with the closed parent ticket) — revert via git if narration becomes clearly degraded, accept that subtle changes won't be attributable.

## Background

- #092 (closed wontfix 2026-04-22): [lifecycle/archive/remove-progress-update-scaffolding-from-long-running-prompts-dr-3-wave-1/research.md](../lifecycle/archive/remove-progress-update-scaffolding-from-long-running-prompts-dr-3-wave-1/research.md)
- Anthropic migration guide: `platform.claude.com/docs/en/about-claude/models/migration-guide` item 4
- Epic research: `research/opus-4-7-harness-adaptation/research.md` (DR-3)

## Priority

Low. Single-site, opportunistic. Natural pickup if any other ticket edits `implement.md` (e.g., sibling M1 work in #067/#068/#069).
