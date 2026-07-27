---
name: requirements-gather
description: Interview-only sub-skill that produces a structured Q&A markdown block for /requirements-write to synthesize. Invoked by the /cortex-core:requirements orchestrator.
when_to_use: "Use only as a sub-skill of /cortex-core:requirements. Gather conducts the interview; the orchestrator hands its Q&A block to /requirements-write."
argument-hint: "<scope>"
---

# /requirements-gather

Interview for intent, priorities, constraints, and boundaries; return a Q&A markdown block. Never write the project or area doc — synthesis is `/requirements-write`'s job, so an abandoned interview leaves no partial doc behind.

## Stance

Run the interview loop from `/cortex-core:interview`: one question at a time, codebase-trumps-interview, recommend before asking. Every question carries a **Recommended answer:** grounded in explored code, the existing target doc, the parent requirements (area scope), or stated conventions — or `none — open question` with the gap explained.

## Glossary

The one write this sub-skill owns is a per-term entry in `cortex/requirements/glossary.md`'s `## Language` section. Probe before classifying:

```bash
cortex-append-glossary-term --term "{term}"
```

`found` → use the returned definition verbatim, or surface the conflict via `AskUserQuestion` (keep / replace / flag as ambiguity); "replace" re-invokes with `--definition` and `--replace`. `not-found` → classify, then write with `--definition` only on a pass.

Project-specific terms whose meaning is shaped by this repo's conventions ("phase transition", "kept user pauses") earn an entry; general programming terms ("timeout", "race condition") do not — explain the rejection in the interview turn and write nothing. Only a user-named or user-confirmed term persists; a mention inside a **Recommended answer:** is not consent. Entries must be definitional, not classification-shaped (`phase_transition: the named event emitted when …`), since `/cortex-core:critical-review` feeds this section in as reasoning-free Project Context.

## Scope

**Project**: Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading, Optional. **Area**: Overview, Functional Requirements, Non-Functional Requirements, Architectural Constraints, Dependencies, Edge Cases, Open Questions — reusing parent context from `cortex/requirements/project.md` rather than re-asking settled project-level positions.

Anchor each question block to one section; ordering and formatting belong to `/requirements-write`.

## Output

```
## Q&A: {scope}

### {Section name}
- **Q:** {question}
- **Recommended answer:** {grounded recommendation, or "none — open question" with rationale}
- **User answer:** {captured response or confirmation}
- **Code evidence:** {file paths or excerpts; omit for intent-only questions — never fabricate or write N/A}
```

One H3 per template section; a section with no live questions collapses to a single bullet noting the confirmed code-derived position.

Announce completion and return the block to the caller — do NOT invoke `/requirements-write` yourself; the orchestrator owns sequencing. Post-handoff change requests re-enter here with the prior block as context.
