---
schema_version: "1"
uuid: f3b4b249-b40c-4d70-a06c-f3e95030ba21
title: "Audit dispatch-skill prompts and reference docs for 4.7 at-risk patterns"
status: refined
priority: high
type: feature
created: 2026-04-18
updated: 2026-04-21
parent: "82"
tags: [opus-4-7-harness-adaptation, skills]
discovery_source: research/opus-4-7-harness-adaptation/research.md
blocked-by: [83]
session_id: 0807d4ab-1191-4d06-b82e-85d0470608d2
lifecycle_phase: specify
lifecycle_slug: audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns
complexity: complex
criticality: high
spec: lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/spec.md
areas: [skills]
---

# Audit dispatch-skill prompts and reference docs for 4.7 at-risk patterns

## Motivation

DR-2 in the research artifact scopes this audit to the 7 skills that dispatch subagents via the Agent tool — these are the surface where Anthropic's own 4.7 guidance names regressions ("fewer subagents by default", "fewer tool calls") and where all five observed failures (F1–F5) occurred.

## Research context

Prior art: backlog #053 (complete) softened aggressive imperatives (`CRITICAL:`, `MUST`, `ALWAYS`, `NEVER`, `IMPORTANT:`, `make sure to`, etc.) for the 4.5/4.6 migration. This ticket audits six *additional* at-risk patterns that 4.7's stricter literalism exposes — patterns #053 did not cover.

See `research/opus-4-7-harness-adaptation/research.md` §"Six at-risk patterns not covered by #053" for the full pattern table and example sites.

## Size acknowledgment

The M frontmatter size is provisional and likely undersized. Baseline comparison: backlog #053 (complete) was `complexity: complex, criticality: high`, covering 9 skills × 2 axes (~18 work cells) across ~2185 lines. #85 as written covers (7 skills + 5 reference files) × 7 patterns ≈ 84 work cells on a comparable line base. Expect the lifecycle Plan phase to confirm "complex" sizing and possibly recommend decomposition into per-methodology tasks (see Methodology dimensions below).

## Audit surface (DR-2)

- **7 dispatch skills**: `critical-review`, `research`, `pr-review`, `discovery`, `lifecycle`, `diagnose`, `overnight` (SKILL.md + `references/*.md`)
- **5 reference files**: `claude/reference/claude-skills.md`, `context-file-authoring.md`, `output-floors.md`, `parallel-agents.md`, `verification-mindset.md`

## Methodology dimensions (three distinct audit passes, not one)

This ticket stacks three methodologies that share the same surface but have different execution logic. Plan phase should treat them as separate passes:

- **Pass 1 — Pattern-grep audit** (P1–P6 on the 12 surfaces). Mostly grep-amenable with per-site judgment at flagged matches. Pattern-bucketed commits recommended (one commit per pattern across all files), matching #053's verification strategy.
- **Pass 2 — Reference-file negation-only remediation** (P3 subclass). Scope narrowed post-#084 spike: 4 of 5 reference files (`claude-skills.md`, `context-file-authoring.md`, `parallel-agents.md`, `output-floors.md`) verified to load reliably under 4.7 and need no P3 remediation. Pass 2 is now scoped to `verification-mindset.md` alone, whose Q1 LOW verdict (15 historical JSONL hits but 0 probe-time Reads across 6 probes) requires validation before any rewrite. Per #084's reopener clause, #085 must run at least one validation probe from an actual git repo with a recent "tests pass" claim — to distinguish "behavior internalized from training" from "file not loading at all" — before designing remediation. If the validation probe shows loading does fire in real-task context, Pass 2 closes with a documentation note and no rewrite.
- **Pass 3 — `consider`-hedge audit (P7)**. Requires `git blame` against #053's commit hashes to identify sites #053 specifically introduced via its `think about → consider` rewrite row. Three-category classification per site: (a) conditional requirement, (b) genuinely optional, (c) polite imperative. Scope may shrink to zero after blame filter — actual `\b[Cc]onsider\b` occurrences in `skills/` are ~9, subset introduced by #053 is unknown.

## At-risk patterns to audit

- **P1**: Double-negation suppression (`omit X entirely — do not emit empty header`)
- **P2**: Ambiguous conditional bypass (`Only X satisfies this check ... If Y, always run Z`)
- **P3**: Negation-only prohibition (`Do not be balanced. Do not cover other angles.`)
- **P4**: Multi-condition gates with implicit short-circuit
- **P5**: Procedural order dependency (`do not omit, reorder, or paraphrase`)
- **P6**: Examples-as-exhaustive lists (`Select from this menu`, `such as`)
- **P7 (from Ask-2 fold-in)**: `consider` / `try to` / `if possible` hedges — see Pass 3 methodology above

## Dependencies and pre-lifecycle scope re-derivation

**Pre-lifecycle read complete (2026-04-20).** Both spike deliverables were reviewed before entering Clarify:

- **#083** (`research/opus-4-7-harness-adaptation/claude-api-migrate-results.md`): `/claude-api migrate` touched only `bin/count-tokens` and `bin/audit-doc` (3-line model-ID swap). No SKILL.md, `claude/reference/*.md`, `Agents.md`, hooks, or settings mutated. Matches the "SDK-only, no prompt changes" branch → **Passes 1, 2, 3 surface unchanged.**
- **#084** (`research/opus-4-7-harness-adaptation/reference-loading-verification.md`): 4/5 reference files verified to load reliably under 4.7 (no P3 work); `verification-mindset.md` is the lone outlier with Q1 LOW verdict. Outcome sits between the ticket's original binary branches → **Pass 2 narrowed (see Pass 2 above); Passes 1 and 3 unchanged.**

Net scope delta: Pass 2 shrinks from ~5 files × P3 to 1 file + one validation probe. Passes 1 and 3 dominate the workload (~72+ work cells across 12 surfaces × 6 patterns for Pass 1 alone). Size frontmatter remains M; Plan phase is still expected to confirm Complex tier and recommend per-pass decomposition.

## Scope exclusions

Preservation rules from #053 are out of scope per DR-1. Specifically (re-attached from #053 adversarial review — do NOT touch these without strong new 4.7-specific evidence):

1. **Security/injection-resistance instructions** — e.g., `research/SKILL.md` untrusted-data warnings and their verbatim copies in agent dispatch prompts.
2. **Output-channel directives** — "present via AskUserQuestion", "append to events.log", "write to lifecycle/{feature}/review.md" and similar control directives.
3. **Control flow gates** — env var checks (e.g., `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` in diagnose), availability checks, "skip entirely when running autonomously" guards.
4. **Output floor field names** — Decisions/Scope delta/Blockers/Next and Produced/Trade-offs/Veto surface/Scope boundaries.
5. **Quoted source material** — Anthropic guidance, user prompts, research findings in quotation marks.
6. **Example code blocks and output templates** — content inside ``` fences.
7. **Section headers** — `## Open Questions`, `## Open Decisions`, `## Epic Reference` (counted by lifecycle complexity heuristics).

Specific anchored preservation decisions from #053 (line numbers from #053's research time; verify before acting):
- `critical-review/SKILL.md` "Do not soften or editorialize" (fights Opus warmth training).
- `critical-review/SKILL.md` distinct-angle rule (load-bearing for parallel-anchoring-free differentiator).
- `research/SKILL.md` empty-agent handling (exact fallback string formats downstream synthesis relies on).
- `research/SKILL.md` contradiction handling (feeds Spec's Open Questions section).
- `diagnose/SKILL.md` root-cause-before-fixes core principle.
- `diagnose/SKILL.md` competing-hypotheses conditions (env var gate + autonomous skip).
- `lifecycle/SKILL.md` epic-research path announcement (defense-in-depth disclosure).
- `lifecycle/SKILL.md` prerequisite-missing warn (safety rail against Plan without research).
- `backlog/SKILL.md` AskUserQuestion directives (output-channel directives).
- `discovery/SKILL.md` "summarize findings, and proceed" (phase-transition floor).

If #084 surfaces new 4.7-specific evidence against any of these, bring to Clarify as an open question before acting.

- Non-dispatch skills (`backlog`, `commit`, `retro`, etc.) are excluded per DR-2's scoping.
