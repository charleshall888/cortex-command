# Specification: audit-auto-memory

## Problem Statement

An audit of the 5 auto-memory files at `~/.claude/projects/-Users-charlie-hall-Workspaces-cortex-command/memory/` produced 3 PROMOTE and 2 DISCARD verdicts. The three PROMOTE memories carry load-bearing repo-authoring or plugin-workflow guidance that is currently invisible to PR review and the MUST-escalation gate. This spec lands each PROMOTE memory's intent in the canonical visible-rail file for its rail type: two repo-authoring principles into this repo's `CLAUDE.md`, and one plugin-workflow strengthening into `skills/critical-review/SKILL.md` (which ships via the cortex-core plugin to every repo where critical-review is used). Auto-memory disable and existing-file deletion are out of scope — the user owns those steps and will handle them separately.

## Phases

- **Phase 1: Land rails** — codify the 3 PROMOTE memories' contents as visible rails in `CLAUDE.md` (R1, R2) and `skills/critical-review/SKILL.md` (R3).

(One phase. Simple-tier features require ≥1 phase per the lifecycle's `## Phases` schema; this audit's surviving scope does not partition further.)

## Priority (MoSCoW)

All 3 requirements below are **must-have** for a coherent audit landing — each PROMOTE verdict's principle becomes invisible drift if left as memory while the audit's stated purpose is to make these rules visible. There are no **should-have** or **could-have** items in this spec. The Non-Requirements section enumerates the **won't-have** items (including the user-owned disable and deletion work, deliberately scoped out of this spec).

## Requirements

1. **R1 — Land memory #1 (user-facing affordances) as a skill-authoring rail in `CLAUDE.md`**: A new "Skill / phase authoring guidelines" subsection is added to `CLAUDE.md` (placement: between the existing `## Conventions` and `## MUST-escalation policy` sections, or as a labeled subsection within `## Conventions`). Content must include: (a) the directive that phase-boundary audits must identify the user-facing affordance the boundary protects before classifying it as ceremonial, (b) the cross-reference to `skills/lifecycle/SKILL.md`'s "Kept user pauses" inventory as the concrete artifact this principle protects, and to the parity test at `tests/test_lifecycle_kept_pauses_parity.py`, (c) the principle that structural separation is stronger than prose-only enforcement for sequential gates. **Acceptance**: `grep -c "user-facing affordance" CLAUDE.md` ≥ 1 AND `grep -c "Kept user pauses\|kept-pauses" CLAUDE.md` ≥ 1 AND `grep -c "structural separation\|prose-only enforcement" CLAUDE.md` ≥ 1. **Phase**: Phase 1.

2. **R2 — Land memory #3 (prescribe What and Why, not How) as a design-principle rail in `CLAUDE.md`**: A new "Design principle: prescribe What and Why, not How" subsection is added to `CLAUDE.md` (placement: immediately preceding or directly within the existing `## MUST-escalation policy (post-Opus 4.7)` section). Content must include: (a) the rule that skill/hook/lifecycle/template authoring prescribes decisions, gates, output shapes, and intent (What+Why) but resists prescribing step-by-step method (How), (b) the Why — capable models (Opus 4.7+) figure out method themselves; how-prescription wastes tokens and constrains capable agents, (c) a cross-reference to the MUST-escalation policy as the conceptual partner (both are "trust capable models, don't over-prescribe"). **Acceptance**: `grep -c "What and Why\|what and why" CLAUDE.md` ≥ 1 AND `grep -c "Opus 4.7\|capable models" CLAUDE.md` ≥ 1 AND the subsection is positioned adjacent to (preceding, within, or immediately following) the existing `## MUST-escalation policy` section. **Phase**: Phase 1.

3. **R3 — Land memory #4 (measure don't re-read) as a critical-review Step 4 anchor-check strengthening**: `skills/critical-review/SKILL.md` Step 4 is extended so the existing anchor-check sentence at line ~104 — "Anchor-checks: dismissals must be pointable to artifact text, not memory; resolutions must rest on new evidence, not prior reasoning." — is followed by a one-sentence operationalization: when a reviewer cites a specific empirical claim (latency, file size, blast radius, baseline behavior), the orchestrator runs the actual measurement (`time`, `wc -c`, grep) before classifying Apply/Dismiss; re-reading the artifact text is not "new evidence." The existing sentence is preserved verbatim. **Acceptance**: `grep -c "new evidence, not prior reasoning" skills/critical-review/SKILL.md` ≥ 1 (existing sentence preserved) AND `grep -ci "measurement\|measure" skills/critical-review/SKILL.md` ≥ 1 within Step 4 AND `grep -c "time.*wc.*grep\|wc -c\|empirical claim" skills/critical-review/SKILL.md` ≥ 1. **Phase**: Phase 1.

## Non-Requirements

- **Auto-memory disable policy in `CLAUDE.md`.** User owns this — they will handle turning off auto-memory through their preferred mechanism.
- **Cross-referencing auto-memory in the MUST-escalation policy.** Moot — the disable lives outside this spec.
- **Deleting the 5 existing memory files** (`feedback_*.md` and `MEMORY.md`). User-owned cleanup. The 2 DISCARD verdicts (memories #2 and #5) justify deletion; the 3 PROMOTE files become redundant once R1–R3 land. The user handles execution.
- **A `PreToolUse` / `PostToolUse` hook enforcing memory-write blocks.** Out of scope for this spec; user's disable mechanism is the user's call.
- **New `MUST` / `CRITICAL` / `REQUIRED` prescriptive language anywhere.** Per the MUST-escalation policy at `CLAUDE.md:52`, no new MUSTs without evidence-artifact links. R1–R3 use soft positive-routing phrasing throughout.
- **Promoting memories #2 (commit-to-recommendation) or #5 (parallel-sessions inline default).** Triage verdict is DISCARD for both (see `research.md`); no rail is authored from them in this spec.
- **Modifying the harness system prompt's auto-memory text.** Outside this repo's surface; not a sensible scope for any cortex-command lifecycle.
- **Touching auto-memory directories for other projects** under `~/.claude/projects/`.

## Edge Cases

- **R3 line-number drift**: the spec cites `skills/critical-review/SKILL.md:104` as the anchor-check location, but line numbers drift as the file evolves. R3's acceptance criteria use grep counts and "within Step 4" state, not literal line numbers, so the test remains stable across reasonable edits. The implementer verifies the existing sentence is preserved by exact-match grep, not by line position.
- **R1/R2 placement collision**: both new subsections are positioned near the existing `## Conventions` / `## MUST-escalation policy` boundary. The implementer must choose an ordering (R1 before R2 or vice versa) and a heading level consistent with the rest of `CLAUDE.md`; either ordering satisfies acceptance.
- **Mirror regeneration on `skills/critical-review/SKILL.md` edit**: the dual-source pre-commit hook (`just setup-githooks`) regenerates `plugins/cortex-core/skills/critical-review/SKILL.md`. The implementer commits both the canonical source edit and the regenerated mirror; otherwise the pre-commit hook fails and the commit is rejected.
- **CLAUDE.md edits don't trigger a mirror**: `CLAUDE.md` is not part of the dual-source mirror. R1 and R2 are single-file edits with no companion mirror commit needed.

## Changes to Existing Behavior

- **ADDED**: `CLAUDE.md` § "Skill / phase authoring guidelines" subsection codifying memory #1's principle (R1).
- **ADDED**: `CLAUDE.md` § "Design principle: prescribe What and Why, not How" subsection codifying memory #3's principle (R2).
- **MODIFIED**: `skills/critical-review/SKILL.md` Step 4 — anchor-check sentence preserved, operationalization sentence added so "new evidence" explicitly means measurement, not re-read (R3). Mirror regenerated at `plugins/cortex-core/skills/critical-review/SKILL.md`.

## Technical Constraints

- The MUST-escalation policy at `CLAUDE.md:52` applies: no new MUST/CRITICAL/REQUIRED language is permitted in any of R1–R3 without an evidence-artifact link. This spec uses soft positive-routing phrasing throughout; implementation must preserve that posture.
- Edits to `skills/` require lifecycle structure per `CLAUDE.md` Conventions — this lifecycle satisfies the requirement for R3.
- The dual-source pre-commit hook (`just setup-githooks`) mirrors `skills/`, `hooks/`, and `bin/` into `plugins/cortex-core/`. R3's edit to `skills/critical-review/SKILL.md` will trigger mirror regeneration; the implementer must commit the mirrored copy as well.
- Memory #4's anchor-check sentence ("resolutions must rest on new evidence, not prior reasoning") is already verbatim at `skills/critical-review/SKILL.md:104`. R3 strengthens by appending an operationalization sentence; it does not duplicate or replace the existing sentence.
- The kept-pauses parity test at `tests/test_lifecycle_kept_pauses_parity.py` enforces ±20-line tolerance for the inventory entries. R1's cross-reference cites the inventory section by name (not enumerated lines), so the parity test is unaffected.

## Open Decisions

None. All design choices were resolved during research and the §2b Open Decision Resolution check.
