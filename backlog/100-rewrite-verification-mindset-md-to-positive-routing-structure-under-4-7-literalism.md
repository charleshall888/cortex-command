---
schema_version: "1"
uuid: 279717cb-b00f-46aa-8180-bbad65e7eb4c
title: "Rewrite verification-mindset.md to positive-routing structure under 4.7 literalism"
status: backlog
priority: high
type: feature
created: 2026-04-21
updated: 2026-04-21
parent: "82"
tags: [opus-4-7-harness-adaptation, skills]
blocked-by: [88]
---

# Rewrite verification-mindset.md to positive-routing structure under 4.7 literalism

Split from #85 Pass 2 scope. #85 treats `verification-mindset.md` as read-only; this child ticket owns the whole-file rewrite decision.

## Starting Context

*(Verbatim from `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/research.md` §"verification-mindset.md structural inventory (for Pass 2)" — copied rather than referenced to avoid dangling cross-lifecycle reference.)*

106 lines total. Structural at-risk content:

- **Lines 9–31 (Iron Law + Gate Function)**: Opens with "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE" (negation-only framing) followed by a 5-step positive gate. Under 4.7 literalism, the opening negation may block before the positive gate is reached.
- **Lines 34–42 (Common Failures table)**: negations paired with positive requirements ("Tests pass | requires Test command output: 0 failures") — mitigated.
- **Lines 44–51 (Red Flags - STOP)**: 6-item negation-only list with no positive alternative. **Adversarial flag: compound P3+P6 hazard** (list presented as exhaustive).
- **Lines 85–95 (Common Rationalizations table)**: 2-column excuse/reality format, mitigated.

**Adversarial position**: the entire file is negative-framing. A one-section patch to Red Flags leaves the other four sections unpatched; whichever fires next under 4.7 will be blamed on "patched the wrong section." Consider whole-file rewrite (Iron Law → "Before claiming: positive checklist"; Gate Function → retain with positive framing; Red Flags → "Verification checklist before completion claim"; Rationalizations → delete or convert to "instead of X, do Y").

## Scope

Identify which of Iron Law, Gate Function, Red Flags, Common Failures, and Common Rationalizations sections exhibit P3 failure mode under 4.7 via a validation probe (per #084 reopener clause: real git repo + "tests pass" claim context). Remediate only the failing sections under M1 (positive routing). Preserve the 5-step Gate Function structure as the authoritative positive process regardless of rewrite extent — it is load-bearing.

## Non-requirement

Not committed to "whole-file rewrite" if probe identifies only 1–2 sections as failing. "Whole-file rewrite" in the parent spec is shorthand for "Pass 2's full scope lives in the child"; this ticket may ship a section-level rewrite if its own Research supports it.

## Acceptance

- Probe log committed to this ticket's lifecycle directory.
- Remediated sections structurally positive-routed.
- Ring-fenced Gate Function intact (5-step structure preserved).
