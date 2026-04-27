---
schema_version: "1"
uuid: 0483eebe-92eb-435f-ae65-a17961af4a2f
id: "139"
title: "Add vendor-endorsement value gating to /discovery decompose phase"
type: chore
status: complete
priority: medium
parent: "137"
blocked-by: []
tags: [discovery, rigor, skills]
areas: [skills]
created: 2026-04-22
updated: 2026-04-22
discovery_source: research/audit-and-improve-discovery-skill-rigor/research.md
session_id: null
lifecycle_phase: research
lifecycle_slug: add-vendor-endorsement-value-gating-to-discovery-decompose-phase
complexity: simple
criticality: high
spec: lifecycle/archive/add-vendor-endorsement-value-gating-to-discovery-decompose-phase/spec.md
---

# Add vendor-endorsement value gating to /discovery decompose phase

Close the value-case capture path that let #092 through the decomposition-time user-approval gate despite having an unverified codebase premise.

## Context from discovery

From `research/audit-and-improve-discovery-skill-rigor/research.md` §Feasibility, Approach C, and §Codebase Analysis H4 (revised):

- `decompose.md:29` ("Present the proposed work items to the user for review before creating tickets") IS a user-approval gate in practice. Combined with `decompose.md:23` (flag weak value), it's a flag-then-approve gate.
- The gate can only catch issues the agent surfaces. In #092's chain, the Value case was "endorsed by Anthropic's 4.7 migration guide" — a vendor quote treated as sufficient value on its own. Nothing flagged that the codebase premise under the quote was unverified, so the gate approved it.
- Every existing post-hoc check for the generating artifact ran and passed (per `research/opus-4-7-harness-adaptation/events.log`): orchestrator-review cycle 1 clean; critical-review 4/4 objections applied; user gate on DR-4 approved decomposition. Human discipline at every layer did not catch the failure.

## Findings

`skills/discovery/references/decompose.md:23` instructs the agent to flag a weak value case, but accepts vendor endorsement or external guidance ("Anthropic says…", "CrewAI docs recommend…") as sufficient value by default. The user-approval step at `decompose.md:29` has no specific trigger to pause on external-endorsement items, so they batch-approve with the rest.

## Success criteria

- When a work item's Value rests on external endorsement (vendor guidance, best practices, industry standards) AND the codebase premise for the work is unverified (per #138's `premise-unverified` signal, or absent citations in the source research.md), the agent must flag the item explicitly at the `decompose.md:23` Value field.
- The user-approval step at `decompose.md:29` must pause on flagged items rather than batch-approving — the user must explicitly acknowledge each such item before the ticket is created.
- Legitimate vendor-guided work with a grounded codebase premise remains unaffected — the trigger is "external endorsement WITHOUT grounded premise," not vendor endorsement alone.

## Dependencies

- Blocked by #138. The vendor-endorsement gate reads the `premise-unverified` signal codified in #138's rule edit to `research.md`. #139 can be scoped as a same-file edit to `decompose.md` once that signal exists.
