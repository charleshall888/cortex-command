# Specify Phase

Structured interview surfacing hidden requirements, edge cases, and priorities before planning; depth adapts to what research already settles.

### 1. Load context

Read `cortex/lifecycle/{feature}/research.md` and `cortex/lifecycle.config.md` if present. Requirements were loaded in Clarify — don't re-load; use them to avoid re-asking settled questions, and note any concept missing from the glossary for the next requirements interview.

### 2. Interview

Per area, judge first: **clear** → state it and move on; **partial** → ask only the gaps; **unclear** → full interview. Areas: problem statement (what, who benefits, cost of not building) · requirements (acceptance criteria each; must-have vs nice-to-have) · ADR posture (draft any hard-to-reverse, surprising, real-trade-off decision into `## Proposed ADR` in the same turn) · non-requirements (push back on vague boundaries) · edge cases (challenge optimistic assumptions) · technical constraints (from research).

<!-- pause: spec-interview-gapfill question -->
Probe until ambiguities resolve; batch only independent questions.

Interactive in-session verification is a legitimate criterion form. Name the grounding file for a code-derived criterion so a wrong location surfaces early; omit rather than fabricate for intent-only criteria. Where criteria look thin, invent and surface one concrete stress scenario before locking.

### 2a. Research confidence check

**No research.md** → announce Research must run first, log a `confidence_check` event with `"signals": ["research.md missing"]` and `"action": "loop_back"`, go to Research bypassing its sufficiency check.

Otherwise three signals: **C1** an answer made the researched approach unusable (abandon, not adjust) · **C2** unknowns needing codebase files absent from research.md · **C3** constraints relying on codebase patterns absent from research.md. All pass → §3, no event. (Don't re-run clarify.md §6 — that ran at Research entry.) `current_cycle` = `confidence_check` events + 1.

**Flagged, cycle 1** → terse bullets, state Research must re-run, go there bypassing the sufficiency check (research.md is invalidated; without the bypass Research declares it sufficient and bounces back).

<!-- pause: spec-confidence-loopback question -->
**Flagged, cycle ≥2** → present the same way, then ask: loop back or proceed.

### 2b. Pre-write checks

Silent on pass; on failure one terse bullet per failing item.

**Research cross-check** — re-read research.md in full; every behavioral requirement, constraint, guard, and edge case must land in Requirements, Edge Cases, or Technical Constraints. An absent item is a silent omission, not a scope decision — if intentional, record it under Non-Requirements or Open Decisions.

<!-- pause: spec-open-decision-ask question -->
**Open Decisions** — before adding one, in order: resolve from research.md and fold in; ask the user now (the implementer can't resolve it mid-implementation); defer only when the decision needs implementation-level context unobtainable without writing code, with a one-sentence reason.

### 3. Write `spec.md`

`cortex/lifecycle/{feature}/spec.md` — WHAT, not HOW; no implementation code. If §2a ended with the user declining to loop back, prepend an advisory blockquote before `## Problem Statement` (one bullet per flagged signal: research gaps unresolved, requirements may be incomplete, downstream proceeds normally).

```markdown
# Specification: {feature}

## Problem Statement
[One paragraph: what this solves, who benefits, why it matters]

## Phases
<!-- ≥1 for complexity=simple, ≥2 for complex. Each phase name matches the **Phase** tag on its requirements. -->
- **Phase 1: <name>** — <one-line goal>

## Requirements
1. [Requirement]: [Acceptance criteria — binary-checkable: (a) command + expected output + pass/fail; (b) observable state naming file + pattern; (c) `Interactive/session-dependent: [rationale]`]. **Phase**: <name>

## Non-Requirements
## Edge Cases
- [Edge case]: [Expected behavior]

## Changes to Existing Behavior
<!-- MODIFIED / REMOVED / ADDED. Omit only for pure-greenfield work in a new domain. -->

## Technical Constraints

## Open Decisions
<!-- Only when implementation-level context is required and unavailable at spec time, with a one-sentence reason. -->

## Proposed ADR
None considered.
<!-- Replace with `### Proposed ADR: <NNNN-slug>` + one paragraph of context, decision, and trade-off. -->
```

### 3a. Orchestrator review

Run the orchestrator-review protocol (propagated **orchestrator-review** path) for `specify`; it must pass before approval.

### 3b. Critical review

Use the tier and criticality `reconcile-clarify` just ratcheted (`cortex-lifecycle-state --feature {feature}` if not in context; that read wins over Clarify's original value). `"corrupted": true` → run the gate rather than skip.

**Run** `/cortex-core:critical-review` on the spec, presenting the synthesis before approval, when `tier = complex` AND `criticality ∈ {medium, high, critical}` — or when the backend ≠ `cortex-backlog` AND the condition failed only because `tier = simple` AND research.md exists (a seed-tier fail-safe: on a non-local backend Clarify may have been bypassed, leaving the `simple/medium` seed; the local path re-sources tier from frontmatter). Otherwise skip to approval. The gate runs at spec only; end-of-implementation review is the backstop.

### 4. Approval

<!-- pause: spec-complexity-value-gate question -->
**Complexity/value gate**, regardless of critical-review: fires on 3+ new state surfaces, a new persistent data format or config section, or a subsystem needing per-feature upkeep. Default full scope; otherwise recommend the smallest downsize preserving the primary outcome, rationale-first, citing the driving surface. Ask only when the recommendation isn't full scope or confidence is low; else fold into the approval surface. The lead option ends ` (Recommended)` and opens with the rationale; offer applicable downsizes ("drop entirely", "bugs-only", "minimum viable"). This surface wins over the Open-Decisions gate when both fire.

<!-- pause: spec-approval relayed-consent -->
Present **Produced** (one line), **Value** (the problem solved and why now — flag weak cases), **Trade-offs** (alternatives and rationale), **Proposed ADRs** (`<NNNN-slug>` list or `None`), then `Approve` | `Request changes` | `Cancel` → `--decision approved` / `revise` / `cancelled`:

```bash
cortex-lifecycle-advance spec-approve --feature <name> --decision <approved|cancelled|revise> \
  --backend {resolved} --backlog-file {backlog-filename-slug} \
  --spec-path cortex/lifecycle/{lifecycle-slug}/spec.md \
  [--emit-transition|--no-emit-transition] [--areas <a> <b>|--clear-areas]
```

The verb owns the consent record, the flag-gated spec-exit transition, and the backend-gated `status:refined` + `spec` + `areas` write-back; route on the returned `state`, never re-derive. `/cortex-core:refine` passes `--no-emit-transition`; this verb is the sole emitter of the `specify→plan` row.

- `approved` / `approved-direct` → done. `approved-direct` means the verb routed the spec exit down the short road (simple tier, low/medium criticality), which `/cortex-core:build` reads to skip Plan.
- `revise` → nothing recorded; collect changes, revise, re-present. Only the final Approve records consent.
- `cancelled` → `lifecycle_cancelled` recorded; halt.
- `error` → surface `message`, halt. Exit 2 → ambiguous backlog slug; apply backlog-writeback.md's rule and re-run. Missing verb → halt and ask the operator to install or upgrade the cortex-command CLI; never record approval, transition, or write-back by hand.
