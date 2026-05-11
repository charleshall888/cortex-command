---
schema_version: "1"
uuid: c799c6d4-b846-40ff-814f-41354861bbb4
title: "Investigate epic-172 closure-inaccuracy base rate"
type: spike
status: complete
priority: high
parent: 187
blocked-by: []
tags: [process, closure-quality, epic-172, dr-5]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/lifecycle-discovery-token-audit/research.md
findings: research/epic-172-closure-audit/findings.md
---

# Investigate epic-172 closure-inaccuracy base rate

## Problem

This audit found that ticket #179 was marked `status: complete` 2026-05-11 but the deliverable files (`a-b-downgrade-rubric.md`, `implement-daytime.md`) do not exist; the target line counts (`implement.md` ~210) are not met (actual: 283). #179 is one of 11 child tickets of epic #172 (all closed 2026-05-11). The audit did not sample the other 10 (#173-178, #180-183).

Audit's DR-5 (`research/lifecycle-discovery-token-audit/research.md` DR-5 area) flagged this as a potential systemic closure-quality gap and proposed a project-wide mechanical completion gate. Critical-review challenged that recommendation as extrapolation from N=1: before committing to a structural gate, sample the base rate.

## Why it matters

- A project-wide gate is friction added to every closure. It has to be earned.
- The cost of investigating now (while #172 context is fresh) is low; the cost later (after context decay) is high.
- The outcome shapes whether any follow-up "closure verification" ticket is justified — and what kind. Three failure modes are possible from one observation:
  - **Discipline gap** (reviewers skipping `ls`-level verification): culture/process fix, not tooling.
  - **Scope-drift specific** (acceptance criteria not re-aligned after mid-flight scope changes, as #179 had): scope-change re-acceptance prompt, not closure-time gate.
  - **General closure-inaccuracy**: mechanical completion gate as originally proposed.

Each diagnosis demands a different intervention. The spike's job is to discriminate.

## Constraints

- **Read-only**: no fixes during the spike. Findings feed a follow-up ticket (or none).
- **Sample size**: 2-3 sibling tickets is enough to discriminate "one-off" from "systemic." Larger samples are diminishing returns.
- **Validate against the actual deliverables**: don't trust the ticket's `status` field — re-check the spec's acceptance criteria against current repo state.
- **Honest scoping**: this audit's own `[premise-unverified]` markers means the audit itself doesn't meet DR-5's proposed standard. The spike's recommendation should acknowledge that asymmetry rather than ignore it.

## Out of scope

- Building any tooling.
- Re-opening any tickets to "fix" non-#179 issues found.
- Sampling beyond the 11 epic-172 children unless a sibling clearly points outside that scope.

## Acceptance signal

- 2-3 sibling tickets of #172 sampled; each compared against its spec's acceptance criteria.
- For each sample: closure-quality verdict (clean / scope-drift confound / discipline gap / other).
- A summary findings document at `research/epic-172-closure-audit/findings.md` (or similar) committed alongside the spike completion.
- A clear recommendation: was #179 a one-off, or is closure-inaccuracy systemic? If systemic, which failure mode dominates? Does that motivate a follow-up ticket, and what kind?

## Research hooks

- Which 2-3 tickets to sample? Pick a mix: at least one that did NOT undergo scope changes (control), at least one that did (variable). Candidates by recall: #173 (literal-bug-fix), #178 (skill-creator-lens, which touched many files), #181 (test infrastructure).
- What's the sampling protocol? For each ticket: read the spec, re-derive acceptance criteria, check current repo state against them, document gaps.
- Are there closure-quality signals beyond "files exist and match line counts"? E.g., behavior tests pass, downstream tickets that referenced this one still work, the implementation actually solved the problem the spec named.
- Should the spike examine the closure mechanism itself (who/what marked status:complete; was a checklist run; is there a transcript)? If lifecycle telemetry exists for closure transitions, mine it.

The audit's DR-5 (post-critical-review) and the alternative-exploration outputs frame the three diagnosis options; treat those as evidence, not pre-decided answers.
