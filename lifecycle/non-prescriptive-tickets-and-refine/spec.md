# Specification: non-prescriptive-tickets-and-refine

## Problem Statement

Backlog tickets are routinely authored with prescriptive implementation details — exact bash commands, specific function names, a single "Proposed Fix" framing — that bypass the research and planning discipline the lifecycle exists to enforce. Tickets 001 and 002 illustrate the pattern: both include exact implementation steps despite anti-prescription guidance already existing in `skills/backlog/references/schema.md`. That guidance was present but not specific enough to distinguish acceptable evidence-based context from problematic prescription. When `/refine` processes prescriptive tickets, it anchors its research on the suggested approach without exploring alternatives, creating a risk of executing a minimally-validated path simply because it appeared in the ticket. Two places need fixing: (1) ticket authoring guidance must be strengthened across all creation paths so new tickets express findings and context without prescribing exact solutions; and (2) `/refine` and the clarify phase must explicitly treat ticket implementation suggestions as unvalidated hypotheses, not scope anchors.

## Requirements

All four requirements are must-have. The user explicitly selected all four target files as in scope; none can be deferred without leaving a creation or execution path uncovered.

1. **`skills/backlog/references/schema.md` — Strengthen anti-prescription guidance (Must-have)**: The existing template comment is updated with a narrowed two-part rule: (a) always use exploratory framing ("one approach might be...", "consider...", "research could explore..."); (b) prescription of a specific implementation is only acceptable in two narrow cases: the approach is the only feasible one (no viable alternatives exist), OR it exactly follows an already-established pattern in the codebase. "I researched it and believe this is correct" does not pass the bar — that level of confidence is what the lifecycle research and plan phases exist to establish.
   - Acceptance criteria: Template comment names the two specific exception cases (no alternatives exist; follows established codebase pattern) and explicitly excludes "investigated and confident" as a sufficient bar; no frontmatter fields added or changed.

2. **`skills/discovery/references/decompose.md` — Prohibit "Proposed Fix" sections (Must-have)**: The existing Constraint "No implementation planning" is strengthened to explicitly name what is prohibited ("Proposed Fix", "Implementation Steps" sections) and what is permitted in ticket bodies ("Research Context:", "Findings:", "Context from discovery:" — summarizing what discovery research revealed about the problem space).
   - Acceptance criteria: Constraints section names the prohibited section-header patterns and the permitted alternatives; the distinction is grounded in what decompose.md's creation path produces (discovery findings, not prescriptions).

3. **`skills/refine/SKILL.md` — Explicit alternative-exploration requirement (Must-have)**: Step 4 (Research Phase) is updated to state that the clarified intent — not the ticket suggestion — is the scope anchor for research. When the backlog item contains implementation suggestions AND the feature is complex-tier or high/critical criticality, research must explicitly explore at least one alternative approach (within the research, not a separate competing research agent). For simple-tier, low/medium features with ticket suggestions, alternative exploration is encouraged but not required.
   - Acceptance criteria: Step 4 contains an explicit instruction that (a) names clarified intent (not the ticket body) as the research anchor; (b) requires "at least one alternative" for complex/high-critical features with ticket suggestions; (c) notes this is encouraged-but-not-required for simple/low-medium features.

4. **`skills/lifecycle/references/clarify.md` — Separate scope from implementation direction (Must-have)**: §1 (Resolve Input) is updated with a note that when reading the backlog item body, implementation suggestions are hypotheses for research to evaluate — not scope constraints. Scope is determined by the problem statement, not the proposed solution. This note must carry through to §3 (Confidence Assessment): a prescriptive ticket body should not inflate the scope-boundedness rating. Scope boundedness is assessed against the problem statement alone; a detailed proposed fix does not make scope "more bounded."
   - Acceptance criteria: The guidance explicitly addresses both §1 (reading the body) and §3 (scope-boundedness dimension) — either as a §1 note that references §3 explicitly, or as additions in both sections; it does not add a new required step or change the confidence assessment flow otherwise.

## Non-Requirements

- Does not add any new YAML frontmatter fields to the backlog schema
- Does not retroactively rewrite existing tickets (001, 002, or any already-created items)
- Does not add enforcement or linting for ticket content (guidance only)
- Does not prevent tickets from including implementation context — the constraint is on prescription framing, not on mentioning implementation approaches
- Does not change `/refine` behavior for tickets that contain no implementation suggestions
- Does not modify the `/lifecycle` plan or implement phases

## Edge Cases

- **Ticket with "no alternatives exist"**: A ticket says "setsid is the POSIX-specified way to create a new process group; there is no alternative mechanism on Linux"; this satisfies exception (a) — citing that no alternatives exist is different from citing that one alternative is preferred
- **Ticket following established pattern**: A ticket says "this follows the same pattern as skill X which already does Y (see `skills/X/SKILL.md:L12`)"; this satisfies exception (b) — references an explicit existing pattern
- **Ticket with strong evidence but alternatives unstated**: A ticket says "I traced the issue to batch_runner.py:L45 and setsid fixes it"; this does NOT satisfy the exception — strong evidence for an approach is not the same as no alternatives or established pattern
- **Discovery ticket with only a problem statement**: No change to behavior — decompose adds a "Research Context" section summarizing findings from `discovery_source`; no "Proposed Fix" section is created
- **Research validates the ticket suggestion**: `/refine` explores alternatives and finds the ticket's suggestion is the best approach anyway — correct outcome; the requirement is to explore alternatives, not to reject the suggestion
- **Clarify reads a ticket body with no implementation suggestions**: The new §1 note is a no-op — scope assessment proceeds normally

## Technical Constraints

- All changes are text-only edits to four markdown files: `skills/refine/SKILL.md`, `skills/backlog/references/schema.md`, `skills/discovery/references/decompose.md`, `skills/lifecycle/references/clarify.md`
- Changes are guidance additions only — no new required workflow steps, no new tool calls, no structural changes to skill flows
- `clarify.md` is used by both `/refine` and `/lifecycle` directly; the additions must be non-disruptive for features with clean (non-prescriptive) tickets

## Open Decisions

None.
