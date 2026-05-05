---
schema_version: "1"
uuid: 3d0dcb32-5995-49f6-83f2-89184a8c6c46
title: "Add parent-epic alignment check to refine's clarify-critic"
status: complete
priority: medium
type: feature
created: 2026-05-04
updated: 2026-05-04
blocked-by: []
tags: [refine, clarify-critic, epic-alignment, drift]
discovery_source: research/refine-load-epic-context/research.md
session_id: null
lifecycle_phase: complete
lifecycle_slug: add-parent-epic-alignment-check-to-refine-clarify-critic
complexity: complex
criticality: high
spec: lifecycle/add-parent-epic-alignment-check-to-refine-clarify-critic/spec.md
areas: [skills]
---

# Add parent-epic alignment check to refine's clarify-critic

When `/cortex-interactive:refine` runs on a child ticket whose backlog frontmatter has a `parent:` field, the parent epic's intent should be one of the inputs the clarify-critic step evaluates against. Today, refine has no awareness of the parent epic at any phase — clarified intent statements can drift silently from the epic's higher-level goal.

## Why clarify-critic is the right placement

`clarify-critic.md` already dispatches a fresh general-purpose agent for review (round-2 audit-pattern infrastructure analysis: it's the cortex-command surface that uses fresh-agent dispatch + Apply / Dismiss / Ask per-finding verdicts). Loading parent-epic content into that **fresh-agent critic only** — not into the upstream Clarify worker that produces the clarified intent — avoids the anchoring failure mode that round 1's inline-load proposal had: the worker's clarified intent is authored without epic anchoring; the critic then evaluates the resulting intent against the epic from clean context. This is the worker/auditor separation pattern Anthropic's subagent docs and `arxiv 2412.06593`'s anchoring-bias evidence converge on.

Catching mismatches at clarify-critic — before research dispatch and before spec writing — minimizes blast radius. If the clarified intent is misaligned with the epic, the critic surfaces it as an Apply / Dismiss / Ask finding, the operator dispositions it, and the resulting clarified intent (with alignment notes preserved) hands off to Research with epic-aware scope.

## What the check does

The dispatched fresh-agent critic receives, in addition to its existing inputs (ticket body, clarified intent draft):

- The parent epic's body (read in full when `parent:` is set in the child's frontmatter)
- A brief evaluation rubric: (a) does the clarified intent align with the parent epic's intent? (b) what divergences exist? (c) what considerations should Research investigate to validate or explore those divergences?

The critic emits findings in the existing Apply / Dismiss / Ask shape. Apply: alignment-improving edits to the clarified intent. Dismiss: deliberate divergences justified in-place ("this child intentionally narrows scope per maintainer judgment; epic deliverable deferred"). Ask: genuinely uncertain cases the operator must decide.

Findings tagged as "considerations for Research" propagate forward into the clarified-intent → Research handoff, so the Research dispatch is epic-aware in scope.

## Failure-mode degradation

- Child has no `parent:` field → silently skip the epic-alignment evaluation; clarify-critic proceeds with its existing rubric unchanged
- `parent:` set but file missing → emit a warning into the critic's input ("parent epic <id> referenced but file missing"), skip the alignment evaluation
- `parent:` resolves to a non-epic ticket → load it as "linked context" and run the alignment evaluation anyway (still useful)
- Nested parent chain → load only the direct parent

## Honest scope statement

This catches **commission-class drift visible at clarify time** — when a child's clarified intent diverges from the parent epic's stated intent in a way detectable from the epic body alone.

It explicitly does **not** catch:

- **Research-phase scope expansion** (e.g., ticket 110-style "found 7 implementations instead of 2"). Drift that emerges during research is invisible to a clarify-time check. The auto-fired `/cortex-interactive:critical-review` from `specify.md §3b` is the next-line defense for those cases.
- **Sibling-driven evolution / stale epics**. When sibling children have collectively evolved the epic's intent without the epic being updated, clarify-critic still treats the (stale) epic as ground truth and may flag legitimate sibling-aligned scope as drift. This is the auditor blind-spot #5 documented in the discovery research; addressing it requires reading sibling specs (rejected as too much overhead during decomposition).
- **Refined / in-progress sibling conflicts**. No sibling-ticket awareness in this check.
- **Omission-class drift** (premature closure on epic-chosen approach, inherited framing without re-justification). These are process-level failures invisible from any artifact text; no auditor pattern catches them.

## Discovery context

Full design rationale, drift taxonomy, expanded sample evidence (17 tickets across 5 epics), worker/auditor prior-art research, and rejected-alternative analysis are at `research/refine-load-epic-context/research.md`. Notable rejected alternatives the discovery walked through:

1. **Inline epic load at Clarify worker** — rejected on anchoring-bias grounds (`arxiv 2412.06593`: framing-mitigation instructions are largely ineffective).
2. **S7 item in `orchestrator-review.md`** — rejected because orchestrator-review mandates main-context execution, defeats fresh-reviewer separation, and binary pass/flag verdict scheme has no workable disposition for deliberate-descope (C3) cases like ticket 064.
3. **Critical-review angle at spec-time** — defensible alternative; this ticket's clarify-critic placement was chosen instead because earlier catch (pre-research) has smaller blast radius and uses an already-fresh-agent surface.
4. **Bidirectional design with write-back to parent epic and unrefined siblings** — rejected as too much overhead for the observed drift rate; would be the natural next step if clarify-critic alignment proves insufficient and sibling-evolution drift becomes the dominant failure mode.
