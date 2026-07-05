---
name: requirements-gather
description: Interview-only sub-skill that produces a structured Q&A markdown block for /requirements-write to synthesize. Adopts mattpocock interview patterns. Invoked by the /cortex-core:requirements orchestrator.
when_to_use: "Use only as a sub-skill of /cortex-core:requirements. Gather conducts the interview; the orchestrator hands its Q&A block to /requirements-write."
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

Surfacing the intent, priorities, constraints, and boundaries a downstream artifact will codify. The output is the raw interview record; `/requirements-write` selects sections and formats prose.

## Decision criteria

### Codebase trumps interview

Per the codebase-trumps-interview rule in `skills/interview/references/loop.md`: before drafting a question, check whether the answer is recoverable from code, configs, README, CLAUDE.md, or the existing target doc. If so, draft the answer with citations and ask the user to confirm rather than asking cold. Reserve live questions for intent, priorities, scope boundaries, and non-functional bars source code cannot reveal.

### Recommend before asking

Every question carries a **Recommended answer:** line — the position the model would adopt on "go with your best guess." Ground it in explored code, the existing target doc, the parent requirements (area scope), or stated conventions. When no grounded recommendation is possible, mark it `none — open question` and explain the gap.

### Ask one at a time

Conduct the interview one question at a time, per the canonical cadence rule in `skills/interview/references/loop.md`.

### Lazy artifact creation

Hold the Q&A block in conversation context until the orchestrator's handoff — synthesis of project.md and area docs belongs to `/requirements-write`, so abandoning the interview leaves no partial doc behind. The only write this sub-skill owns is a per-term append to `cortex/requirements/glossary.md` (created lazily on the first resolved term).

Glossary appends persist immediately, so entries written before an abandoned interview remain in the file — an abandoned interview still leaves the glossary coherent.

### Inline glossary write with term-already-exists probe

When a term resolves during the interview, probe before writing: read `cortex/requirements/glossary.md` if it exists, and check whether the term is already present. If it is, use the existing entry verbatim, or surface the conflict via `AskUserQuestion` ("the glossary defines X as Y; this interview suggests Z — keep / replace / surface as Flagged Ambiguity?") before any reclassification. If the term is absent, apply the classifier described below; on a project-specific verdict, append the entry to `glossary.md` (creating the file lazily if it does not yet exist).

### Project-specific vs general programming

The binary classifier decides whether a resolved term earns a glossary entry. Pocock's rule: project-specific terms get written, general programming terms do not. "Phase transition," "kept user pauses," "sentinel-as-used-here" are project-specific — their meaning is shaped by this repo's conventions and would not be obvious to a reader who knew Python and Claude Code generally. "Timeout," "callback," "race condition" are general programming — defining them in the glossary adds noise rather than disambiguation. When the classifier rejects a term, explain the rejection in the interview turn and proceed; nothing is written.

### User-confirmation gate

A user-confirmation gate sits in front of every inline write: only user-named or user-confirmed terms persist. A term that surfaced only in a `Recommended answer:` line and was never user-named or user-confirmed does NOT trigger an inline write — the recommendation alone is not consent to persist. If the user later names or confirms the term explicitly, the write fires then. This keeps the glossary anchored to the user's vocabulary rather than the model's paraphrases.

### Language-content constraint

Entries written into the glossary's `## Language` section must be definitional, not classification-shaped — the section feeds `critical-review`'s Project Context, which must stay reasoning-free. Anchor pair: `phase_transition: the named event emitted when ...` is admitted (defines the term); `phase_transition — genuinely-domain term; contract-shaped in lifecycle.md` is rejected (classifies rather than defines). Write the first shape; never the second.

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

Omit **Code evidence** for intent-only questions with no codebase grounding — do not fabricate a citation or write `N/A`.

## Handoff contract

When the interview is complete, announce completion and return the Q&A block to the caller. Do NOT invoke `/requirements-write` directly — the `/cortex-core:requirements` orchestrator owns sequencing. If the user requests changes after handoff, the orchestrator re-enters this sub-skill with the prior Q&A block as starting context.

## Constraints

| Thought | Reality |
|---------|---------|
| "I should write the requirements file once the interview is done" | Writing is `/requirements-write`'s job. This sub-skill stops at the Q&A block. |
| "I'll just ask the user — it's faster than reading code" | Codebase-trumps-interview applies: explore code instead when the answer is recoverable from source, then confirm. |
| "I'll skip the Recommended answer when I'm unsure" | Mark it `none — open question` with a one-line rationale. Never omit the field. |
| "Empty sections should be dropped from the output" | Keep the H3 header and note the confirmed code-derived position so synthesis has full template coverage. |
