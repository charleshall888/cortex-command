# Plan: extract-interview-skill

## Overview
Create a standalone, user-invocable `/interview` grilling skill whose canonical loop lives in a shared reference (`skills/interview/references/loop.md`), then single-source the verbatim one-at-a-time cadence rule by repointing `requirements-gather` and `specify.md`'s note at that reference. Prose-only skill; plugin mirror regenerated per edit; routing disambiguation verified by the skill-creator eval harness.
**Architectural Pattern**: plug-in
<!-- A new self-contained skill plugged into the existing skill/plugin registry; callers consume the shared loop reference via a read-and-follow pointer. -->

## Outline

### Phase 1: Standalone /interview skill (tasks: 1, 2, 3, 4)
**Goal**: Ship a first-class, user-invocable `/interview` skill that follows a canonical interview-loop reference, is distributed via the plugin mirror, and routes without colliding with `backlog-author`.
**Checkpoint**: `just test` green; `plugins/cortex-core/skills/interview/` byte-identical to canonical; skill-creator routing eval shows `/interview` and `backlog-author` each resolve for their representative phrasings.

### Phase 2: Single-source the cadence rule (tasks: 5, 6)
**Goal**: Repoint `requirements-gather`'s verbatim cadence block and `specify.md`'s cross-reference note at the canonical `loop.md`, preserving requirements-gather's grounded clauses and specify.md's behavior/pauses.
**Checkpoint**: no verbatim cadence dup remains; grounded recommend + reserve clauses still inline in requirements-gather; kept-pauses parity and full suite green; mirrors byte-identical.

## Tasks

### Task 1: Author the canonical interview loop reference
- **Files**: `skills/interview/references/loop.md`
- **What**: Create the shared interview-loop reference that `/interview` follows and that Phase 2 repoints other surfaces at. It holds only generic, caller-agnostic loop mechanics.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Content per spec R2/R5/R6/R8: (a) one-at-a-time cadence (previous answer gates the next — this is the rule single-sourced in Phase 2); (b) recommend-before-asking, suppressed on taste/preference questions; (c) codebase-trumps-interview (explore code first, then confirm); (d) funnel ordering (broad/open → narrow/closed); (e) saturation-based stopping (stop when new answers stop changing the picture — NOT template-coverage) + early-exit + soft cap. Include a sentence excluding the grilling from batched `AskUserQuestion` (conversational plain-text cadence) with its rationale. Author as What/Why decision rules, not procedural How. Soft-positive phrasing only. Model the shared-reference shape on `skills/lifecycle/references/load-requirements.md` (the read-and-follow idiom). Authoring tool: `/skill-creator:skill-creator`.
- **Verification**: `test -f skills/interview/references/loop.md` AND `grep -ciE 'one at a time|recommend|codebase|funnel|saturation|cap' skills/interview/references/loop.md` ≥ 5 AND `grep -ciE 'saturation|stop when' skills/interview/references/loop.md` ≥ 1 AND the AskUserQuestion mention is an *exclusion* — `grep -ciE 'not .*(batch|AskUserQuestion)|not batched' skills/interview/references/loop.md` ≥ 1 (guards against the false-pass where a bare `AskUserQuestion` mention reads as inclusion) AND `grep -cE '\b(MUST|CRITICAL|REQUIRED)\b' skills/interview/references/loop.md` = 0 — pass if all hold. Note: keyword greps confirm topical presence only; correctness of the decision-rule prose (saturation-not-template-coverage; taste-suppressed recommendations) is a review-gated property confirmed at §3a orchestrator review and the implement-phase review, not by grep alone.
- **Status**: [x] done

### Task 2: Author the standalone /interview SKILL.md
- **Files**: `skills/interview/SKILL.md`
- **What**: Create the first-class, user-invocable skill that follows `loop.md`, accepts an optional topic (falls back to context), and offers a brief.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Per spec R1/R3/R4/R7/R8. Frontmatter: `name: interview`; `description:` scoped as a general-purpose priming interview (explicitly NOT backlog-ticket authoring — disambiguate from `skills/backlog-author/SKILL.md:5`); optional `when_to_use:`; `argument-hint:` for the optional topic. Body: direct reading-and-following `skills/interview/references/loop.md` (do not restate the loop inline); topic-arg-or-context anchor with a single topic-establishing question when neither present; answers accumulate in conversation context; offer a concise brief at conclusion AND allow the user to request the brief at any point (default in-conversation summary; on request, write to a user-specified path — no hardcoded location). Soft-positive phrasing. Authoring tool: `/skill-creator:skill-creator`. Mirror frontmatter conventions from `skills/requirements-gather/SKILL.md`.
- **Verification**: `grep -c '^name: interview' skills/interview/SKILL.md` = 1 AND `grep -c 'references/loop.md' skills/interview/SKILL.md` ≥ 1 AND `grep -c 'argument-hint' skills/interview/SKILL.md` ≥ 1 AND brief affordances present (R7) — `grep -ciE 'brief' skills/interview/SKILL.md` ≥ 1 AND `grep -cE '\b(MUST|CRITICAL|REQUIRED)\b' skills/interview/SKILL.md` = 0 — pass if all hold. Note: the SKILL.md must delegate to loop.md rather than restate the loop inline (no verbatim cadence/recommend/codebase blocks duplicated from loop.md); single-sourcing and the brief/topic-anchor prose are confirmed at §3a orchestrator review, since a path-mention grep alone cannot detect inline restatement.
- **Status**: [x] done

### Task 3: Wire /interview into plugin distribution + size/parity hygiene
- **Files**: `justfile`, `plugins/cortex-core/skills/interview/SKILL.md`, `plugins/cortex-core/skills/interview/references/loop.md`
- **What**: Add `interview` to the cortex-core `SKILLS=(...)` allowlist and regenerate the byte-identical plugin mirror; confirm size and parity hygiene.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Per spec R9/R10. Append `interview` to the `SKILLS=(...)` array at `justfile:582` (the cortex-core list — NOT the overnight list at `:588`). Run `just build-plugin` to rsync the canonical `skills/interview/` into `plugins/cortex-core/skills/interview/`. Edit canonical only; the mirror is generated. Prose-only skill — no `bin/cortex-*` helper, no `.parity-exceptions.md` entry needed.
- **Verification**: `sed -n '582p' justfile | grep -c '\binterview\b'` ≥ 1 AND `test -f plugins/cortex-core/skills/interview/SKILL.md` AND `test -f plugins/cortex-core/skills/interview/references/loop.md` AND (after `just build-plugin`) `git diff --quiet -- plugins/cortex-core/skills/interview/` returns 0 (mirror in sync) AND `just test` exits 0 — pass if all hold.
- **Status**: [x] done

### Task 4: Verify routing disambiguation (eval) + conditional backlog-author clarification
- **Files**: `cortex/lifecycle/extract-interview-skill/routing-eval.md` (captured eval result) (+ conditionally `skills/backlog-author/SKILL.md`, `plugins/cortex-core/skills/backlog-author/SKILL.md`)
- **What**: Use the skill-creator eval harness to confirm representative "interview me about X" phrasings route to `/interview` and ticket-authoring phrasings still route to `backlog-author`. Only if the eval shows a residual collision, apply spec R14 (minimal description-text clarification to backlog-author; subcommand/behavior untouched) and re-run.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**: Per spec R1 (routing verified, not asserted) and R14 (conditional, eval-gated). The `/skill-creator:skill-creator` eval harness exercises routing across representative phrasings. R14 fires ONLY on residual collision; if it fires, qualify the bare "interview" token in `backlog-author`'s `description`/`when_to_use` so it reads as ticket-authoring, regenerate the mirror, and do not alter the `interview|compose` subcommand declaration. Capture the eval result to `routing-eval.md`.
- **Verification**: Interactive/session-dependent: rationale — routing-eval execution and judgment run through the skill-creator harness in-session and cannot be reduced to a fixed command. The pass is recorded, not asserted: capture the representative phrasing set and per-phrase routing outcome to `cortex/lifecycle/extract-interview-skill/routing-eval.md`, so the result is later inspectable (`grep -c 'no mis-route\|PASS' cortex/lifecycle/extract-interview-skill/routing-eval.md` ≥ 1). Pass = that file records `/interview` and `backlog-author` each resolving to their own skill with no mis-route. If R14 fired: the captured eval is a POST-edit RE-RUN showing the collision resolved (not merely that an edit was made), AND `git diff -- skills/backlog-author/SKILL.md` shows only description/when_to_use lines changed (the `interview|compose` subcommand declaration line unchanged), AND `git diff --quiet -- plugins/cortex-core/skills/backlog-author/` returns 0 after rebuild.
- **Status**: [x] done

### Task 5: Single-source requirements-gather's cadence (lossless)
- **Files**: `skills/requirements-gather/SKILL.md`, `plugins/cortex-core/skills/requirements-gather/SKILL.md`
- **What**: Replace ONLY the verbatim one-at-a-time cadence block with a read-and-follow pointer to `loop.md`'s cadence rule and remove the stale mirror note; keep the grounded recommend-before-asking and codebase-trumps-with-reserve clauses inline.
- **Depends on**: [1, 3]
- **Complexity**: simple
- **Context**: Per spec R11. Edit `### Ask one at a time` (lines ~31-33, the block carrying the "Mirrored in `skills/lifecycle/references/specify.md`" note) → a one-line pointer to the cadence rule in `skills/interview/references/loop.md`, and delete the mirror note. Leave `### Recommend before asking` (~27-29, including "Recommendations are grounded — derived from explored code, the existing target doc, the parent requirements … none — open question") and `### Codebase trumps interview` (~23-25, including "Reserve interview questions for intent, priorities, scope boundaries …") INLINE — they are requirements-specialized and NOT extracted. Regenerate the mirror via `just build-plugin`.
- **Verification**: `grep -c 'references/loop.md' skills/requirements-gather/SKILL.md` ≥ 1 AND `grep -c 'Mirrored in' skills/requirements-gather/SKILL.md` = 0 AND `grep -c 'Recommendations are grounded' skills/requirements-gather/SKILL.md` ≥ 1 AND `grep -c 'Reserve interview questions' skills/requirements-gather/SKILL.md` ≥ 1 AND (after rebuild) `git diff --quiet -- plugins/cortex-core/skills/requirements-gather/` returns 0 — pass if all hold.
- **Status**: [x] done

### Task 6: Repoint specify.md's cadence note + full regression
- **Files**: `skills/lifecycle/references/specify.md`, `plugins/cortex-core/skills/lifecycle/references/specify.md`
- **What**: Repoint specify.md:42's `**Cadence**` mirror note at the canonical `loop.md` (text-only, no orphaning, no behavior change, no pause-site movement); run full regression including kept-pauses parity.
- **Depends on**: [1, 3]
- **Complexity**: simple
- **Context**: Per spec R12/R13. In the `**Cadence**` bullet at `skills/lifecycle/references/specify.md:42`, replace the "Mirrored in `skills/requirements-gather/SKILL.md` — when editing this rule, update the other surface too" text with a canonical reference to `skills/interview/references/loop.md` (e.g. "This cadence is the canonical rule at `skills/interview/references/loop.md`."). Same-line-count replacement to keep pause anchors at 36/67/155 within ±35 tolerance. Do NOT drop the note entirely (orphaning) and do NOT change interview behavior. Regenerate the mirror via `just build-plugin`.
- **Verification**: `grep -c 'interview/references/loop.md' skills/lifecycle/references/specify.md` ≥ 1 AND `grep -c 'Mirrored in .*requirements-gather' skills/lifecycle/references/specify.md` = 0 AND `python3 -m pytest tests/test_lifecycle_kept_pauses_parity.py` exits 0 AND `just test` exits 0 AND (after rebuild) `git diff --quiet -- plugins/cortex-core/skills/lifecycle/references/specify.md` returns 0 — pass if all hold.
- **Status**: [x] done

## Risks
- **R14 nudges the "don't touch backlog-author" boundary** (operator-approved at spec): the conditional clarification fires only on a residual routing collision and is text-only. If the operator prefers renaming `/interview` over ever editing backlog-author, that would change Task 2/4 — flagged but approved.
- **Prose-only cadence enforcement** (accepted limitation per critical-review): the conversational one-at-a-time cadence cannot be structurally gated; no automated test catches a runtime revert to `AskUserQuestion`. Mitigated by prominent prose + rationale in loop.md.
- **specify.md pause-anchor tolerance**: Task 6 must be a same-line-count text replacement; a larger edit could drift the parity anchors. Verification runs the parity test.

## Acceptance
`/interview` is invocable and conducts a one-at-a-time, saturation-bounded, conversational (plain-text, not batched `AskUserQuestion`) interview that accumulates answers in context and offers a brief; the new skill files carry zero MUST/CRITICAL/REQUIRED escalation tokens; `requirements-gather` and `specify.md` reference the canonical `loop.md` cadence with no verbatim duplication, and requirements-gather's grounded recommend + reserve clauses remain inline; the skill-creator routing eval (captured in `routing-eval.md`) shows `/interview` and `backlog-author` each resolve correctly; `just test` and `tests/test_lifecycle_kept_pauses_parity.py` pass; and `plugins/cortex-core/` mirrors are byte-identical to canonical.
