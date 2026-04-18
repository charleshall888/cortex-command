---
schema_version: "1"
uuid: 496e9d2e-a44b-4b12-9622-289b75561442
title: "Verify claude/reference/*.md conditional-loading behavior under Opus 4.7"
status: backlog
priority: high
type: spike
created: 2026-04-18
updated: 2026-04-18
parent: "82"
tags: [opus-4-7-harness-adaptation, spike]
discovery_source: research/opus-4-7-harness-adaptation/research.md
---

# Verify claude/reference/*.md conditional-loading behavior under Opus 4.7

## Motivation

DR-1's scope contraction (prompt-delta audit, not harness re-think) is **provisional on OQ5**: whether 4.7 changes the conditional-loading semantics for `claude/reference/*.md` files. If those reference files stop loading reliably when their triggers fire, the audit surface shifts and DR-1 may need to expand.

## Research context

Open Question 5 from discovery:

> Are `claude/reference/*.md` files globally loaded (via `~/.claude/CLAUDE.md` conditional table) reliably under 4.7, or does 4.7's stricter instruction-following change the conditional loading semantics? Agent A flagged risk around `verification-mindset.md`'s `STOP` header and `parallel-agents.md`'s `Don't use when` list. Need a quick 4.7 invocation to confirm the reference files still load and fire correctly — otherwise the audit target shifts.

## Deliverable

A one-page report answering:
- Do the five reference files (`claude-skills.md`, `context-file-authoring.md`, `output-floors.md`, `parallel-agents.md`, `verification-mindset.md`) load when their triggers fire under 4.7?
- Does 4.7's stricter instruction-following change their behavior in ways that matter (e.g., over-triggering on the Red Flags `STOP` header, all-or-nothing refusal on `parallel-agents.md`'s "Don't use when" list)?
- If semantics changed, which reference files need patterns P3 (negation-only) or similar remediation added to #085's scope?

## Scope

- Exploratory only; no file edits
- Probe each reference's conditional trigger with an interactive or scripted Claude Code invocation
- Results feed into #085's scope decisions and unblock DR-1's firmness
