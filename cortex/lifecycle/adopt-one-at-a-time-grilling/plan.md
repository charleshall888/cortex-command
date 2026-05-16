# Plan: adopt-one-at-a-time-grilling

## Overview

Prose-only edits to three files: `skills/requirements-gather/SKILL.md`, `skills/lifecycle/references/specify.md`, and `skills/lifecycle/SKILL.md`. Tasks 1–2 land the atomic cadence prose in both interview surfaces simultaneously to satisfy Phase 1's no-forward-pointer-window invariant. Tasks 3–5 add §2-only behavioral guidelines and the SKILL.md parity-prose drift fix. Task 6 runs the global verification gates over the final committed state of all three files. All edits are soft-positive routing within existing fields; no new files, no schema changes.

## Outline

### Phase 1: Atomic cadence prose (tasks: 1, 2)
**Goal**: Land cadence prose, cross-reference pointer, and grounded file-path citation guidance in both `requirements-gather/SKILL.md` and `specify.md` §2 in the same PR so neither surface holds a forward pointer to a not-yet-mirrored target.
**Checkpoint**: R1–R6 acceptance greps each return ≥ 1.

### Phase 2: §2 additions, drift fix, and verification gates (tasks: 3, 4, 5, 6)
**Goal**: Land soft mid-interview verification guideline (R7) and judgmental edge-case invention (R8) in specify §2; fix the kept-user-pauses tolerance prose drift in `skills/lifecycle/SKILL.md` (R10); run global verification gates (R9, R11, R12, R13, R14) over the combined Phase 1+2 final state.
**Checkpoint**: R7–R14 acceptance checks pass.

## Tasks

### Task 1: Edit requirements-gather SKILL.md — cadence prose, cross-reference pointer, and grounded file-path citation
- **Files**: `skills/requirements-gather/SKILL.md`
- **What**: Within the existing `## Decision criteria` section, add a new H3 subsection (or fold into an existing subsection) introducing the one-at-a-time cadence rule in soft-positive routing prose, with a one-line cross-reference pointer noting the cadence is mirrored in `skills/lifecycle/references/specify.md` §2. Within the existing `## Output shape` section's documentation of the `**Code evidence:**` field (around line 53), append guidance that the field names the file path when the `**Recommended answer:**` is derived from code, preserving the existing "omit otherwise" semantics for intent-only questions.
- **Depends on**: none
- **Complexity**: simple
- **Context**: File is 72 lines today. The existing `## Decision criteria` block contains two H3 subsections (`### Codebase trumps interview` at line 23, `### Recommend before asking` at line 27, `### Lazy artifact creation` at line 31). Pick the natural insertion point — a new `### Ask one at a time` H3 between Recommend before asking and Lazy artifact creation is the most readable home for cadence prose. Use soft-positive phrasing analogous to the existing decision-criteria entries (e.g., "Ask questions one at a time…" rather than "MUST ask…"). The cross-reference pointer reads roughly: "Mirrored in `skills/lifecycle/references/specify.md` §2 — when editing this rule, update the other surface too." For the `**Code evidence:**` rule, append a phrase to the existing field's parenthetical (current text: `{file paths or excerpts, when codebase-trumps-interview applied; omit otherwise}`) — e.g., add a sentence below the output-shape block stating: "When the **Recommended answer** is derived from code, the **Code evidence** field names the file path that grounds it; omit when the answer is intent-only."
- **Verification**: `awk '/^## Decision criteria/,/^## Output shape/' skills/requirements-gather/SKILL.md | grep -ci "one at a time"` returns ≥ 1 AND `awk '/^## Decision criteria/,/^## Output shape/' skills/requirements-gather/SKILL.md | grep -c "specify.md"` returns ≥ 1 AND `grep -ci "derived from code\|grounded in code" skills/requirements-gather/SKILL.md` returns ≥ 1.
- **Status**: [ ] pending

### Task 2: Edit specify.md §2 — cadence prose, cross-reference pointer, and grounded file-path citation
- **Files**: `skills/lifecycle/references/specify.md`
- **What**: Within `### 2. Structured Interview` (lines 11–36 today), add the same cadence rule, a cross-reference pointer to `skills/requirements-gather/SKILL.md`, and the grounded file-path citation guidance. The cadence prose pairs naturally with the existing "Ask probing questions… Use the AskUserQuestion tool to present questions interactively" guidance at line 36.
- **Depends on**: none
- **Complexity**: simple
- **Context**: §2 currently lists interview areas in sequence (Problem statement line 23, Requirements line 25, Non-requirements line 30, Edge cases line 32, Technical constraints line 34) with a final paragraph at line 36 about asking probing questions. Insert the cadence prose either as a new opening paragraph in §2 (before the bullet sequence) or at the closing paragraph (line 36 area). Cross-reference pointer reads roughly: "Mirrored in `skills/requirements-gather/SKILL.md` — when editing this rule, update the other surface too." Grounded file-path citation reads roughly: "When recommending an acceptance criterion derived from code, name the file path that grounds it; omit when the criterion is intent-only." Match soft-positive phrasing to surrounding §2 prose (the section already uses imperative-but-soft framing like "Ask probing questions…", "Push back on vague boundaries", "Challenge optimistic assumptions"). Do NOT introduce new MUST/CRITICAL/REQUIRED tokens. Do NOT add new `AskUserQuestion` call sites; cadence is encoded as prose only.
- **Verification**: `awk '/^### 2\. Structured Interview/,/^### 2a/' skills/lifecycle/references/specify.md | grep -ci "one at a time"` returns ≥ 1 AND `awk '/^### 2\. Structured Interview/,/^### 2a/' skills/lifecycle/references/specify.md | grep -c "requirements-gather"` returns ≥ 1 AND `awk '/^### 2\. Structured Interview/,/^### 2a/' skills/lifecycle/references/specify.md | grep -ci "file path\|file-path"` returns ≥ 1.
- **Status**: [ ] pending

### Task 3: Edit specify.md §2 — soft mid-interview verification guideline
- **Files**: `skills/lifecycle/references/specify.md`
- **What**: Add a soft-positive guideline in §2 stating that the agent verifies file paths and function-behavior claims as it cites them during the interview, without dismantling the §2b end-of-interview Verification check.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Lands inside the §2 awk window (between `### 2. Structured Interview` line 11 and `### 2a` line 38). The guideline pairs with the grounded file-path citation rule added in Task 2 — when the agent cites a file path in a recommendation, it confirms the path exists; when it cites a function's behavior, it verifies against the actual function before locking the criterion. Soft-positive phrasing: "When citing a file path or function-behavior claim during the interview, verify it against the actual code before accepting the user's confirmation. This does NOT replace the §2b Pre-Write Verification check — that gate still fires end-of-interview on the full candidate claim-set." Adds 1–2 new lines containing `\bverify\b`.
- **Verification**: `(awk '/^### 2\. Structured Interview/,/^### 2a/' skills/lifecycle/references/specify.md | grep -ci '\bverify\b')` returns ≥ 1 (baseline on main is 0, so any non-zero count satisfies R7's delta).
- **Status**: [ ] pending

### Task 4: Edit specify.md §2 — judgmental edge-case invention prose
- **Files**: `skills/lifecycle/references/specify.md`
- **What**: Add a soft-positive guideline in §2 stating that when a requirement's acceptance criteria look under-specified, the agent invents an edge-case scenario to force precision. Categorical per-requirement invention is explicitly NOT prescribed.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Lands inside the §2 awk window. The guideline pairs with the existing "**Edge cases**" interview area at line 32 (section-level edge-case prompts) — this new guideline is per-requirement and judgmental: fires when the agent senses the acceptance criteria are loose, not categorically on every requirement. Soft-positive phrasing: "When a requirement's acceptance criteria look under-specified, invent one concrete edge-case scenario that would stress the criterion and surface it to the user before locking. Apply judgmentally — skip when criteria are already tight." Must use the literal token `under-specified` to satisfy R8's AC.
- **Verification**: `awk '/^### 2\. Structured Interview/,/^### 2a/' skills/lifecycle/references/specify.md | grep -ci "under-specified"` returns ≥ 1.
- **Status**: [ ] pending

### Task 5: Update kept-user-pauses tolerance prose in skills/lifecycle/SKILL.md
- **Files**: `skills/lifecycle/SKILL.md`
- **What**: Update the prose at line ~191 from "±20-line tolerance" to "±35-line tolerance" to match `LINE_TOLERANCE = 35` at `tests/test_lifecycle_kept_pauses_parity.py:27`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Single-character class swap inside the kept-user-pauses inventory introduction. Current line 191 reads: "The parity test at `tests/test_lifecycle_kept_pauses_parity.py` enforces that this inventory and the actual call sites stay in sync (±20-line tolerance)." Replace `±20-line tolerance` with `±35-line tolerance`. Use `Edit` tool with `old_string`/`new_string` for an exact replacement; the surrounding sentence stays intact. Do not change `LINE_TOLERANCE` in the test file; the spec's Non-Requirements explicitly forbid lowering the constant.
- **Verification**: `grep -c "±35-line tolerance" skills/lifecycle/SKILL.md` returns ≥ 1 AND `grep -c "±20-line tolerance" skills/lifecycle/SKILL.md` returns 0.
- **Status**: [ ] pending

### Task 6: Run global verification gates on the final state of all three edited files
- **Files**: `skills/requirements-gather/SKILL.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/SKILL.md` (read-only inspection)
- **What**: Run the five global gates from the spec: R9 (§2b Verification check sub-block stayed put), R11 (Q&A block schema preserved verbatim), R12 (zero MUST/CRITICAL/REQUIRED tokens in final state of both edited skill files), R13 (`just test` exits 0), R14 (all three files under 500-line cap). If any gate fails, stop and surface the failing AC.
- **Depends on**: [1, 2, 3, 4, 5]
- **Complexity**: simple
- **Context**: Verification-only task; no file edits. Run each AC as written in the spec. R11's AC uses the placeholder-anchored pattern `^\s*-\s+\*\*(Q|Recommended answer|User answer|Code evidence):\*\*\s+\{` to count exactly 4 schema-definition bullets (the trailing example continuation at line 56 lacks the `:** {` placeholder and is excluded). R12 runs `grep -cE '\b(MUST|CRITICAL|REQUIRED)\b' skills/requirements-gather/SKILL.md skills/lifecycle/references/specify.md | awk -F: '{s+=$2} END{exit !(s==0)}'` and checks exit code 0.
- **Verification**: All five commands return their pass conditions: `awk '/^### 2b/,/^### 3/' skills/lifecycle/references/specify.md | grep -c "Verification check"` ≥ 1 AND `grep -cE '^\s*-\s+\*\*(Q|Recommended answer|User answer|Code evidence):\*\*\s+\{' skills/requirements-gather/SKILL.md` = 4 AND `grep -cE '\b(MUST|CRITICAL|REQUIRED)\b' skills/requirements-gather/SKILL.md skills/lifecycle/references/specify.md | awk -F: '{s+=$2} END{exit !(s==0)}'` exits 0 AND `just test` exits 0 AND `awk 'END{exit !(NR<500)}' skills/requirements-gather/SKILL.md && awk 'END{exit !(NR<500)}' skills/lifecycle/references/specify.md && awk 'END{exit !(NR<500)}' skills/lifecycle/SKILL.md` exits 0.
- **Status**: [ ] pending

## Risks

- **R1/R4 phrasing lock**: AC requires literal `one at a time` substring. If a future editor prefers a phrasing like "single question per turn" or "ask individually", the AC fails despite preserving meaning. Acceptable cost — phrasing match is the cheapest behavior-anchor available under prose-only enforcement; future re-phrasings can update both the prose and the ACs together.
- **Pointer-note drift (R2, R5)**: Pointers are weak human-readable cross-references, not enforced parity. The spec accepts this; revisit Approach B (shared reference file) if post-landing observation shows the two cadence blocks drift in substance.
- **Behavioral validation gap**: All cadence ACs verify prose emission, not behavior. If post-landing observation shows interview cadence unchanged, the recovery path is a future evidence-collection cycle (transcript inspection, events.log F-row capture, effort=high dispatch) per CLAUDE.md MUST-escalation policy. The current spec does not commission that cycle; an operator who notices cadence unchanged would file a follow-up.

## Acceptance

The complete feature is in its intended end state when, on the final committed state of `skills/requirements-gather/SKILL.md`, `skills/lifecycle/references/specify.md`, and `skills/lifecycle/SKILL.md`, every R1–R14 acceptance criterion from `cortex/lifecycle/adopt-one-at-a-time-grilling/spec.md` returns its pass condition, AND `just test` exits 0 with no test breakage attributable to these edits, AND no MUST/CRITICAL/REQUIRED tokens appear in the two edited skill files' final state.
