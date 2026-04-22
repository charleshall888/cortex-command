---
schema_version: "1"
uuid: 0a2f1fee-dd42-49ff-b393-bd16d1fa5607
title: "Remove progress-update scaffolding from long-running prompts (DR-3 Wave 1)"
status: backlog
priority: medium
type: feature
created: 2026-04-18
updated: 2026-04-21
parent: "82"
tags: [opus-4-7-harness-adaptation, capability-adoption]
discovery_source: research/opus-4-7-harness-adaptation/research.md
blocked-by: []
---

# Remove progress-update scaffolding from long-running prompts (DR-3 Wave 1)

## Status update (2026-04-21)

#088 closed as wontfix — the baseline snapshot this ticket was designed to compare against will not be produced. `blocked-by: [88]` was auto-cleared when #088 reached terminal status.

Two paths forward:

1. **Ship without baseline comparison**: trust Anthropic's 4.7 guidance that built-in progress updates supersede explicit scaffolding; remove the scaffolding, run a couple of overnight rounds to catch loud regressions by inspection, and accept that subtle regressions won't be attributable with evidence. This is the pragmatic path if the scaffolding feels obviously outdated.
2. **Defer to match #088**: close this as wontfix too, on the reasoning that without measurement the DR-3 Wave 1 premise ("scaffolding becomes counterproductive — verify by comparing") can't be validated.

The Deliverable and Dependencies sections below describe the original measurement-gated plan and are historical — they need revision before this ticket starts if path (1) is chosen.

## Motivation

Anthropic's 4.7 guidance says built-in progress updates in long agentic traces are now more regular and higher-quality; explicit "summarize after every N tool calls" scaffolding in our prompts should become counterproductive. This is the actual scaffolding-removal work; baseline collection is in #88.

## Research context

Split from the original #88 (see critical-review cycle on decomposed.md 2026-04-18). DR-3 Wave 1 and DR-4 ordering requirement from `research/opus-4-7-harness-adaptation/research.md`:

- **DR-3 Wave 1**: "Remove progress-update scaffolding. Must not ship until DR-4 has collected 2–3 overnight rounds of clean 4.7 baseline data."
- **DR-4 ordering requirement**: "(1) ship 4.7 with existing prompts → (2) collect 2–3 rounds of baseline data → (3) only then ship Wave-1 prompt changes → (4) revisit matrix recalibration decision."

Steps 1–2 are in #88; this ticket is step 3.

## Deliverable

- Identify prompts with progress-update scaffolding (e.g., "summarize after every N tool calls", "every 3 turns provide a status update") across skills and reference docs
- Remove or soften the scaffolding per Anthropic best-practices §4.7
- Run 2–3 overnight rounds post-change
- Compare against #88's baseline snapshot (committed artifact from Phase 1); report delta in turn usage, cost, and qualitative progress-update quality
- If post-change data shows regression (e.g., native progress updates are thinner than our scaffolding), revert

## Dependencies

- Blocked by #88 — baseline snapshot must exist and be committed to git before this ticket starts. #88's terminal-status (`complete`) + the presence of a committed baseline artifact together signal readiness. The `blocked-by` edge enforces the status-terminality half; the artifact check is a procedural responsibility for whoever starts this ticket's lifecycle.

## Scope bounds

- No other prompt changes in the same lifecycle run — ordering discipline is the point
- If #88's baseline shows surprising 4.7 behavior (e.g., unexpected turn distributions), revisit the scaffolding-removal design in Clarify before proceeding
