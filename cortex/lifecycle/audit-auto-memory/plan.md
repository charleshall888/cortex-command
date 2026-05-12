# Plan: audit-auto-memory

## Overview

Land 3 PROMOTE rails from the audit-auto-memory triage: two new `CLAUDE.md` authoring-guideline subsections (R1 + R2) and one operationalization sentence appended to `skills/critical-review/SKILL.md` Step 4 anchor-check (R3). The critical-review edit triggers automatic plugin mirror regeneration via the `.githooks/pre-commit` dual-source drift hook; the implementer stages both canonical and regenerated mirror in the same commit.

## Outline

### Phase 1: Land rails (tasks: 1, 2)
**Goal**: All 3 spec requirements landed as visible rails — R1 + R2 in `CLAUDE.md`, R3 in `skills/critical-review/SKILL.md` (+ mirrored copy in `plugins/cortex-core/`).
**Checkpoint**: All 3 acceptance grep checks pass against the committed working tree; lifecycle directory ready for Review phase.

## Tasks

### Task 1: Add Skill-authoring (R1) and What-Why-not-How (R2) subsections to CLAUDE.md
- **Files**: `CLAUDE.md`
- **What**: Add two new subsections to `CLAUDE.md` codifying the two repo-authoring PROMOTE memories. Place both subsections adjacent to the existing `## MUST-escalation policy (post-Opus 4.7)` heading (currently at line ~52, between `## Conventions` at line ~38 and the post-Opus-4.7 policy text) so the related authoring rules are co-located. The MUST-escalation policy is the conceptual partner to R2 in particular.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **R1 content** (codifies `feedback_audit_user_facing_affordances.md`, paraphrased from research.md "Memory 1" section): rule that phase-boundary audits identify the user-facing affordance the boundary protects before classifying it as ceremonial; cross-reference `skills/lifecycle/SKILL.md`'s "Kept user pauses" inventory as the concrete artifact this principle protects; cross-reference the parity test at `tests/test_lifecycle_kept_pauses_parity.py`; principle that structural separation is stronger than prose-only enforcement for sequential gates.
  - **R1 acceptance keywords** (must appear in the new prose): "user-facing affordance"; "Kept user pauses" OR "kept-pauses"; "structural separation" OR "prose-only enforcement".
  - **R2 content** (codifies `feedback_design_principle_what_why_not_how.md`, paraphrased from research.md "Memory 3" section): rule that skill/hook/lifecycle/template authoring prescribes decisions, gates, output shapes, and intent (What+Why) but resists prescribing step-by-step method (How); the Why — capable models (Opus 4.7+) figure out method themselves; how-prescription wastes tokens and constrains capable agents; cross-reference the MUST-escalation policy as conceptual partner.
  - **R2 acceptance keywords** (must appear in the new prose): "What and Why" (case-sensitive matches either capitalization per `grep -c "What and Why\|what and why"`); "Opus 4.7" OR "capable models".
  - **Placement options** (either satisfies acceptance): (a) two new H2 subsections (`## Skill / phase authoring guidelines` + `## Design principle: prescribe What and Why, not How`) inserted between line ~50 (end of Conventions bullets) and line ~52 (`## MUST-escalation policy`); (b) labeled H3 subsections nested under a renamed `## Conventions and authoring guidelines` parent.
  - **Style constraint**: use soft positive-routing phrasing throughout — no new `MUST` / `CRITICAL` / `REQUIRED` language. The MUST-escalation policy at `CLAUDE.md:52` forbids new MUSTs without evidence-artifact links; these rails carry none.
  - **Source paraphrase rule**: paraphrase the memory contents into new prose; do not paste memory text verbatim — the rails are net-new authored content informed by the audit verdicts, not copy-pastes.
- **Verification**: Run `grep -c "user-facing affordance" CLAUDE.md && grep -c "Kept user pauses\|kept-pauses" CLAUDE.md && grep -c "structural separation\|prose-only enforcement" CLAUDE.md && grep -c "What and Why\|what and why" CLAUDE.md && grep -c "Opus 4.7\|capable models" CLAUDE.md` — pass if all five counts return ≥ 1.
- **Status**: [x] completed (commit `1d4adf45`)

### Task 2: Append measurement operationalization to critical-review Step 4 anchor-check (R3)
- **Files**: `skills/critical-review/SKILL.md`, `plugins/cortex-core/skills/critical-review/SKILL.md`
- **What**: Append a one-sentence operationalization to the existing anchor-check at `skills/critical-review/SKILL.md` Step 4 so that "new evidence" explicitly means measurement (`time`, `wc -c`, grep), not re-reading the artifact text. Preserve the existing anchor-check sentence verbatim. The `.githooks/pre-commit` hook regenerates `plugins/cortex-core/skills/critical-review/SKILL.md` automatically; the implementer commits both files in one shot.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **Existing anchor-check sentence** (currently at `skills/critical-review/SKILL.md:104`, must remain verbatim): `Default ambiguous to Ask. Anchor-checks: dismissals must be pointable to artifact text, not memory; resolutions must rest on new evidence, not prior reasoning.`
  - **Appended sentence shape** (paraphrased from research.md "Memory 4" section; final wording is the implementer's call within the keyword constraint): a one-sentence operationalization that names a specific empirical claim type (latency, file size, blast radius, baseline behavior), instructs the agent to run the actual measurement (`time`, `wc -c`, grep) before classifying Apply/Dismiss, and contrasts re-reading the artifact text as NOT "new evidence."
  - **R3 acceptance keywords** (must appear in Step 4 region of the canonical file): "new evidence, not prior reasoning" (preserves the existing sentence); "measure" or "measurement"; "wc -c" or "empirical claim" or a similar token from `time`/`wc -c`/`grep`/`empirical claim`.
  - **Mirror regeneration mechanics**: `.githooks/pre-commit` runs `just build-plugin` automatically when staged paths include `skills/`. The hook then verifies no drift between fresh build and index — failure here means `git add plugins/cortex-core/skills/critical-review/SKILL.md` and re-commit. Alternative: run `just build-plugin` before the first `git add` so both files are staged in one shot.
  - **No new MUST language**: the operationalization uses positive-routing prose ("run the actual measurement before classifying…"), not a `MUST`.
- **Verification**: Run `grep -c "new evidence, not prior reasoning" skills/critical-review/SKILL.md` (expect ≥ 1, preserves existing sentence) AND `grep -c "new evidence, not prior reasoning" plugins/cortex-core/skills/critical-review/SKILL.md` (expect ≥ 1, mirror parity) AND `awk '/^## Step 4/,/^## Step 5/' skills/critical-review/SKILL.md | grep -ci "measure\|measurement"` (expect ≥ 1, Step 4 region contains the operationalization keyword) AND `awk '/^## Step 4/,/^## Step 5/' skills/critical-review/SKILL.md | grep -c "wc -c\|empirical claim\|time.*wc.*grep"` (expect ≥ 1, Step 4 region names a concrete measurement form). Pass if all four counts ≥ 1.
- **Status**: [x] completed (commit `2fed8ab6`)

## Risks

None controversial — the rails carry low reversibility cost (text-only additions in already-identified placement) and the spec acceptance is grep-keyword-based so wording variations within the keyword constraints are non-blocking. Two minor design choices the operator might want to revisit:

1. **R1/R2 placement granularity**: two new H2 subsections vs. H3 subsections under a renamed `## Conventions and authoring guidelines` parent. Both satisfy acceptance; H2 is the lower-touch choice and matches the file's existing heading-level conventions (sections like `## Distribution`, `## Conventions`, `## MUST-escalation policy` are all H2).
2. **R3 mirror-staging workflow**: rely on the `.githooks/pre-commit` automatic regeneration (with the failure-and-retry dance documented in the hook's Phase 4) vs. run `just build-plugin` proactively before the first commit. Either works; the proactive run avoids the retry.
