---
schema_version: "1"
uuid: f90dd3eb-bd20-4f98-98db-63377b8b40a6
title: "Extend output-floors.md with M1 Subagent Disposition section"
status: wontfix
priority: medium
type: feature
created: 2026-04-18
updated: 2026-04-29
parent: "82"
tags: [opus-4-7-harness-adaptation, reference-docs]
discovery_source: cortex/research/opus-4-7-harness-adaptation/research.md
session_id: null
lifecycle_phase: null
lifecycle_slug: extend-output-floorsmd-with-m1-subagent-disposition-section
complexity: simple
criticality: high
blocked-by: []
---

# Extend output-floors.md with M1 Subagent Disposition section

## Closure note (2026-04-29)

Closed wontfix. The target file `claude/reference/output-floors.md` was deleted in commit `08d1102` (2026-04-23) along with the rest of `claude/reference/` and `claude/rules/`, as part of retiring shareable-install scaffolding (spec R4/R5). The deletion commit notes that rule and reference content migrations are tracked under tickets #120 and #121, but M1 Subagent Disposition codification was preventive ("for a hypothetical future dispatch-skill site" — see deferred clause below) and the harm is already prevented: F1/F4/F5 fixes shipped via #067/#068/#069 (all complete).

The original blocker #85 has since reached `status: complete`, but the target file's removal makes the ticket as written non-executable. If a future dispatch-skill site surfaces the same M1 mechanism, file a fresh ticket against the new home for skill-authoring guidance (likely `~/.claude/rules/cortex-*.md` per the rules-only deployment model — see #120/#121).

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

## Deferred (2026-04-18)

Deferred behind #085 after a lifecycle research pass surfaced coherence problems that belong upstream of this ticket:

1. **M1 taxonomy may not be a clean category.** Two of DR-6's three canonical phrasings (`silent re-run, surface pass/fail`; `absorb into internal state, emit nothing`) mix routing with gating/length (M3 territory). The "60% of failures are M1" figure depends on that collapse.
2. **Applicability scope gap.** The worked-example most cleanly shaped by M1 (#067) lives in `critical-review/SKILL.md`. `output-floors.md`'s document-level Applicability block excludes `critical-review`. Either the Applicability block must be revised (scope expansion beyond this ticket) or #067 cannot be a worked example.
3. **Agents.md trigger likely under-fires.** Line 25's trigger ("Writing phase transition summaries, approval surfaces, or editing skill output instructions") plausibly does not match subagent-dispatch authoring under 4.7's literal reading. Updating the trigger is outside this ticket's current deliverables.
4. **Harm already prevented.** #067/#068/#069 have all landed (`status: complete`). Codification here is preventive for a hypothetical future dispatch-skill site. `requirements/project.md` favors simpler-when-in-doubt.

**Revisit trigger**: after #085 completes. #085's dispatch-skill audit (Passes 1–3, including P1 pattern classification) is expected to produce empirical evidence on whether M1 is a clean category. If #085 finds coherent M1 patterns across the existing dispatch surface, #086 resumes with a sharper source of truth. If #085 finds M1/M3 blur as suspected, #086 either reopens DR-6 upstream or closes naturally.

Lifecycle artifacts preserved at `lifecycle/extend-output-floorsmd-with-m1-subagent-disposition-section/` — see `research.md` for full research output and the 8 open questions.
