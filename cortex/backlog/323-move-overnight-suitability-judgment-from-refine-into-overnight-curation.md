---
schema_version: "1"
uuid: af87592d-32ef-4c41-98e9-49ef90e7b3d9
title: Move overnight-suitability judgment from refine into /overnight curation
status: in_progress
priority: low
type: feature
created: 2026-06-25
updated: 2026-06-29
complexity: complex
criticality: high
spec: cortex/lifecycle/move-overnight-suitability-judgment-from-refine/spec.md
areas: ['overnight-runner', 'skills']
lifecycle_phase: plan
---
## Why

When you finish refining a ticket, refine itself decides whether the resulting spec is a good candidate for unattended overnight execution and warns you about it. To make that call it has to infer whether it was run on its own or inside a full lifecycle — which it does by counting phase-transition rows in the event log, a brittle proxy. Two things are wrong: refine is carrying overnight-execution concerns that are not its job, and the warning fires at spec-writing time rather than when you are actually choosing what to run overnight, so it lands too early to act on. The net effect is a bloated refine skill and a suitability judgment made in the wrong place.

## Role

After this lands, the judgment of whether a ticket is fit to run unattended belongs to overnight's interactive curation step, which proposes a vetted run list and lets the operator approve or amend it before anything executes. Refine's responsibility narrows back to a single job — producing an approved spec — and it no longer reasons about overnight execution at all. Overnight becomes the single owner of "what is safe to run while no one is watching," which is the only place that has both a human in the loop at curation time and the full execution context to make the call.

## Integration

The judgment extends overnight's existing selection path rather than adding a new surface. Overnight already runs an interactive curation step: its `cortex overnight prepare` selection emits an envelope of eligible items, batches, and ineligible items with reasons, and the skill presents that summary for operator approval before launch. The suitability auto-drop becomes additional drop-reasons on that same envelope — poor candidates are set aside with a per-item reason alongside the existing ineligibility reasons, the operator reviews and can re-add any of them at the existing approval gate, and on approval the list is frozen. The unattended overnight harness consumes only that frozen list and makes no suitability calls of its own. On the refine side, removing the advisory also removes refine's only dependency on inferring run-mode from the phase-transition event stream; refine's existing behavior of emitting no phase-transition events is deliberately left unchanged, because completing a refined ticket remains a separate operation — the lifecycle pick-up path or an overnight run — rather than a continuation of the same refine session.

## Edges

- The unattended harness must not make suitability judgments; it executes only the human-approved frozen list. All judgment lives in the interactive curation step.
- No drop may be silent: every set-aside candidate must be surfaced with its reason at the approval gate. That reviewable gate is precisely what makes aggressive dropping safe.
- Drops fire on both mechanical signals (an acceptance criterion marked interactive or session-dependent; unresolved open-decisions in the spec) and soft judgment signals (work that needs network or credentials the sandbox lacks, leans on human-visual or human-judgment verification, or is exploratory and under-specified). Bias toward exclusion — keep failure-prone work out by default.
- Non-goal: do not change refine's event-logging boundary. Refine continues to emit no phase-transition events; this ticket explicitly does not "repair" that, because under the bounded-spec-producer model it is correct, not broken.
- Non-goal: leave no residual overnight-suitability or run-mode-detection logic in refine — the advisory and its mode-detection are removed together.
- The advisory's current suitability criteria are the seed for curation's drop logic, not a fresh invention; preserve their meaning when relocating.

## Touch points

- `skills/refine/SKILL.md` — remove the Step 6 "Overnight-candidate advisory (standalone /refine only)" section in full, including the `grep -c '"event": "phase_transition"'` mode-detection and its standalone-vs-lifecycle branching.
- `skills/refine/SKILL.md` §5 — leave the `phase_transition` skip note intact; it is the legitimate boundary, not part of the advisory.
- The `cortex overnight prepare` selection logic (the `cortex_command` overnight prepare module) — extend the eligibility/selection step to also set aside refined-but-poor-fit specs, emitting them with per-item reasons in the existing `selection` envelope (the same channel that already carries ineligible items + reasons). Seed the criteria from the removed refine advisory.
- `skills/overnight/SKILL.md` — the "Select eligible features" and "Present selection summary" steps already surface ineligible-with-reasons for approval; confirm the suitability drops ride that same summary and the operator can re-add before approving.
- `plugins/cortex-core/skills/refine/SKILL.md`, `plugins/cortex-core/skills/overnight/SKILL.md` — regenerate mirrors via `just build-plugin` if the overnight skill body changes.
- Relates to the skill-trimming thread (backlog item 322).