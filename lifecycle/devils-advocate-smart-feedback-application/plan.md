# Plan: devils-advocate-smart-feedback-application

## Overview

Single-file skill edit plus description change plus two doc updates. Task 1 adds Step 3 "Apply Feedback" to `skills/devils-advocate/SKILL.md` (all 14 requirements' behavioral content lands here — rated `complex` because it's 9 prose subsections against 24 verification checks). Task 2 updates the frontmatter description to surface the apply-loop (R11). Tasks 3 and 4 update `docs/skills-reference.md` and `docs/agentic-layer.md` to reflect the lifecycle-path behavior change (R12). All four tasks have independent inputs (the spec pins wording) — they can run in parallel or in any order. Task dependencies are set to `none` across the board; sequencing is a tooling concern, not a design constraint.

## Tasks

### Task 1: Add Step 3 "Apply Feedback" section to skills/devils-advocate/SKILL.md

- **Files**: `skills/devils-advocate/SKILL.md`
- **What**: Insert a new `## Step 3: Apply Feedback` section between the existing `## Step 2: Make the Case` and `## Success Criteria`. The section contains the inversion-callout preamble, the lifecycle-only gate, the three dispositions (Apply / Dismiss / Ask) with inverted anchor semantics, the Tradeoff-Blindspot exemption, self-resolution step, apply bar, surgical-write rule, abort conditions, and apply mechanics.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Target file: `skills/devils-advocate/SKILL.md` (94 lines currently). Insertion point: immediately before `## Success Criteria` (which is line 58 today; the exact line number may shift after insertion). This is NOT a simple edit — 9 distinct prose subsections must land in one coherent section satisfying 24 verification checks. Budget accordingly.
  - Preamble paragraph must contain: `INVERTED` (exactly once across the file — per spec R8); wording like `adapted from /critical-review Step 4 with INVERTED anchor semantics: CR anchors Dismiss-to-artifact; this step anchors Apply-to-artifact` and `Changes to CR Step 4 must not be propagated here verbatim`.
  - Lifecycle-only gate: opening sentence of Step 3 states that the apply loop runs only when Step 1 read a lifecycle artifact; if no lifecycle was active, Step 3 is skipped and the skill stops after Step 2. Must include the phrase `no lifecycle` (for R2 grep).
  - Three dispositions use bold labels `**Apply**`, `**Dismiss**`, `**Ask**` at the start of their paragraphs (for R3 grep anchors, each exactly once).
  - Default disposition is Dismiss. Apply anchor rule uses the inverted form: "if your apply reason cannot be pointed to in the artifact text (or semantic equivalent)" — this is the structural mirror of critical-review Step 4's Dismiss anchor check. Include a `default.*Dismiss` or `Dismiss.*default` phrase within Step 3 (for R6 grep).
  - Unit of classification: names the three in-scope sections (Strongest Failure Mode, Unexamined Alternatives, Fragile Assumption) and explicitly exempts `Tradeoff Blindspot` with a one-sentence rationale ("produces a priorities judgment, not an applyable fix" or equivalent).
  - Self-resolution paragraph adapted from `skills/critical-review/SKILL.md` lines 209 — adjusted for the inline-context case. Include the token `self-resolution` (for R5 grep) and the guard "uncertainty still defaults to Ask" or semantic equivalent.
  - Apply bar paragraph: include the literal label `Apply bar` (for R6 grep).
  - Surgical-write rule (R13): explicitly states Apply fixes use Edit-tool-style surgical replacement (old_string → new_string) and forbids full-file rewrite. Include at least one of the tokens `surgical`, `Edit tool`, or `old_string` (for R13 grep).
  - Abort conditions (R14): names the three abort scenarios in prose — (a) artifact changed by another session between Step 1 and Step 3, (b) artifact cannot be re-read at Step 3 time (deleted, path changed, permission error), (c) host agent's context no longer contains Step 1 read and a pre-classification re-read is required. Include the token `abort` or `Abort` (for R14 grep).
  - Apply mechanics paragraph: describes the re-read / apply / summary sequence. Explicitly allows the re-read to occur before or during classification (not strictly after). Compact summary format: one line per Apply fix, dismissed items with reasons, Ask items as a single consolidated question bundle.
  - Section structure reference: critical-review's Step 4 (`skills/critical-review/SKILL.md` lines 197–217) is the source pattern. Preserve wording tight to project convention — no preamble line in the file should exceed ~100 words.
  - Must NOT touch Step 2's H3 headers (`### Strongest Failure Mode`, `### Unexamined Alternatives`, `### Fragile Assumption`, `### Tradeoff Blindspot`) — preserve verbatim (R10).
  - Must NOT touch the `## What This Isn't` section — the four key phrases `Stop after making the case`, `Don't repeat objections after they've been acknowledged`, `Don't negotiate or defend your position`, `Not a blocker` remain exactly where they are (R9).
- **Verification**:
  - `grep -c '^## Step 3: Apply Feedback' skills/devils-advocate/SKILL.md` = 1
  - `grep -c 'no lifecycle' skills/devils-advocate/SKILL.md` ≥ 1
  - `grep -c '^\*\*Apply\*\*' skills/devils-advocate/SKILL.md` = 1
  - `grep -c '^\*\*Dismiss\*\*' skills/devils-advocate/SKILL.md` = 1
  - `grep -c '^\*\*Ask\*\*' skills/devils-advocate/SKILL.md` = 1
  - `grep -c 'Tradeoff Blindspot' skills/devils-advocate/SKILL.md` ≥ 2
  - `grep -c 'self-resolution' skills/devils-advocate/SKILL.md` ≥ 1
  - `grep -cE 'uncertainty.*defaults? to Ask|Ask.*default' skills/devils-advocate/SKILL.md` ≥ 1 — enforces R5's "uncertainty still defaults to Ask" guard, which was otherwise only covered by the `self-resolution` token
  - `grep -c 'Apply bar' skills/devils-advocate/SKILL.md` ≥ 1
  - `grep -cE 'default.*[Dd]ismiss|[Dd]ismiss.*default' skills/devils-advocate/SKILL.md` ≥ 1
  - `grep -c 'INVERTED' skills/devils-advocate/SKILL.md` = 1
  - `grep -c 'not be propagated' skills/devils-advocate/SKILL.md` ≥ 1
  - `grep -cE 'surgical|Edit tool|old_string' skills/devils-advocate/SKILL.md` ≥ 1
  - R14 three abort conditions — all three must appear in Step 3 prose, enforced by separate greps:
    - `grep -cE '[Aa]bort.*changed|changed.*[Aa]bort|modified.*[Aa]bort|[Aa]bort.*modified' skills/devils-advocate/SKILL.md` ≥ 1 — condition (a) artifact changed since Step 1
    - `grep -cE 'not found|deleted|cannot be re-read|cannot re-read' skills/devils-advocate/SKILL.md` ≥ 1 — condition (b) artifact not re-readable at Step 3 time
    - `grep -cE 'context[- ]loss|lost artifact context|pre-classification re-read' skills/devils-advocate/SKILL.md` ≥ 1 — condition (c) host context lost, pre-classification re-read needed
  - `grep -cE 'before or during classification|re-read.*before classification|pre-classification re-read' skills/devils-advocate/SKILL.md` ≥ 1 — enforces R7's re-read ordering flexibility
  - `grep -c '^### Strongest Failure Mode' skills/devils-advocate/SKILL.md` = 1
  - `grep -c '^### Unexamined Alternatives' skills/devils-advocate/SKILL.md` = 1
  - `grep -c '^### Fragile Assumption' skills/devils-advocate/SKILL.md` = 1
  - `grep -c '^### Tradeoff Blindspot' skills/devils-advocate/SKILL.md` = 1
  - Section ordering: `awk '/^## / {print NR, $0}' skills/devils-advocate/SKILL.md` lists H2 headers in file order. Expected sequence: `# Devil's Advocate` is H1 (skip), then H2s appear in order: `## Input Validation`, `## Step 1: Read First`, `## Step 2: Make the Case`, `## Step 3: Apply Feedback`, `## Success Criteria`, `## Output Format Example`, `## Error Handling`, `## What This Isn't`. Interactive/session-dependent: confirm the order matches by reading awk's line-numbered output — a single grep cannot enforce ordering.
  - H3 section-membership check: run `awk '/^## Step 2:/,/^## Step 3:/' skills/devils-advocate/SKILL.md | grep -cE '^### (Strongest Failure Mode|Unexamined Alternatives|Fragile Assumption|Tradeoff Blindspot)'` = 4 — confirms all 4 H3 headers remain inside Step 2 (not accidentally moved into Step 3).
  - `grep -c 'Stop after making the case' skills/devils-advocate/SKILL.md` ≥ 1 (was `= 1` — loosened so Step 3 can cross-reference this preserved phrase if needed)
  - `grep -c "Don't repeat objections after they've been acknowledged" skills/devils-advocate/SKILL.md` ≥ 1
  - `grep -c "Don't negotiate or defend your position" skills/devils-advocate/SKILL.md` ≥ 1
  - `grep -c 'Not a blocker' skills/devils-advocate/SKILL.md` ≥ 1
  - "What This Isn't" paragraph verbatim check: `awk '/^## What This Isn't/,/^##/' skills/devils-advocate/SKILL.md | grep -c 'Not a blocker. The user might hear the case against and proceed anyway'` ≥ 1 — anchors the opening-sentence glue text, not just isolated phrases. Interactive/session-dependent: the full paragraph can be diff'd against the pre-change version at review time; this grep catches glue-text rewrites that the individual phrase greps miss.
- **Status**: [x] complete

### Task 2: Update frontmatter description in skills/devils-advocate/SKILL.md

- **Files**: `skills/devils-advocate/SKILL.md`
- **What**: Revise the frontmatter `description:` line to surface the new apply-loop behavior while preserving the existing trigger phrases. The revised description must include "inline" (or a semantic equivalent naming single-context execution), mention the apply-loop behavior (keywords like "apply", "fix", or "dispositions"), and contain no phrase that appears verbatim in `skills/critical-review/SKILL.md`'s description line.
- **Depends on**: none — the description wording is determined by the spec, not by Task 1's final prose. Task 2 can run in parallel with Task 1. (Both edit the same file; sequencing is a tooling concern, not a dependency.)
- **Complexity**: simple
- **Context**:
  - Current description line (`skills/devils-advocate/SKILL.md` line 3): `description: Inline devil's advocate — argues against the current direction from the current agent's context (no fresh agent). Use when the user says "challenge this", "poke holes", "devil's advocate", "argue against this", "what could go wrong", or "stress-test this". Works in any phase — no lifecycle required.`
  - Revised version must (a) keep "inline" (already present), (b) add an apply-loop phrase (e.g., "— and applies clear-cut fixes when invoked on a lifecycle artifact"), (c) not duplicate any phrase verbatim from critical-review's description.
  - Reference: critical-review's description at `skills/critical-review/SKILL.md` line 3 — avoid reusing its literal phrases.
  - Preserve the six existing DA trigger phrases ("challenge this", "poke holes", "devil's advocate", "argue against this", "what could go wrong", "stress-test this") — the consolidate lifecycle established the non-overlapping trigger sets and any removal risks regression.
- **Verification**:
  - `grep 'description:' skills/devils-advocate/SKILL.md` returns a line containing "inline"
  - `grep 'description:' skills/devils-advocate/SKILL.md` returns a line containing at least one of: "apply", "fix", "dispositions", "clear-cut"
  - Interactive/session-dependent: confirm no phrase appears verbatim in both `grep 'description:' skills/devils-advocate/SKILL.md` and `grep 'description:' skills/critical-review/SKILL.md` — requires human comparison because a phrase-level diff has no single-command form.
  - `grep -c '"challenge this"' skills/devils-advocate/SKILL.md` ≥ 1, `grep -c '"poke holes"' skills/devils-advocate/SKILL.md` ≥ 1, `grep -c "\"devil's advocate\"" skills/devils-advocate/SKILL.md` ≥ 1, `grep -c '"argue against this"' skills/devils-advocate/SKILL.md` ≥ 1, `grep -c '"what could go wrong"' skills/devils-advocate/SKILL.md` ≥ 1, `grep -c '"stress-test this"' skills/devils-advocate/SKILL.md` ≥ 1 — all six trigger phrases preserved
- **Status**: [x] complete

### Task 3: Update /devils-advocate entry in docs/skills-reference.md

- **Files**: `docs/skills-reference.md`
- **What**: Add a one-line note to the `/devils-advocate` entry reflecting that the skill now applies clear-cut fixes in lifecycle mode (Apply/Dismiss/Ask dispositions). Conversation-mode behavior unchanged.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Target entry: `docs/skills-reference.md` lines 112–115 (the `/devils-advocate` row). Read the existing entry structure before editing — match its format.
  - The note should be concise (one line). Example phrasing: "In lifecycle mode, applies clear-cut fixes and surfaces tie-breaks via Apply/Dismiss/Ask dispositions; conversation mode unchanged."
  - Do NOT change the skill's other listed behaviors — only add the note.
- **Verification**:
  - Entry-scope grep using awk boundaries: `awk '/^[^#]*\/devils-advocate/,/^[^#]*\/[a-z]/' docs/skills-reference.md | grep -cE 'Apply|Dismiss|Ask|dispositions|apply loop|clear-cut' ` ≥ 1. Awk extracts the block starting at the /devils-advocate entry and ending at the next skill entry; the grep then confirms the behavioral-change keyword appears within that bounded scope. The naive whole-file grep passes trivially because "Ask" likely appears in other skill entries; this bounded form catches the actual change. Interactive/session-dependent: the awk range pattern depends on the file's structure — verify the boundaries match the entry layout before relying on the check alone.
- **Status**: [x] complete

### Task 4: Update /devils-advocate entry in docs/agentic-layer.md

- **Files**: `docs/agentic-layer.md`
- **What**: Update the `/devils-advocate` row (line 43) to reflect the lifecycle-mode apply-loop behavior. One-line update to the "Produces" or equivalent column.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Target row: `docs/agentic-layer.md` line 43 (the `/devils-advocate` row in a table). Read the row and surrounding table structure before editing — match the existing column format.
  - If the row has a "Produces" column showing "Coherent argument (conversational)", update to reflect the new lifecycle-mode behavior — e.g., "Coherent argument; applies clear-cut fixes + dispositions summary in lifecycle mode".
- **Verification**:
  - Row-scope grep: run `grep -n '/devils-advocate' docs/agentic-layer.md` to locate the row (should be line ~43). Then confirm the update is on THAT row: `sed -n '${N}p' docs/agentic-layer.md | grep -cE 'Apply|Dismiss|Ask|dispositions|apply loop|clear-cut'` ≥ 1 where `${N}` is the line number found in the first command. Interactive/session-dependent: the row number may shift; confirm the grep targets the actual `/devils-advocate` table row and not an adjacent row or header.
- **Status**: [x] complete

## Verification Strategy

After all four tasks complete, verify end-to-end:

1. Run all Task 1 grep checks (20 independent checks) — all must pass simultaneously to confirm Step 3 is structurally complete without regressing Step 2 or "What This Isn't".
2. Run Task 2 description checks — description reflects apply-loop + preserves triggers + remains distinct from critical-review.
3. Read the updated /devils-advocate entries in both docs manually to confirm the one-line notes are coherent and accurate (Task 3 + Task 4).
4. Invoke `/devils-advocate` manually on an UNRELATED lifecycle's `spec.md` or `plan.md` as a smoke test — NOT this lifecycle's own artifacts (self-reference risk: Step 3 would try to apply fixes to the spec driving its own implementation). Good candidates: a recently-completed lifecycle's plan.md. Confirm Step 3 runs, produces dispositions for three sections (Strongest Failure Mode, Unexamined Alternatives, Fragile Assumption; Tradeoff Blindspot is exempt), and either applies surgical fixes via Edit-tool-style replacement or cleanly Dismisses/Asks.
5. Invoke `/devils-advocate` in a conversation without an active lifecycle — confirm Step 3 is skipped and the output is the unchanged 4 H3 sections.

## Veto Surface

Design choices the user may want to revisit before implementation:

- **Task 2 wording**: The exact wording of the revised description is not pinned in the spec — the plan suggests "— and applies clear-cut fixes when invoked on a lifecycle artifact" but the implementer will finalize the phrasing during the task. If you have a preferred phrasing, state it before implementation begins.
- **Tradeoff Blindspot exemption**: the research and spec both concluded this section is exempt from the apply loop. If you want to reconsider (e.g., make Tradeoff Blindspot classifiable as Ask but never Apply), flag now — this plan does not include that variant.
- **"Apply bar" label**: R6 requires the literal label `Apply bar` to appear in Step 3. If you prefer a different label (e.g., "Apply threshold"), change it in the spec first — the plan's Task 1 verification greps for the literal label.

## Scope Boundaries

Maps to the spec's Non-Requirements:

- No fresh-agent dispatch, no parallel reviewers, no Opus synthesis (devils-advocate remains single-context).
- No Project Context loading step analogous to CR §2a.
- No apply loop in the no-lifecycle (conversation-context) path.
- No revision of "What This Isn't" — all four load-bearing phrases preserved verbatim.
- No restructuring of Step 2 — the 4 H3 headers and their prose preserved.
- No third shared reference file for the Apply/Dismiss/Ask framework — framework inlined with explicit inversion callout.
- No per-objection classification within a section — one disposition per in-scope section.
- No auto-trigger in the lifecycle — manual invocation only, same as today.
