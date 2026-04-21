---
schema_version: "1"
uuid: 4451ab84-0143-46d9-ba83-958165b2fb32
title: "Classify /critical-review findings by class and add B-class action surface"
status: ready
priority: high
type: feature
tags: [critical-review, scope-expansion-bias, skills]
areas: [skills]
created: 2026-04-21
updated: 2026-04-21
session_id: null
blocks: []
blocked-by: []
discovery_source: research/critical-review-scope-expansion-bias/research.md
complexity: complex
criticality: medium
---

# Classify /critical-review findings by class and add B-class action surface

## Context from discovery

/critical-review dispatches parallel reviewer agents, then synthesizes findings with Opus. A documented failure (Kotlin Android bug, protein-grams merge mapper) surfaced a structural defect: four reviewers raised real B-class adjacent-gap findings (analytics flushing, post-submit flow, create-order path, third-party checkout); the synthesizer aggregated them into a C-class verdict ("the real defect is upstream, both fixes insufficient"), which the operator read as authoritative and flipped to a wrong-layer fix.

The failure is B→A promotion in synthesis. The reviewer and synthesis prompts do not distinguish findings that invalidate a proposed fix from findings that identify adjacent pre-existing gaps. Without that distinction, the "strongest objections" tone the synthesis prompt is told to produce reads as verdict rather than prosecution.

Prior art converges on the same move (Conventional Comments, Google eng-practices, peer-review Major/Minor, CVSS scope axis, AI Safety via Debate): force reviewers to commit to blocking status per finding, and give the synthesizer a classification-aware rule rather than through-line aggregation. See research `## Domain & Prior Art`.

## Value

Addresses the one documented failure of this skill directly. The skill's purpose is to surface the strongest coherent challenge; when the coherent challenge is a prosecution-reading of adjacent gaps, the operator flips to a worse fix. That negates the ROI the skill was built to produce — one observed instance has already cost one wrong-layer implementation and an operator-supplied correction. The fix is confined to two prompt templates plus an action-surface mechanism; blast radius is local to the critical-review skill.

## Research context

- Research artifact: `research/critical-review-scope-expansion-bias/research.md`
- Key decision records: DR-1 (required cross-epic AC for B-class action surface), DR-4 (FP2 is load-bearing; FP1 is its prerequisite), DR-6 (FP5 deferred, not ticketed)
- Grounded defects the fix addresses: H1 (incomplete≠incorrect), H3 (verdict-framing tone), H4 (Apply-bar permissive on framing claims). H2 (no pattern anchor) and FP5 are explicitly deferred — the Kotlin failure was B→A promotion, not C-class reviewer objections without pattern evidence
- Related completed work: backlog/067 (Step 4 Dismiss-output restructure — complete, no regression expected)

## Acceptance criteria

- Each reviewer agent (Step 2c of critical-review/SKILL.md) emits findings tagged with a finding class. Classes cover at minimum: fix-invalidating (A), adjacent-gap (B), framing (C). The reviewer prompt template provides the taxonomy with at least one worked example per class
- The synthesizer (Step 2d) receives class-tagged findings and applies a rule that refuses to promote B-only evidence into an A-class verdict. Through-line flagging is scoped to same-class findings
- B-class findings have a defined action surface — e.g., auto-emit a follow-up backlog ticket stub for each B-class finding, or a structured residue artifact that produces observable evidence when a B-class finding is not actioned. Silent dismissal of B-class findings is not a valid end state
- Classifier accuracy is validated against at least one historical /critical-review output (Kotlin session if recoverable, otherwise a synthetic analog) before shipping
- Straddle-case protocol defined: findings that are simultaneously A and B (e.g., "this fix matches the existing pattern but the pattern is wrong") have an explicit routing rule — either multi-class tagging, a precedence ordering, or a rubric directing the reviewer to one class with reasoning
- `skills/critical-review/SKILL.md` updated; no regression to Step 4 Apply/Dismiss/Ask behavior beyond the intended C-class → Ask routing tightening

## Open design questions for planning

- Action-surface mechanism (auto-ticket, structured residue file, synthesis-appendix escalation, or other) — choose at plan time per research Open Questions
- Class count (ternary A/B/C vs. binary blocking + orthogonal type axis à la CVSS) — research flagged the ternary as asserted rather than derived; planning must justify the choice
- Whether to pilot on a held-out /critical-review output before merging, or ship behind an opt-in flag
