# Specify Phase

Structured interview to surface hidden requirements, edge cases, and priorities before planning. Runs for both tiers — adapts depth to what research already makes clear.

## Protocol

### 1. Load Context

Read `cortex/lifecycle/{feature}/research.md` (codebase analysis + open questions) and `cortex/lifecycle.config.md` if it exists. Load requirements via the shared protocol — read `load-requirements.md` at the lifecycle-resolved, propagated path (see lifecycle SKILL.md "Reference-path propagation") and follow it; if no `cortex/requirements/` exists, note it and proceed. Use requirements to avoid re-asking settled questions — focus the interview on what they don't cover. If a needed concept isn't in the glossary, surface the term in the next requirements interview.

### 2. Structured Interview

For each area below, first assess from research + feature description whether the answer is already evident:
- **Already clear** → state what you found, move on (don't confirm the obvious).
- **Partially covered** → ask only about the gaps.
- **Unclear** → run the full interview for that area.

Areas, in sequence (adapt on answers):
- **Problem statement** — what it solves, who benefits, what happens if unbuilt.
- **Requirements** — per requirement, acceptance criteria (how you'll know it works); probe must-have vs nice-to-have, measurable success, user-facing vs internal.
- **ADR posture (in-the-moment)** — if a requirement decision meets `cortex/adr/README.md`'s three-criteria gate (hard to reverse + surprising without context + real trade-off), draft it in the spec's `## Proposed ADR` in the same turn rather than deferring.
- **Non-requirements** — what it intentionally does NOT do; push back on vague boundaries.
- **Edge cases** — unexpected inputs, unavailable systems, unexpected user behavior; challenge optimistic assumptions.
- **Technical constraints** — from the research findings: performance, compatibility, integration boundaries.

Probe — don't just confirm what's written. Present questions via the AskUserQuestion tool (not plain markdown), continuing until ambiguities resolve.

**Interview posture (interactive default)**: assume the work is verified interactively — the user is in-session to confirm acceptance criteria. Don't interrogate how criteria would be verified autonomously or overnight; in-session verification is a first-class, legitimate outcome. This governs posture only — §3's acceptance-criteria format still prefers testable criteria and does not relax binary-checkability.

**Cadence**: one question at a time, waiting for each answer — never batch (the canonical rule at `skills/interview/references/loop.md`).

**File-path citation**: for a code-derived acceptance criterion, name the grounding file path so the user can flag a wrong location before code is written. Omit the citation for intent-only criteria — don't fabricate.

**Verification posture**: verify any file path or function-behavior claim against the actual code before accepting the user's confirmation (§2b's end-of-interview check still runs).

**Edge-case invention**: when a requirement's criteria look under-specified, invent one concrete stress scenario and surface it before locking. Skip when the criteria are already tight.

### 2a. Research Confidence Check

**Missing research.md guard**: before any signal evaluation, if `cortex/lifecycle/{feature}/research.md` does NOT exist, announce that Research must run before Specify, then trigger the cycle-1 loop-back: log a `confidence_check` event with `"signals": ["research.md missing"]` and `"action": "loop_back"`, and transition to Research bypassing /refine's Sufficiency Check — don't evaluate C1/C2/C3. If it exists, evaluate the signals.

After the interview, assess whether `research.md` is still sufficient to write accurate acceptance criteria — three pass/fail signals:
- **C1 (Approach invalidated)** — an answer made the researched approach unusable (abandon, not adjust). Only fires when the approach can't be used at all; still-viable-with-modifications does not.
- **C2 (Investigation unknowns)** — unknowns surfaced that require reading codebase files not in `research.md`. Only fires when new file-level investigation is required; answerable from research or user input does not.
- **C3 (Uncovered dependencies)** — constraints/dependencies rely on codebase patterns not in `research.md`, and accurate criteria are impossible without them. Only fires when the patterns are required, not merely helpful.

> Do not re-evaluate clarify.md §6 staleness signals — checked at Research entry.

**All three pass** → proceed to §3, no event logged, no acknowledgment.

**Cycle count**: `current_cycle = (count of confidence_check events in cortex/lifecycle/{feature}/events.log) + 1` (1 on the first pass).

**Any signal flagged AND cycle = 1**: present the flagged signals as a bulleted list (one per signal, ≤15 words, no prose outside the bullets), state Research must re-run, then transition to Research **bypassing /refine's Sufficiency Check** (treat `research.md` as invalidated and re-run from scratch — else Step 4 may declare it sufficient and skip back to Spec).

**Any signal flagged AND cycle ≥ 2**: present the flagged signals as in cycle 1, then ask (via AskUserQuestion) whether to loop back to Research or proceed to §3. Loop back → repeat the cycle-1 procedure; proceed → §3.

### 2b. Pre-Write Checks

Run before drafting §3; all silent on pass (proceed to §3 with no output). On failure, surface only the failing claim/item as a single terse bullet (≤15 words) — no preamble, no restatement, no pass-side narration.

**Verification check** — verify any code-behavior claim against actual code before writing it:
- **Git command syntax** — for a `git diff`, confirm two-dot (`A..B`) vs three-dot (`A...B`) semantics.
- **Function behavior** — read the function before asserting what it does/accepts/returns; don't infer from name or call sites alone.
- **File paths** — verify the file exists at the path before referencing it in a requirement.
- **State ownership** — confirm which function owns a write and when it runs (an in-memory increment can be silently overwritten by an end-of-batch writeback owner).

**Research cross-check** — re-read `research.md` in full; for each explicit behavioral requirement, constraint, guard, or edge case, verify it appears in the spec's Requirements, Edge Cases, or Technical Constraints. A research item absent from the spec is a silent omission, not a scope decision — if intentional, note it in Non-Requirements or Open Decisions.

**Open Decision resolution** — before adding to `## Open Decisions`, try in order: (1) resolve from `research.md` and fold into Requirements/Constraints/body; (2) ask the user now (they're present; the implementer can't resolve it mid-implementation); (3) defer only when the decision needs implementation-level context unobtainable without writing/reading the code. A deferred item must include a one-sentence reason why it can't be resolved at spec time.

### 3. Write Specification Artifact

Compile answers into `cortex/lifecycle/{feature}/spec.md`.

**If §2a ended with the user declining to loop back** (a `confidence_check` event with `"action": "declined"` in `cortex/lifecycle/{feature}/events.log`): before `## Problem Statement`, prepend a short advisory blockquote noting the confidence check found unresolved research gaps (requirements below may be incomplete there; downstream phases proceed normally), one bullet per flagged signal. Omit it when §2a passed cleanly or no loop-back occurred.

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
[One-paragraph context, decision, and trade-off, suitable for promotion into cortex/adr/<NNNN-slug>.md.]
-->
```

### 3a. Orchestrator Review

Before user presentation, read and follow the orchestrator-review protocol (the propagated `<target>` path — the **orchestrator-review** target) for the `specify` phase. It must pass before approval.

### 3b. Critical Review

After orchestrator review passes, read tier and criticality (rules: criticality-matrix.md §Reading lifecycle state — the propagated `<target>` path):

```bash
cortex-lifecycle-state --feature {feature} --field tier
cortex-lifecycle-state --feature {feature} --field criticality
```

Also resolve the active backlog backend once via `cortex-read-backlog-backend` (argless) before deciding to skip — the non-local seed-tier fail-safe below keys on it, and the gate-protocol reference is consulted only on the skip branch, so the backend read happens here at the inline decision.

**Run** when `tier = complex` AND `criticality ∈ {medium, high, critical}`: invoke the `critical-review` skill with the spec artifact; present the synthesis to the user before spec approval.

**Non-local seed-tier fail-safe**: when the resolved backend ≠ `cortex-backlog` AND the run condition above did not fire because `tier = simple` AND `cortex/lifecycle/{feature}/research.md` exists, invoke the `critical-review` skill with the spec artifact and present its synthesis before spec approval rather than skipping. (Rationale — why the `simple` seed is un-reconciled and why the local `cortex-backlog` path is exempt — lives in critical-review-gate.md's Non-Local Seed-Tier Rule.)

Otherwise, read and follow the critical-review gate protocol (the propagated `<target>` path — the **critical-review-gate** target) for the `specify` phase.

### 4. User Approval

Present the specification summary via the AskUserQuestion tool with these approval-surface fields:
- **Produced** (one-line summary of the artifact)
- **Value** (what problem this solves and why it's worth building now — flag weak value cases explicitly)
- **Trade-offs** (alternatives considered and rationale for the chosen approach)
- **Proposed ADRs** (comma-separated `<NNNN-slug>` list from `## Proposed ADR`; `None` when that section's body is `None considered.`)

Enumerate the options explicitly as `Approve` | `Request changes` | `Cancel`. Route on the response:

- **Approve** → append `spec_approved`, then §5's `phase_transition`, then auto-advance to Plan (no re-confirmation): `cortex-lifecycle-event spec-approved --feature <name>`
- **Request changes** → collect the changes, revise the spec, re-present the surface. No `spec_approved` on revision loops — only the final Approve emits it.
- **Cancel** → append `lifecycle_cancelled` and halt (resume by re-invoking `/cortex-core:lifecycle`).

### 5. Transition

On `Approve`, append a `phase_transition` event:

`cortex-lifecycle-event phase-transition --feature <name> --from specify --to plan`

## Hard Gate

Do NOT write implementation code during this phase. Define WHAT to build, not HOW.
