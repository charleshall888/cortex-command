---
schema_version: "1"
uuid: f90dd3eb-bd20-4f98-98db-63377b8b40a6
title: "Extend output-floors.md with M1 Subagent Disposition section"
status: backlog
priority: medium
type: feature
created: 2026-04-18
updated: 2026-04-18
parent: "82"
tags: [opus-4-7-harness-adaptation, reference-docs]
discovery_source: research/opus-4-7-harness-adaptation/research.md
---

# Extend output-floors.md with M1 Subagent Disposition section

## Motivation

DR-6 in the research artifact codifies the M1 (audience/routing) pattern observed in F1, F4, F5 — the dominant mechanism (60%) across observed 4.7 failures. Under 4.7, subagent returns without explicit disposition default to user-visible relay; the fix is explicit positive routing (`log-only`, `silent re-run, surface pass/fail`, `absorb into internal state, emit nothing`).

## Research context

From `research/opus-4-7-harness-adaptation/research.md` §"Five observed-failure patterns":

- F1 (ticket #068) — Dismiss-rationale leak in clarify-critic
- F4 (ticket #069) — Clean-pass silence ambiguity
- F5 (ticket #069) — Fix-agent report absorption ambiguity

All three share mechanism M1 and converge on the same structural fix. Codifying this pattern gives new dispatch-skill authors a template.

## Deliverable

Extend `claude/reference/output-floors.md` with a new section — scoped via the existing Applicability pattern — covering:
- When a dispatch-skill invokes a subagent, the prompt should specify an explicit disposition for the return (`log-only`, `silent re-run`, `absorb and surface pass/fail`, `emit only Ask items`, etc.)
- Worked examples drawn from the in-flight fixes in tickets #067, #068, #069
- Applicability: lifecycle and discovery skills (matching `output-floors.md`'s existing scope)

## Scope discipline

- Codifies M1 only. M2 (length-calibration regressions) and M3 (output-gating on internal verification) are handled by the per-ticket fixes in #067/#069 and not promoted to the reference until a second skill surfaces the same mechanism.
- Extends `output-floors.md` (per DR-6's chosen option) rather than creating a new reference file, to avoid adding conditional-loading weight.

## Not blocked

Can run in parallel with #085 — different files, different intent.
