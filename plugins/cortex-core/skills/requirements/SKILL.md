---
name: requirements
description: Use /cortex-core:requirements to gather requirements or define project scope. Interviews, then writes cortex/requirements/{project|area}.md — explicit slash command only.
disable-model-invocation: true
argument-hint: "[area|project|list]"
---

# Requirements

Interview, then synthesize. Nothing is written until the interview completes.

## Scope

`$ARGUMENTS`: **`list`** → `cortex-list-requirements` and exit (`absent` → "No requirements documented yet. Run `/cortex-core:requirements` to start with project-level requirements."; `ok` → render `rows` as a table: file, scope, last_gathered, requirement_count; excludes `glossary.md`). **empty or `project`** → scope `project`. **any other token** → that kebab-case area slug. Target `cortex/requirements/{scope}.md`; when it exists, refine rather than rewrite.

## 1. Interview

Run `/cortex-core:interview`'s loop: batch only independent questions, codebase trumps interview, recommend before asking. Every question carries a **Recommended answer:** grounded in explored code, the existing doc, the parent requirements (area scope), or stated conventions — or `none — open question` with the gap explained.

Anchor each block to one section in template order. **Project**: Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading, Optional. **Area**: Overview, Functional Requirements, Non-Functional Requirements, Architectural Constraints, Dependencies, Edge Cases, Open Questions — reusing `cortex/requirements/project.md` rather than re-asking settled positions.

```
### {Section name}
- **Q:** {question}
- **Recommended answer:** {grounded recommendation, or "none — open question" with rationale}
- **User answer:** {captured response or confirmation}
- **Code evidence:** {file paths or excerpts; omit for intent-only questions — never fabricate or write N/A}
```

A section with no live questions collapses to one bullet noting the confirmed code-derived position.

### Glossary

The one write during the interview: a per-term entry in `cortex/requirements/glossary.md`'s `## Language`. Probe first:

```bash
cortex-append-glossary-term --term "{term}"
```

`found` → use the definition verbatim, or offer keep / replace / flag as ambiguity ("replace" re-invokes with `--definition` and `--replace`). `not-found` → classify, then write with `--definition` only on a pass: project-shaped terms ("phase transition", "kept user pauses") earn an entry; general programming terms ("timeout") do not — explain the rejection, write nothing. Only a user-named or user-confirmed term persists; a mention inside a Recommended answer is not consent. Entries are definitional, not classification-shaped — `/cortex-core:critical-review` feeds this section in as reasoning-free context.

## 2. Synthesize

Preserve existing prose the user confirms — refine in place. H2/H3 anchors stay verbatim (downstream consumers grep them). A collapsed section takes the template default; a missing answer keeps the H2 with a one-line pointer to Open Questions (area) or a `## Optional` bullet (project). Bump `> Last gathered:` when any section changes.

**Project** — `# Requirements: {project-name}` + `> Last gathered: {YYYY-MM-DD}`, then eight H2s in order: `## Overview` (1–2 paragraph north star; distribution posture if load-bearing) · `## Philosophy of Work` (cross-cutting principles, bold-led bullets) · `## Architectural Constraints` (strategic only; operational detail lives in CLAUDE.md) · `## Quality Attributes` · `## Project Boundaries` (`### In Scope`, `### Out of Scope`, `### Deferred`) · `## Conditional Loading` (many-to-one area→doc map, `{area key}/{synonym key} → cortex/requirements/{area}.md` per line; keys match a lifecycle `index.md`'s `areas:` by exact lookup, so every key is a real area name and a doc gains reach by listing more synonyms) · `## Global Context` (bare paths under `cortex/requirements/` every consumer loads on every invocation; absent paths are skipped, so listing one early is valid) · `## Optional` (prunable; first line states the convention; token budget ≤1,200 `cl100k_base` — overflow goes here or into an area doc, never new H2s).

**Area** — `# Requirements: {area-name}` + `> Last gathered:` + `**Parent doc**: [requirements/project.md](project.md)` verbatim, then seven H2s: `## Overview`, `## Functional Requirements` (one H3 per capability with `**Description**`, `**Inputs**`, `**Outputs**`, nested `**Acceptance criteria**`, `**Priority**`), `## Non-Functional Requirements`, `## Architectural Constraints`, `## Dependencies`, `## Edge Cases` (`**Condition**: behavior`), `## Open Questions` (`- None` when empty). No token budget.

## 3. Accept and commit

```bash
cortex-validate-requirements-doc --path {written-path} --scope {project|area}
```

`pass` → surface the path for approval. `fail` → `checks` names the failing check; fix and re-run. `file-not-found`/`error` → resolve before returning. On approval, stage `cortex/requirements/` and commit. Requirements are passive — dispatch no consumer; downstream skills load them on their own schedule.
