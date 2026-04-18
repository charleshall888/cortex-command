---
schema_version: "1"
uuid: 7e6b212e-f74e-4f48-9fd6-30152c27b872
title: "Decide and document post-4.7 policy settings (MUST-escalation, tone regression)"
status: backlog
priority: low
type: chore
created: 2026-04-18
updated: 2026-04-18
parent: "82"
tags: [opus-4-7-harness-adaptation, policy]
discovery_source: research/opus-4-7-harness-adaptation/research.md
blocked-by: [83, 84, 85]
---

# Decide and document post-4.7 policy settings (MUST-escalation, tone regression)

## Motivation

Two open policy questions emerged from discovery that aren't technical decisions — they're durable policy choices about how the harness should work under 4.7. Consolidated here to reduce ticket count (both likely touch CLAUDE.md or `claude/reference/` files).

## Research context

**OQ3 — `MUST`-escalation norm**: Anthropic's skill-authoring doc still endorses escalating to `MUST`-style language when an observed failure shows Claude is skipping a rule, even while the migration guide says "dial back aggressive imperatives." The reconciliation ("default soft, escalate on observed failure") is currently an inference, not a documented policy. Decision needed: when we encounter a post-migration `MUST` escalation, do we keep it or normalize it back and re-observe?

**OQ6 — Tone regression**: 4.7 is documented as "less conciliatory, fewer emoji" compared to 4.6. Voice/tone regression is a user-experience concern, not a correctness one. Decision needed: do we add a warmth-setting directive to `CLAUDE.md` or global settings, or accept the new voice?

## Deliverable

Short written policy entries, likely in `CLAUDE.md` or a new/existing `claude/reference/` file, answering both questions. Keep each to a paragraph or two — these are durable norms, not prescriptions.

## Dependencies

- Blocked by #083, #084, #085 — concrete evidence from those helps calibrate the right policy (e.g., if the audit reveals many sites where `MUST` would mask a real problem, the OQ3 answer tilts toward "normalize and re-observe")

## Scope

- Policy documentation only, no code changes
- Two decisions, not three — if another policy question surfaces later, it gets its own ticket
