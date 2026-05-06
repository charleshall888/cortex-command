---
schema_version: "1"
uuid: 536b2399-506c-40c8-90da-78abdb01ec8c
title: "Merge clarify and research lifecycle phases into single investigate phase"
type: feature
status: backlog
priority: medium
blocked-by: []
tags: [lifecycle, phase-shape, refine, token-efficiency, six-phase]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/epic-172-audit/research.md
---

# Merge clarify and research lifecycle phases into single investigate phase

Collapse the current 7-phase lifecycle (`clarify → research → spec → plan → implement → review → complete`) to a 6-phase shape (`investigate → spec → plan → implement → review → complete`) by merging Clarify and Research into a single "Investigate" phase. The phase boundary between Clarify and Research is mostly bookkeeping — `refine/SKILL.md:18` already chains them as one delegation, both phases load `requirements/` context with duplicated logic, and Clarify produces no artifact (it's an aim-setting gate before Research's artifact production).

## Context from discovery

Per `research/epic-172-audit/research.md` DR-4 (six-phase lifecycle):

- **Evidence for keeping the split**: distinct retro patterns — Clarify retros are about "intent built on wrong premise," Research retros are about "agent didn't read the file." Different failure surfaces.
- **Evidence supporting merge**: `refine/SKILL.md:18` already chains Clarify → Research → Spec as a single `/cortex-core:refine` delegation; `lifecycle/SKILL.md:210–245` re-orchestrates them with a `phase_transition` event ceremony between. Discovery Bootstrap (`lifecycle/SKILL.md:170–196`) skips Clarify entirely if epic context exists, proving Clarify isn't an artifact-producing phase.
- Both phases load `requirements/` context with duplicated logic at `clarify.md:25–31` and `research.md:23–30`.

The merged "Investigate" phase preserves Clarify's load-bearing What (confidence assessment + critic + ≤5 Q's) and Research's load-bearing What (read-only artifact production + dependency verification + Open-Questions Exit Gate) while dropping the phase-transition ceremony between them.

## What to land

### 1. Merged Investigate phase reference

Create `skills/lifecycle/references/investigate.md` (or repurpose `research.md`) that combines:
- Confidence assessment + critic dispatch + Q&A cap (currently in `clarify.md`)
- Read-only codebase exploration + dependency verification (currently in `research.md`)
- Open Questions Exit Gate (currently in `research.md`)
- Single `requirements/` loading step (deduplicated from current double-load)

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
- A fresh feature lifecycle run completes with phase transitions: `investigate → spec → plan → implement → review → complete`
- An existing in-flight feature with `lifecycle/<feature>/research.md` but no `spec.md` is correctly identified as "investigate phase complete" by phase-detection logic
- Replaying an archived events.log file (with `phase_transition: from=clarify, to=research` events) through `cortex_command/pipeline/parser.py` produces no errors
- Refine skill produces an `investigate→spec` transition event (not `research→specify`)
- `pytest` passes after migration
- Pre-commit dual-source drift hook passes after `just build-plugin`
