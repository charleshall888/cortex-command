# Specification: favor-long-term-solutions

## Problem Statement

This repo lacks an explicit "solution horizon" axis in its guidance. `cortex/requirements/project.md` and the system prompt cover anti-over-engineering ("Complexity must earn its place", "When in doubt, the simpler solution is correct", "Don't design for hypothetical future requirements"). Nothing names the complementary bias: when redo of a fix is already known to be needed, the agent should propose the durable version rather than a stop-gap. Without this axis, agents may default to the simplest local fix even in cases where a follow-up patch is already on the visible horizon — producing rework and accumulating short-term patches the user did not want. This spec adds the missing axis as a soft positive-routing principle, anchored on *known* redo (not predicted redo) so it does not conflict with existing anti-speculation guidance.

## Phases

- **Phase 1: Add solution-horizon principle** — Add canonical principle to `cortex/requirements/project.md` Philosophy of Work and operational pointer to `CLAUDE.md`.

## Requirements

**Priority classification**: All three requirements below (R1, R2, R3) are **Must-have** — they form the minimum viable change. No Should-have or Could-have requirements were identified; explicit Won't-have boundaries are captured in Non-Requirements.

1. **R1 — Canonical principle in `project.md`**: Add a bold-prefixed `**Solution horizon**` paragraph to the Philosophy of Work section of `cortex/requirements/project.md`, placed immediately after the `**Complexity**` paragraph. The paragraph states the known-redo test (propose the durable version when redo is already known via planned follow-up, multiple known applications, or a nameable sidestepped constraint; otherwise the simpler fix is correct) and the phased-lifecycle carve-out (a deliberately-scoped phase of a multi-phase plan is not a stop-gap). Soft positive-routing language only — no MUST/NEVER/REQUIRED. **Acceptance**: `grep -c '^\*\*Solution horizon\*\*:' cortex/requirements/project.md` returns `1`, AND `grep -c 'known-redo\|already planned\|unplanned-redo\|phased lifecycle\|deliberately-scoped phase' cortex/requirements/project.md` returns ≥`2`, AND `grep -ciE 'MUST|NEVER|REQUIRED|CRITICAL' cortex/requirements/project.md` against the new paragraph block (lines from `**Solution horizon**` through the next blank line) returns `0`. **Phase**: Phase 1: Add solution-horizon principle.

2. **R2 — Operational pointer in `CLAUDE.md`**: Add a new `## Solution horizon` section to `CLAUDE.md`, placed immediately before `## Design principle: prescribe What and Why, not How`. The section contains the one-sentence operational trigger ("Before suggesting a fix, ask whether you already know it will need to be redone…") and a cross-reference pointing to `cortex/requirements/project.md`'s Philosophy of Work for the canonical statement. Soft positive-routing language only. **Acceptance**: `grep -c '^## Solution horizon$' CLAUDE.md` returns `1`, AND the new section appears textually before `## Design principle: prescribe What and Why, not How` (verified by `awk '/^## Solution horizon$/{a=NR} /^## Design principle: prescribe What and Why, not How$/{b=NR} END{exit !(a && b && a < b)}' CLAUDE.md` exits `0`), AND the new section references `cortex/requirements/project.md` (`grep -c 'cortex/requirements/project.md' CLAUDE.md` returns ≥ its prior baseline + 1), AND `grep -ciE 'MUST|NEVER|REQUIRED|CRITICAL' CLAUDE.md` against the new section block returns `0`. **Phase**: Phase 1: Add solution-horizon principle.

3. **R3 — Explicit reconciliation with project.md's "simpler is correct"**: The new `**Solution horizon**` paragraph in `project.md` must contain text that explicitly states the principle does NOT override the **Complexity** philosophy in the no-known-redo case — i.e., that when redo is not already known, the simpler fix remains correct. **Acceptance**: `grep -c 'simpler\|simple' <new-paragraph-block-of-project.md>` returns ≥`1` AND the surrounding sentence expresses the *when-condition* relationship (not an override). Verified by reading the paragraph in review. **Phase**: Phase 1: Add solution-horizon principle.

## Non-Requirements

- Does NOT modify any file in `skills/`, `hooks/`, `claude/`, `bin/`, or `plugins/`. The principle is repo-local; skills are shared cross-repo via the cortex-core plugin and are explicitly out of scope.
- Does NOT add or modify a MUST/NEVER/REQUIRED directive. The MUST-escalation policy in `CLAUDE.md` requires an F-row evidence artifact for new escalations; this lifecycle was initiated as a general principle without a specific incident, so no F-row exists.
- Does NOT modify the existing `**Complexity**` paragraph in `project.md`. The new paragraph constrains it (adds a *when* condition) but does not replace it.
- Does NOT modify the existing `## Design principle: prescribe What and Why, not How` or `## MUST-escalation policy` sections in `CLAUDE.md`.
- Does NOT define an enforcement mechanism (hook, parity test, lint rule). The principle is prose-only.
- Does NOT add a backlog item, retro, or research doc beyond this lifecycle's own artifacts.

## Edge Cases

- **The new paragraph is later misread as endorsing speculative future-proofing**: Mitigated by R3's explicit reconciliation language and by anchoring the heuristic on *known* (not predicted) redo. Implementation review should verify the prose does not invite speculation.
- **A future agent reads CLAUDE.md but not project.md**: CLAUDE.md's new section includes the one-sentence operational trigger in addition to the cross-reference, so the agent has a usable test even without loading project.md.
- **A future agent reads project.md but skips CLAUDE.md**: Not a realistic edge case — CLAUDE.md is always loaded by Claude Code at session start. project.md is the conditionally-loaded surface.
- **The MUST-escalation policy is itself audited and softened/removed in the future**: Independent of this lifecycle. If the policy is removed, the new prose still functions as soft guidance.

## Changes to Existing Behavior

- **ADDED**: A new `**Solution horizon**` paragraph in `cortex/requirements/project.md` Philosophy of Work, alongside existing Complexity / Quality bar / Workflow trimming principles.
- **ADDED**: A new `## Solution horizon` section in `CLAUDE.md`, sibling to the existing `## Design principle: prescribe What and Why, not How` section.
- **MODIFIED**: The effective decision filter agents apply when proposing fixes in this repo — they now consider a known-redo check before defaulting to the simplest local fix. This is a behavioral surface change in the agentic layer's guidance, but no code or skill prose changes accompany it.

## Technical Constraints

- **Soft positive-routing only**: `CLAUDE.md`'s MUST-escalation policy (lines 68–77) requires an evidence artifact (F-row events.log line OR transcript excerpt) before adding any MUST/CRITICAL/REQUIRED escalation. This lifecycle has no F-row evidence (user confirmed "general principle, no specific incident"), so all new prose must use soft positive-routing phrasing. Acceptance R1 and R2 include grep checks against MUST/NEVER/REQUIRED/CRITICAL in the new blocks.
- **Insertion-point anchoring**: R1 anchors on existing structure ("immediately after `**Complexity**`") and R2 anchors on existing structure ("immediately before `## Design principle: prescribe What and Why, not How`"). If those anchor sections move in a concurrent edit, the implementer must re-locate by section heading rather than by line number.
- **No new MUST in project.md either**: The MUST-escalation policy applies repo-wide, not only to CLAUDE.md. The new `**Solution horizon**` paragraph in `project.md` is also constrained to soft positive-routing language.
- **No enforcement gate**: This is intentionally a prose-only change. The repo's parity tests (`bin/cortex-check-parity`, `tests/test_lifecycle_kept_pauses_parity.py`) and lifecycle-config gates do not need to be extended for this principle. Adding a parity test for prose guidance would be itself an example of over-engineering this principle is meant to constrain.

## Open Decisions

None. All design questions were resolved during clarify Q&A (heuristic = known-redo test; surface = dual canonical/pointer split).
