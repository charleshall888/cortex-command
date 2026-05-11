---
schema_version: "1"
uuid: 536b2399-506c-40c8-90da-78abdb01ec8c
title: "Merge clarify and research lifecycle phases into single investigate phase"
type: feature
status: complete
priority: medium
blocked-by: []
tags: [lifecycle, phase-shape, refine, token-efficiency, six-phase]
created: 2026-05-06
updated: 2026-05-11
discovery_source: research/epic-172-audit/research.md
complexity: complex
criticality: high
---

# Merge clarify and research lifecycle phases into single investigate phase

Collapse the current 7-phase lifecycle (`clarify → research → spec → plan → implement → review → complete`) to a 6-phase shape (`investigate → spec → plan → implement → review → complete`) by merging Clarify and Research into a single "Investigate" phase.

**Critical preservation requirement (user-stated):** Clarify's load-bearing function is the **user-blocking question gate** — when a user's prompt is vague or a ticket lacks crisp intent/scope, Clarify forces the agent to ASK the user up to 5 targeted questions BEFORE burning time on read-only codebase exploration. The merged Investigate phase MUST preserve this gate as its first step. Going straight to read-only research on a vague ticket is exactly the failure mode Clarify was designed to prevent (per retros `2026-04-22-2143-lifecycle-140-spec.md:5–9`, `2026-04-21-2108-lifecycle-129.md:13`).

The phase boundary between Clarify and Research is mostly bookkeeping — `refine/SKILL.md:18` already chains them as one delegation, both phases load `requirements/` context with duplicated logic, and Clarify produces no artifact (it's a gate before Research's artifact production). The merge collapses the ceremony, not the function.

## Context from discovery

Per `research/epic-172-audit/research.md` DR-4 (six-phase lifecycle):

- **Evidence for keeping the split**: distinct retro patterns — Clarify retros are about "intent built on wrong premise," Research retros are about "agent didn't read the file." Different failure surfaces.
- **Evidence supporting merge**: `refine/SKILL.md:18` already chains Clarify → Research → Spec as a single `/cortex-core:refine` delegation; `lifecycle/SKILL.md:210–245` re-orchestrates them with a `phase_transition` event ceremony between. Discovery Bootstrap (`lifecycle/SKILL.md:170–196`) skips Clarify entirely if epic context exists, proving Clarify isn't an artifact-producing phase.
- Both phases load `requirements/` context with duplicated logic at `clarify.md:25–31` and `research.md:23–30`.

The merged "Investigate" phase preserves Clarify's load-bearing What (confidence assessment + critic + ≤5 Q's) and Research's load-bearing What (read-only artifact production + dependency verification + Open-Questions Exit Gate) while dropping the phase-transition ceremony between them.

## What to land

### 1. Merged Investigate phase reference — gate-first structure

Create `skills/lifecycle/references/investigate.md` (or repurpose `research.md`) with strict ordering:

**Step 1 (gate, must complete before Step 2 begins):**
- Confidence assessment on intent/scope/alignment dimensions (from current `clarify.md`)
- Clarify-critic dispatch to challenge unsupported high-confidence ratings (from current `clarify-critic.md`)
- **If any dimension is low-confidence: ASK THE USER ≤5 targeted questions and WAIT for answers before continuing.** This is the user-blocking gate — research-phase work must not begin on a vague brief.

**Step 2 (artifact production, gated by Step 1 completion):**
- Read-only codebase exploration + dependency verification (from current `research.md`)
- Single `requirements/` loading step (deduplicated from current double-load across clarify.md:25-31 + research.md:23-30)

**Step 3 (exit gate):**
- Open Questions Exit Gate (from current `research.md`) — research questions either answered or explicitly deferred with rationale

The Step 1 → Step 2 ordering is non-negotiable. The merged file must make it explicit that an agent reading the file cannot start codebase exploration before the confidence-assessment + question-gate completes.

### 2. Phase set update in lifecycle SKILL.md

Update `skills/lifecycle/SKILL.md`:
- Phase enum: `investigate → spec → plan → implement → review → complete` (6 phases)
- Remove `phase_transition` event from clarify→research (single phase now)
- Update phase-detection state machine (`SKILL.md:55–63`) to reflect 6-phase shape

### 3. Refine skill alignment

Update `skills/refine/SKILL.md` to use Investigate phase terminology:
- Refine still chains Investigate → Spec
- Phase transitions emitted: `investigate→spec` (replacing `clarify→research`, `research→specify`)

### 4. Backwards compatibility for existing lifecycle dirs

Existing `lifecycle/<feature>/` dirs may have artifacts at clarify or research phase. Phase-detection logic must:
- Treat presence of `research.md` (without `spec.md`) as "investigate phase complete" (same as before)
- Existing `phase_transition` events with `from: clarify, to: research` continue to be parsed valid in archived events.log files

### 5. Discovery skill alignment

Discovery has its own clarify and research phases (per `skills/discovery/SKILL.md`). Decision: discovery is independent of lifecycle phase set; this ticket does NOT change discovery. (Optional follow-up: align discovery to single Investigate phase too, separate ticket.)

## Touch points

- `skills/lifecycle/references/clarify.md` (merge into investigate.md or delete)
- `skills/lifecycle/references/clarify-critic.md` (preserve; surviving subroutine of investigate)
- `skills/lifecycle/references/research.md` (merge with clarify.md content, rename to investigate.md or keep as research.md with merged content)
- `skills/lifecycle/SKILL.md` (phase enum, state machine, transition events)
- `skills/refine/SKILL.md` (terminology)
- `cortex_command/pipeline/parser.py` (if phase-name strings appear)
- `cortex_command/overnight/events.py` (if phase enum referenced)
- `tests/test_*` (any phase-string assertions)
- All `plugins/cortex-core/skills/*` mirrors auto-regenerated

## Risks

- **Backward compatibility with archived lifecycle dirs**: archived events.log files contain `phase_transition` events with old phase names. Phase-detection and replay logic must remain tolerant.
- **Refine skill chaining**: refine currently uses three discrete phase calls. Collapsing to two may simplify or complicate the orchestration depending on internal structure.
- **Discovery skill divergence**: leaving discovery on the 3-phase clarify/research/decompose shape creates terminology drift between lifecycle and discovery. Acceptable as a temporary state if a follow-up aligns discovery later.

## Verification

- `skills/lifecycle/SKILL.md` phase enum lists exactly 6 phases: investigate, spec, plan, implement, review, complete
- `grep -c "phase: clarify" skills/lifecycle/` returns 0 (or only in deprecated/migration prose)
- `grep -c "from.*clarify.*to.*research" skills/lifecycle/SKILL.md` returns 0 (no clarify→research transition)
- **User-question-gate preserved (load-bearing):** the merged investigate.md / SKILL.md instructs the agent to halt and ASK the user ≤5 targeted questions BEFORE codebase exploration whenever any of intent/scope/alignment dimensions is low-confidence. Verified by:
  - A fresh lifecycle run on a deliberately-vague ticket pauses for user questions before running any Read or Grep tool calls (manual inspection of transcript)
  - `clarify_critic` event is still emitted in events.log for the merged investigate phase
  - The "Step 1 must complete before Step 2 begins" ordering appears in the skill prose with explicit gate language
- A fresh feature lifecycle run with a clear ticket completes with phase transitions: `investigate → spec → plan → implement → review → complete`
- An existing in-flight feature with `lifecycle/<feature>/research.md` but no `spec.md` is correctly identified as "investigate phase complete" by phase-detection logic
- Replaying an archived events.log file (with `phase_transition: from=clarify, to=research` events) through `cortex_command/pipeline/parser.py` produces no errors
- Refine skill produces an `investigate→spec` transition event (not `research→specify`)
- `pytest` passes after migration
- Pre-commit dual-source drift hook passes after `just build-plugin`

## Disposition (2026-05-11): Considered, not implementing

Closed after full refine cycle (clarify → research → spec → critical-review). Decision: keep Clarify and Research as separate phases.

**Rationale**:
- **Structural gate enforcement is load-bearing**: two-file delegation forces the agent through clarify.md before research.md can be read. Merging makes the question gate prose-only — Anthropic's chain-prompts doc explicitly recommends chaining over single-prompt collapse for sequential reliability ("when a single prompt handles everything, Claude can drop steps").
- **Value driver was overstated**: realistic token savings is ~100–150 tokens per refine chain, not the ~700–900 initially implied. Clarity-of-flow gain doesn't outweigh loss of structural gate enforcement.
- **Cited retros argued for preserving Clarify, not collapsing it**: `lifecycle-140-spec.md:5–9` and `lifecycle-129.md:13` are confidence-calibration failures (gate fired but calibration was bad). The fix is stronger calibration, not phase merger.
- **Distinct failure surfaces**: per discovery research, Clarify retros are "intent built on wrong premise" while Research retros are "agent didn't read the file" — separate phases keep failure modes independently auditable.
- **Skill family symmetry**: discovery uses Clarify+Research+Decompose; keeping lifecycle/refine on the same vocabulary aligns the family.

**Audit trail**: full investigation preserved in `lifecycle/merge-clarify-and-research-lifecycle-phases-into-single-investigate-phase/` (research.md, spec.md, critical-review-residue.json, events.log) for future re-evaluation if Anthropic ships an officially-supported gate-enforcement mechanism or the empirical evidence on prose-only ordering shifts.

**Follow-up ticket candidate**: if the ~75-100 token duplication in the `requirements/` load is genuinely irritating, file a small ticket for Alternative D — extract `skills/lifecycle/references/requirements-load.md` and reference it from both clarify.md and research.md. No phase merge needed.
