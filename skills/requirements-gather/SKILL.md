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

Conduct a structured requirements interview surfacing intent, priorities, constraints, and boundaries, and return a Q&A markdown block — the raw interview record. This sub-skill never writes to disk or formats prose; synthesis and section selection are `/requirements-write`'s job.

## Decision criteria

### Interview stance

- **Codebase trumps interview**: per `skills/interview/references/loop.md`, check whether code, configs, README, CLAUDE.md, or the existing target doc already answers a question before asking it; if so, draft the answer with citations for the user to confirm. Reserve live questions for intent, priorities, scope boundaries, and non-functional bars source code cannot reveal.
- **Recommend before asking**: every question carries a **Recommended answer:** line grounded in explored code, the existing target doc, the parent requirements (area scope), or stated conventions; when no grounded recommendation is possible, mark it `none — open question` and explain the gap.
- **Ask one at a time**, per `skills/interview/references/loop.md`'s cadence rule.

### Glossary writes

Hold the Q&A block in conversation context until the orchestrator's handoff — synthesis belongs to `/requirements-write`, so an abandoned interview leaves no partial project/area doc behind. The one write this sub-skill owns is a per-term append to `cortex/requirements/glossary.md` (created lazily on first resolved term, persisted immediately, so entries survive an abandoned interview). Before writing, probe for an existing entry: if found, use it verbatim or surface the conflict via `AskUserQuestion` ("the glossary defines X as Y; this interview suggests Z — keep / replace / surface as Flagged Ambiguity?"); if absent, classify and gate below.

### Classify, gate, and format

The binary classifier: project-specific terms — meaning shaped by this repo's conventions, e.g. "phase transition," "kept user pauses" — earn a glossary entry; general programming terms — "timeout," "race condition" — do not. When rejected, explain why in the interview turn and write nothing. Even on a project-specific verdict, only a user-named or user-confirmed term persists — a `Recommended answer:` mention alone is not consent. `## Language` entries must be definitional, not classification-shaped (`phase_transition: the named event emitted when ...`, not `phase_transition — genuinely-domain term; contract-shaped in lifecycle.md`), since the section feeds `critical-review`'s reasoning-free Project Context.

## Scope shaping

- **Project scope**: seven sections — Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries (In/Out/Deferred), Conditional Loading (trigger phrase → area doc), and the prunable Optional. Anchor each question block to one.
- **Area scope**: seven sections — Overview, Functional Requirements, Non-Functional Requirements, Architectural Constraints, Dependencies, Edge Cases, Open Questions. Reuse parent project context loaded from `cortex/requirements/project.md`; don't re-ask settled project-level positions.

Full section ordering and formatting live in `/requirements-write`'s templates; this skill only needs to label each Q&A under the section it feeds.

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

One H3 per template section; a section with no live questions collapses to a single bullet noting the confirmed code-derived position. The orchestrator passes this block verbatim to `/requirements-write`.

Omit **Code evidence** for intent-only questions with no codebase grounding — do not fabricate a citation or write `N/A`.

## Handoff contract

When the interview is complete, announce completion and return the Q&A block to the caller — do NOT invoke `/requirements-write` directly; the orchestrator owns sequencing. If the user requests changes after handoff, it re-enters this sub-skill with the prior Q&A block as context.
