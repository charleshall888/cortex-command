---
schema_version: "1"
uuid: 7e6b212e-f74e-4f48-9fd6-30152c27b872
title: "Decide and document post-4.7 policy settings (MUST-escalation, tone regression)"
status: complete
priority: low
type: chore
created: 2026-04-18
updated: 2026-05-04
parent: "82"
tags: [opus-4-7-harness-adaptation, policy]
discovery_source: research/opus-4-7-harness-adaptation/research.md
blocked-by: []
complexity: complex
criticality: high
spec: lifecycle/archive/decide-and-document-post-47-policy-settings-must-escalation-tone-regression/spec.md
areas: [docs]
session_id: null
lifecycle_phase: complete
---

# Decide and document post-4.7 policy settings (MUST-escalation, tone regression)

## Update (2026-04-29)

- Blocker #85 reached `status: complete` — its dispatch-skill audit findings are now available as the empirical input for OQ3 (see `lifecycle/archive/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/`).
- `claude/reference/` was deleted in commit `08d1102` (2026-04-23) as part of retiring shareable-install scaffolding. The remaining viable target for these durable policy entries is `CLAUDE.md` (or, if cortex-deploys-only-rules conventions apply, `~/.claude/rules/cortex-*.md` — see #120/#121).
- `blocked-by: [85]` cleared.

## Motivation

Two open policy questions emerged from discovery that aren't technical decisions — they're durable policy choices about how the harness should work under 4.7. Consolidated here to reduce ticket count (both likely target `CLAUDE.md` — `claude/reference/` was deleted in commit `08d1102` and is no longer a candidate location).

## Research context

**OQ3 — `MUST`-escalation norm**: Anthropic's skill-authoring doc still endorses escalating to `MUST`-style language when an observed failure shows Claude is skipping a rule, even while the migration guide says "dial back aggressive imperatives." The reconciliation ("default soft, escalate on observed failure") is currently an inference, not a documented policy. Decision needed: when we encounter a post-migration `MUST` escalation, do we keep it or normalize it back and re-observe?

**OQ6 — Tone regression**: 4.7 is documented as "less conciliatory, fewer emoji" compared to 4.6. Voice/tone regression is a user-experience concern, not a correctness one. Decision needed: do we add a warmth-setting directive to `CLAUDE.md` or global settings, or accept the new voice?

## Deliverable

Short written policy entries in `CLAUDE.md` (or `~/.claude/rules/cortex-*.md` if scoped to global rules per the cortex deployment model — see #120/#121), answering both questions. Keep each to a paragraph or two — these are durable norms, not prescriptions.

## Dependencies

- Originally blocked by #085 (now `status: complete` as of 2026-04-21). Its dispatch-skill audit produced the empirical input for OQ3. OQ6 (tone regression) needs no evidence; it's a user-preference decision that could ship independently, but stays in this consolidated ticket.
- Previously also listed #083 and #084; those were removed after critical review flagged them as evidence-mismatched blockers — #083 produces migration automation diff and #084 produces reference-loading semantics, neither of which calibrates the MUST-escalation policy.

## Scope

- Policy documentation only, no code changes
- Two decisions, not three — if another policy question surfaces later, it gets its own ticket

## Resolution (2026-05-04)

OQ3 lands as Alternative A (default soft, escalate on observed failure). FM-1 (drift) is mitigated by the R2 artifact-bound evidence requirement; FM-2 (tone-as-correctness creep) by the R4 "tone perception" carve-out; FM-5 (MUST-as-effort-workaround) by the R3 effort-first dispatch clause. Pre-existing MUSTs are grandfathered. Re-evaluation triggers in R8.

OQ6 lands as Alternative I (no shipped tone directive). R6 records the user-self-action recommendation (`Use a warm, collaborative tone…` in personal `~/.claude/CLAUDE.md`) with an explicit epistemic-honest caveat about CLAUDE.md tone overrides having inconsistent leverage against Claude Code's built-in system-prompt tone section (per support.tools analysis). R7 re-evaluation triggers include (d) — empirical rules-file leverage test — pre-filed as backlog #157.
