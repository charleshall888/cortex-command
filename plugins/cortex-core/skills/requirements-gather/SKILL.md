---
name: requirements-gather
description: Interview-only sub-skill that produces a structured Q&A markdown block for /requirements-write to synthesize. Invoked by the /cortex-core:requirements orchestrator. Adopts mattpocock interview patterns (recommend-before-asking, codebase trumps interview, lazy artifact creation).
when_to_use: "Use only as a sub-skill of /cortex-core:requirements. Different from /cortex-core:requirements — gather only conducts the interview; the orchestrator hands the resulting Q&A block to /requirements-write for synthesis."
argument-hint: "<scope>"
inputs:
  - "scope: string (required) — 'project' for project-level, or area kebab-case slug for area-level"
  - "existing-doc: string (optional) — path to an existing cortex/requirements/{scope}.md the interview should refine rather than write fresh"
outputs:
  - "Structured Q&A markdown block returned to the orchestrator (held in conversation context; no file written by this sub-skill)"
---

# /requirements-gather

Conduct a structured requirements interview and return a Q&A markdown block. This sub-skill never writes to disk — synthesis is `/requirements-write`'s job.

## What this skill is for

Surfacing the intent, priorities, constraints, and boundaries that a downstream artifact will codify. The output is the raw interview record. Section selection and prose formatting belong to `/requirements-write`.

## Decision criteria

### Codebase trumps interview

Before drafting a question, decide whether the answer is recoverable from code, configs, README, CLAUDE.md, or the existing target doc. If yes, explore code instead of asking — read the relevant files, draft the answer with citations, and ask the user to confirm or correct. Reserve interview questions for intent, priorities, scope boundaries, and non-functional bars that source code cannot reveal. The bias is: code-derived answer with confirmation prompt beats an open question every time.

### Recommend before asking

Every question carries a **Recommended answer:** line stating the position the model would adopt if the user said "go with your best guess." The user adjusts the recommendation rather than answering from scratch. Recommendations are grounded — derived from explored code, the existing target doc, the parent requirements (for area scope), or stated project conventions. When no grounded recommendation is possible, mark the recommendation as `none — open question` and explain why so the user understands the gap.

### Ask one at a time

Ask interview questions one at a time, waiting for the user's response before posing the next. The previous answer is the gate to the next question, so each question can be shaped by what just landed. Avoid batching multiple questions into a single turn — batched questions invite partial answers, hide decision-tree branches that should resolve sequentially, and create respondent fatigue. Mirrored in `skills/lifecycle/references/specify.md` §2 — when editing this rule, update the other surface too.

### Lazy artifact creation

Hold the Q&A block in conversation context until the orchestrator's handoff. Only write when synthesis has something concrete to produce — that decision belongs to `/requirements-write`. This sub-skill never touches the filesystem under `cortex/requirements/`. If the user abandons mid-interview, no partial file is left behind.

## Scope shaping

- **Project scope**: cover the parent template's seven required sections — Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries (In/Out/Deferred), Conditional Loading (trigger phrase → area doc map), and the prunable Optional section. Anchor each block of questions to one of these sections so the synthesis step has a clean mapping.
- **Area scope**: cover the area template's seven required sections — Overview, Functional Requirements, Non-Functional Requirements, Architectural Constraints, Dependencies, Edge Cases, Open Questions. Reuse parent project context loaded from `cortex/requirements/project.md`; do not re-ask settled project-level positions.

The full section list and ordering live in the artifact-format documentation that `/requirements-write` consumes. This skill needs only to label each Q&A under the section it feeds.

## Output shape

Return one markdown block of the form:

```
## Q&A: {scope}

### {Section name from template}
- **Q:** {question}
- **Recommended answer:** {grounded recommendation, or "none — open question" with rationale}
- **User answer:** {captured response or confirmation}
- **Code evidence:** {file paths or excerpts, when codebase-trumps-interview applied; omit otherwise}

### {Next section name}
- **Q:** ...
```

One H3 per template section. Sections with no live questions (because code already answered everything and the user confirmed) collapse to a single bullet noting the confirmed code-derived position. The orchestrator passes this block verbatim to `/requirements-write`.

When the **Recommended answer** is derived from code, the **Code evidence** field names the file path that grounds it (so the user can flag a wrong-place-to-implement before any code is written). For intent-only questions with no codebase grounding, omit the field per the existing semantics — do not fabricate a citation or write `N/A`.

## Handoff contract

When the interview is complete, announce completion and return the Q&A block to the caller. Do NOT invoke `/requirements-write` directly — the `/cortex-core:requirements` orchestrator owns sequencing. If the user requests changes after handoff, the orchestrator re-enters this sub-skill with the prior Q&A block as starting context.

## Constraints

| Thought | Reality |
|---------|---------|
| "I should write the requirements file once the interview is done" | Writing is `/requirements-write`'s job. This sub-skill stops at the Q&A block. |
| "I'll just ask the user — it's faster than reading code" | Codebase-trumps-interview applies: explore code instead when the answer is recoverable from source, then confirm. |
| "I'll skip the Recommended answer when I'm unsure" | Mark it `none — open question` with a one-line rationale. Never omit the field. |
| "Empty sections should be dropped from the output" | Keep the H3 header and note the confirmed code-derived position so synthesis has full template coverage. |
