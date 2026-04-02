# Review: non-prescriptive-tickets-and-refine

## Stage 1: Spec Compliance

### Requirement 1: `skills/backlog/references/schema.md` -- Strengthen anti-prescription guidance (Must-have)
- **Expected**: Template comment updated with a two-part rule: (a) exploratory framing required by default with example phrases; (b) prescription acceptable only in two narrow cases (no alternatives exist; follows established codebase pattern); "investigated and confident" explicitly excluded as sufficient bar. No frontmatter fields added or changed.
- **Actual**: The existing single-paragraph comment was replaced with a bolded default rule ("Implementation approaches must use exploratory framing by default.") with three example phrases ("one approach might be...", "consider...", "research could explore..."), followed by a numbered list of two narrow exceptions with clear descriptions, and a closing paragraph explicitly naming "I investigated this and believe it is correct" as insufficient. No frontmatter fields were added or changed.
- **Verdict**: PASS
- **Notes**: All three acceptance criteria met. The text is inside the template code block, so it serves as inline guidance when tickets are created from the template.

### Requirement 2: `skills/discovery/references/decompose.md` -- Prohibit "Proposed Fix" sections (Must-have)
- **Expected**: Constraints section names prohibited section-header patterns ("Proposed Fix", "Implementation Steps") and permitted alternatives ("Research Context:", "Findings:", "Context from discovery:"); distinction grounded in what decompose produces (discovery findings, not prescriptions).
- **Actual**: The "No implementation planning" constraint was extended in-place to name three prohibited headers ("## Proposed Fix", "## Implementation Steps", "## How to Fix") and three permitted alternatives ("## Research Context", "## Findings", "## Context from discovery:"). The closing sentence grounds the distinction: "Tickets may reference findings from `discovery_source` to give implementers background, but should never prescribe solutions."
- **Verdict**: PASS
- **Notes**: The original framing ("Don't specify HOW to build each item -- that's `/lifecycle`'s plan phase") is preserved and extended, not replaced. Acceptance criteria fully met.

### Requirement 3: `skills/refine/SKILL.md` -- Explicit alternative-exploration requirement (Must-have)
- **Expected**: Step 4 updated to: (a) name clarified intent (not ticket body) as research anchor; (b) require "at least one alternative" for complex/high-critical features with ticket suggestions; (c) note that alternative exploration is encouraged-but-not-required for simple/low-medium features.
- **Actual**: Two new paragraphs added to Step 4's "Research Execution" subsection. The first ("Research scope anchor") explicitly states the clarified intent from Step 3 is the scope anchor, not the original ticket body. The second ("Alternative exploration") requires at least one alternative approach when the backlog item has implementation suggestions AND the feature is complex-tier or high/critical criticality, notes this happens within the `/research` call (not a separate agent), states it is encouraged but not required for simple-tier or low/medium-criticality features, and clarifies that validating the ticket's suggestion is a correct outcome.
- **Verdict**: PASS
- **Notes**: All three sub-criteria (a), (b), (c) are explicitly addressed. The text also correctly handles the edge case from the spec (research validates the suggestion = correct outcome).

### Requirement 4: `skills/lifecycle/references/clarify.md` -- Separate scope from implementation direction (Must-have)
- **Expected**: Section 1 (Resolve Input) updated with a note that implementation suggestions are hypotheses for research, not scope constraints. Section 3 (Confidence Assessment) updated so a prescriptive ticket body does not inflate scope-boundedness rating. No new required step or change to the confidence assessment flow.
- **Actual**: A blockquote note was added after step 4 in section 1: "If the body contains implementation suggestions (e.g., a proposed fix or a specific approach), treat them as unvalidated hypotheses for the research phase -- not as constraints on scope. Scope is determined by the problem to solve, not the suggested solution." A second blockquote note was added after the confidence assessment table in section 3: "A prescriptive ticket body -- one that suggests a specific fix or approach -- does not make scope 'more bounded.' Scope boundedness is assessed against the problem statement and what is in/out; a detailed implementation suggestion in the body should not raise the scope-boundedness rating." Both are informational notes (blockquotes), not new numbered steps or required actions.
- **Verdict**: PASS
- **Notes**: The spec allowed either a section 1 note that references section 3 explicitly, or additions in both sections. The implementation chose additions in both sections, which satisfies the criteria. The section 3 note does not explicitly reference section 1, but neither does the section 1 note reference section 3 -- this is fine since the spec stated "either" approach was acceptable.

## Requirements Compliance

- **No new YAML frontmatter fields**: Confirmed. The schema.md changes are entirely within the template comment block; no new fields were added to the frontmatter table or template.
- **No retroactive ticket rewrites**: Confirmed. No existing backlog items were modified.
- **No enforcement/linting added**: Confirmed. All changes are guidance text only -- no scripts, hooks, or validation logic.
- **Tickets can still include implementation context**: Confirmed. The guidance distinguishes prescription framing from mentioning implementation approaches. The schema template says "Frame approaches as suggestions, not instructions" -- context is allowed, prescription is not.
- **No change to /refine for tickets without suggestions**: Confirmed. The alternative-exploration paragraph in SKILL.md is explicitly conditional on "when a backlog item contains implementation suggestions."
- **No changes to /lifecycle plan or implement phases**: Confirmed. Only clarify.md (used by both /refine and /lifecycle) and refine's SKILL.md were touched. No plan or implement phase files were modified.
- **Complexity earned its place (project requirement)**: All four changes are text additions to existing guidance files. No new files, no new workflow steps, no new tool calls. The complexity added is minimal and directly justified by the problem statement.
- **Failure handling -- no silent skips**: Not applicable (these are guidance-only changes, not executable behavior). No existing failure handling was altered.
- **Artifacts are self-contained**: Each modified file is self-contained guidance. The clarify.md additions work for both /refine and /lifecycle callers without requiring cross-references.

## Stage 2: Code Quality

- **Naming conventions**: Consistent. The new paragraphs in SKILL.md use bolded labels ("Research scope anchor", "Alternative exploration") matching the existing pattern in that file (e.g., "Bypass case" on line 80). The clarify.md additions use blockquote notes (`> **Note:**`), which is consistent with how clarify.md structures advisory text.
- **Error handling**: Not applicable -- these are all markdown guidance additions with no executable behavior. No existing error handling was modified or bypassed.
- **Test coverage**: The plan's verification strategy called for: (1) reading all four files and confirming acceptance criteria, (2) running `just validate-commit`, (3) confirming no new frontmatter fields, (4) confirming no new numbered steps in clarify.md. Items 1, 3, and 4 are confirmed by this review. Item 2 (validate-commit) is a commit-time check that would have run at commit time.
- **Pattern consistency**: All four changes follow the existing conventions of their respective files. Schema.md extends the template comment block. Decompose.md extends an existing constraint bullet. SKILL.md adds labeled paragraphs in the Research Execution subsection. Clarify.md uses blockquote notes positioned after the relevant content. No new patterns were introduced.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": []}
```
