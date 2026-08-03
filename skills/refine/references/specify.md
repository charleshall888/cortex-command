# Specify Phase

Structured interview surfacing hidden requirements, edge cases, and priorities before planning. Both tiers; depth adapts to what research already makes clear.

### 1. Load Context

Read `cortex/lifecycle/{feature}/research.md` and `cortex/lifecycle.config.md` if present. Requirements were loaded in Clarify — don't re-load. Use them to avoid re-asking settled questions; surface any concept missing from the glossary in the next requirements interview.

### 2. Structured Interview

Per area, judge first whether research already answers it: **clear** → state it and move on; **partial** → ask only the gaps; **unclear** → full interview.

Problem statement (what it solves, who benefits, cost of not building) · Requirements (acceptance criteria each; must-have vs nice-to-have) · ADR posture (draft any hard-to-reverse, surprising, real-trade-off decision into `## Proposed ADR` in the same turn — don't defer) · Non-requirements (push back on vague boundaries) · Edge cases (challenge optimistic assumptions) · Technical constraints (from research).

<!-- pause: spec-interview-gapfill question -->
Probe via `AskUserQuestion` until ambiguities resolve; batch only independent questions.

Interactive in-session verification is a legitimate default — don't interrogate how criteria would be verified overnight. Name the grounding file for a code-derived criterion so a wrong location surfaces before code is written; omit rather than fabricate for intent-only criteria. Where criteria look under-specified, invent and surface one concrete stress scenario before locking.

### 2a. Research Confidence Check

**No research.md** → announce Research must run first, log a `confidence_check` event with `"signals": ["research.md missing"]` and `"action": "loop_back"`, transition to Research bypassing the Sufficiency Check.

Otherwise three signals: **C1** an answer made the researched approach unusable (abandon, not adjust) · **C2** unknowns needing codebase files absent from research.md · **C3** constraints relying on codebase patterns absent from research.md.

All pass → §3, no event, no acknowledgment. Don't re-evaluate clarify.md §6's staleness signals — those ran at Research entry.

`current_cycle` = count of `confidence_check` events + 1.

**Flagged, cycle 1** → present the signals as bullets (≤15 words each, no other prose), state Research must re-run, transition to Research **bypassing the Sufficiency Check** — research.md is invalidated, and without the bypass Research declares it sufficient and bounces straight back.

<!-- pause: spec-confidence-loopback question -->
**Flagged, cycle ≥2** → present the same way, then ask via `AskUserQuestion` whether to loop back or proceed.

### 2b. Pre-Write Checks

Silent on pass; on failure surface only the failing item as one bullet (≤15 words).

**Verification** — check code-behavior claims against actual code. Two recurring traps: `git diff` two-dot (`A..B`) vs three-dot (`A...B`), and state ownership (an in-memory increment silently overwritten by an end-of-batch writeback owner).

**Research cross-check** — re-read research.md in full; every behavioral requirement, constraint, guard, and edge case must appear in Requirements, Edge Cases, or Technical Constraints. An absent research item is a silent omission, not a scope decision — if intentional, record it in Non-Requirements or Open Decisions.

<!-- pause: spec-open-decision-ask question -->
**Open Decisions** — before adding one, try in order: resolve from research.md and fold into the body; ask the user now (the implementer can't resolve it mid-implementation); defer only when the decision needs implementation-level context unobtainable without writing code, with a one-sentence reason.

### 3. Write Specification Artifact

Compile into `cortex/lifecycle/{feature}/spec.md`. Define WHAT to build, not HOW — no implementation code. If §2a ended with the user declining to loop back, prepend a short advisory blockquote before `## Problem Statement` — unresolved research gaps, requirements may be incomplete, downstream phases proceed normally — one bullet per flagged signal.

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

### 3a. Orchestrator Review

Run the orchestrator-review protocol (propagated **orchestrator-review** path) for `specify`. It must pass before approval.

### 3b. Critical Review

Use the tier and criticality Step 4's `reconcile-clarify` just ratcheted; read them with `cortex-lifecycle-state --feature {feature}` if they aren't in context. Trust that read over Clarify's original value — the caller may have escalated tier between Research and Spec. `"corrupted": true` → run the gate rather than skipping, never treating it as `simple` (canonical rule: SKILL.md § Criticality).

**Run** `/cortex-core:critical-review` on the spec, presenting the synthesis before approval, when `tier = complex` AND `criticality ∈ {medium, high, critical}` — **or** when the backend ≠ `cortex-backlog` AND the condition failed only because `tier = simple` AND research.md exists. That second arm is a seed-tier fail-safe: on a non-local backend Clarify may have been bypassed, leaving state at the `simple/medium` seed. The local `cortex-backlog` path is exempt — `reconcile-clarify --backlog-slug` re-sources tier from frontmatter on resume. (Backend comes from Step 1's envelope; `cortex-read-backlog-backend` re-reads it only if it isn't in context.)

Otherwise the critical-review gate protocol skips to approval. The gate runs at spec only; the plan phase dispatches none — end-of-implementation review is the backstop.

### 4. User Approval

<!-- pause: spec-complexity-value-gate question -->
**Complexity/value gate**, regardless of critical-review. Fires on 3+ new state surfaces, a new persistent data format or config section to maintain, or a subsystem needing ongoing per-feature upkeep. Default full scope; otherwise recommend the smallest downsize preserving the primary outcome, rationale-first ("I recommend X because Y", citing the driving surface). `AskUserQuestion` only when the recommendation isn't full scope or confidence is low; else fold into the approval surface. The lead `label` ends ` (Recommended)`, its `description` opens with the rationale. Offer applicable downsizes ("drop entirely", "bugs-only", "minimum viable"), noting when one doesn't apply. This surface wins over the Open-Decisions gate when both fire.

<!-- pause: spec-approval relayed-consent -->
Present via `AskUserQuestion` with **Produced** (one-line artifact summary), **Value** (the problem solved and why it's worth building now — flag weak cases explicitly), **Trade-offs** (alternatives and rationale), **Proposed ADRs** (comma-separated `<NNNN-slug>` list, or `None`).

Enumerate options as `Approve` | `Request changes` | `Cancel`, map to `--decision` (`approved` / `revise` / `cancelled`), and hand off. The verb owns this arm's ordered emissions — the consent record, the flag-gated spec-exit transition, and the backend-gated `status:refined` + `spec` + `areas` write-back — so route on the returned `state`, don't re-derive it:

```bash
cortex-lifecycle-advance spec-approve --feature <name> --decision <approved|cancelled|revise> \
  --backend {resolved} --backlog-file {backlog-filename-slug} \
  --spec-path cortex/lifecycle/{lifecycle-slug}/spec.md \
  [--emit-transition|--no-emit-transition] [--areas <a> <b>|--clear-areas]
```

`/cortex-core:refine` passes `--no-emit-transition` — it stops at `spec.md`. This verb is the sole emitter of the `specify→plan` row.

- **`approved`** / **`approved-direct`** → the spec is approved and written back; refine is done. `approved-direct` records that the verb routed the spec exit down the short road (simple tier, low/medium criticality), which `/cortex-core:build` reads to skip the Plan phase.
- **`revise`** → nothing recorded; collect changes, revise, re-present. Only the final Approve records consent.
- **`cancelled`** → `lifecycle_cancelled` recorded; halt.
- **`error`** → surface `message` and halt. **exit 2** → ambiguous backlog slug; apply the build skill's backlog-writeback.md disambiguation and re-run. Missing verb → halt and tell the operator to install or upgrade the cortex-command CLI; never record the approval, transition, or write-back by hand.
