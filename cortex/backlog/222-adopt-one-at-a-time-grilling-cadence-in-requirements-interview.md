---
schema_version: "1"
uuid: 3c6cede4-bbe1-4e72-9413-04feb0206afb
title: "Adopt one-at-a-time grilling cadence in requirements interview"
status: backlog
priority: medium
type: feature
parent: 221
tags: [requirements, skills, lifecycle, grill-me-with-docs-learnings]
created: 2026-05-15
updated: 2026-05-15
discovery_source: cortex/research/grill-me-with-docs-learnings/research.md
---

## Role

Bring Matt Pocock's interview cadence into the requirements interview surfaces. Each requirements question is asked one at a time (the user's response on the previous question is the gate to the next), the agent leads with a recommended answer instead of asking blank, and as each requirement is asked the agent also names the file path that would be modified so the user can catch a wrong-place-to-implement before any code is written. For each requirement, the agent invents one edge-case scenario before locking acceptance criteria, stress-testing the requirement against a concrete failure mode at interview time rather than at review time.

## Integration

Lands as in-place prose edits to two existing skills with no new files and no new contracts. Interacts with the existing recommend-before-asking pattern (already adopted) by tightening the cadence rule from soft guidance to explicit one-at-a-time gating. Interacts with the existing pre-write Verification check in the spec phase by repositioning code-vs-claim cross-reference from end-of-interview to during-interview as a passive posture (the agent is asked to cite the relevant code path as it asks each requirement, not as a separate gate after the interview ends).

## Edges

- Soft-positive-routing prose only. No new MUST or REQUIRED escalations without effort=high dispatch evidence per the project MUST-escalation policy.
- Behaviors limited to passive-precondition encoding: cadence (one-at-a-time), recommendation-leading questions, and during-interview code citation are all satisfiable as preconditions the agent passes through. Interrupt-driven mid-turn injections (active conflict-flagging, fuzzy-language sharpening) are explicitly out of scope.
- Must not break the existing Q&A block contract that /requirements-gather hands to /requirements-write.

## Touch points

- skills/requirements-gather/SKILL.md (interview body — cadence, recommend-and-wait, file-path citation)
- skills/lifecycle/references/specify.md §2 (Structured Interview body — same cadence and during-interview verification posture)
- skills/lifecycle/references/specify.md §2b (Verification check — repositioned commentary)
