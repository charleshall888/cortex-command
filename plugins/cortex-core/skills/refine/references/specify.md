# Specify Phase

Structured interview to surface hidden requirements, edge cases, and priorities before planning. Runs for both tiers — adapts depth to what research already makes clear.

## Protocol

### 1. Load Context

Read `cortex/lifecycle/{feature}/research.md` (codebase analysis + open questions) and `cortex/lifecycle.config.md` if it exists. Load requirements via the shared protocol (`load-requirements.md` at the lifecycle-resolved, propagated path — see lifecycle SKILL.md "Reference-path propagation"); none found → note it and proceed. Under `/cortex-core:refine`, requirements were already loaded in Clarify — re-read `research.md` but skip the redundant requirements loading. Use requirements to avoid re-asking settled questions, focusing the interview on the gaps; surface any concept missing from the glossary in the next requirements interview.

### 2. Structured Interview

For each area, first assess from research + feature description whether the answer is already evident: **already clear** → state it, move on; **partially covered** → ask only the gaps; **unclear** → run the full interview.

Areas, in sequence (adapt on answers):
- **Problem statement** — what it solves, who benefits, what happens if unbuilt.
- **Requirements** — per requirement, acceptance criteria (how you'll know it works); probe must-have vs nice-to-have, measurable success, user-facing vs internal.
- **ADR posture (in-the-moment)** — draft a hard-to-reverse, surprising, real-trade-off decision into the spec's `## Proposed ADR` in the same turn, rather than deferring.
- **Non-requirements** — what it intentionally does NOT do; push back on vague boundaries.
- **Edge cases** — unexpected inputs, unavailable systems, unexpected user behavior; challenge optimistic assumptions.
- **Technical constraints** — from the research findings: performance, compatibility, integration boundaries.

<!-- pause: spec-interview-gapfill question -->
Probe via the AskUserQuestion tool (not plain markdown), one question at a time, never batch (`skills/interview/references/loop.md`), until ambiguities resolve.

**Interview posture**: interactive, in-session verification is a legitimate default — don't interrogate how criteria would be verified autonomously or overnight. Posture only; §3's acceptance-criteria format still prefers testable, binary-checkable criteria.

**File-path citation**: name the grounding file for a code-derived acceptance criterion (so a wrong location can be flagged before code is written); omit for intent-only criteria — don't fabricate. Verify file-path/function-behavior claims against actual code before accepting the user's confirmation (§2b's check still runs at interview end).

**Edge-case invention**: when a requirement's criteria look under-specified, invent and surface one concrete stress scenario before locking; skip when already tight.

### 2a. Research Confidence Check

**Missing research.md guard**: if `cortex/lifecycle/{feature}/research.md` does NOT exist, announce Research must run before Specify, then trigger the cycle-1 loop-back: log a `confidence_check` event with `"signals": ["research.md missing"]` and `"action": "loop_back"`, transition to Research bypassing /refine's Sufficiency Check — skip C1/C2/C3. Otherwise evaluate the signals below.

After the interview, assess whether `research.md` is still sufficient for accurate acceptance criteria — three pass/fail signals:
- **C1 (Approach invalidated)** — an answer made the researched approach unusable, abandon not adjust (still-viable-with-modifications doesn't fire this).
- **C2 (Investigation unknowns)** — unknowns surfaced requiring codebase files not in `research.md` (answerable from research or user input doesn't fire this).
- **C3 (Uncovered dependencies)** — constraints/dependencies rely on codebase patterns not in `research.md`, without which accurate criteria are impossible (merely helpful patterns don't fire this).

> Do not re-evaluate clarify.md §6 staleness signals — checked at Research entry.

**All three pass** → proceed to §3, no event logged, no acknowledgment.

**Cycle count**: `current_cycle = (count of confidence_check events in cortex/lifecycle/{feature}/events.log) + 1` (1 on the first pass).

**Any signal flagged AND cycle = 1**: present the flagged signals as a bulleted list (≤15 words each, no other prose), state Research must re-run, then transition to Research **bypassing /refine's Sufficiency Check** (`research.md` is invalidated, re-run from scratch — else Step 4 may declare it sufficient and skip back to Spec).

<!-- pause: spec-confidence-loopback question -->
**Any signal flagged AND cycle ≥ 2**: present the flagged signals as in cycle 1, then ask (via AskUserQuestion) whether to loop back to Research or proceed to §3. Loop back → repeat the cycle-1 procedure; proceed → §3.

### 2b. Pre-Write Checks

Runs before drafting §3; silent on pass. On failure, surface only the failing claim/item as a single terse bullet (≤15 words) — no preamble, no restatement, no pass-side narration.

**Verification check** — verify any code-behavior claim against actual code before writing it:
- **Git command syntax** — for a `git diff`, confirm two-dot (`A..B`) vs three-dot (`A...B`) semantics.
- **State ownership** — confirm which function owns a write and when it runs (an in-memory increment can be silently overwritten by an end-of-batch writeback owner).

**Research cross-check** — re-read `research.md` in full; verify every explicit behavioral requirement, constraint, guard, and edge case appears in the spec's Requirements, Edge Cases, or Technical Constraints. An absent research item is a silent omission, not a scope decision — if intentional, note it in Non-Requirements or Open Decisions.

<!-- pause: spec-open-decision-ask question -->
**Open Decision resolution** — before adding to `## Open Decisions`, try in order: (1) resolve from `research.md`, fold into Requirements/Constraints/body; (2) ask the user now (implementer can't resolve mid-implementation); (3) defer only when the decision needs implementation-level context unobtainable without writing/reading code — with a one-sentence reason why.

### 3. Write Specification Artifact

Compile answers into `cortex/lifecycle/{feature}/spec.md`.

**If §2a ended with the user declining to loop back** (a `confidence_check` event with `"action": "declined"`): prepend a short advisory blockquote before `## Problem Statement` — unresolved research gaps found, requirements below may be incomplete, downstream phases proceed normally — one bullet per flagged signal. Omit when §2a passed cleanly or no loop-back occurred.

```markdown
# Specification: {feature}

## Problem Statement
[One paragraph: what this solves, who benefits, why it matters]

## Phases
<!-- Group requirements into phases. ≥1 for complexity=simple, ≥2 for complex. Each phase name must match the **Phase** tag on its requirements. -->
- **Phase 1: <name>** — <one-line goal>

## Requirements
1. [Requirement]: [Acceptance criteria — binary-checkable: (a) command + expected output + pass/fail; (b) observable state naming file + pattern (e.g. `grep -c 'keyword' path` = 1); (c) `Interactive/session-dependent: [rationale]`]. **Phase**: <name>
...

## Non-Requirements
- [What this feature intentionally does NOT do]

## Edge Cases
- [Edge case]: [Expected behavior]

## Changes to Existing Behavior
<!-- Include when this modifies/removes/extends existing behavior (including additions that change a domain's behavioral surface). Omit only for pure-greenfield work in a new domain. -->
- [MODIFIED: existing] → [new]
- [REMOVED: eliminated]
- [ADDED: extending an existing domain]

## Technical Constraints
- [Constraint from research or architecture]

## Open Decisions
- [Only when implementation-level context is required and unavailable at spec time — with a one-sentence reason. Spec-time resolution strongly preferred; ask the user if uncertain.]

## Proposed ADR
None considered.
<!-- Per ADR-shaped decision negotiated in the interview, replace the default with one sub-entry:
### Proposed ADR: <NNNN-slug>
[One-paragraph context, decision, and trade-off, suitable for promotion into an ADR.]
-->
```

### 3a. Orchestrator Review

Before user presentation, read and follow the orchestrator-review protocol (the propagated `<target>` path — the **orchestrator-review** target) plus its Post-Specify checklist (`orchestrator-checklist-specify.md`, sibling of that target) for the `specify` phase. It must pass before approval.

### 3b. Critical Review

After orchestrator review passes, read tier and criticality (rules: criticality-matrix.md §Reading lifecycle state — the propagated `<target>` path):

```bash
cortex-lifecycle-state --feature {feature} --field tier
cortex-lifecycle-state --feature {feature} --field criticality
```

The caller may have escalated tier between Research and Spec — trust this read, not Clarify's value. `"corrupted": true` → treat as requiring review (run the gate), not `simple`-and-skip; canonical rule + full matrix in criticality-matrix.md.

Resolve the active backlog backend once via `cortex-read-backlog-backend` (argless) before deciding to skip — the non-local seed-tier fail-safe below keys on it.

**Run** when `tier = complex` AND `criticality ∈ {medium, high, critical}`: invoke the `critical-review` skill with the spec artifact; present the synthesis before spec approval.

**Non-local seed-tier fail-safe**: also run (rather than skip) when the resolved backend ≠ `cortex-backlog` AND the run condition above didn't fire only because `tier = simple` AND `cortex/lifecycle/{feature}/research.md` exists. (Rationale + the local-`cortex-backlog` exemption: critical-review-gate.md's Non-Local Seed-Tier Rule.)

Otherwise, read and follow the critical-review gate protocol (the propagated `<target>` path — the **critical-review-gate** target) for the `specify` phase.

### 4. User Approval

<!-- pause: spec-complexity-value-gate question -->
**Complexity/value gate** — before the approval surface, gate the spec on complexity/value proportionality (regardless of critical-review). Fire on 3+ new state surfaces, a new persistent data format/config section to maintain, or a subsystem needing ongoing per-feature upkeep. Default full scope; else recommend the smallest downsize preserving the primary outcome, rationale-first: "I recommend X because Y" (citing the driving surface) before the user-facing question. `AskUserQuestion` only when the recommendation isn't full scope or confidence is low; otherwise fold into the approval surface (Approve / Request changes / Cancel), no pick-menu. Lead option `label` ends ` (Recommended)`, `description` opens with the rationale (`Confirm current scope (Recommended)` for full scope, else the downsize labeled `… (Recommended)`). Offer applicable downsizes ("drop entirely", "bugs-only", "minimum viable"), noting when one doesn't apply. When the `## Hard Gate` Open-Decisions row and this gate both fire, this gate's surface flow wins.

<!-- pause: spec-approval relayed-consent -->
Present the specification summary via the AskUserQuestion tool with these approval-surface fields:
- **Produced** — one-line artifact summary.
- **Value** — the problem solved and why it's worth building now; flag weak value cases explicitly.
- **Trade-offs** — alternatives considered, rationale for the chosen approach.
- **Proposed ADRs** — comma-separated `<NNNN-slug>` list from `## Proposed ADR`; `None` when that section's body is `None considered.`

Enumerate the options explicitly as `Approve` | `Request changes` | `Cancel`. Route on the response:

- **Approve** → append `spec_approved`, then §5's `phase_transition`, then auto-advance to Plan (no re-confirmation): `cortex-lifecycle-event spec-approved --feature <name>`
- **Request changes** → collect the changes, revise the spec, re-present the surface. No `spec_approved` on revision loops — only the final Approve emits it.
- **Cancel** → append `lifecycle_cancelled` and halt (resume by re-invoking `/cortex-core:lifecycle`).

### 5. Transition

On `Approve`, append a `phase_transition` event:

`cortex-lifecycle-event phase-transition --feature <name> --from specify --to plan`

Under `/cortex-core:refine`, skip this emission — the `/cortex-core:lifecycle` caller owns phase-transition logging and commit-artifacts; the refine Step-2 `lifecycle_start` sentinel is exempt.

## Hard Gate

Do NOT write implementation code during this phase. Define WHAT to build, not HOW.
