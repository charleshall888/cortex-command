# Plan: non-prescriptive-tickets-and-refine

## Overview

Four independent text edits to skill markdown files. No structural changes to skill flows, no new tool calls, no frontmatter changes. Each task can be executed and verified in isolation; all four can run in parallel.

## Tasks

### Task 1: Strengthen anti-prescription guidance in backlog schema

- **Files**: `skills/backlog/references/schema.md`
- **What**: Replace the existing template comment with a two-part rule: (a) exploratory framing is always required by default; (b) prescription is acceptable only in two narrow exceptions — no viable alternatives exist, or the approach exactly follows an already-established codebase pattern. Explicitly name "investigated and found this to be correct" as insufficient for the exception bar.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The existing comment appears at the end of the `## Item Template` code block (`skills/backlog/references/schema.md` approx L60–63):
  > "When describing potential implementation approaches, frame them as **suggestions to explore**, not prescriptions. Use language like 'one approach might be...' or 'consider...' — the lifecycle's research and planning phases exist to evaluate approaches critically. Backlog items that prescribe exact solutions bypass the thinking that makes lifecycle valuable."
  Replace this paragraph with the expanded two-part rule. The new text should: (1) state the default framing requirement with examples; (2) name the two narrow exceptions; (3) explicitly state that "I researched it and believe this is correct" does not satisfy either exception — that confidence level is what the lifecycle research and plan phases exist to establish.
- **Verification**: Read `skills/backlog/references/schema.md`. Confirm: (a) exploratory framing examples are present ("one approach might be...", "consider...", "research could explore..."); (b) the two exception cases are named explicitly (no alternatives exist; follows established codebase pattern); (c) "investigated and confident" or equivalent is explicitly called out as not meeting the bar.

---

### Task 2: Prohibit prescriptive sections in discovery/decompose.md

- **Files**: `skills/discovery/references/decompose.md`
- **What**: Strengthen the "No implementation planning" constraint in the Constraints section to explicitly name prohibited section-header patterns and permitted alternatives.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current Constraints section (`skills/discovery/references/decompose.md` L96–100):
  ```
  ## Constraints

  - **No implementation planning**: Don't specify HOW to build each item — that's `/lifecycle`'s plan phase
  - **One epic max**: A single discovery produces at most one epic with children
  - **Respect backlog conventions**: Follow the backlog skill's frontmatter schema exactly
  ```
  Expand the "No implementation planning" bullet to name the prohibited section headers ("## Proposed Fix", "## Implementation Steps", "## How to Fix") and the permitted alternatives for summarizing research context in ticket bodies ("## Research Context", "## Findings", "## Context from discovery:"). The constraint should make clear that ticket bodies may reference findings from `discovery_source` (the context), not prescribe solutions.
- **Verification**: Read `skills/discovery/references/decompose.md`. Confirm the Constraints section names at least two prohibited section-header patterns and at least two permitted alternatives; the original "No implementation planning" framing is preserved and extended (not replaced).

---

### Task 3: Add alternative-exploration requirement to /refine Step 4

- **Files**: `skills/refine/SKILL.md`
- **What**: Update Step 4 (Research Phase) to: (a) explicitly state that the clarified intent — not the ticket body — is the scope anchor for research; and (b) add a conditional alternative-exploration requirement: when the backlog item contains implementation suggestions AND the feature is complex-tier or high/critical criticality, research must explicitly explore at least one alternative approach within the research (not a separate competing agent). For simple/low-medium features, alternative exploration is encouraged but not required.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Step 4 (`skills/refine/SKILL.md` L71–109) contains a "Research Execution" subsection that delegates to `/research` with the clarified intent (L84–90):
  ```
  /research topic="{clarified intent}" lifecycle-slug="{lifecycle-slug}" tier={tier} criticality={criticality}
  ```
  Add a paragraph within Research Execution (before or after this delegation block) that says: the clarified intent is the research scope anchor — not the ticket body. If the backlog item contains implementation suggestions (e.g., a "Proposed Fix" or "one approach might be..." section) AND the feature is complex-tier or high/critical, research must explicitly explore at least one alternative approach alongside the ticket's suggestion. For simple/low-medium features, this is encouraged but not required. If research ultimately validates the ticket's suggestion, that is a correct outcome — the requirement is to explore, not to reject.
- **Verification**: Read `skills/refine/SKILL.md` Step 4. Confirm: (a) clarified intent (not ticket body) is named as research anchor; (b) "at least one alternative" is named as a requirement for complex/high-critical features with ticket suggestions; (c) simple/low-medium features are noted as encouraged-but-not-required.

---

### Task 4: Update clarify.md to separate scope from implementation direction

- **Files**: `skills/lifecycle/references/clarify.md`
- **What**: Add two notes — one in §1 (Resolve Input) and one in §3 (Confidence Assessment) — clarifying that implementation suggestions in the ticket body are hypotheses for research, not scope constraints, and that a prescriptive body must not inflate the scope-boundedness rating.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Two insertion points in `skills/lifecycle/references/clarify.md`:
  - **§1 insertion** (after step 4, reading frontmatter and body, approx L18–19): Add a note: "If the body contains implementation suggestions (e.g., a proposed fix or a specific approach), treat them as unvalidated hypotheses for the research phase — not as constraints on scope. Scope is determined by the problem to solve, not the suggested solution."
  - **§3 insertion** (in or after the confidence table, approx L30–39): Add a note under the scope-boundedness dimension: "A prescriptive ticket body — one that suggests a specific fix or approach — does not make scope 'more bounded.' Scope boundedness is assessed against the problem statement and what is in/out; a detailed implementation suggestion in the body should not raise the scope-boundedness rating."
  Neither addition should introduce a new required step or change the confidence assessment flow. Both are informational notes.
- **Verification**: Read `skills/lifecycle/references/clarify.md`. Confirm: (a) §1 contains a note about implementation suggestions being hypotheses, not scope constraints; (b) §3 or the scope-boundedness dimension text contains a note that a prescriptive body does not elevate the scope-boundedness rating; (c) no new numbered step or required action was added.

---

## Verification Strategy

After all four tasks complete, verify end-to-end:

1. Read all four modified files and confirm each spec requirement's acceptance criteria is met (see spec.md Requirements section for the exact criteria).
2. Run `just validate-commit` to confirm no hook regressions.
3. Confirm no new frontmatter fields were added to `skills/backlog/references/schema.md`.
4. Confirm `skills/lifecycle/references/clarify.md` has no new numbered steps (only prose notes added).
