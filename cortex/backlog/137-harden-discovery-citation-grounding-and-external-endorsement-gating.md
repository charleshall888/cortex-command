---
schema_version: "1"
uuid: 15ee4b9e-c570-4d25-ab98-a49e34e59890
id: "137"
title: "Harden /discovery citation grounding and external-endorsement value gating"
type: epic
status: complete
priority: medium
blocked-by: []
tags: [discovery, rigor, skills]
areas: [skills]
created: 2026-04-22
updated: 2026-04-22
discovery_source: cortex/research/audit-and-improve-discovery-skill-rigor/research.md
---

# Harden /discovery citation grounding and external-endorsement value gating

Two paired rule edits to `/discovery` targeting the failure mode exposed by backlog #092 — a ticket that closed wontfix after its generating research artifact projected a codebase locator from vendor guidance without a grep to verify it. Every existing human-layer check (orchestrator-review, critical-review, user gate on decomposition) ran and passed while the premise was silently wrong.

## Context from discovery

From `research/audit-and-improve-discovery-skill-rigor/research.md`:

- The `/discovery` skill's citation norm is empirically strong (85–95% across sampled artifacts) but not codified as a rule. The failing artifact (opus-4-7-harness-adaptation) sat at ~83% — the sample floor, not safely above any threshold.
- In #092's chain, "endorsed by Anthropic's 4.7 migration guide" functioned as sufficient value at the decomposition-time user-approval gate. The gate exists structurally (`decompose.md:29`) but had nothing to gate on — vendor-endorsement-as-value was accepted upstream without a weakness flag.
- The audit surfaced a novel framing bug: `research.md`'s Feasibility template puts "Identify X in the codebase" prerequisites in a column that reads as implementation sequencing, not as premise verification. This lets the codebase-check slide to the implementer.

The full research and decision records are in the source artifact. Two work items split from DR-1(c):

## Child tickets

- 138 — Codify citation norm and premise-as-verification in `/discovery` research phase (Approach A)
- 139 — Add vendor-endorsement value gating to `/discovery` decompose phase (Approach C)

## Non-goals

- Rebuilding parallel dispatch or adding tooling for automated codebase-claim verification (Approach F). Considered and deferred; revisit if A+C prove insufficient on future web-heavy discovery topics.
- Closure feedback loop that updates research artifacts when derived tickets close wontfix (Approach D). Deferred as low-urgency given the 1–2/111 base rate.
- Auditing the 68 tickets currently counted "complete" for silent premise-weakness. Out of scope for this discovery; would require a separate ticket-audit effort.
