# Specify Phase

An interview that finds hidden requirements, edge cases, and priorities before planning. Go only as deep as research left open.

### 1. Load context

Read `cortex/lifecycle/{feature}/research.md` and `cortex/lifecycle.config.md` if present. Requirements were loaded in Clarify — don't re-load. Use them to avoid asking settled questions, and note any concept missing from the glossary for the next requirements interview.

### 2. Interview

For each area, judge first: **clear** → state it and move on; **partial** → ask only the gaps; **unclear** → full interview. Areas: problem statement (what, who benefits, cost of not building) · requirements (acceptance criteria each; must-have vs nice-to-have) · ADR posture (draft any decision that is hard to reverse, surprising, or a real trade-off into `## Proposed ADR` in the same turn) · non-requirements (push back on vague boundaries) · edge cases (challenge optimistic assumptions) · technical constraints (from research).

<!-- pause: spec-interview-gapfill question -->
Keep asking until nothing is ambiguous. Batch only questions that don't depend on each other.

A criterion may be checked interactively in the session. For a criterion taken from code, name the file it rests on so a wrong location shows up early; for intent-only criteria, leave it out rather than make one up. Where criteria look thin, make up and show one concrete stress scenario before locking.

### 2a. Research confidence check

**No research.md** → announce Research must run first, log a `confidence_check` event with `"signals": ["research.md missing"]` and `"action": "loop_back"`, go to Research and skip its sufficiency check.

Otherwise three signals: **C1** an answer made the researched approach unusable (drop it, not adjust it) · **C2** unknowns that need codebase files research.md lacks · **C3** constraints that rely on codebase patterns research.md lacks. All pass → §3, no event. (Don't re-run clarify.md §6 — that ran at Research entry.) `current_cycle` = `confidence_check` events + 1.

**Flagged, cycle 1** → short bullets, say Research must re-run, go there and skip the sufficiency check (research.md is no longer valid; without the skip Research calls it sufficient and sends you back).

<!-- pause: spec-confidence-loopback question -->
**Flagged, cycle ≥2** → present the same way, then ask: loop back or proceed.

### 2b. Pre-write checks

Say nothing on pass; on failure, one short bullet per failing item.

**Research cross-check** — re-read research.md in full; every behavioral requirement, constraint, guard, and edge case must land in Requirements, Edge Cases, or Technical Constraints. A missing item is an omission, not a scope decision — if you mean to drop it, record it under Non-Requirements or Open Decisions.

<!-- pause: spec-open-decision-ask question -->
**Open Decisions** — before adding one, in order: resolve from research.md and fold in; ask the user now (the implementer can't resolve it mid-implementation); defer only when the decision needs context you can't get without writing code, with a one-sentence reason.

### 3. Write `spec.md`

`cortex/lifecycle/{feature}/spec.md` — WHAT, not HOW; no implementation code. If §2a ended with the user declining to loop back, put a warning blockquote before `## Problem Statement` (one bullet per flagged signal: research gaps unresolved, requirements may be incomplete, downstream proceeds normally).

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

Use the tier and criticality `reconcile-clarify` just set (`cortex-lifecycle-state --feature {feature}` if not in context; that read wins over Clarify's original value). `"corrupted": true` → run the review rather than skip.

**Run** `/cortex-core:critical-review` on the spec, showing its summary before approval, when `tier = complex` AND `criticality ∈ {medium, high, critical}` — or when the backend ≠ `cortex-backlog` AND the condition failed only because `tier = simple` AND research.md exists (a safety net: on a non-local backend Clarify may have been skipped, leaving the default `simple/medium`; the local path reads tier from frontmatter). Otherwise skip to approval. This review runs at spec only; end-of-implementation review catches the rest.

### 4. Approval

<!-- pause: spec-complexity-value-gate question -->
**Complexity/value gate**, whether or not critical-review ran. It fires on 3+ new places that hold state, a new persistent data format or config section, or a subsystem needing per-feature upkeep. Default to full scope; otherwise recommend the smallest cut that keeps the main outcome, reason first, naming what triggered it. Ask only when you don't recommend full scope or confidence is low; else fold it into the approval prompt. The first option ends ` (Recommended)` and opens with the reason; offer the cuts that apply ("drop entirely", "bugs-only", "minimum viable"). This question wins over the Open-Decisions one when both fire.

<!-- pause: spec-approval relayed-consent -->
Present **Produced** (one line), **Value** (the problem solved and why now — flag weak cases), **Trade-offs** (alternatives and rationale), **Proposed ADRs** (`<NNNN-slug>` list or `None`), then `Approve` | `Request changes` | `Cancel` → `--decision approved` / `revise` / `cancelled`:

```bash
cortex-lifecycle-advance spec-approve --feature <name> --decision <approved|cancelled|revise> \
  --backend {resolved} --backlog-file {backlog-filename-slug} \
  --spec-path cortex/lifecycle/{lifecycle-slug}/spec.md \
  [--emit-transition|--no-emit-transition] [--areas <a> <b>|--clear-areas]
```

The verb records consent, writes the spec-exit transition (when the flag says so), and writes `status:refined` + `spec` + `areas` back per backend. Act on the returned `state`; never work it out yourself. `/cortex-core:refine` passes `--no-emit-transition`; only this verb writes the `specify→plan` row.

- `approved` / `approved-direct` → done. `approved-direct` means the verb sent the spec exit down the short road (simple tier, low/medium criticality), which `/cortex-core:build` reads to skip Plan.
- `revise` → nothing recorded; collect changes, revise, re-present. Only the final Approve records consent.
- `cancelled` → `lifecycle_cancelled` recorded; stop.
- `error` → show `message`, stop. Exit 2 → ambiguous backlog slug; apply backlog-writeback.md's rule and re-run. Missing verb → stop and ask the operator to install or upgrade the cortex-command CLI; never record approval, transition, or write-back by hand.
