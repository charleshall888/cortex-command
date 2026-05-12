# Plan: favor-long-term-solutions

## Overview

Two-file prose insertion. Add a canonical `**Solution horizon**` paragraph to `cortex/requirements/project.md`'s Philosophy of Work section, anchored after `**Complexity**`. Add a `## Solution horizon` section to `CLAUDE.md` placed immediately before `## Design principle: prescribe What and Why, not How`, containing the operational trigger and a cross-reference to `project.md`. Both insertions use soft positive-routing language only; no MUST/NEVER directives.

## Outline

### Phase 1: Add solution-horizon principle (tasks: 1, 2)
**Goal**: Canonical principle in `project.md`; operational pointer in `CLAUDE.md`.
**Checkpoint**: Both files updated, all spec acceptance greps pass (R1, R2, R3 from spec.md).

## Tasks

### Task 1: Add `**Solution horizon**` paragraph to `cortex/requirements/project.md`
- **Files**: `cortex/requirements/project.md`
- **What**: Insert a new bold-prefixed paragraph in the Philosophy of Work section, placed immediately after the `**Complexity**` paragraph (currently line 19) and before `**Quality bar**` (currently line 21). Paragraph must state the known-redo test (current-knowledge anchor: planned follow-up, multiple known applications, or nameable sidestepped constraint), the simpler-is-correct-when-unknown reconciliation with the existing `**Complexity**` paragraph, and the phased-lifecycle carve-out (a deliberately-scoped phase of a multi-phase plan is not a stop-gap; stop-gap means unplanned-redo).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing Philosophy of Work paragraphs use bold-prefixed style with no bullet lists: `**Day/night split**: ...`, `**Complexity**: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct.`, `**Quality bar**: ...`. New paragraph follows the same style — ~5–8 sentences, no bullets. Soft positive-routing only (no MUST/NEVER/REQUIRED/CRITICAL — per CLAUDE.md lines 68–77 MUST-escalation policy). The known-redo phrasing drafted in research.md §"Operational test (the heuristic)" is the reference text. The reconciliation sentence must explicitly tie back to the immediately-preceding `**Complexity**` paragraph (e.g., "This does not override **Complexity** above…"). The carve-out must name "phased lifecycle" or equivalent so a reader doesn't misread the principle as opposing MVPs and phase-1 work.
- **Verification**: `grep -c '^\*\*Solution horizon\*\*:' cortex/requirements/project.md` returns `1`; `grep -ciE '\*\*Solution horizon\*\*.*\b(MUST|NEVER|REQUIRED|CRITICAL)\b' cortex/requirements/project.md` returns `0`; `awk '/^\*\*Complexity\*\*:/{c=NR} /^\*\*Solution horizon\*\*:/{s=NR} /^\*\*Quality bar\*\*:/{q=NR} END{exit !(c && s && q && c < s && s < q)}' cortex/requirements/project.md` exits `0` (confirms placement between `**Complexity**` and `**Quality bar**`).
- **Status**: [x] completed

### Task 2: Add `## Solution horizon` section to `CLAUDE.md`
- **Files**: `CLAUDE.md`
- **What**: Insert a new top-level section `## Solution horizon` immediately before `## Design principle: prescribe What and Why, not How`. Section contains a one-sentence operational trigger (the known-redo question to ask before proposing a fix) and a cross-reference pointing to `cortex/requirements/project.md`'s Philosophy of Work for the canonical statement.
- **Depends on**: none
- **Complexity**: simple
- **Context**: CLAUDE.md section structure (newest → most mature): `## Conventions` → `## Skill / phase authoring guidelines` → `## Design principle: prescribe What and Why, not How` → `## MUST-escalation policy`. Insert `## Solution horizon` between `## Skill / phase authoring guidelines` and `## Design principle: prescribe What and Why, not How`. Section body: 2–4 sentences max. Soft positive-routing only. The cross-reference must use the literal path `cortex/requirements/project.md` so a grep matches. Operational trigger should be a single sentence the agent can apply at decision time — the known-redo question. Do not duplicate the full canonical statement here; the pointer is the canonical authority.
- **Verification**: `grep -c '^## Solution horizon$' CLAUDE.md` returns `1`; `awk '/^## Solution horizon$/{a=NR} /^## Design principle: prescribe What and Why, not How$/{b=NR} END{exit !(a && b && a < b)}' CLAUDE.md` exits `0`; `awk '/^## Solution horizon$/,/^## Design principle/' CLAUDE.md | grep -c 'cortex/requirements/project.md'` returns ≥`1`; `awk '/^## Solution horizon$/,/^## Design principle/' CLAUDE.md | grep -ciE '\b(MUST|NEVER|REQUIRED|CRITICAL)\b'` returns `0`.
- **Status**: [x] completed

## Risks

- **Tone drift**: Prose strong enough to actually shift agent behavior may inadvertently trip the soft-positive-routing constraint (e.g., implicit imperatives like "always ask…" read as MUST). Mitigation: implementer keeps the question-form framing ("Before suggesting a fix, ask…") and the verification grep on MUST/NEVER/REQUIRED/CRITICAL catches literal directive vocabulary.
- **Anchor drift**: If a future edit moves `**Complexity**` or `## Design principle: prescribe What and Why, not How`, the new content's logical position weakens. Mitigation: anchored on section headers in verification (not line numbers); a future edit that moves those anchors would still need to keep `**Solution horizon**` between `**Complexity**` and `**Quality bar**` per the awk check.
- **Operational trigger misreads as endorsing speculation**: A reader interprets "ask whether you already know" as "always look hard for reasons to do the durable version." Mitigation: prose explicitly anchors on *current knowledge*, not search/speculation; the reconciliation sentence pins this.
