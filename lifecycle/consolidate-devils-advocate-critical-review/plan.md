# Plan: consolidate-devils-advocate-critical-review

## Overview

Four targeted edits across three files. Restructure DA's body (Step 2, examples, error handling), then independently update both skill descriptions and fix clarify-critic.md. DA body restructuring runs first since the description update should align with the finished body; the CR description and clarify-critic.md edits are fully independent.

## Tasks

### Task 1: Restructure DA body — H3 headers, error table, one example

- **Files**: `skills/devils-advocate/SKILL.md`
- **What**: Rewrite DA's three body sections (Step 2, Output Format Examples, Error Handling) to use H3 element headers, a compact failure table, and one example that demonstrates the new structure. Frontmatter and Input Validation, Step 1, Success Criteria, and "What This Isn't" sections are unchanged.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current Step 2 (lines ~38–48): opens with "Write a coherent argument against the current approach — not a bullet list of nitpicks. Cover these four things in a flowing narrative (not a checklist):" followed by four bold-label paragraphs. Replace entirely with four H3 subsections inside Step 2, one per element. Each subsection: one sentence describing what to write for this element, one "useless" vs. "useful" inline contrast.
  - H3 names (exact): `### Strongest Failure Mode`, `### Unexamined Alternatives`, `### Fragile Assumption`, `### Tradeoff Blindspot`
  - Current Output Format Examples (lines ~59–84): two examples — Kafka/webhook architectural decision, and Input Validation Failure (vague direction). Keep only the Kafka/webhook example. Update it so the response body uses the four H3 headers (i.e., the example output shows `### Strongest Failure Mode:`, `### Unexamined Alternatives:`, etc.). The Input Validation Failure example is removed entirely.
  - Current Error Handling (lines ~86–117): three subsections with verbose recovery steps. Replace with a single markdown table. Three rows: "No direction", "Vague direction", "Insufficient context". Columns: `Error | Detection | Recovery`. Recovery is one sentence per row — the most actionable step only.
  - Success Criteria section (lines ~50–57): update to align with the H3 section structure. The current criterion "The argument is coherent and narrative (not a bullet list of gripes)" contradicts the new H3-section format. Update to: "Each section contains substantive, specific prose — not a one-line bullet or vague generalization." Retain the other four criteria unchanged.
- **Verification**: Read `skills/devils-advocate/SKILL.md`. Confirm: (1) Step 2 contains exactly four `###` headers with the specified names; (2) "flowing narrative" does not appear; (3) exactly one output example is present; (4) the example uses the four `###` headers; (5) error handling is a table with three rows; (6) Success Criteria no longer says "coherent and narrative (not a bullet list of gripes)"; (7) file is meaningfully shorter than 121 lines (sanity target: 70–90 lines, not a hard gate).
- **Status**: [x] complete

---

### Task 2: Update DA description frontmatter with execution model + trigger domain

- **Files**: `skills/devils-advocate/SKILL.md`
- **What**: Rewrite the `description:` frontmatter field to state DA's execution model (inline, same-context, no fresh agent) and use only the assigned trigger phrases, removing "pressure test" overlap.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Current description: "Stress-tests a direction, plan, or approach by arguing against it. Use when the user says "challenge this", "poke holes", "devil's advocate", "what could go wrong", "stress test this", "argue against this", or "play devil's advocate". Works in any phase — no lifecycle required. Reads relevant artifacts if a lifecycle is active; otherwise works from conversation context."
  - New description must: (a) mention it is an inline critique from the current agent — no fresh agent spawned, works mid-conversation; (b) list trigger phrases: "challenge this", "poke holes", "devil's advocate", "argue against this", "what could go wrong", "stress-test this"; (c) not contain "pressure test".
  - Example shape: "Inline devil's advocate — argues against the current direction from the current agent's context (no fresh agent). Use when the user says 'challenge this', 'poke holes', 'devil's advocate', 'argue against this', 'what could go wrong', or 'stress-test this'. Works in any phase — no lifecycle required."
- **Verification**: Read frontmatter of `skills/devils-advocate/SKILL.md`. Confirm: (1) description mentions inline or same-context execution; (2) "pressure test" does not appear; (3) all six trigger phrases are present.
- **Status**: [x] complete

### Task 3:
 Update CR description frontmatter with execution model + trigger domain

- **Files**: `skills/critical-review/SKILL.md`
- **What**: Rewrite the `description:` frontmatter field to lead with the fresh-unanchored-agent execution model and use only the assigned CR trigger phrases. Remove "stress test" if present.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current description (first line): "Dispatches a fresh, unanchored agent to deeply challenge a plan, spec, or research artifact from multiple angles before you commit..."
  - The execution model (fresh unanchored agent) is already in the description — keep and strengthen this framing.
  - New trigger phrases to ensure are listed: "critical review", "pressure test", "adversarial review", "pre-commit challenge", "deeply question", "challenge from multiple angles".
  - Confirm "stress test" does not appear in the description (check: it likely doesn't, but verify before editing).
  - The lifecycle auto-trigger note ("Also auto-triggers in the lifecycle for Complex + medium/high/critical features after plan approval") must be retained — it is behavioral context.
  - The "More thorough than /devils-advocate" phrase should be updated to clarify WHY it is more thorough: fresh agent removes anchoring bias from the critique-generation step.
- **Verification**: Read frontmatter of `skills/critical-review/SKILL.md`. Confirm: (1) description leads with or prominently includes fresh/unanchored agent execution model; (2) anchoring bias rationale is present; (3) all six CR trigger phrases appear; (4) "stress test" does not appear; (5) lifecycle auto-trigger note is retained.
- **Status**: [x] complete

---

### Task 4: Fix clarify-critic.md — remove cross-reference sentence, add comment

- **Files**: `skills/lifecycle/references/clarify-critic.md`
- **What**: Remove the "Mirror the critical-review skill's framework exactly:" sentence from the Disposition Framework section. The Apply/Dismiss/Ask definitions that follow it are already correct inline — do not touch them. Add a brief comment noting the CR connection.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Target location: `## Disposition Framework` section, currently around line 60. The section reads:
    ```
    After the critic agent returns its list of objections, the orchestrator (not the critic) classifies each objection with one of three dispositions. Mirror the critical-review skill's framework exactly:
    ```
  - Replace the last sentence of that opening paragraph — "Mirror the critical-review skill's framework exactly:" — with a comment that reads: "(Apply/Dismiss/Ask framework below matches `/critical-review` Step 4 — reproduced here to avoid silent drift.)"
  - Result: The paragraph becomes: "After the critic agent returns its list of objections, the orchestrator (not the critic) classifies each objection with one of three dispositions. (Apply/Dismiss/Ask framework below matches `/critical-review` Step 4 — reproduced here to avoid silent drift.)"
  - The **Apply**, **Dismiss**, **Ask**, and **Apply bar** definition blocks that follow are unchanged.
- **Verification**: Read `skills/lifecycle/references/clarify-critic.md`. Confirm: (1) "Mirror the critical-review skill's framework exactly" no longer appears; (2) the comment referencing `/critical-review` Step 4 is present; (3) the Apply, Dismiss, Ask, and Apply bar definition blocks are unchanged word-for-word.
- **Status**: [x] complete

---

## Verification Strategy

After all tasks complete:
1. `wc -l skills/devils-advocate/SKILL.md` — sanity check: should be meaningfully shorter than 121 lines (range 70–90 expected; not a hard gate)
2. `grep -c "###" skills/devils-advocate/SKILL.md` — should return 4 (the four H3 element headers)
3. `grep "flowing narrative" skills/devils-advocate/SKILL.md` — should return nothing
4. `grep "pressure test" skills/devils-advocate/SKILL.md` — should return nothing
5. `grep "stress test" skills/critical-review/SKILL.md` — should return nothing
6. `grep "Mirror the critical-review" skills/lifecycle/references/clarify-critic.md` — should return nothing
7. Read both SKILL.md description fields and confirm execution model language is present in both
8. Run `/devils-advocate` on a test direction and confirm the response uses the four H3 headers
