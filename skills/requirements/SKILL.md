---
name: requirements
description: Use /cortex-core:requirements to gather requirements or define project scope. Interviews, then writes cortex/requirements/{project|area}.md; disable-model-invocation:true — explicit slash command only.
disable-model-invocation: true
argument-hint: "[area|project|list]"
---

# Requirements

Interview, then synthesize. Nothing is written until the interview completes, so an abandoned interview leaves no partial doc behind.

## Scope

Parse `$ARGUMENTS`:

- **`list`** → run `cortex-list-requirements` and exit. `absent` → "No requirements documented yet. Run `/cortex-core:requirements` to start with project-level requirements." `ok` → render `rows` as a table (file, scope, last_gathered, requirement_count). Excludes `glossary.md`, a producer-managed vocabulary artifact rather than a scope-level doc.
- **empty or `project`** → scope `project`.
- **any other single token** → that token as a kebab-case area slug.

The target is `cortex/requirements/{scope}.md`. When it already exists, refine it rather than rewriting.

## 1. Interview

Run the interview loop from `/cortex-core:interview`: one question at a time, codebase-trumps-interview, recommend before asking. Every question carries a **Recommended answer:** grounded in explored code, the existing target doc, the parent requirements (area scope), or stated conventions — or `none — open question` with the gap explained.

Anchor each question block to one section, in template order. **Project**: Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading, Optional. **Area**: Overview, Functional Requirements, Non-Functional Requirements, Architectural Constraints, Dependencies, Edge Cases, Open Questions — reusing parent context from `cortex/requirements/project.md` rather than re-asking settled project-level positions.

Capture answers as:

```
### {Section name}
- **Q:** {question}
- **Recommended answer:** {grounded recommendation, or "none — open question" with rationale}
- **User answer:** {captured response or confirmation}
- **Code evidence:** {file paths or excerpts; omit for intent-only questions — never fabricate or write N/A}
```

A section with no live questions collapses to a single bullet noting the confirmed code-derived position.

### Glossary

The one write that happens during the interview is a per-term entry in `cortex/requirements/glossary.md`'s `## Language` section. Probe before classifying:

```bash
cortex-append-glossary-term --term "{term}"
```

`found` → use the returned definition verbatim, or surface the conflict via `AskUserQuestion` (keep / replace / flag as ambiguity); "replace" re-invokes with `--definition` and `--replace`. `not-found` → classify, then write with `--definition` only on a pass.

Project-specific terms whose meaning is shaped by this repo's conventions ("phase transition", "kept user pauses") earn an entry; general programming terms ("timeout", "race condition") do not — explain the rejection in the interview turn and write nothing. Only a user-named or user-confirmed term persists; a mention inside a **Recommended answer:** is not consent. Entries must be definitional, not classification-shaped (`phase_transition: the named event emitted when …`), since `/cortex-core:critical-review` feeds this section in as reasoning-free Project Context.

## 2. Synthesize

Preserve existing prose wherever the user's answer confirms it — refine in place, never rewrite from scratch. H2/H3 anchors stay verbatim across rewrites: downstream consumers grep section names. For a section the interview collapsed to a confirmed code-derived position, apply the template default. For a missing answer, keep the H2 with a one-line note pointing at Open Questions (area) or a `## Optional` bullet (project). Update `> Last gathered:` to today when any section changes.

**Project template** — `# Requirements: {project-name}` + `> Last gathered: {YYYY-MM-DD}`, then these eight H2s in order:

1. `## Overview` — 1–2 paragraph north star; distribution posture if load-bearing.
2. `## Philosophy of Work` — cross-cutting principles, bold-led bullets.
3. `## Architectural Constraints` — strategic constraints only; operational detail lives in CLAUDE.md.
4. `## Quality Attributes` — the non-functional bar.
5. `## Project Boundaries` — H3s `### In Scope`, `### Out of Scope`, `### Deferred`.
6. `## Conditional Loading` — `{trigger phrase} → cortex/requirements/{area}.md` lines; trigger phrases must intersect real lifecycle `index.md` `tags:` words.
7. `## Global Context` — bare paths under `cortex/requirements/` that every consumer loads on every invocation regardless of tag matches. No trigger phrases, no conditional prose. Absent paths are silently skipped, so listing one before its file exists is valid.
8. `## Optional` — prunable; first line states the prunability convention. Token budget ≤1,200 (`cl100k_base`); overflow goes here or into an area doc, never into new top-level H2s.

**Area template** — `# Requirements: {area-name}` + `> Last gathered:` + a backlink written verbatim as `**Parent doc**: [requirements/project.md](project.md)`, then seven H2s in order: `## Overview`, `## Functional Requirements` (one H3 per capability, with `**Description**`, `**Inputs**`, `**Outputs**`, nested `**Acceptance criteria**`, `**Priority**`), `## Non-Functional Requirements`, `## Architectural Constraints`, `## Dependencies`, `## Edge Cases` (`**Condition**: behavior`), `## Open Questions` (`- None` when nothing is open). No token budget; the parent backlink is the only navigation element.

## 3. Accept and commit

```bash
cortex-validate-requirements-doc --path {written-path} --scope {project|area}
```

`pass` → surface the path for approval. `fail` → `checks` names the failing check (missing canonical H2, over-budget `## Optional`); fix in place and re-run. `file-not-found`/`error` → the doc isn't where expected; resolve before returning.

On approval, stage `cortex/requirements/` and commit via `/cortex-core:commit`.

Requirements are passive artifacts — do not auto-dispatch any consumer; downstream skills load them on their own schedule. The glossary is the one producer-managed exception.
